"""
reader_web.py

Backend de VECTOR.

Python se ocupa de:

- abrir archivos .imgmap;
- mantener abierto el archivo actual;
- servir manifest.json;
- servir imágenes;
- guardar el último archivo abierto;
- administrar la biblioteca;
- seleccionar la carpeta de biblioteca.

HTML/CSS/JavaScript se ocupa de la interfaz
y del renderizado.
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

from mapformat import (
    read_manifest,
    EXTENSION,
)

from settings import (
    get_last_file,
    set_last_file,
    get_library_path,
    set_library_path,
)

from library import (
    get_library_files,
    read_cover,
)


# =========================================================
# RUTAS
# =========================================================

BASE_DIR = Path(__file__).parent

WEB_DIR = BASE_DIR / "web"

ERROR_LOG = (
    Path.home()
    / "imgmap_reader_web_error.log"
)


# =========================================================
# MIME
# =========================================================

EXT_MIME = {

    ".jpg":
        "image/jpeg",

    ".jpeg":
        "image/jpeg",

    ".png":
        "image/png",

    ".webp":
        "image/webp",
}


# =========================================================
# ESTADO DEL MAPA ACTUAL
# =========================================================

class MapState:
    """
    Guarda el .imgmap actualmente abierto.

    Solo hay un mapa abierto a la vez.
    """

    def __init__(self):

        self.path = None

        self.manifest = None

        self.zf = None

        self.lock = threading.Lock()


    def open(self, path):

        path = Path(path).resolve()

        if not path.is_file():

            raise FileNotFoundError(
                f"No existe el archivo: {path}"
            )


        if (
            path.suffix.lower()
            != EXTENSION
        ):

            raise ValueError(
                f"El archivo no tiene extensión {EXTENSION}"
            )


        with self.lock:

            if self.zf:

                self.zf.close()

                self.zf = None


            self.path = path

            self.manifest = (
                read_manifest(path)
            )

            self.zf = zipfile.ZipFile(
                path,
                "r"
            )


        # Guardamos el último archivo
        # solamente después de abrirlo correctamente.

        set_last_file(path)


    def close(self):

        with self.lock:

            if self.zf:

                self.zf.close()

                self.zf = None

            self.path = None

            self.manifest = None


    def read(self, arcname):

        with self.lock:

            if self.zf is None:

                raise FileNotFoundError(
                    "No hay ningún archivo abierto."
                )

            return self.zf.read(
                arcname
            )


STATE = MapState()


# =========================================================
# SERVIDOR HTTP
# =========================================================

class Handler(
    http.server.BaseHTTPRequestHandler
):

    def log_message(
        self,
        fmt,
        *args
    ):
        """
        Evita llenar la consola con
        un mensaje por cada imagen.
        """

        pass


    def do_GET(self):

        try:

            parsed = urlparse(
                self.path
            )

            route = parsed.path


            # -----------------------------------------
            # INTERFAZ
            # -----------------------------------------

            if route in (
                "/",
                "/index.html"
            ):

                return self._serve_static(
                    "index.html",
                    "text/html; charset=utf-8"
                )


            if route == "/app.js":

                return self._serve_static(
                    "app.js",
                    "application/javascript; charset=utf-8"
                )


            if route == "/app.css":

                return self._serve_static(
                    "app.css",
                    "text/css; charset=utf-8"
                )


            # -----------------------------------------
            # MANIFEST
            # -----------------------------------------

            if route == "/manifest":

                return self._serve_manifest()


            # -----------------------------------------
            # IMÁGENES
            # -----------------------------------------

            if route.startswith("/cover/"):

                arcname = unquote(
                    route[len("/cover/"):]
                )

                return self._serve_library_cover(
                    arcname
                )

            if route.startswith("/img/"):

                arcname = unquote(
                    route[len("/img/"):]
                )

                return self._serve_image(
                    arcname
                )


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

    def _serve_library_cover(
        self,
        encoded_path
    ):

        try:

            decoded = unquote(
                encoded_path
            )

            separator = "|"

            if separator not in decoded:

                self.send_error(404)

                return


            file_path_text, cover_arcname = (
                decoded.split(
                    separator,
                    1
                )
            )


            file_path = Path(
                file_path_text
            ).resolve()


            library = get_library_path()


            if library is None:

                self.send_error(404)

                return


            try:

                file_path.relative_to(
                    library
                )

            except ValueError:

                self.send_error(403)

                return


            data = read_cover(
                file_path,
                cover_arcname
            )


            mime = EXT_MIME.get(
                Path(cover_arcname)
                .suffix
                .lower(),

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
                "public, max-age=3600"
            )

            self.end_headers()

            self.wfile.write(
                data
            )


        except Exception:

            self.send_error(404)

    def _serve_static(
        self,
        filename,
        content_type
    ):

        path = (
            WEB_DIR
            / filename
        )


        if not path.is_file():

            self.send_error(
                404,
                f"No existe {filename}"
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

        self.wfile.write(
            data
        )


    def _serve_manifest(self):

        if STATE.manifest is None:

            self.send_error(
                404,
                "No hay ningún archivo abierto"
            )

            return


        body = dict(
            STATE.manifest
        )


        body["_path"] = str(
            STATE.path
        )


        data = json.dumps(
            body,
            ensure_ascii=False
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

        self.wfile.write(
            data
        )


    def _serve_image(
        self,
        arcname
    ):

        try:

            data = STATE.read(
                arcname
            )

        except (
            KeyError,
            FileNotFoundError
        ):

            self.send_error(404)

            return


        mime = EXT_MIME.get(
            Path(arcname)
            .suffix
            .lower(),

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


        # Las imágenes no cambian dentro del .imgmap.
        # Permitimos que el WebView las mantenga
        # en caché.

        self.send_header(
            "Cache-Control",
            "public, max-age=31536000, immutable"
        )


        self.end_headers()

        self.wfile.write(
            data
        )


# =========================================================
# API PARA JAVASCRIPT
# =========================================================

class Api:
    """
    Métodos accesibles desde JavaScript mediante:

        window.pywebview.api.metodo(...)
    """

    def __init__(self):

        self.window = None


    # =====================================================
    # ABRIR ARCHIVO MANUALMENTE
    # =====================================================

    def choose_and_open(self):

        result = (
            self.window.create_file_dialog(
                webview.OPEN_DIALOG,

                file_types=(
                    f"Mapa de imágenes (*{EXTENSION})",
                    "Todos los archivos (*.*)",
                ),
            )
        )


        if not result:

            return None


        path = Path(
            result[0]
        )


        STATE.open(
            path
        )


        return {
            "path":
                str(path.resolve())
        }


    # =====================================================
    # ÚLTIMO ARCHIVO
    # =====================================================

    def get_last_file(self):

        path = get_last_file()


        if path is None:

            return None


        return {
            "path":
                str(path),

            "name":
                path.name,
        }


    # =====================================================
    # ABRIR EL ÚLTIMO ARCHIVO
    # =====================================================

    def open_last_file(self):

        path = get_last_file()


        if path is None:

            return None


        STATE.open(
            path
        )


        return {
            "path":
                str(path),

            "name":
                path.name,
        }


    # =====================================================
    # ELEGIR CARPETA DE BIBLIOTECA
    # =====================================================

    def choose_library_folder(self):

        result = (
            self.window.create_file_dialog(
                webview.FOLDER_DIALOG
            )
        )


        if not result:

            return None


        folder = Path(
            result[0]
        ).resolve()


        set_library_path(
            folder
        )


        files = get_library_files(
            folder
        )


        return {
            "path":
                str(folder),

            "files":
                files,
        }


    # =====================================================
    # OBTENER BIBLIOTECA
    # =====================================================

    def get_library(self):

        folder = (
            get_library_path()
        )


        if folder is None:

            return {
                "path":
                    None,

                "files":
                    [],
            }


        files = get_library_files(
            folder
        )


        return {
            "path":
                str(folder),

            "files":
                files,
        }


    # =====================================================
    # ABRIR DESDE LA BIBLIOTECA
    # =====================================================

    def open_library_file(
        self,
        path
    ):

        if not path:

            return None


        file_path = Path(
            path
        ).resolve()


        # ---------------------------------------------
        # Comprobamos que sea un .imgmap
        # ---------------------------------------------

        if (
            file_path.suffix.lower()
            != EXTENSION
        ):

            raise ValueError(
                "El archivo seleccionado no es un .imgmap."
            )


        # ---------------------------------------------
        # Comprobamos que pertenezca a la biblioteca
        # actualmente seleccionada.
        # ---------------------------------------------

        library = (
            get_library_path()
        )


        if library is None:

            raise ValueError(
                "No hay una biblioteca seleccionada."
            )


        try:

            file_path.relative_to(
                library
            )

        except ValueError:

            raise PermissionError(
                "El archivo no pertenece a la biblioteca seleccionada."
            )


        if not file_path.is_file():

            raise FileNotFoundError(
                f"No existe el archivo: {file_path}"
            )


        STATE.open(
            file_path
        )


        return {
            "path":
                str(file_path),

            "name":
                file_path.name,
        }


    # =====================================================
    # CREAR
    # =====================================================

    def create_new_map(self):

        # El creador se implementará posteriormente.

        return {
            "ok": False,
            "message": (
                "El creador todavía no está implementado."
            )
        }


# =========================================================
# SERVIDOR
# =========================================================

def start_server():

    httpd = (
        socketserver.ThreadingTCPServer(
            (
                "127.0.0.1",
                0
            ),
            Handler
        )
    )


    port = (
        httpd.server_address[1]
    )


    thread = threading.Thread(
        target=httpd.serve_forever,
        daemon=True
    )


    thread.start()


    return port


# =========================================================
# MAIN
# =========================================================

def main():

    # -----------------------------------------------------
    # Si se pasa un .imgmap como argumento:
    #
    #     python reader_web.py mapa.imgmap
    #
    # lo abrimos directamente.
    # -----------------------------------------------------

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


    port = start_server()


    api = Api()


    window = webview.create_window(

        "VECTOR",

        url=(
            f"http://127.0.0.1:{port}/"
        ),

        js_api=api,

        width=1400,

        height=900,

        min_size=(
            800,
            600
        ),
    )


    api.window = window


    webview.start()


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    try:

        main()

    except Exception:

        ERROR_LOG.write_text(
            traceback.format_exc(),
            encoding="utf-8"
        )

        raise