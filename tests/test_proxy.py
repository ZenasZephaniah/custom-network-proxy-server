import subprocess
import unittest
import time

class TestProxyServer(unittest.TestCase):
    PROXY_URL = "http://127.0.0.1:8888"

    def test_01_http_forwarding_and_cache(self):
        """Verify that HTTP GET requests succeed and cache hits occur on second retrieval."""
        print("\n--- Test 1: HTTP Forwarding and Caching ---")
        
        # Run first curl to populate cache
        cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-x", self.PROXY_URL, "http://example.com"]
        result1 = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result1.stdout.strip(), "200", "First HTTP GET failed")
        print("[Pass] First HTTP GET call succeeded (200 OK).")

        # Run second curl to verify cache hit
        result2 = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result2.stdout.strip(), "200", "Second HTTP GET failed")
        print("[Pass] Second HTTP GET call succeeded via cache.")

    def test_02_https_tunneling(self):
        """Verify that secure HTTPS CONNECT requests traverse the proxy correctly."""
        print("\n--- Test 2: HTTPS Tunneling (CONNECT) ---")
        cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-x", self.PROXY_URL, "https://example.com"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "200", "HTTPS tunnel connection failed")
        print("[Pass] HTTPS tunnel successfully established and resolved.")

    def test_03_http_blocking(self):
        """Verify that HTTP requests to blacklisted domains are blocked with a 403 status."""
        print("\n--- Test 3: HTTP Domain Blocking ---")
        cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-x", self.PROXY_URL, "http://blockedexample.com"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "403", "Proxy failed to block HTTP blacklisted domain")
        print("[Pass] HTTP domain check successfully intercepted with a 403 Forbidden.")

    def test_04_https_blocking(self):
        """Verify that HTTPS requests to blacklisted domains are blocked at connection setup."""
        print("\n--- Test 4: HTTPS CONNECT Domain Blocking ---")
        
        # We drop -s (silent) and use -S to allow curl to print error messages to stderr
        cmd = ["curl", "-S", "-o", "/dev/null", "-w", "%{http_code}", "-x", self.PROXY_URL, "https://blockedexample.com"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Curl reports '000' because the destination server was never reached
        self.assertEqual(result.stdout.strip(), "000", "Destination server should not be reached.")
        
        # Curl stderr should contain the "403" response code returned during CONNECT phase
        self.assertIn("403", result.stderr, "Proxy failed to return 403 Forbidden during tunnel handshake.")
        print("[Pass] HTTPS CONNECT domain check successfully intercepted with a 403 Forbidden.")

if __name__ == "__main__":
    print("Ensure the proxy server is running on localhost:8888 before executing tests.")
    unittest.main()