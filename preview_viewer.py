#!/usr/bin/env python3
"""Simple HTTP server to preview viewer.html changes locally.

Serves the template directory and proxies R2 requests to avoid CORS issues.

Usage:
    python preview_viewer.py
    # Then open: http://localhost:8000/viewer.html
"""

import http.server
import socketserver
from pathlib import Path
import urllib.request
import json

PORT = 8000
TEMPLATE_DIR = Path(__file__).parent / "src/birdbird/templates"
R2_BASE_URL = "https://pub-975f47bf9a614239932c993acd009ad5.r2.dev"

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(TEMPLATE_DIR), **kwargs)

    def do_GET(self):
        # Proxy requests to R2 to avoid CORS
        if self.path.startswith('/latest.json') or self.path.startswith('/batches/'):
            try:
                r2_url = f"{R2_BASE_URL}{self.path}"

                # Create request with browser-like headers
                req = urllib.request.Request(
                    r2_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                    }
                )

                with urllib.request.urlopen(req) as response:
                    content = response.read()
                    content_type = response.headers.get('Content-Type', 'application/octet-stream')

                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self.send_error(500, f"Error fetching from R2: {e}")
                return

        # Serve local files normally
        super().do_GET()

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), ProxyHTTPRequestHandler) as httpd:
        print(f"Preview server running at http://localhost:{PORT}/")
        print(f"Open http://localhost:{PORT}/viewer.html in your browser")
        print(f"Serving from: {TEMPLATE_DIR}")
        print(f"Proxying R2 requests from: {R2_BASE_URL}")
        print(f"\nPress Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
