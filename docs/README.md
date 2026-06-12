# Custom Concurrent Forward Proxy Server

A lightweight, concurrent forward proxy server implemented in Python, capable of handling unencrypted HTTP traffic and establishing transparent HTTPS CONNECT tunnels. The server integrates customizable rule-based domain filtering and an in-memory, thread-safe Least Recently Used (LRU) cache constructed from scratch.

---

## Technical Features

*   **Bounded Concurrency (Thread Pool)**: Rather than spawning unbounded threads, the server utilizes a configured `ThreadPoolExecutor` to handle concurrent connections safely within a stable system memory envelope.
*   **Thread-Safe LRU Caching**: An in-memory cache implemented from scratch using a Doubly Linked List (DLL) for $O(1)$ node promotion and a Hash Map for $O(1)$ lookups. Thread safety is enforced via a mutual exclusion lock (`threading.Lock`).
*   **HTTPS CONNECT Tunneling**: Supports transparent SSL/TLS tunneling. Once the `CONNECT` handshake is established, the proxy transitions client and server sockets to non-blocking states and multiplexes data bidirectionally using `select.select()`.
*   **Recursive Suffix Policy Filtering**: Intercepts requests pointing to blacklisted domains. Suffix logic guarantees that blocking a parent host (e.g., `blockedexample.com`) automatically denies access to all subdomains (e.g., `sub.blockedexample.com`).
*   **Graceful Signal Termination**: Handlers for `SIGINT` and `SIGTERM` guarantee that running worker threads flush their streaming buffers and release socket descriptors cleanly before shutdown.

---

## Directory Layout

This project maintains a strict separation of concerns to ensure modules can be tested independently:

```text
custom-network-proxy-server/
|-- config/
|   |-- blocked_domains.txt     # Domain policy block rules
|   +-- server_config.json      # JSON server configurations
|-- deliverables/
|   |-- report.pdf              # Academic and design document PDF
|   +-- manual.pdf              # Supplementary test screenshot manual
|-- docs/
|   |-- README.md               # Quickstart guide
|   +-- architecture.md         # Detailed design manual
|-- logs/
|   +-- proxy.log               # Live persistent system logs
|-- src/
|   |-- proxy.py                # Listening socket loop & worker threads
|   |-- parser.py               # Robust raw HTTP parser
|   |-- filter.py               # Recursive suffix filter
|   |-- cache.py                # Custom thread-safe LRU Cache
|   +-- logger.py               # Synchronous dual-sink logger
+-- tests/
    +-- test_proxy.py           # Automated integration test suite
```

---

## Deployment & Running

### 1. Configure the Proxy
Modify the parameters in `config/server_config.json` to fit your local environment:
```json
{
  "host": "127.0.0.1",
  "port": 8888,
  "thread_pool_size": 16,
  "log_file": "logs/proxy.log",
  "blocked_domains_file": "config/blocked_domains.txt",
  "timeout": 15,
  "cache_capacity": 5
}
```

### 2. Configure the Blocklist
Add target domains to restrict into `config/blocked_domains.txt` (one domain per line):
```text
blockedexample.com
badsite.org
```

### 3. Start the Server
Run the listener using the local Python interpreter:
```bash
python3 src/proxy.py
```

---

## Verification & Testing Suite

With the proxy server running in one terminal tab, open a secondary terminal tab to run validation tests:

### 1. Automated Integration Tests
Executes sequential assertions for HTTP forwarding, caching, HTTPS tunneling, and policy interceptions:
```bash
python3 tests/test_proxy.py
```

### 2. Verification of LRU Cache Hits
To manually verify that static GET responses are served from memory:
```bash
# First request (Cache Miss - populated into memory)
curl -I -x http://127.0.0.1:8888 http://example.com

# Second request (Cache Hit - served directly from LRU cache)
curl -I -x http://127.0.0.1:8888 http://example.com
```
*Verify that your proxy terminal outputs a corresponding `Cache HIT` log statement.*

### 3. Verification of Secure Tunneling (CONNECT)
Verify that HTTPS tunnels complete TLS handshakes cleanly through the proxy:
```bash
curl -I -x http://127.0.0.1:8888 https://example.com
```

### 4. Malformed Request Resilience Test
Verify the proxy handles corrupt HTTP lines without crashing:
```bash
echo "MALFORMED_GARBAGE_REQUEST_WITHOUT_HEADERS" | nc 127.0.0.1:8888
```
*The client receives a `400 Bad Request` and disconnects, while the server remains active to handle subsequent clients.*

### 5. High Concurrency Load Testing
Use Apache Benchmark (`ab`) to send 100 requests with a concurrency level of 10:
```bash
ab -n 100 -c 10 -X 127.0.0.1:8888 http://example.com/
```

---

## Specifications & Systems Design Highlights

### Bidirectional Non-Blocking I/O
Secure connections (HTTPS) require bidirectional data transfer. Rather than allocating two threads per connection, we use `select.select()` to poll both sockets concurrently:
```python
# Transition sockets to non-blocking states
client_socket.setblocking(False)
target_socket.setblocking(False)
sockets_list = [client_socket, target_socket]

# Single-threaded bidirectional multiplexing loop
while keep_tunneling:
    readable, _, exceptional = select.select(sockets_list, [], sockets_list, timeout)
    if exceptional:
         break
    for s in readable:
         sender, receiver = (client_socket, target_socket) if s is client_socket else (target_socket, client_socket)
         data = sender.recv(8192)
         if not data:
             keep_tunneling = False
             break
         receiver.sendall(data)
```
This reduces the thread count by 50% for HTTPS streams, decreasing memory usage and context-switching overhead.
