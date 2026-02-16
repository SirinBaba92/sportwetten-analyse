"""
Health Check für Railway
"""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.getenv("PORT", 8080))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')
    
    def log_message(self, format, *args):
        pass  # Keine Logs

def run():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"✅ Health check läuft auf Port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
