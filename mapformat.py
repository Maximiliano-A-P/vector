"""
mapformat.py
Lógica del formato de archivo .imgmap (mapa de imágenes).
Solo depende de la librería estándar de Python.

Formatos de imagen aceptados para portadas e imágenes: .jpg, .jpeg, .png, .webp

Para las imágenes dentro de cada rama, el orden se determina buscando el
ÚLTIMO número que aparece en el nombre del archivo. Esto permite nombres
como "1.jpg", "pagina_07.png" o "49 (12).jpg".
"""
import json
import re
import zipfile
from pathlib import Path

MANIFEST_NAME = "manifest.json"
FORMAT_VERSION = 1
EXTENSION = ".imgmap"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _find_cover(dir_path: Path):
    for p in sorted(dir_path.iterdir()):
        if p.is_file() and p.stem.lower() == "portada" and p.suffix.lower() in IMAGE_EXTENSIONS:
            return p
    return None


def _extract_number(name: str):
    matches = re.findall(r"\d+", name)
    if not matches:
        return None
    return int(matches[-1])


def _list_branch_images(dir_path: Path, cover_path: Path):
    candidates = []
    cover_resolved = cover_path.resolve()
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if p.resolve() == cover_resolved:
            continue
        if p.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        candidates.append((_extract_number(p.stem), p))

    sin_numero = [p.name for num, p in candidates if num is None]
    if sin_numero:
        raise ValueError(
            "No se pudo determinar el número de orden de: " + ", ".join(sorted(sin_numero))
        )

    candidates.sort(key=lambda t: t[0])
    return [p for _, p in candidates]


def build_from_folder(folder_path: Path, output_path: Path, title: str = None) -> Path:
    folder_path = Path(folder_path)
    output_path = Path(output_path)

    root_cover = _find_cover(folder_path)
    if root_cover is None:
        raise FileNotFoundError(
            "Falta la portada en la carpeta raíz "
            "(portada.jpg, portada.jpeg, portada.png o portada.webp)"
        )

    branch_dirs = [p for p in folder_path.iterdir() if p.is_dir() and p.name.isdigit()]
    if not branch_dirs:
        raise FileNotFoundError("No se encontraron carpetas numeradas (ramas) dentro de la carpeta raíz")
    branch_dirs = sorted(branch_dirs, key=lambda p: int(p.name))

    branches = []
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(root_cover, root_cover.name)

        for bdir in branch_dirs:
            bnum = bdir.name
            bcover = _find_cover(bdir)
            if bcover is None:
                raise FileNotFoundError(
                    f"Falta la portada en la rama {bnum} "
                    "(portada.jpg, portada.jpeg, portada.png o portada.webp)"
                )
            zf.write(bcover, f"{bnum}/{bcover.name}")

            images = _list_branch_images(bdir, bcover)
            image_arcnames = []
            for img in images:
                arcname = f"{bnum}/{img.name}"
                zf.write(img, arcname)
                image_arcnames.append(arcname)

            branches.append({
                "id": int(bnum),
                "name": bnum,
                "cover": f"{bnum}/{bcover.name}",
                "images": image_arcnames,
            })

        manifest = {
            "format_version": FORMAT_VERSION,
            "title": title or folder_path.name,
            "cover": root_cover.name,
            "branches": branches,
        }
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))

    return output_path


def read_manifest(map_path: Path) -> dict:
    with zipfile.ZipFile(map_path, "r") as zf:
        with zf.open(MANIFEST_NAME) as f:
            return json.load(f)


def read_entry(map_path: Path, arcname: str) -> bytes:
    with zipfile.ZipFile(map_path, "r") as zf:
        return zf.read(arcname)


def total_image_count(manifest: dict) -> int:
    return sum(len(b["images"]) for b in manifest["branches"])