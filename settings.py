from pathlib import Path
import json
import os


APP_NAME = "VECTOR"

CONFIG_DIR = (
    Path.home()
    / "AppData"
    / "Local"
    / APP_NAME
)

CONFIG_FILE = CONFIG_DIR / "settings.json"


DEFAULT_SETTINGS = {
    "last_file": None,
    "library": None,
}


def _ensure_config_dir():
    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


def load_settings():
    _ensure_config_dir()

    if not CONFIG_FILE.exists():
        return dict(DEFAULT_SETTINGS)

    try:
        data = json.loads(
            CONFIG_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            return dict(DEFAULT_SETTINGS)

        result = dict(DEFAULT_SETTINGS)
        result.update(data)

        return result

    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    _ensure_config_dir()

    CONFIG_FILE.write_text(
        json.dumps(
            settings,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def get_last_file():
    settings = load_settings()

    path = settings.get("last_file")

    if not path:
        return None

    path = Path(path)

    if not path.is_file():
        return None

    return path


def set_last_file(path):
    settings = load_settings()

    settings["last_file"] = str(
        Path(path).resolve()
    )

    save_settings(settings)


def get_library_path():
    settings = load_settings()

    path = settings.get("library")

    if not path:
        return None

    path = Path(path)

    if not path.is_dir():
        return None

    return path


def set_library_path(path):
    settings = load_settings()

    if path is None:
        settings["library"] = None

    else:
        settings["library"] = str(
            Path(path).resolve()
        )

    save_settings(settings)

# ---------------- ZOOM ----------------
# "zoom"       -> ultimo zoom usado en el programa
# "file_zooms" -> zoom recordado por cada archivo (clave: ruta normalizada)

ZOOM_MIN = 10
ZOOM_MAX = 150


def _zoom_key(path):
    # normcase: en Windows ignora mayusculas y unifica / y \
    return os.path.normcase(str(Path(path).resolve()))


def _clamp_zoom(value):
    return max(ZOOM_MIN, min(ZOOM_MAX, int(round(float(value)))))


def get_zoom(path=None):
    """
    Zoom del archivo si tiene uno guardado; si no, el ultimo zoom del
    programa; si tampoco hay, None.
    """
    data = load_settings()

    if path:
        file_zooms = data.get("file_zooms")
        if isinstance(file_zooms, dict):
            value = file_zooms.get(_zoom_key(path))
            if value is not None:
                try:
                    return _clamp_zoom(value)
                except (TypeError, ValueError):
                    pass

    value = data.get("zoom")
    if value is None:
        return None

    try:
        return _clamp_zoom(value)
    except (TypeError, ValueError):
        return None


def set_zoom(path, value):
    """Guarda el zoom como ultimo del programa y, si hay path, tambien del archivo."""
    value = _clamp_zoom(value)

    data = load_settings()
    data["zoom"] = value

    if path:
        file_zooms = data.get("file_zooms")
        if not isinstance(file_zooms, dict):
            file_zooms = {}
        file_zooms[_zoom_key(path)] = value
        data["file_zooms"] = file_zooms

    save_settings(data)
    return value