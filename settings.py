from pathlib import Path
import json


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