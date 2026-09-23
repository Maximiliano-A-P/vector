"""
reader.py
Lector del formato .imgmap.
Dependencias: tkinter (incluido en Python) + Pillow (pip install Pillow).

Zoom: se calcula como PORCENTAJE DEL ANCHO DE PANTALLA (no del ancho de la
ventana), así que el resultado es predecible sin importar el tamaño de la
ventana. Arranca en 50%. El re-render al cambiar el zoom se hace de a una
imagen por vez (vía after) para no congelar la interfaz con imágenes grandes.
"""
import io
import sys
import threading
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog

from PIL import Image, ImageTk

from mapformat import read_manifest, read_entry, total_image_count, EXTENSION

CARD_WIDTH = 160

ZOOM_MIN = 10
ZOOM_MAX = 150
ZOOM_STEP = 5
ZOOM_DEFAULT = 50


class ScrollableFrame(tk.Frame):
    """Frame con scroll vertical (canvas + scrollbar), rueda del mouse y touchpad."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        if event.delta == 0:
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def enable_wheel(self):
        """Convierte a esta vista en la única que responde a la rueda/touchpad.
        Se llama cada vez que esta vista pasa a estar visible, para que no
        quede 'pisada' por la vista anterior."""
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

    def viewport_width(self):
        return self.canvas.winfo_width()


class RootView(tk.Frame):
    def __init__(self, parent, manifest, cover_photo, on_open_branch):
        super().__init__(parent)
        self.on_open_branch = on_open_branch

        tk.Label(self, image=cover_photo).pack(pady=6)
        self._cover_ref = cover_photo

        tk.Label(self, text=manifest.get("title", ""), font=("Segoe UI", 14, "bold")).pack(pady=4)

        self.scroll = ScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)

        self.cols = 4
        self._card_refs = []

    def add_card(self, branch, cover_photo, index):
        row, col = divmod(index, self.cols)
        card = tk.Frame(self.scroll.inner, width=CARD_WIDTH, bd=1, relief="solid", cursor="hand2")
        card.grid(row=row, column=col, padx=6, pady=6)
        img_label = tk.Label(card, image=cover_photo)
        img_label.pack()
        name_label = tk.Label(card, text=branch["name"])
        name_label.pack()

        for widget in (card, img_label, name_label):
            widget.bind("<Button-1>", lambda e, bid=branch["id"]: self.on_open_branch(bid))

        self._card_refs.append(cover_photo)


class BranchView(tk.Frame):
    def __init__(self, parent, screen_width):
        super().__init__(parent)
        self.screen_width = screen_width

        top = tk.Frame(self)
        top.pack(fill="x")
        self.title_label = tk.Label(top, text="", font=("Segoe UI", 11, "bold"))
        self.title_label.pack(side="left", padx=8)

        tk.Button(top, text="-", width=3, command=self.zoom_out).pack(side="right", padx=(0, 6))
        self.zoom_entry = tk.Entry(top, width=5, justify="center")
        self.zoom_entry.pack(side="right")
        self.zoom_entry.bind("<Return>", self._on_zoom_entry)
        tk.Label(top, text="%").pack(side="right")
        tk.Button(top, text="+", width=3, command=self.zoom_in).pack(side="right", padx=(6, 2))

        self.scroll = ScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)

        self.image_labels = {}
        self.pil_images = {}
        self.photo_refs = {}
        self.zoom_percent = ZOOM_DEFAULT
        self._render_job = None

        self._update_zoom_entry()

    def _update_zoom_entry(self):
        self.zoom_entry.delete(0, tk.END)
        self.zoom_entry.insert(0, str(self.zoom_percent))

    def clear(self):
        if self._render_job:
            self.after_cancel(self._render_job)
            self._render_job = None
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        self.image_labels = {}
        self.pil_images = {}
        self.photo_refs = {}

    def set_branch(self, branch):
        self.clear()
        self.title_label.config(text=branch["name"])
        for arcname in branch["images"]:
            label = tk.Label(
                self.scroll.inner, text="Cargando...",
                bd=0, highlightthickness=0, padx=0, pady=0
            )
            label.pack(fill="x")
            self.image_labels[arcname] = label

    def set_image(self, arcname, pil_image):
        if arcname not in self.image_labels:
            return
        self.pil_images[arcname] = pil_image
        self._render_one(arcname)

    def _target_width(self):
        return max(100, int(self.screen_width * self.zoom_percent / 100))

    def _render_one(self, arcname):
        pil_image = self.pil_images.get(arcname)
        label = self.image_labels.get(arcname)
        if pil_image is None or label is None:
            return
        width = self._target_width()
        ratio = width / pil_image.width
        height = max(1, int(pil_image.height * ratio))
        resized = pil_image.resize((width, height), Image.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        label.config(image=photo, text="", bd=0, highlightthickness=0, padx=0, pady=0)
        self.photo_refs[arcname] = photo

    def _apply_zoom_progressively(self):
        """Re-renderiza una imagen por vez (no todas juntas) para no congelar la ventana."""
        pending = list(self.pil_images.keys())

        def step():
            if not pending:
                self._render_job = None
                return
            arcname = pending.pop(0)
            self._render_one(arcname)
            self._render_job = self.after(1, step)

        if self._render_job:
            self.after_cancel(self._render_job)
        step()

    def _set_zoom(self, value):
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        self.zoom_percent = value
        self._update_zoom_entry()
        self._apply_zoom_progressively()

    def zoom_in(self):
        self._set_zoom(self.zoom_percent + ZOOM_STEP)

    def zoom_out(self):
        self._set_zoom(self.zoom_percent - ZOOM_STEP)

    def _on_zoom_entry(self, event):
        try:
            value = int(self.zoom_entry.get())
        except ValueError:
            self._update_zoom_entry()
            return
        self._set_zoom(value)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lector de mapas de imágenes")
        self.geometry("1000x720")

        self.map_path = None
        self.manifest = None
        self.pil_cache = {}
        self.current_branch_index = None
        self.q = queue.Queue()
        self.loading_thread = None
        self.screen_width = self.winfo_screenwidth()

        top = tk.Frame(self)
        top.pack(fill="x")
        tk.Button(top, text=f"Abrir {EXTENSION}...", command=self.open_file_dialog).pack(side="left", padx=6, pady=4)

        self.container = tk.Frame(self)
        self.container.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")

        self.root_view = None
        self.branch_view = BranchView(self.container, self.screen_width)

        self.bind_all("<Escape>", lambda e: self._esc_key())
        self.bind_all("<Right>", lambda e: self._nav_key(1))
        self.bind_all("<Left>", lambda e: self._nav_key(-1))

    def _focus_is_entry(self):
        return isinstance(self.focus_get(), tk.Entry)

    def _esc_key(self):
        if self._focus_is_entry():
            return
        self.go_back()

    def _nav_key(self, direction):
        if self._focus_is_entry():
            return
        self.go_sibling(direction)

    def open_file_dialog(self):
        path = filedialog.askopenfilename(
            title="Abrir mapa de imágenes",
            filetypes=[("Mapa de imágenes", f"*{EXTENSION}")],
        )
        if path:
            self.load_map(Path(path))

    def _to_photo(self, pil_image, max_width):
        ratio = max_width / pil_image.width
        resized = pil_image.resize((max_width, int(pil_image.height * ratio)), Image.LANCZOS)
        return ImageTk.PhotoImage(resized)

    def load_map(self, path: Path):
        self.map_path = path
        self.manifest = read_manifest(path)
        self.pil_cache = {}

        root_cover_bytes = read_entry(path, self.manifest["cover"])
        root_cover_img = Image.open(io.BytesIO(root_cover_bytes))
        root_cover_img.load()
        root_cover_photo = self._to_photo(root_cover_img, 360)

        if self.root_view is not None:
            self.root_view.destroy()
        self.root_view = RootView(self.container, self.manifest, root_cover_photo, self.open_branch)

        for i, branch in enumerate(self.manifest["branches"]):
            cover_bytes = read_entry(path, branch["cover"])
            cover_img = Image.open(io.BytesIO(cover_bytes))
            cover_img.load()
            self.pil_cache[branch["cover"]] = cover_img
            cover_photo = self._to_photo(cover_img, CARD_WIDTH - 16)
            self.root_view.add_card(branch, cover_photo, i)

        self.branch_view.pack_forget()
        self.root_view.pack(fill="both", expand=True)
        self.root_view.scroll.enable_wheel()
        self.current_branch_index = None

        total = total_image_count(self.manifest)
        if total > 0:
            self.progress["maximum"] = total
            self.progress["value"] = 0
            self.progress.pack(fill="x", side="bottom")

        self.loading_thread = threading.Thread(target=self._preload_worker, args=(path, self.manifest), daemon=True)
        self.loading_thread.start()
        self.after(30, self._poll_queue)

    def _preload_worker(self, path, manifest):
        for branch in manifest["branches"]:
            for arcname in branch["images"]:
                data = read_entry(path, arcname)
                pil_image = Image.open(io.BytesIO(data))
                pil_image.load()
                self.q.put(("image", arcname, pil_image))
        self.q.put(("done", None, None))

    def _poll_queue(self):
        try:
            while True:
                kind, arcname, payload = self.q.get_nowait()
                if kind == "image":
                    self.pil_cache[arcname] = payload
                    if self.current_branch_index is not None:
                        branch = self.manifest["branches"][self.current_branch_index]
                        if arcname in branch["images"]:
                            self.branch_view.set_image(arcname, payload)
                    self.progress["value"] += 1
                elif kind == "done":
                    self.progress.pack_forget()
        except queue.Empty:
            pass
        if self.loading_thread and self.loading_thread.is_alive():
            self.after(30, self._poll_queue)

    def open_branch(self, branch_id):
        index = next(i for i, b in enumerate(self.manifest["branches"]) if b["id"] == branch_id)
        self.current_branch_index = index
        branch = self.manifest["branches"][index]

        self.branch_view.set_branch(branch)
        for arcname in branch["images"]:
            pil_image = self.pil_cache.get(arcname)
            if pil_image is not None:
                self.branch_view.set_image(arcname, pil_image)

        self.root_view.pack_forget()
        self.branch_view.pack(fill="both", expand=True)
        self.branch_view.scroll.enable_wheel()

    def go_back(self):
        if self.current_branch_index is None:
            return
        self.current_branch_index = None
        self.branch_view.pack_forget()
        self.root_view.pack(fill="both", expand=True)
        self.root_view.scroll.enable_wheel()

    def go_sibling(self, delta):
        if self.current_branch_index is None:
            return
        new_index = self.current_branch_index + delta
        if 0 <= new_index < len(self.manifest["branches"]):
            self.open_branch(self.manifest["branches"][new_index]["id"])


def main():
    app = App()
    if len(sys.argv) > 1:
        app.load_map(Path(sys.argv[1]))
    app.mainloop()


if __name__ == "__main__":
    main()