"""
mapformat.py
Lógica del formato de archivo .imgmap (mapa de imágenes).

Un .imgmap es un ZIP con una miniatura de la portada raíz (JPEG/PNG)
pegada AL PRINCIPIO del archivo. Windows usa esa imagen para mostrar la
miniatura en el Explorador, y Python / 7-Zip siguen abriendo el ZIP igual.

Dependencias: solo la librería estándar. Pillow es opcional (si está,
la miniatura se reduce a 512 px; si no, se usa la portada tal cual
cuando es .jpg/.jpeg/.png).

Formatos de imagen aceptados para portadas e imágenes: .jpg, .jpeg, .png, .webp

Para las imágenes dentro de cada rama, el orden se determina buscando el
ÚLTIMO número que aparece en el nombre del archivo. Esto permite nombres
como "1.jpg", "pagina_07.png" o "49 (12).jpg".
"""
import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

MANIFEST_NAME = "manifest.json"
FORMAT_VERSION = 1
EXTENSION = ".imgmap"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

THUMB_SIZE = 512


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


# ---------------------------------------------------------
# MINIATURA (imagen al principio del archivo)
# ---------------------------------------------------------

def _make_thumbnail(data: bytes, suffix: str):
    """
    Devuelve los bytes de una imagen (JPEG o PNG) para poner al inicio del
    .imgmap, o None si no se pudo generar.
    """
    try:
        from PIL import Image
    except ImportError:
        Image = None

    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.thumbnail((THUMB_SIZE, THUMB_SIZE))
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                out = io.BytesIO()
                im.save(out, "JPEG", quality=85)
                return out.getvalue()
        except Exception:
            pass

    # Sin Pillow: JPG y PNG se pueden usar tal cual.
    if suffix.lower() in (".jpg", ".jpeg", ".png"):
        return data

    return None


def _write_with_prefix(output_path: Path, prefix, zip_path: Path):
    """output = prefix (si hay) + contenido del ZIP, copiado por bloques."""
    with open(output_path, "wb") as out:
        if prefix:
            out.write(prefix)
        with open(zip_path, "rb") as src:
            shutil.copyfileobj(src, out, 1024 * 1024)


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

    # El ZIP se arma primero en un archivo temporal y después se le pega
    # la miniatura por delante.
    tmp_zip = output_path.with_name(output_path.name + ".tmp")

    try:
        branches = []
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
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

        thumb = _make_thumbnail(root_cover.read_bytes(), root_cover.suffix)
        _write_with_prefix(output_path, thumb, tmp_zip)

    finally:
        if tmp_zip.exists():
            tmp_zip.unlink()

    return output_path


def add_thumbnail(map_path: Path) -> bool:
    """
    Agrega la miniatura al inicio de un .imgmap ya existente.
    Devuelve True si lo modificó, False si no hacía falta o no se pudo.
    Cerrá VECTOR antes: Windows no deja reemplazar un archivo abierto.
    """
    map_path = Path(map_path)

    with open(map_path, "rb") as f:
        if f.read(2) != b"PK":
            return False  # ya empieza con una imagen

    manifest = read_manifest(map_path)
    cover = manifest["cover"]
    thumb = _make_thumbnail(read_entry(map_path, cover), Path(cover).suffix)
    if thumb is None:
        return False

    tmp = map_path.with_name(map_path.name + ".tmp")
    try:
        _write_with_prefix(tmp, thumb, map_path)
        os.replace(tmp, map_path)
    finally:
        if tmp.exists():
            tmp.unlink()

    return True


# ---------------------------------------------------------
# LECTURA
# ---------------------------------------------------------

def read_manifest(map_path: Path) -> dict:
    with zipfile.ZipFile(map_path, "r") as zf:
        with zf.open(MANIFEST_NAME) as f:
            return json.load(f)


def read_entry(map_path: Path, arcname: str) -> bytes:
    with zipfile.ZipFile(map_path, "r") as zf:
        return zf.read(arcname)


def total_image_count(manifest: dict) -> int:
    return sum(len(b["images"]) for b in manifest["branches"])


# Uso:  python mapformat.py "D:\Biblioteca"   (o uno o varios .imgmap)
# Agrega la miniatura a los archivos que todavía no la tienen.
if __name__ == "__main__":
    import sys

    files = []
    for arg in sys.argv[1:]:
        target = Path(arg)
        if target.is_dir():
            files.extend(sorted(target.glob(f"*{EXTENSION}")))
        else:
            files.append(target)

    for f in files:
        try:
            print(("listo    " if add_thumbnail(f) else "omitido  ") + str(f))
        except Exception as exc:
            print(f"ERROR    {f}: {exc}")