from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class BackendHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            status = 200
            body = b"ok\n"
        elif path == "/":
            status = 200
            body = b"Hello from backend\n"
        else:
            status = 404
            body = b"Not found\n"

        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), BackendHandler)
    print("Backend listening on port 8080", flush=True)
    server.serve_forever()