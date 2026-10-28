"""Translate the allowlisted renderer operations into established Tk callbacks.

The application continues to own validation and scientific state. This adapter
only applies widget operations and reproduces existing pointer/key bindings.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

from desktop.protocol import POINTER_SEQUENCES


def dispatch_event(controller, request):
    action = request["action"]
    if "rootx" in request:
        controller.pointer = (int(request["rootx"]), int(request.get("rooty", 0)))
    if action == "answer":
        item = controller.pending.get(request["id"])
        if (
            item
            and (not item.get("answered"))
            and controller.dialog
            and (controller.dialog["id"] == request["id"])
        ):
            item["answered"] = True
            item["value"] = request.get("value")
            item["variable"].set(True)
        return
    if action == "resize":
        controller.viewport = (int(request["width"]), int(request["height"]))
        controller.app.geometry(
            f"{max(850, int(request['width']))}x{max(600, int(request['height']))}-32000-32000"
        )
        return
    if action == "dismiss_menu":
        controller.menu = None
        return
    try:
        widget = controller.app.nametowidget(request["id"])
    except KeyError:
        return
    if action == "close":
        command = widget.protocol("WM_DELETE_WINDOW")
        if command:
            widget.tk.call(command)
        elif widget is not controller.app:
            widget.destroy()
        return {"closed": controller.stopped}
    if action == "window_size" and isinstance(widget, tk.Toplevel):
        widget.geometry(f"{max(300, int(request['width']))}x{max(250, int(request['height']))}")
        return
    if action == "column_size" and isinstance(widget, ttk.Treeview):
        widget.column(request["column"], width=max(40, int(request["width"])), stretch=False)
        return
    if isinstance(widget, ttk.Widget) and widget.instate(["disabled"]):
        return
    if action == "invoke" and isinstance(
        widget,
        (tk.Button, ttk.Button, tk.Checkbutton, ttk.Checkbutton, tk.Radiobutton, ttk.Radiobutton),
    ):
        widget.invoke()
    elif action == "value" and isinstance(
        widget, (tk.Entry, ttk.Entry, tk.Spinbox, tk.Text, tk.Scale, ttk.Scale)
    ):
        value = str(request.get("value", ""))
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        elif isinstance(widget, (tk.Scale, ttk.Scale)):
            widget.set(float(value))
        else:
            variable = widget.cget("textvariable")
            if variable:
                widget.setvar(variable, value)
            else:
                widget.delete(0, "end")
                widget.insert(0, value)
        if isinstance(widget, ttk.Combobox):
            if request.get("selection", True):
                widget.event_generate("<<ComboboxSelected>>")
            else:
                controller.event({"action": "pointer", "id": widget._w, "sequence": "<KeyRelease>"})
        else:
            controller.event({"action": "pointer", "id": widget._w, "sequence": "<KeyRelease>"})
    elif action == "tab" and isinstance(widget, ttk.Notebook):
        target = widget.index(request["tab"])
        positions = []
        for y in (10, 25, 40, 5):
            for x in range(0, widget.winfo_width(), 2):
                try:
                    if widget.index(f"@{x},{y}") == target:
                        positions.append(x)
                except tk.TclError:
                    pass
            if positions:
                break
        if positions:
            x = round(
                min(positions) + (max(positions) - min(positions)) * float(request.get("rx", 0.5))
            )
            height = min(
                (c.winfo_y() for c in widget.winfo_children() if c.winfo_ismapped()), default=40
            )
            y = max(3, round(height * float(request.get("ry", 0.5))))
            if widget is controller.app.nb:
                if (
                    controller.app._on_main_notebook_button_press(
                        SimpleNamespace(x=x, y=y, widget=widget)
                    )
                    == "break"
                ):
                    return
            widget.select(request["tab"])
        else:
            widget.select(request["tab"])
    elif action == "selection" and isinstance(widget, ttk.Treeview):
        ids = request.get("items", [])
        if any((not widget.exists(i) for i in ids)):
            return
        widget.selection_set(ids)
        if ids:
            widget.focus(ids[-1])
        widget.event_generate("<<TreeviewSelect>>")
    elif action == "selection" and isinstance(widget, tk.Listbox):
        widget.selection_clear(0, "end")
        for index in request.get("items", []):
            widget.selection_set(int(index))
        widget.event_generate("<<ListboxSelect>>")
    elif action == "expand" and isinstance(widget, ttk.Treeview):
        widget.item(request["item"], open=bool(request["open"]))
    elif action == "heading" and isinstance(widget, ttk.Treeview):
        command = widget.heading(request["column"], "command")
        if command:
            widget.tk.call(command)
    elif action == "post" and isinstance(widget, ttk.Combobox):
        command = widget.cget("postcommand")
        if command:
            widget.tk.call(command)
    elif action == "sash" and isinstance(widget, ttk.Panedwindow):
        widget.sashpos(int(request["index"]), int(request["position"]))
        widget.event_generate("<<PaneResized>>")
    elif action == "menu":
        if isinstance(widget, (ttk.Menubutton, tk.Menubutton)):
            controller.menu = {
                "widget": str(widget.cget("menu")),
                "x": request.get("x", 0),
                "y": request.get("y", 0),
            }
        elif isinstance(widget, tk.Menu):
            index = int(request["index"])
            controller.menu = None
            if widget.type(index) == "cascade":
                controller.menu = {
                    "widget": str(widget.entrycget(index, "menu")),
                    "x": request.get("x", 0),
                    "y": request.get("y", 0),
                }
            else:
                widget.invoke(index)
    elif action == "scroll":
        amount = max(0, min(1, float(request["position"])))
        axis = request.get("axis", "y")
        if isinstance(widget, (tk.Scrollbar, ttk.Scrollbar)):
            command = widget.cget("command")
            if command:
                widget.tk.call(*widget.tk.splitlist(command), "moveto", amount)
        elif isinstance(widget, (tk.Canvas, tk.Text, tk.Listbox, ttk.Treeview)):
            (widget.xview_moveto if axis == "x" else widget.yview_moveto)(amount)
    elif action == "pointer":
        _dispatch_pointer(controller, widget, request)


def _dispatch_pointer(controller, widget, request):
    sequence = request.get("sequence")
    if sequence not in POINTER_SEQUENCES:
        raise ValueError("Unsupported event.")
    kwargs = {
        "x": int(request.get("x", 0)),
        "y": int(request.get("y", 0)),
        "state": int(request.get("state", 0)),
    }
    if sequence.startswith(("<Button", "<Double", "<Motion", "<B1", "<Enter", "<Leave")):
        kwargs.update(
            rootx=widget.winfo_rootx() + kwargs["x"], rooty=widget.winfo_rooty() + kwargs["y"]
        )
    if sequence == "<MouseWheel>":
        kwargs["delta"] = int(request.get("delta", 0))
    if (
        isinstance(widget, ttk.Treeview)
        and request.get("item")
        and (sequence in ("<Button-3>", "<Double-Button-1>"))
    ):
        widget.see(request["item"])
        controller.app.update_idletasks()
        bbox = widget.bbox(request["item"])
        if bbox:
            kwargs["y"] = bbox[1] + bbox[3] // 2
    if sequence in (
        "<Double-Button-1>",
        "<Return>",
        "<Delete>",
        "<Escape>",
        "<Control-c>",
        "<Control-v>",
        "<KeyRelease>",
        "<FocusIn>",
        "<FocusOut>",
    ) or isinstance(widget, (tk.Label, ttk.Label)):
        script = widget.bind(sequence)
        if sequence in ("<Return>", "<Escape>") and widget.winfo_toplevel() is not widget:
            script += "\n" + widget.winfo_toplevel().bind(sequence)
        if script:
            substitutions = {k: "??" for k in tk.Misc._subst_format}
            substitutions.update(
                {
                    "%#": 0,
                    "%b": 1,
                    "%f": 0,
                    "%h": widget.winfo_height(),
                    "%k": 0,
                    "%s": kwargs["state"],
                    "%t": 0,
                    "%w": widget.winfo_width(),
                    "%x": kwargs["x"],
                    "%y": kwargs["y"],
                    "%A": "",
                    "%E": 0,
                    "%K": sequence.strip("<>"),
                    "%N": 0,
                    "%W": widget._w,
                    "%T": 4,
                    "%X": request.get("rootx", 0),
                    "%Y": request.get("rooty", 0),
                    "%D": 0,
                }
            )
            substitutions.update(
                {
                    "%X": kwargs.get("rootx", 0),
                    "%Y": kwargs.get("rooty", 0),
                    "%T": 7
                    if sequence == "<Enter>"
                    else 8
                    if sequence == "<Leave>"
                    else 6
                    if "Motion" in sequence
                    else 5
                    if "Release" in sequence
                    else 4,
                }
            )
            script = re.sub(
                "%[#bfhkst wxyAEKNWTXYD]".replace(" ", ""),
                lambda m: tk._stringify(substitutions.get(m[0], "??")),
                script,
            )
            try:
                widget.tk.eval(script)
            except tk.TclError as error:
                if "break" not in str(error):
                    raise
    else:
        widget.event_generate(sequence, **kwargs)
