"""Cover notebook content during layout, without a timed animation or delay."""
import tkinter as tk
from tkinter import ttk
from xinpilot_theme import COLORS


def install_page_presentation(root):
    def visit(widget):
        if isinstance(widget, ttk.Notebook) and not hasattr(widget, "_page_presentation"):
            widget._page_presentation = PagePresentation(widget)
        for child in widget.winfo_children():
            visit(child)
    visit(root)


class PagePresentation:
    def __init__(self, notebook):
        self.notebook = notebook
        self.cover = None
        self.job = None
        self.generation = 0
        self.tag = "PagePresentation" + str(notebook)
        notebook.bind_class(self.tag, "<<NotebookTabChanged>>", self.prepare)
        notebook.bindtags((self.tag,) + notebook.bindtags())
        notebook.bind("<Destroy>", self.close, add="+")

    def prepare(self, event=None):
        self.clear()
        selected = self.notebook.select()
        if not selected:
            return
        page = self.notebook.nametowidget(selected)
        self.cover = tk.Frame(page, background=COLORS["panel"], borderwidth=0)
        tk.Label(self.cover, text="Loading…", background=COLORS["panel"],
                 foreground=COLORS["muted"], font=("Segoe UI", 10)).place(relx=.5, rely=.5, anchor="center")
        self.cover.place(x=0, y=0, relwidth=1, relheight=1)
        self.cover.lift()
        generation = self.generation
        # Allow the selection callbacks and queued geometry work to finish first.
        self.job = self.notebook.after_idle(lambda: self.settle(generation))

    def settle(self, generation):
        if generation != self.generation:
            return
        self.job = self.notebook.after_idle(lambda: self.reveal(generation))

    def reveal(self, generation):
        if generation == self.generation:
            self.job = None
            self.clear()

    def clear(self):
        self.generation += 1
        if self.job:
            self.notebook.after_cancel(self.job)
            self.job = None
        if self.cover:
            self.cover.destroy()
            self.cover = None

    def close(self, event):
        if event.widget is self.notebook:
            self.clear()
            self.notebook.unbind_class(self.tag, "<<NotebookTabChanged>>")
