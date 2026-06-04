import socket
from urllib.parse import urlparse

class HTTPRequest:
    def __init__(self):
        self.method = ""          # e.g., "GET", "POST", "CONNECT"
        self.raw_target = ""      # e.g., "http://example.com/index.html" or "/index.html" or "example.com:443"
        self.http_version = ""    # e.g., "HTTP/1.1"
        self.headers = {}         # Case-insensitive header dictionary
        self.host = ""            # Destination domain (e.g., "example.com")
        self.port = 80            # Destination port (defaults to 80 for HTTP, 443 for HTTPS)
        self.path = "/"           # Relative path for forwarding (e.g., "/index.html")
        self.body = b""           # Body payload if present

class HTTPParser:
    @staticmethod
    def read_headers(client_socket: socket.socket, max_header_size: int = 8192) -> bytes:
        """
        Reads from the socket in a loop until the HTTP header terminator (\r\n\r\n) is found.
        Raises ValueError if headers exceed the safety threshold or if the stream ends prematurely.
        """
        header_bytes = bytearray()
        while b"\r\n\r\n" not in header_bytes:
            if len(header_bytes) > max_header_size:
                raise ValueError("413 Request Header Fields Too Large")
            
            chunk = client_socket.recv(1024)
            if not chunk:
                # Connection closed prematurely
                break
            header_bytes.extend(chunk)
            
        return bytes(header_bytes)

    @classmethod
    def parse(cls, raw_header_bytes: bytes, client_socket: socket.socket) -> HTTPRequest:
        """
        Parses raw HTTP header bytes and reads any accompanying body.
        Returns an HTTPRequest object.
        """
        if not raw_header_bytes:
            raise ValueError("Empty request received.")

        # Split headers into header section and any partial body read during the loop
        parts = raw_header_bytes.split(b"\r\n\r\n", 1)
        header_text = parts[0].decode('utf-8', errors='ignore')
        partial_body = parts[1] if len(parts) > 1 else b""

        lines = header_text.split("\r\n")
        request_line = lines[0]
        
        # Parse Request-Line: Method Request-URI HTTP-Version
        request_line_parts = request_line.split()
        if len(request_line_parts) < 3:
            raise ValueError("400 Bad Request: Invalid request line format.")

        req = HTTPRequest()
        req.method = request_line_parts[0].upper()
        req.raw_target = request_line_parts[1]
        req.http_version = request_line_parts[2]

        # Parse Headers (case-insensitive keys)
        for line in lines[1:]:
            if not line.strip():
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                req.headers[key.strip().lower()] = val.strip()

        # Parse Host and Port out of the request
        cls._parse_host_and_port(req)

        # Read Request Body if applicable (e.g., POST/PUT with Content-Length)
        if req.method in ("POST", "PUT", "PATCH"):
            content_length = int(req.headers.get("content-length", 0))
            if content_length > 0:
                bytes_to_read = content_length - len(partial_body)
                body_accumulated = bytearray(partial_body)
                
                while len(body_accumulated) < content_length:
                    chunk = client_socket.recv(min(4096, bytes_to_read))
                    if not chunk:
                        break
                    body_accumulated.extend(chunk)
                    bytes_to_read -= len(chunk)
                
                req.body = bytes(body_accumulated[:content_length])
        
        return req

    @classmethod
    def _parse_host_and_port(cls, req: HTTPRequest):
        """
        Extracts destination host, port, and relative path from the request.
        """
        # Scenario A: CONNECT requests (e.g., Tunneling to "example.com:443")
        if req.method == "CONNECT":
            req.port = 443
            if ":" in req.raw_target:
                host, port_str = req.raw_target.split(":", 1)
                req.host = host
                try:
                    req.port = int(port_str)
                except ValueError:
                    pass
            else:
                req.host = req.raw_target
            return

        # Scenario B: Absolute URIs (e.g., "http://example.com/path?query")
        if req.raw_target.startswith("http://") or req.raw_target.startswith("https://"):
            parsed_url = urlparse(req.raw_target)
            req.host = parsed_url.hostname
            req.port = parsed_url.port if parsed_url.port else 80
            req.path = parsed_url.path if parsed_url.path else "/"
            if parsed_url.query:
                req.path += f"?{parsed_url.query}"
        else:
            # Scenario C: Relative URIs (e.g., "/path") - must check Host header
            req.path = req.raw_target
            host_header = req.headers.get("host")
            if host_header:
                if ":" in host_header:
                    host, port_str = host_header.split(":", 1)
                    req.host = host
                    try:
                        req.port = int(port_str)
                    except ValueError:
                        req.port = 80
                else:
                    req.host = host_header
                    req.port = 80
            else:
                raise ValueError("400 Bad Request: Missing Host header in relative request.")