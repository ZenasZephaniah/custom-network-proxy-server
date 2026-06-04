import socket
import json
import os
import signal
import sys
import select
from concurrent.futures import ThreadPoolExecutor
from logger import setup_logger
from parser import HTTPParser
from filter import URLFilter
from cache import LRUCache

class ProxyServer:
    def __init__(self, config_path: str):
        """
        Initializes the custom network proxy server, loading configurations,
        the thread-safe logger, the policy blocklist, and the LRU cache.
        """
        self.config_path = config_path
        self.config = self.load_config()
        
        # Initialize Logger
        self.logger = setup_logger(self.config.get("log_file", "logs/proxy.log"))
        
        # Initialize Domain/IP Filter
        self.filter = URLFilter(self.config.get("blocked_domains_file", "config/blocked_domains.txt"))
        
        # Initialize LRU Cache with configurable capacity
        self.cache = LRUCache(capacity=self.config.get("cache_capacity", 5))
        
        # Thread Pool Executor for concurrent client handling
        self.executor = ThreadPoolExecutor(
            max_workers=self.config.get("thread_pool_size", 16),
            thread_name_prefix="ProxyWorker"
        )
        
        # Server Socket variables
        self.server_socket = None
        self.is_running = False

    def load_config(self) -> dict:
        """Loads configuration from JSON file; falls back to default values on error."""
        default_config = {
            "host": "127.0.0.1",
            "port": 8888,
            "thread_pool_size": 16,
            "log_file": "logs/proxy.log",
            "blocked_domains_file": "config/blocked_domains.txt",
            "timeout": 15,
            "cache_capacity": 5
        }
        if not os.path.exists(self.config_path):
            print(f"Config file not found at {self.config_path}. Using default configuration.")
            return default_config
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}. Using defaults.")
            return default_config

    def start(self):
        """Initializes the server socket, binds to host:port, and enters the accept loop."""
        host = self.config.get("host", "127.0.0.1")
        port = self.config.get("port", 8888)

        # Register OS signals for graceful termination
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        try:
            # Create a TCP Socket (AF_INET = IPv4, SOCK_STREAM = TCP)
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Set SO_REUSEADDR to allow instant port re-binding upon restart
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind and start listening
            self.server_socket.bind((host, port))
            self.server_socket.listen(128)
            
            self.is_running = True
            self.logger.info(f"Proxy server successfully started on {host}:{port}")

            # Connection accept loop
            while self.is_running:
                try:
                    # Accept blocks until a new client establishes a TCP handshake
                    client_socket, client_address = self.server_socket.accept()
                    
                    # Offload the socket processing to the Thread Pool to keep accept loop free
                    self.executor.submit(self.handle_client, client_socket, client_address)
                except socket.timeout:
                    continue
                except OSError:
                    # Triggered when socket is closed during shutdown
                    break

        except Exception as e:
            self.logger.critical(f"Server initialization failed: {e}")
            self.shutdown()

    def handle_client(self, client_socket: socket.socket, client_address: tuple):
        """
        Worker thread routine. Reads raw headers from the client, parses the HTTP attributes,
        validates blocklists, evaluates LRU cache state, and tunnels/forwards connection.
        """
        timeout = self.config.get("timeout", 15)
        client_socket.settimeout(timeout)
        
        self.logger.info(f"Handling connection from {client_address[0]}:{client_address[1]}")
        target_socket = None

        try:
            # 1. Read and parse incoming HTTP/CONNECT request headers
            raw_headers = HTTPParser.read_headers(client_socket)
            if not raw_headers:
                return
            
            request = HTTPParser.parse(raw_headers, client_socket)
            
            self.logger.info(
                f"Parsed Request -> {request.method} {request.host}:{request.port}{request.path}"
            )
            
            if not request.host:
                raise ValueError("No destination host provided in request.")

            # 2. Security Policy Check
            if self.filter.is_blocked(request.host):
                self.logger.warning(
                    f"Blocked Request -> Host '{request.host}' matched policies in blocklist."
                )
                block_body = (
                    "<html>"
                    "<head><title>403 Forbidden</title></head>"
                    "<body style='font-family: Arial, sans-serif; text-align: center; margin-top: 100px;'>"
                    "<h1>403 Access Denied</h1>"
                    f"<p>Access to <strong>{request.host}</strong> has been restricted by local administration policies.</p>"
                    "</body>"
                    "</html>"
                )
                block_response = (
                    "HTTP/1.1 403 Forbidden\r\n"
                    "Content-Type: text/html\r\n"
                    f"Content-Length: {len(block_body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    f"{block_body}"
                )
                client_socket.sendall(block_response.encode('utf-8'))
                return

            # 3. HTTPS CONNECT Tunnel Interception
            if request.method == "CONNECT":
                self.handle_connect_tunnel(client_socket, request)
                return

            # 4. Standard HTTP Outbound Forwarding with LRU Cache Evaluation
            cache_key = f"{request.host}{request.path}"

            # If request is a GET, check if we have a valid cache hit
            if request.method == "GET":
                cached_data = self.cache.get(cache_key)
                if cached_data:
                    self.logger.info(f"Cache HIT -> Serving '{cache_key}' directly from LRU Cache.")
                    client_socket.sendall(cached_data)
                    return

            # If Cache Miss (or non-GET method), establish outbound connection to target
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(timeout)
            
            try:
                target_socket.connect((request.host, request.port))
            except socket.gaierror:
                self.logger.error(f"DNS lookup failed for destination host: {request.host}")
                raise

            # Reconstruct clean HTTP Request to forward to target server
            request_line = f"{request.method} {request.path} {request.http_version}\r\n"
            
            # Ensure Host header exists and default connection is closed
            if "host" not in request.headers:
                request.headers["host"] = request.host if request.port == 80 else f"{request.host}:{request.port}"
            request.headers["connection"] = "close"
            
            header_lines = []
            for key, val in request.headers.items():
                formatted_key = "-".join([part.capitalize() for part in key.split("-")])
                header_lines.append(f"{formatted_key}: {val}")
                
            headers_payload = "\r\n".join(header_lines) + "\r\n\r\n"
            payload = request_line.encode('utf-8') + headers_payload.encode('utf-8')
            if request.body:
                payload += request.body

            # Send payload to remote server
            target_socket.sendall(payload)
            
            # Read from destination and stream back to client while accumulating response bytes
            response_chunks = []
            bytes_transferred = 0
            while True:
                response_chunk = target_socket.recv(4096)
                if not response_chunk:
                    break
                client_socket.sendall(response_chunk)
                response_chunks.append(response_chunk)
                bytes_transferred += len(response_chunk)
                
            full_response = b"".join(response_chunks)

            # Store in cache only if it was a successful GET request (HTTP 200 OK)
            if request.method == "GET" and b"200 OK" in full_response[:50]:
                self.cache.put(cache_key, full_response)
                self.logger.info(f"Cache STORE -> Saved '{cache_key}' to LRU Cache.")

            self.logger.info(
                f"Success -> {request.method} {request.host} | Transferred: {bytes_transferred} bytes"
            )

        except Exception as e:
            self.logger.error(f"Error handling traffic for {client_address}: {e}")
            try:
                error_resp = "HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n"
                client_socket.sendall(error_resp.encode('utf-8'))
            except Exception:
                pass
        finally:
            # Ensure both connection sockets are closed cleanly
            client_socket.close()
            if target_socket:
                try:
                    target_socket.close()
                except Exception:
                    pass

    def handle_connect_tunnel(self, client_socket: socket.socket, request):
        """
        Manages raw bidirectional TCP tunneling (HTTPS). Establishes a raw TCP stream 
        with the target, returns a 200 Established status, and pipes uninspected encrypted bytes.
        """
        target_socket = None
        timeout = self.config.get("timeout", 15)
        self.logger.info(f"Establishing HTTPS Tunnel to {request.host}:{request.port}")
        
        try:
            # 1. Establish direct connection to remote server
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(timeout)
            target_socket.connect((request.host, request.port))
            
            # 2. Respond to client browser that tunnel is established
            established_response = "HTTP/1.1 200 Connection Established\r\n\r\n"
            client_socket.sendall(established_response.encode('utf-8'))
            
            # 3. Transition both sockets to a non-blocking state to use select()
            client_socket.setblocking(False)
            target_socket.setblocking(False)
            
            sockets_list = [client_socket, target_socket]
            keep_tunneling = True
            
            # Bidirectional streaming loop
            while keep_tunneling and self.is_running:
                # select block blocks until client or server socket has data ready to read
                readable, _, exceptional = select.select(sockets_list, [], sockets_list, timeout)
                
                if exceptional:
                    break
                    
                for s in readable:
                    if s is client_socket:
                        sender, receiver = client_socket, target_socket
                    else:
                        sender, receiver = target_socket, client_socket
                        
                    try:
                        data = sender.recv(8192)
                        if not data:
                            # EOF received (Connection closed cleanly by sender)
                            keep_tunneling = False
                            break
                        receiver.sendall(data)
                    except Exception:
                        keep_tunneling = False
                        break
                        
            self.logger.info(f"HTTPS Tunnel successfully closed for {request.host}:{request.port}")

        except Exception as e:
            self.logger.error(f"HTTPS Tunnel failed for {request.host}:{request.port} -> {e}")
            try:
                # Fall back to blocking temporarily to transmit error status safely
                client_socket.setblocking(True)
                error_resp = "HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n"
                client_socket.sendall(error_resp.encode('utf-8'))
            except Exception:
                pass
        finally:
            if target_socket:
                try:
                    target_socket.close()
                except Exception:
                    pass

    def shutdown(self, signum=None, frame=None):
        """Gracefully shuts down the listening server socket, the thread pool, and terminates."""
        if not self.is_running and not self.server_socket:
            return
            
        self.logger.info("Initiating graceful shutdown...")
        self.is_running = False
        
        self.logger.info("Shutting down worker threads...")
        self.executor.shutdown(wait=True)
        
        if self.server_socket:
            try:
                self.server_socket.close()
                self.logger.info("Server socket closed.")
            except Exception as e:
                self.logger.error(f"Error closing server socket: {e}")
                
        self.logger.info("Server shutdown complete.")
        sys.exit(0)

if __name__ == "__main__":
    server = ProxyServer("config/server_config.json")
    server.start()