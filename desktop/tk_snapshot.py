"""Read-only Tk widget projection for the TypeScript desktop renderer."""

from __future__ import annotations

import base64
import hashlib
import tkinter as tk
from tkinter import font, ttk


class TkSnapshotProjector:
    """Project Tk widgets into the stable renderer snapshot contract.

    Asset and font caches belong to this projection, never to project state.
    """

    def __init__(self, controller):
        self.controller = controller
        self.app = controller.app
        self.assets = {}
        self.sent_assets = set()
        self._font_cache = {}

    def image(self, name):
        if not name:
            return None
        try:
            names = self.app.tk.splitlist(name)
            name = str(names[0]) if names else str(name)
            raw = self.app.tk.call(name, "data", "-format", "png")
            if isinstance(raw, str):
                raw = raw.encode("latin1")
            key = hashlib.sha256(raw).hexdigest()
            if key not in self.assets:
                self.assets[key] = "data:image/png;base64," + base64.b64encode(raw).decode()
            return key
        except (tk.TclError, UnicodeError):
            return None

    def font(self, value):
        value = str(value or "TkDefaultFont")
        if value not in self._font_cache:
            try:
                f = font.Font(root=self.app, font=value)
                actual = f.actual()
                actual["pixels"] = (
                    abs(actual["size"])
                    if actual["size"] < 0
                    else round(actual["size"] * float(self.app.tk.call("tk", "scaling")))
                )
                self._font_cache[value] = actual
            except tk.TclError:
                self._font_cache[value] = {}
        return self._font_cache[value]

    def style(self, w):
        def get(key, default=""):
            try:
                return w.cget(key)
            except tk.TclError:
                return default

        name = get("style") or w.winfo_class()
        style = ttk.Style(self.app)
        state = w.state() if hasattr(w, "state") and isinstance(w, ttk.Widget) else ()

        def lookup(key, default=""):
            return get(key) or style.lookup(name, key, state=state, default=default)

        def color(value):
            try:
                return (
                    "#" + "".join((f"{c // 257:02x}" for c in w.winfo_rgb(value))) if value else ""
                )
            except tk.TclError:
                return str(value)

        return {
            "foreground": color(lookup("foreground", "#253e50")),
            "background": color(lookup("background", "")),
            "relief": str(get("relief")),
            "font": self.font(lookup("font", "TkDefaultFont")),
            "anchor": str(get("anchor", "w")),
            "justify": str(get("justify", "left")),
            "wrap": str(get("wraplength", "0")),
        }

    def serialize(self, w):
        kind = w.winfo_class()
        data = {
            "id": w._w,
            "kind": kind,
            "x": w.winfo_x(),
            "y": w.winfo_y(),
            "width": w.winfo_width(),
            "height": w.winfo_height(),
            "style": self.style(w),
            "children": [],
        }

        def get(key, default=""):
            try:
                return w.cget(key)
            except tk.TclError:
                return default

        data["text"] = str(get("text"))
        if isinstance(w, (tk.LabelFrame, ttk.LabelFrame)):
            data["labelwidget"] = str(get("labelwidget"))
        data["compound"] = str(get("compound", "none"))
        data["emphasized"] = str(get("style")) == "RowAction.TButton" and str(get("text")) == "Map"
        tooltip = getattr(w, "_xinpilot_tooltip", None)
        if tooltip:
            data["tooltip"] = tooltip.text
        state = str(get("state", "normal"))
        data["disabled"] = state == "disabled" or (
            isinstance(w, ttk.Widget) and w.instate(["disabled"])
        )
        data["readonly"] = state == "readonly"
        if isinstance(w, (tk.Entry, ttk.Entry, tk.Spinbox)):
            data["value"] = w.get()
            data["show"] = str(get("show"))
        if isinstance(w, ttk.Combobox):
            data["values"] = list(w.cget("values"))
        if isinstance(w, (ttk.Checkbutton, ttk.Radiobutton)):
            data["selected"] = w.instate(["selected"])
        elif isinstance(w, (tk.Checkbutton, tk.Radiobutton)):
            try:
                data["selected"] = str(w.getvar(get("variable"))) == str(
                    get("onvalue", get("value"))
                )
            except tk.TclError:
                data["selected"] = False
        if isinstance(w, tk.Text):
            data["value"] = w.get("1.0", "end-1c")
            data["wrap"] = str(get("wrap"))
        if isinstance(w, tk.Listbox):
            data["values"] = list(w.get(0, "end"))
            data["selected"] = list(w.curselection())
            data["multiple"] = str(w.cget("selectmode")) in ("multiple", "extended")
            data["yview"] = list(w.yview())
            data["xview"] = list(w.xview())
        if isinstance(w, ttk.Notebook):
            data["tabs"] = [
                {
                    "id": str(t),
                    "text": str(w.tab(t, "text")),
                    "image": self.image(w.tab(t, "image")),
                    "state": str(w.tab(t, "state")),
                }
                for t in w.tabs()
            ]
            for tab in data["tabs"]:
                tab["label"] = tab["text"] or next(
                    (
                        label
                        for label, frame in getattr(self.app, "synthesis_inline_tabs", {}).items()
                        if str(frame) == tab["id"]
                    ),
                    "",
                )
            data["selected"] = str(w.select())
        if isinstance(w, ttk.Treeview):
            columns = list(w.cget("columns"))
            display = w.cget("displaycolumns")
            if display and tuple(display) != ("#all",):
                columns = [columns[int(c)] if str(c).isdigit() else str(c) for c in display]
            if "tree" in w.cget("show"):
                columns = ["#0"] + columns
            data["columns"] = [
                {
                    "id": c,
                    "text": str(w.heading(c, "text")),
                    "width": int(w.column(c, "width")),
                    "anchor": str(w.column(c, "anchor")),
                }
                for c in columns
            ]
            data["selected"] = list(w.selection())
            data["multiple"] = str(w.cget("selectmode")) == "extended"
            data["rowheight"] = int(
                ttk.Style(self.app).lookup(get("style") or "Treeview", "rowheight") or 25
            )
            data["yview"] = list(w.yview())
            data["xview"] = list(w.xview())
            data["rows"] = []

            def rows(parent="", depth=0):
                for item in w.get_children(parent):
                    row = w.item(item)
                    values = dict(zip(w.cget("columns"), row["values"]))
                    cells = [
                        str(row["text"]) if c == "#0" else str(values.get(c, "")) for c in columns
                    ]
                    rowstyle = {}
                    for tag in row["tags"]:
                        for k, v in w.tag_configure(tag).items():
                            if v:
                                rowstyle[k] = str(v)
                    data["rows"].append(
                        {
                            "id": str(item),
                            "values": cells,
                            "depth": depth,
                            "open": bool(row["open"]),
                            "branch": bool(w.get_children(item)),
                            "style": rowstyle,
                            "image": self.image(row["image"]),
                        }
                    )
                    if row["open"]:
                        rows(item, depth + 1)

            rows()
        if isinstance(w, tk.Canvas):
            data["items"] = []
            data["origin"] = [w.canvasx(0), w.canvasy(0)]
            for item in w.find_all():
                typ = w.type(item)
                if w.itemcget(item, "state") == "hidden" or typ == "window":
                    continue
                props = {k: str(v[-1]) for k, v in w.itemconfigure(item).items()}
                if typ == "image":
                    name = props.get("image")
                    props["image"] = self.image(name)
                    try:
                        props["image_width"] = int(w.tk.call("image", "width", name))
                        props["image_height"] = int(w.tk.call("image", "height", name))
                    except tk.TclError:
                        pass
                if typ == "text":
                    props["font"] = self.font(props.get("font"))
                data["items"].append({"type": typ, "coords": list(w.coords(item)), "props": props})
            data["xview"] = list(w.xview())
            data["yview"] = list(w.yview())
        if isinstance(w, (tk.Scrollbar, ttk.Scrollbar)):
            data["orient"] = str(get("orient"))
            data["range"] = list(w.get())
        if isinstance(w, ttk.Progressbar):
            data["value"] = float(get("value", 0))
            data["maximum"] = float(get("maximum", 100))
            data["mode"] = str(get("mode"))
        if isinstance(w, (tk.Scale, ttk.Scale)):
            data["value"] = float(w.get())
            data["from"] = float(get("from", 0))
            data["to"] = float(get("to", 100))
            data["orient"] = str(get("orient"))
        if isinstance(w, (tk.PanedWindow, ttk.Panedwindow)):
            data["panes"] = list(map(str, w.panes()))
            data["orient"] = str(get("orient"))
        data["image"] = self.image(get("image"))
        if isinstance(w, (tk.Spinbox, ttk.Spinbox)):
            data.update(minimum=get("from"), maximum=get("to"), increment=get("increment", 1))
        for child in w.winfo_children():
            if isinstance(child, (tk.Toplevel, tk.Menu)):
                continue
            if child.winfo_ismapped():
                data["children"].append(self.serialize(child))
        return data

    def snapshot(self):
        windows = []

        def scan(w):
            if isinstance(w, (tk.Tk, tk.Toplevel)) and w.winfo_viewable():
                if w is not self.app:
                    limit_w, limit_h = (
                        max(300, self.controller.viewport[0] - 40),
                        max(250, self.controller.viewport[1] - 65),
                    )
                    if w.winfo_width() > limit_w or w.winfo_height() > limit_h:
                        w.geometry(
                            f"{min(w.winfo_width(), limit_w)}x{min(w.winfo_height(), limit_h)}"
                        )
                        self.app.update_idletasks()
                item = self.serialize(w)
                item["title"] = w.title()
                item["modal"] = False
                grab = self.app.grab_current()
                item["modal"] = bool(grab and grab.winfo_toplevel() == w)
                children = w.winfo_children()
                item["tooltip"] = bool(
                    w is not self.app
                    and (not item["modal"])
                    and (len(children) == 1)
                    and isinstance(children[0], tk.Label)
                    and w.attributes("-topmost")
                )
                windows.append(item)
            for child in w.winfo_children():
                if isinstance(child, tk.Menu):
                    continue
                scan(child)

        scan(self.app)
        menu = None
        if self.controller.menu:
            widget = self.app.nametowidget(self.controller.menu["widget"])
            entries = []
            for i in range(widget.index("end") + 1 if widget.index("end") is not None else 0):
                kind = widget.type(i)
                if kind == "tearoff":
                    continue
                entry = {"index": i, "kind": kind}
                if kind != "separator":
                    entry.update(
                        text=widget.entrycget(i, "label"),
                        disabled=widget.entrycget(i, "state") == "disabled",
                    )
                entries.append(entry)
            menu = {**self.controller.menu, "entries": entries}
        assets = {k: v for k, v in self.assets.items() if k not in self.sent_assets}
        self.sent_assets.update(assets)
        errors = self.controller.errors[:]
        self.controller.errors.clear()
        return {
            "windows": windows,
            "assets": assets,
            "menu": menu,
            "dialog": self.controller.dialog,
            "errors": errors,
        }
