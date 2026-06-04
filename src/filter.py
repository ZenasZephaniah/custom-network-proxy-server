import os

class URLFilter:
    def __init__(self, blocklist_path: str):
        self.blocklist_path = blocklist_path
        self.blocked_domains = set()
        self.load_blocklist()

    def load_blocklist(self):
        """
        Reads the blocked domains from a text file, canonicalizes them,
        and loads them into a fast-lookup set.
        """
        if not os.path.exists(self.blocklist_path):
            return
        try:
            with open(self.blocklist_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Ignore empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Canonicalize (lowercase and strip whitespace)
                    self.blocked_domains.add(line.lower())
        except Exception as e:
            print(f"Error loading blocklist: {e}")

    def is_blocked(self, host: str) -> bool:
        """
        Checks if a host or its parent domains are present in the blocked set.
        E.g., if 'badsite.org' is blocked, then 'sub.badsite.org' should also be blocked.
        """
        if not host:
            return False
        
        host = host.lower().strip()
        
        # Direct Match Check
        if host in self.blocked_domains:
            return True
        
        # Suffix/Subdomain Match Check (e.g., sub.badsite.org checking badsite.org)
        parts = host.split('.')
        for i in range(1, len(parts)):
            parent_domain = ".".join(parts[i:])
            if parent_domain in self.blocked_domains:
                return True
                
        return False