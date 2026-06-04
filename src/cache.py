import threading

class CacheNode:
    def __init__(self, key: str, value: bytes):
        self.key = key          # The normalized request URI (e.g., "example.com/index.html")
        self.value = value      # The complete raw binary HTTP response payload
        self.prev = None
        self.next = None

class LRUCache:
    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self.cache_map = {}     # Maps key -> CacheNode
        self.lock = threading.Lock()
        
        # Sentinel Nodes for the Doubly Linked List (helps avoid boundary/null checks)
        self.head = CacheNode("", b"")
        self.tail = CacheNode("", b"")
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node: CacheNode):
        """Removes a node from its current position in the doubly linked list."""
        prev_node = node.prev
        next_node = node.next
        prev_node.next = next_node
        next_node.prev = prev_node

    def _add_to_head(self, node: CacheNode):
        """Inserts a node right after the head sentinel (marking it as Most Recently Used)."""
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def get(self, key: str) -> bytes:
        """
        Retrieves cached response bytes. If found, promotes the node 
        to the head of the list (MRU) and returns the data.
        """
        with self.lock:
            if key in self.cache_map:
                node = self.cache_map[key]
                self._remove(node)
                self._add_to_head(node)
                return node.value
            return None

    def put(self, key: str, value: bytes):
        """
        Stores response bytes in the cache. Evicts the Least Recently 
        Used (LRU) node from the tail if capacity is exceeded.
        """
        with self.lock:
            if key in self.cache_map:
                # Update existing entry
                node = self.cache_map[key]
                node.value = value
                self._remove(node)
                self._add_to_head(node)
            else:
                # Create a new entry
                new_node = CacheNode(key, value)
                self.cache_map[key] = new_node
                self._add_to_head(new_node)
                
                # Check capacity bounds
                if len(self.cache_map) > self.capacity:
                    # Evict the node right before the tail sentinel (LRU)
                    lru_node = self.tail.prev
                    self._remove(lru_node)
                    if lru_node.key in self.cache_map:
                        del self.cache_map[lru_node.key]