"""
reader_web.py

Lector del formato .imgmap usando un WebView nativo (pywebview).

Python funciona como servidor HTTP local y entrega:
  - index.html
  - app.js, CSS y demas archivos estaticos
  - manifest
  - imagenes contenidas dentro del .imgmap

Los archivos web se buscan (en este orden) en:
  1. static/
  2. templates/
  3. la carpeta de este script

Uso:
    python reader_web.py
o:
    python reader_web.py "archivo.imgmap"
"""

import re
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

from mapformat import read_manifest, build_from_folder, EXTENSION

try:
    import settings  # guarda "ultimo archivo" y "biblioteca" en %LOCALAPPDATA%\\VECTOR
except ImportError:
    settings = None

# Carpetas donde se buscan los archivos web.
WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
SEARCH_DIRS = [STATIC_DIR, TEMPLATES_DIR, WEB_DIR]

ERROR_LOG = Path.home() / "imgmap_reader_web_error.log"

# Tipos de imagen que se sirven desde dentro del .imgmap.
EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Solo estas extensiones se sirven como archivos estaticos.
# (Asi nunca se expone un .py, el .imgmap ni otros archivos del proyecto.)
STATIC_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


# El HTML usa sintaxis de Flask: {{ url_for('static', filename='app.css') }}
# Este servidor no es Flask, asi que se traduce a /static/app.css al entregarlo.
URL_FOR_STATIC = re.compile(
    r"\{\{\s*url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
)


def find_web_file(rel):
    """
    Busca un archivo estatico en SEARCH_DIRS.
    Devuelve un Path valido o None. Bloquea rutas con ../ y extensiones
    que no esten en STATIC_MIME.
    """
    rel = rel.lstrip("/\\")
    if rel.startswith("static/"):
        rel = rel[len("static/"):]
    if not rel:
        return None

    if Path(rel).suffix.lower() not in STATIC_MIME:
        return None

    for base in SEARCH_DIRS:
        try:
            base_resolved = base.resolve()
            candidate = (base / rel).resolve()
        except (OSError, ValueError):
            continue

        # Evita salirse de la carpeta base (path traversal).
        if base_resolved != candidate and base_resolved not in candidate.parents:
            continue

        if candidate.is_file():
            return candidate

    return None


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
                raise FileNotFoundError("No hay ningun archivo abierto")
            return self.zf.read(arcname)


STATE = MapState()


class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # No llenar la consola con logs de cada pedido.
        pass

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            route = unquote(parsed.path)

            # Pagina principal
            if route in ("/", "/index.html"):
                return self._serve_static("index.html")

            # Manifest del archivo .imgmap
            if route == "/manifest":
                return self._serve_manifest()

            # Imagenes internas del .imgmap
            if route.startswith("/img/"):
                arcname = route[len("/img/"):]
                return self._serve_image(arcname)

            # Cualquier otro archivo estatico: /app.js, /static/style.css,
            # /style.css, fuentes, etc.
            return self._serve_static(route)

        except Exception:
            ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
            try:
                self.send_error(500)
            except Exception:
                pass

    def _serve_static(self, rel):
        path = find_web_file(rel)
        if path is None:
            print("404 ->", rel)
            self.send_error(404, f"No existe el archivo: {rel}")
            return

        data = path.read_bytes()

        # Si es HTML, reemplazar los url_for('static', ...) de Flask.
        if path.suffix.lower() == ".html":
            text = data.decode("utf-8")
            text = URL_FOR_STATIC.sub(r"/static/\1", text)
            data = text.encode("utf-8")

        content_type = STATIC_MIME.get(
            path.suffix.lower(), "application/octet-stream"
        )

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        # Sin cache para ver los cambios de CSS/JS al recargar.
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_manifest(self):
        if STATE.manifest is None:
            self.send_error(404, "No hay ningun archivo abierto")
            return

        body = dict(STATE.manifest)
        body["_path"] = str(STATE.path)
        data = json.dumps(body).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_image(self, arcname):
        try:
            data = STATE.read(arcname)
        except (KeyError, FileNotFoundError):
            self.send_error(404)
            return

        mime = EXT_MIME.get(
            Path(arcname).suffix.lower(), "application/octet-stream"
        )

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        self.wfile.write(data)


def _open_dialog_type():
    """Compatible con versiones nuevas y viejas de pywebview."""
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None and hasattr(file_dialog, "OPEN"):
        return file_dialog.OPEN
    return webview.OPEN_DIALOG


def _dialog_type(name):
    """
    name: "OPEN", "SAVE" o "FOLDER".
    Compatible con pywebview nuevo (webview.FileDialog.X) y viejo (webview.X_DIALOG).
    """
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None and hasattr(file_dialog, name):
        return getattr(file_dialog, name)
    return getattr(webview, f"{name}_DIALOG")


def _first(result):
    """create_file_dialog devuelve tupla/lista o texto segun la version."""
    if not result:
        return None
    if isinstance(result, (list, tuple)):
        return result[0]
    return result


class Api:
    """
    Metodos que JavaScript puede llamar
    mediante pywebview.api.<metodo>().
    """

    def __init__(self):
        self.window = None

    def choose_and_open(self):
        result = self.window.create_file_dialog(
            _open_dialog_type(),
            file_types=(
                f"Mapa de imagenes (*{EXTENSION})",
                "Todos los archivos (*.*)",
            ),
        )

        if not result:
            return None

        path = result[0]
        STATE.open(path)

        return {"path": str(path)}

    def create_new_map(self):
        """
        Boton CREAR.

        1. El usuario elige la carpeta de origen (portada + ramas numeradas).
        2. El usuario elige donde guardar el .imgmap.
        3. Se genera el archivo con mapformat.build_from_folder().
        4. Se abre el archivo nuevo y se recuerda como ultimo archivo.

        Devuelve:
          None                     -> el usuario cancelo
          {"error": "mensaje"}     -> fallo la creacion
          {"path": "ruta.imgmap"}  -> creado y abierto (igual que choose_and_open)
        """
        try:
            folder = _first(
                self.window.create_file_dialog(
                    _dialog_type("FOLDER"),
                )
            )
            if not folder:
                return None

            folder = Path(folder)

            output = _first(
                self.window.create_file_dialog(
                    _dialog_type("SAVE"),
                    save_filename=f"{folder.name}{EXTENSION}",
                    file_types=(
                        f"Mapa de imagenes (*{EXTENSION})",
                    ),
                )
            )
            if not output:
                return None

            output = Path(output)
            if output.suffix.lower() != EXTENSION:
                output = output.with_suffix(EXTENSION)

            build_from_folder(folder, output, title=folder.name)

            STATE.open(output)
            if settings is not None:
                settings.set_last_file(output)

            return {"path": str(output)}

        except Exception as exc:
            ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
            return {"error": str(exc)}


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_server():
    httpd = Server(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    return port


def main():
    # Si se paso un archivo .imgmap como argumento,
    # se abre automaticamente.
    if len(sys.argv) > 1:
        try:
            STATE.open(sys.argv[1])
        except Exception:
            ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")

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
        ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
        raise
