# High-Level Architecture Design Document

## 1. Component Descriptions
The Custom Network Proxy Server comprises four decoupled modules:
*   **Proxy Engine (`proxy.py`)**: Manages the life cycle of the main socket, executes the connection accept loop, delegates task payloads to the thread pool, and coordinates connection endpoints.
*   **HTTP Parser (`parser.py`)**: Implements strict TCP stream accumulation (reading up to `\r\n\r\n`), dissects raw requests into an internal `HTTPRequest` model, and resolves destination parameters.
*   **Domain Filter (`filter.py`)**: Loads, sanitizes, and evaluates incoming requests against blacklisted domains using an $O(1)$ set lookup. Supports recursive parent domain tracking.
*   **LRU Cache (`cache.py`)**: Implements a thread-safe, size-bounded Least Recently Used (LRU) Cache utilizing a Doubly Linked List and a Hash Map for fast retrieval of static resources.

## 2. Concurrency Model
The server utilizes a **Thread Pool model** via Python's `ThreadPoolExecutor`.
*   **Rationale**: Rather than using a naive thread-per-connection pattern (which is vulnerable to resource exhaustion under load) or a single-threaded loop (which blocks on external DNS resolution or slow network transfers), the Thread Pool enforces a strict upper limit on resource utilization (`max_workers`). 
*   **Data Flow**: The main thread remains dedicated to accepting socket connections. Once handshaked, socket descriptors are offloaded immediately to background worker threads, keeping the proxy responsive.

## 3. Data Flow
### Standard HTTP GET
1. `Client` -> `Proxy`: TCP handshake established on port 8888.
2. `Proxy` parses request target host and path.
3. `Proxy` queries `LRU Cache`. If a hit occurs, the cached payload is returned instantly, and the connection closes.
4. On a cache miss, the `Proxy` connects to the resolved remote IP on port 80.
5. `Proxy` transmits the modified headers and streams response chunks from the destination server back to the `Client`.
6. Successful `200 OK` response payloads are stored in the `LRU Cache`.

### HTTPS CONNECT Tunnel
1. `Client` -> `Proxy`: Sends initial unencrypted request line `CONNECT target:443 HTTP/1.1`.
2. `Proxy` establishes a TCP connection to the destination on port 443.
3. `Proxy` responds to `Client` with `HTTP/1.1 200 Connection Established`.
4. Sockets are placed in a non-blocking state. `Proxy` enters a bidirectional stream loop monitored by `select.select()`.
5. Encrypted bytes are piped transparently without inspected interpretation until either side shuts down.

## 4. Error Handling & Limitations
*   **Graceful Termination**: Handles `SIGINT` / `SIGTERM` cleanly, enabling current active worker threads to flush their streaming buffers before socket termination.
*   **Timeouts**: Sockets enforce a default timeout of 15 seconds to prevent dangling, idle TCP connections from exhausting pool capacity.
*   **Limitations**: Does not decrypt HTTPS traffic (no Man-In-The-Middle TLS intercept), which preserves secure end-to-end encryption.