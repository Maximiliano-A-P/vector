"""
packer_gui.py
Empaquetador: elegís una carpeta (con portada.jpg y subcarpetas numeradas)
y genera un archivo .imgmap. Sin dependencias externas (usa tkinter).
"""
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from mapformat import build_from_folder, EXTENSION


class PackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Crear archivo de mapa de imágenes")
        self.geometry("420x180")
        self.folder = None

        self.folder_label = tk.Label(
            self, text="No se seleccionó ninguna carpeta.",
            wraplength=380, justify="left"
        )
        self.folder_label.pack(pady=8, padx=10, anchor="w")

        tk.Button(self, text="Elegir carpeta a convertir...", command=self.choose_folder).pack(pady=4)

        self.title_entry = tk.Entry(self)
        self.title_entry.pack(fill="x", padx=10, pady=6)
        self.title_entry.insert(0, "Título (opcional)")
        self.title_entry.config(fg="grey")
        self.title_entry.bind("<FocusIn>", self._clear_placeholder)

        tk.Button(self, text="Guardar como...", command=self.build).pack(pady=8)

    def _clear_placeholder(self, event):
        if self.title_entry.get() == "Título (opcional)":
            self.title_entry.delete(0, tk.END)
            self.title_entry.config(fg="black")

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Elegir carpeta raíz")
        if folder:
            self.folder = Path(folder)
            self.folder_label.config(text=f"Carpeta seleccionada:\n{folder}")

    def build(self):
        if not self.folder:
            messagebox.showwarning("Falta carpeta", "Primero elegí una carpeta de origen.")
            return

        default_name = self.folder.name + EXTENSION
        output_path = filedialog.asksaveasfilename(
            title="Guardar como",
            initialfile=default_name,
            defaultextension=EXTENSION,
            filetypes=[("Mapa de imágenes", f"*{EXTENSION}")],
        )
        if not output_path:
            return

        title_val = self.title_entry.get().strip()
        if title_val == "Título (opcional)":
            title_val = ""

        try:
            build_from_folder(self.folder, Path(output_path), title=title_val or None)
        except Exception as e:
            messagebox.showerror("Error al generar el archivo", str(e))
            return

        messagebox.showinfo("Listo", f"Archivo generado en:\n{output_path}")


if __name__ == "__main__":
    PackerApp().mainloop()