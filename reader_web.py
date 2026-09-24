"""
reader_web.py

Lector del formato .imgmap usando un WebView nativo (pywebview).

Python funciona como servidor HTTP local y entrega:
  - index.html
  - app.js, CSS y demas archivos estaticos
  - manifest
  - imagenes contenidas dentro del .imgmap

Los archivos web se buscan (en este orden) en:
  1. templates/
  2. la carpeta de este script

Uso:
    python reader_web.py
o:
    python reader_web.py "archivo.imgmap"
"""

import re
import sys
import hashlib
import functools
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
from library import get_library_files, read_cover

try:
    import settings  # guarda "ultimo archivo" y "biblioteca" en %LOCALAPPDATA%\\VECTOR
except ImportError:
    settings = None

# Carpetas donde se buscan los archivos web.
WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
SEARCH_DIRS = [TEMPLATES_DIR, WEB_DIR]

ERROR_LOG = Path.home() / "imgmap_reader_web_error.log"

# python reader_web.py --debug  -> imprime las llamadas de JS a Python y abre las
# herramientas de desarrollo (clic derecho > Inspeccionar) dentro de la ventana.
DEBUG = "--debug" in sys.argv

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


def find_web_file(rel):
    """
    Busca un archivo estatico en SEARCH_DIRS.
    Devuelve un Path valido o None. Bloquea rutas con ../ y extensiones
    que no esten en STATIC_MIME.
    """
    rel = rel.lstrip("/\\")
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


def is_allowed_library_file(path):
    """
    Solo se permite leer .imgmap que esten directamente dentro de la
    carpeta de biblioteca elegida por el usuario.
    """
    try:
        path = Path(path).resolve()
        if path.suffix.lower() != EXTENSION or not path.is_file():
            return False
        library = settings.get_library_path() if settings else None
        return library is not None and path.parent == library.resolve()
    except Exception:
        return False


# ---------------- VELOCIDAD DE DESPLAZAMIENTO (flechas arriba / abajo) ----------------
# Unidad: pixeles por segundo mientras se mantiene apretada la flecha.

DEFAULT_SCROLL_SPEED = 1300
MIN_SCROLL_SPEED = 100
MAX_SCROLL_SPEED = 5000


def _clamp_speed(value):
    return max(MIN_SCROLL_SPEED, min(MAX_SCROLL_SPEED, int(round(float(value)))))


def load_scroll_speed():
    if settings is None:
        return DEFAULT_SCROLL_SPEED
    try:
        return _clamp_speed(
            settings.load_settings().get("scroll_speed", DEFAULT_SCROLL_SPEED)
        )
    except Exception:
        return DEFAULT_SCROLL_SPEED


def save_scroll_speed(value):
    if settings is None:
        return
    data = settings.load_settings()
    data["scroll_speed"] = value
    settings.save_settings(data)


class MapState:
    """Guarda el .imgmap actualmente abierto. Solo hay uno a la vez."""

    def __init__(self):
        self.path = None
        self.manifest = None
        self.zf = None
        self.mtime = 0
        self.lock = threading.Lock()

    def open(self, path):
        with self.lock:
            if self.zf:
                self.zf.close()
            self.path = Path(path)
            self.manifest = read_manifest(self.path)
            self.zf = zipfile.ZipFile(self.path, "r")
            self.mtime = self.path.stat().st_mtime_ns

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

            # Sin icono: responder vacio en vez de 404
            if route == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return

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

            # Portadas de la biblioteca: /library-cover/<ruta>|<portada>
            if route.startswith("/library-cover/"):
                return self._serve_library_cover(route[len("/library-cover/"):])

            # Cualquier otro archivo estatico: /app.js,
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

    def _send_cached(self, data, mime, etag):
        """
        Cache correcto: el navegador guarda la imagen pero revalida con ETag.
        (Antes se usaba 'immutable' un anio: al abrir otro .imgmap con los mismos
        nombres internos, como 1/1.jpg, se veian las imagenes del mapa anterior.)
        """
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
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
        key = f"{STATE.path}|{STATE.mtime}|{arcname}"
        etag = '"' + hashlib.md5(key.encode("utf-8")).hexdigest() + '"'
        self._send_cached(data, mime, etag)

    def _serve_library_cover(self, spec):
        # spec = "C:/carpeta/archivo.imgmap|portada.jpg"
        map_path, _, cover = spec.rpartition("|")
        if not map_path or not cover:
            self.send_error(404)
            return

        if not is_allowed_library_file(map_path):
            self.send_error(403)
            return

        suffix = Path(cover).suffix.lower()
        if suffix not in EXT_MIME:
            self.send_error(404)
            return

        try:
            data = read_cover(map_path, cover)
            mtime = Path(map_path).stat().st_mtime_ns
        except Exception:
            self.send_error(404)
            return

        key = f"{map_path}|{mtime}|{cover}"
        etag = '"' + hashlib.md5(key.encode("utf-8")).hexdigest() + '"'
        self._send_cached(data, EXT_MIME[suffix], etag)


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


def logged(fn):
    """Con --debug imprime cada llamada de JavaScript a Python y su resultado."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if DEBUG:
            print(f"[API] {fn.__name__}{args[1:]}")
        result = fn(*args, **kwargs)
        if DEBUG:
            text = repr(result)
            print(f"[API]   -> {text[:300]}")
        return result

    return wrapper


class Api:
    """
    Metodos que JavaScript puede llamar
    mediante pywebview.api.<metodo>().
    """

    def __init__(self):
        # OJO: con guion bajo a proposito. pywebview expone a JavaScript todos los
        # atributos publicos del Api; si la ventana fuera publica (self.window) intentaba
        # recorrerla entera y fallaba con "maximum recursion depth exceeded".
        self._window = None

    def _open_path(self, path):
        """Abre un .imgmap, lo recuerda como ultimo archivo y avisa a JS."""
        STATE.open(path)
        if settings is not None:
            settings.set_last_file(path)
        return {"path": str(path)}

    @logged
    def choose_and_open(self):
        result = self._window.create_file_dialog(
            _open_dialog_type(),
            file_types=(
                f"Mapa de imagenes (*{EXTENSION})",
                "Todos los archivos (*.*)",
            ),
        )

        if not result:
            return None

        path = result[0]
        return self._open_path(path)

    @logged
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
                self._window.create_file_dialog(
                    _dialog_type("FOLDER"),
                )
            )
            if not folder:
                return None

            folder = Path(folder)

            output = _first(
                self._window.create_file_dialog(
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

            return self._open_path(output)

        except Exception as exc:
            ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
            return {"error": str(exc)}


    # ---------------- VELOCIDAD DE DESPLAZAMIENTO ----------------

    def _speed_info(self):
        return {
            "value": load_scroll_speed(),
            "default": DEFAULT_SCROLL_SPEED,
            "min": MIN_SCROLL_SPEED,
            "max": MAX_SCROLL_SPEED,
        }

    @logged
    def get_scroll_speed(self):
        return self._speed_info()

    @logged
    def set_scroll_speed(self, value):
        try:
            save_scroll_speed(_clamp_speed(value))
        except (TypeError, ValueError):
            return {"error": "La velocidad debe ser un numero"}
        return self._speed_info()

    @logged
    def reset_scroll_speed(self):
        save_scroll_speed(DEFAULT_SCROLL_SPEED)
        return self._speed_info()

    # ---------------- ZOOM ----------------

    @logged
    def get_zoom(self, path=None):
        """Zoom del archivo, o el ultimo del programa, o None."""
        if settings is None:
            return None
        try:
            return settings.get_zoom(path)
        except Exception:
            return None

    @logged
    def set_zoom(self, path, value):
        if settings is None:
            return None
        try:
            return settings.set_zoom(path, value)
        except Exception:
            return None

    # ---------------- CONTINUAR ----------------

    @logged
    def get_last_file(self):
        """{"path", "name"} del ultimo .imgmap abierto, o None si no hay (o ya no existe)."""
        if settings is None:
            return None
        path = settings.get_last_file()
        if not path:
            return None
        return {"path": str(path), "name": Path(path).name}

    @logged
    def open_last_file(self):
        if settings is None:
            return {"error": "No hay un archivo reciente"}
        path = settings.get_last_file()
        if path is None:
            return {"error": "No hay un archivo reciente"}
        try:
            return self._open_path(path)
        except Exception as exc:
            ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
            return {"error": str(exc)}

    # ---------------- BIBLIOTECA ----------------

    @logged
    def get_library(self):
        """
        {"path": carpeta o None, "files": [ {name, path, cover, coverUrl}, ... ]}
        """
        folder = settings.get_library_path() if settings else None
        if folder is None:
            return {"path": None, "files": []}
        return {"path": str(folder), "files": get_library_files(folder)}

    @logged
    def choose_library_folder(self):
        """Boton para elegir la carpeta de biblioteca. Devuelve lo mismo que get_library()."""
        try:
            folder = _first(
                self._window.create_file_dialog(_dialog_type("FOLDER"))
            )
            if not folder:
                return None
            if settings is None:
                return {"error": "Falta settings.py"}
            settings.set_library_path(folder)
            return self.get_library()
        except Exception as exc:
            ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
            return {"error": str(exc)}

    @logged
    def open_library_file(self, path):
        """Abre un .imgmap de la biblioteca (por su ruta completa)."""
        if not is_allowed_library_file(path):
            return {"error": "El archivo no pertenece a la biblioteca"}
        try:
            return self._open_path(path)
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        try:
            STATE.open(args[0])
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
        # Ventana normal (barra de titulo arriba con minimizar / maximizar /
        # cerrar, y Alt+F4 funciona), iniciada maximizada.
        maximized=True,
    )
    api._window = window

    webview.start(debug=DEBUG)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
        raise
