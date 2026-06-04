# Custom Network Proxy Server

A lightweight, concurrent network forward proxy server implemented in Python, handling unencrypted HTTP GET/HEAD requests and encrypted HTTPS CONNECT tunneling.

## Features
*   **Thread Pool Concurrency**: Configurable worker pools to limit resource exhaustion.
*   **Thread-Safe LRU Cache**: Memory-bound cache utilizing a Doubly Linked List and Hash Map.
*   **Recursive Suffix Filtering**: Policies to block access to specific hostnames or wildcards (e.g., blocking `example.com` automatically blocks `sub.example.com`).
*   **Graceful Shut Down**: Safely terminates open connections and worker threads.

## Directory Layout
```text
proxy-project/
├─ src/             # Source implementations
│  ├─ proxy.py      # Entry point & connection coordinator
│  ├─ parser.py     # HTTP header accumulator & parser
│  ├─ filter.py     # Rule-based blocklist validator
│  ├─ cache.py      # Thread-safe LRU Cache
│  └─ logger.py     # Standard thread-safe logger
├─ config/          # Configurations
│  ├─ server_config.json
│  └─ blocked_domains.txt
├─ tests/           # Integration tests
│  └─ test_proxy.py
├─ docs/            # Architectures & Manuals
│  ├─ README.md
│  └─ architecture.md
```

## Setup & Running
1. Configure your listening settings in `config/server_config.json`.
2. Add any restricted domains to `config/blocked_domains.txt`.
3. Start the proxy server:
   ```bash
   python3 src/proxy.py
   ```

## Running Automated Tests
With the server running, execute the following script in a separate terminal window:
```bash
python3 tests/test_proxy.py
```
```

---

### You are all set!

Once these files are created, run the automated integration tests (`python3 tests/test_proxy.py`). It will verify all your hard work and produce a clean, professional status summary. Let me know when you run the tests!