"""
reader_web.py
Lector del formato .imgmap usando un WebView nativo (pywebview).

Python funciona como servidor HTTP local y entrega:
- index.html
- app.js
- manifest
- imagenes contenidas dentro del .imgmap

Uso:

    python reader_web.py

o:

    python reader_web.py "archivo.imgmap"
"""

import sys
import json
import threading
import traceback
import zipfile
import http.server
import socketserver

from pathlib import Path
from urllib.parse import urlparse, unquote

import webview

from mapformat import read_manifest, EXTENSION


# Los archivos web están en la misma carpeta que reader_web.py.
WEB_DIR = Path(__file__).parent

ERROR_LOG = Path.home() / "imgmap_reader_web_error.log"


EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class MapState:
    """Guarda el .imgmap actualmente abierto. Solo hay uno a la vez."""

    def __init__(self):
        self.path = None
        self.manifest = None
        self.zf = None
        self.lock = threading.Lock()

    def open(self, path):
        with self.lock:
            if self.zf:
                self.zf.close()

            self.path = Path(path)
            self.manifest = read_manifest(self.path)
            self.zf = zipfile.ZipFile(self.path, "r")

    def read(self, arcname):
        with self.lock:
            if self.zf is None:
                raise FileNotFoundError(
                    "No hay ningun archivo abierto"
                )

            return self.zf.read(arcname)


STATE = MapState()


class Handler(http.server.BaseHTTPRequestHandler):
        STATIC_MIME = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".woff2": "font/woff2",
        ".ico": "image/x-icon",
    }

    def _serve_file_from(self, base_dir, rel):
        path = (base_dir / rel).resolve()
        # evita salir de la carpeta con ../
        if base_dir.resolve() not in path.parents or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
            self.STATIC_MIME.get(path.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # No llenar la consola con logs de cada pedido.
        pass

    def do_GET(self):

        try:
            parsed = urlparse(self.path)
            route = parsed.path

            # Página principal
            if route in ("/", "/index.html"):
                return self._serve_static(
                    "index.html",
                    "text/html; charset=utf-8"
                )

            # JavaScript
            if route == "/app.js":
                return self._serve_static(
                    "app.js",
                    "application/javascript; charset=utf-8"
                )

            # Manifest del archivo .imgmap
            if route == "/manifest":
                return self._serve_manifest()

            # Imágenes internas del .imgmap
            if route.startswith("/img/"):
                arcname = unquote(
                    route[len("/img/"):]
                )

                return self._serve_image(arcname)

            # Ruta inexistente
            self.send_error(404)

        except Exception:

            ERROR_LOG.write_text(
                traceback.format_exc(),
                encoding="utf-8"
            )

            try:
                self.send_error(500)
            except Exception:
                pass

    def _serve_static(self, filename, content_type):

        path = WEB_DIR / filename

        # Archivos estáticos (css, js, etc.)
        if route.startswith("/static/"):
            return self._serve_file_from(WEB_DIR / "static", route[len("/static/"):])

        if not path.exists():
            self.send_error(
                404,
                f"No existe el archivo: {filename}"
            )
            return

        data = path.read_bytes()

        self.send_response(200)

        self.send_header(
            "Content-Type",
            content_type
        )

        self.send_header(
            "Content-Length",
            str(len(data))
        )

        self.end_headers()

        self.wfile.write(data)

    def _serve_manifest(self):

        if STATE.manifest is None:

            self.send_error(
                404,
                "No hay ningun archivo abierto"
            )

            return

        body = dict(STATE.manifest)

        body["_path"] = str(STATE.path)

        data = json.dumps(
            body
        ).encode("utf-8")

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(data))
        )

        self.end_headers()

        self.wfile.write(data)

    def _serve_image(self, arcname):

        try:

            data = STATE.read(arcname)

        except (
            KeyError,
            FileNotFoundError
        ):

            self.send_error(404)

            return

        mime = EXT_MIME.get(
            Path(arcname).suffix.lower(),
            "application/octet-stream"
        )

        self.send_response(200)

        self.send_header(
            "Content-Type",
            mime
        )

        self.send_header(
            "Content-Length",
            str(len(data))
        )

        self.send_header(
            "Cache-Control",
            "public, max-age=31536000, immutable"
        )

        self.end_headers()

        self.wfile.write(data)


class Api:
    """
    Métodos que JavaScript puede llamar
    mediante pywebview.api.<metodo>().
    """

    def __init__(self):

        self.window = None

    def choose_and_open(self):

        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=(
                f"Mapa de imagenes (*{EXTENSION})",
                "Todos los archivos (*.*)"
            ),
        )

        if not result:
            return None

        path = result[0]

        STATE.open(path)

        return {
            "path": str(path)
        }


def start_server():

    httpd = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0),
        Handler
    )

    port = httpd.server_address[1]

    thread = threading.Thread(
        target=httpd.serve_forever,
        daemon=True
    )

    thread.start()

    return port


def main():

    # Si se pasó un archivo .imgmap como argumento,
    # se abre automáticamente.
    if len(sys.argv) > 1:

        try:

            STATE.open(
                sys.argv[1]
            )

        except Exception:

            ERROR_LOG.write_text(
                traceback.format_exc(),
                encoding="utf-8"
            )

    # Servidor HTTP local
    port = start_server()

    api = Api()

    # Ventana de pywebview
    window = webview.create_window(
        "Lector de mapas de imagenes",
        url=f"http://127.0.0.1:{port}/",
        js_api=api,
        width=1200,
        height=800,
        min_size=(600, 400),
    )

    api.window = window

    webview.start()


if __name__ == "__main__":

    try:

        main()

    except Exception:

        ERROR_LOG.write_text(
            traceback.format_exc(),
            encoding="utf-8"
        )

        raise