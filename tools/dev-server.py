from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "product-analyzer" / "frontend"
API = "https://gracious-renewal-production-aadd.up.railway.app"
PORT = 8000

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _proxy(self):
        target = API + self.path
        body = None

        length = self.headers.get("Content-Length")
        if length:
            body = self.rfile.read(int(length))

        headers = {}
        for key in ("Content-Type", "Accept", "Authorization"):
            value = self.headers.get(key)
            if value:
                headers[key] = value

        req = Request(
            target,
            data=body,
            headers=headers,
            method=self.command
        )

        try:
            response = urlopen(req, timeout=30)
            status = response.status
            data = response.read()
            content_type = response.headers.get(
                "Content-Type",
                "application/json"
            )
        except HTTPError as e:
            status = e.code
            data = e.read()
            content_type = e.headers.get(
                "Content-Type",
                "application/json"
            )
        except URLError as e:
            self.send_error(502, f"API no disponible: {e}")
            return
        except Exception as e:
            self.send_error(502, f"Error de proxy: {e}")
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET,POST,PUT,PATCH,DELETE,OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type,Authorization"
        )
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        if self.path.startswith("/api/v1/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Access-Control-Allow-Methods",
                "GET,POST,PUT,PATCH,DELETE,OPTIONS"
            )
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type,Authorization"
            )
            self.end_headers()
        else:
            self.send_response(204)
            self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/v1/"):
            self._proxy()
            return

        path = urlsplit(self.path).path.rstrip("/")

        if path == "":
            self.path = "/tienda.html"
        elif path in ("/tienda", "/"):
            self.path = "/tienda.html"
        elif path in ("/central", "/admin"):
            self.path = "/index.html"
        elif path == "/tarjetas":
            self.path = "/tarjetas.html"
        elif path == "/vitrina":
            self.path = "/vitrina.html"
        elif path == "/producto" or path.startswith("/producto/"):
            self.path = "/producto.html"

        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/v1/"):
            self._proxy()
            return
        self.send_error(405)

    def do_PUT(self):
        if self.path.startswith("/api/v1/"):
            self._proxy()
            return
        self.send_error(405)

    def do_PATCH(self):
        if self.path.startswith("/api/v1/"):
            self._proxy()
            return
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith("/api/v1/"):
            self._proxy()
            return
        self.send_error(405)

print(f"Central local: http://127.0.0.1:{PORT}")
print(f"Frontend: {ROOT}")
print(f"API: {API}")
print("Ctrl+C para detener")

ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
