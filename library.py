from pathlib import Path
import zipfile

from mapformat import (
    read_manifest,
    EXTENSION,
)


def list_imgmaps(folder):
    """
    Devuelve todos los .imgmap directamente contenidos
    en la carpeta indicada.

    No modifica ningún archivo.
    """

    folder = Path(folder)

    if not folder.is_dir():
        return []

    files = [
        path
        for path in folder.iterdir()
        if (
            path.is_file()
            and path.suffix.lower() == EXTENSION
        )
    ]

    files.sort(
        key=lambda path: path.name.lower()
    )

    result = []

    for path in files:

        try:
            manifest = read_manifest(path)

            cover = manifest.get("cover")

            result.append({
                "name": path.name,
                "path": str(path.resolve()),
                "cover": cover,
                "coverUrl": (
                    "/library-cover/"
                    + str(path.resolve()).replace("\\", "/")
                    + "|"
                    + str(cover)
                ),
            })

        except Exception as error:

            # Un .imgmap defectuoso no impide que
            # aparezcan los demás archivos.

            result.append({
                "name": path.name,
                "path": str(path.resolve()),
                "cover": None,
                "error": str(error),
            })

    return result


def read_cover(path, cover_arcname):
    """
    Lee la portada raíz del .imgmap.

    Devuelve bytes.
    """

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"No existe el archivo: {path}"
        )

    if not cover_arcname:
        raise FileNotFoundError(
            "El manifest no contiene portada."
        )

    with zipfile.ZipFile(
        path,
        "r"
    ) as zf:

        return zf.read(
            cover_arcname
        )


def get_library_files(folder):
    """
    Obtiene los archivos que aparecerán
    en la biblioteca.
    """

    return list_imgmaps(folder)