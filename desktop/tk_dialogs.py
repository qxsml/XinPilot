"""Adapt Tk prompts and menus to renderer/native dialogs for one controller."""

from __future__ import annotations

import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, simpledialog
from typing import Any

from desktop.protocol import FILE_DIALOG_KINDS

MESSAGE_DIALOG_KINDS = (
    "showinfo",
    "showwarning",
    "showerror",
    "askyesno",
    "askyesnocancel",
    "askokcancel",
    "askretrycancel",
    "askquestion",
)
INPUT_DIALOG_KINDS = ("askstring", "askinteger", "askfloat")
FILE_OPTIONS = frozenset(
    {
        "title",
        "initialdir",
        "initialfile",
        "filetypes",
        "defaultextension",
        "mustexist",
    }
)
INPUT_OPTIONS = frozenset({"initialvalue", "minvalue", "maxvalue", "show"})


def prompt(controller, data: dict[str, Any]) -> Any:
    """Wait in Tk's nested loop while IPC continues serving snapshots/answers.

    Each invocation has a unique token. Restoring the previous dialog supports
    prompts raised inside callbacks without allowing stale answers to escape.
    """
    variable = tk.BooleanVar(master=controller.app, value=False)
    token = uuid.uuid4().hex
    previous = controller.dialog
    controller.pending[token] = {
        "variable": variable,
        "value": None,
        "answered": False,
    }
    controller.dialog = {"id": token, **data}
    try:
        controller.app.wait_variable(variable)
        return controller.pending[token]["value"]
    finally:
        controller.pending.pop(token, None)
        controller.dialog = previous


class TkDialogAdapter:
    """Install process-local dialog hooks and restore them at shutdown.

    Tk's functions are global, so one controller owns the hooks for the lifetime
    of its process. Keeping restoration here avoids leaking hooks into tests or
    other embedded consumers when a controller is constructed and destroyed.
    """

    def __init__(self, controller) -> None:
        self.controller = controller
        self._originals: list[tuple[Any, str, Any]] = []

    def _replace(self, owner: Any, name: str, replacement: Any) -> None:
        self._originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)

    def install(self) -> None:
        original_root = tk.Tk.__init__
        original_top = tk.Toplevel.__init__

        def hidden_root(widget, *args, **kwargs):
            original_root(widget, *args, **kwargs)
            widget.withdraw()
            widget.attributes("-alpha", 0)

        def hidden_top(widget, *args, **kwargs):
            original_top(widget, *args, **kwargs)
            widget.attributes("-alpha", 0)
            widget.overrideredirect(True)

        self._replace(tk.Tk, "__init__", hidden_root)
        self._replace(tk.Toplevel, "__init__", hidden_top)
        for kind in MESSAGE_DIALOG_KINDS:
            self._replace(messagebox, kind, self._message_handler(kind))
        for kind in FILE_DIALOG_KINDS:
            self._replace(filedialog, kind, self._file_handler(kind))
        for kind in INPUT_DIALOG_KINDS:
            self._replace(simpledialog, kind, self._input_handler(kind))

        def post(menu, x, y, *args):
            self.controller.menu = {
                "widget": str(menu),
                "x": self.controller.pointer[0],
                "y": self.controller.pointer[1],
            }

        self._replace(tk.Menu, "post", post)
        self._replace(tk.Menu, "tk_popup", post)
        import xinpilot_tooltips

        self._replace(xinpilot_tooltips.Tooltip, "show", lambda tooltip: None)

    def restore(self) -> None:
        while self._originals:
            owner, name, original = self._originals.pop()
            setattr(owner, name, original)

    def _message_handler(self, kind):
        def show(title=None, message=None, **kwargs):
            return self.controller.prompt(
                {
                    "kind": kind,
                    "title": title or "",
                    "message": message or "",
                    "initial": kwargs.get("default"),
                }
            )

        return show

    def _file_handler(self, kind):
        def choose(**kwargs):
            options = {key: value for key, value in kwargs.items() if key in FILE_OPTIONS}
            value = self.controller.prompt({"kind": kind, **options})
            return tuple(value or []) if kind == "askopenfilenames" else value or ""

        return choose

    def _input_handler(self, kind):
        def ask(title, prompt, **kwargs):
            options = {key: value for key, value in kwargs.items() if key in INPUT_OPTIONS}
            while True:
                value = self.controller.prompt(
                    {
                        "kind": kind,
                        "title": title,
                        "message": prompt,
                        **options,
                    }
                )
                if value is None:
                    return None
                try:
                    convert = {"askinteger": int, "askfloat": float, "askstring": str}[kind]
                    converted = convert(value)
                    if kwargs.get("minvalue") is not None and converted < kwargs["minvalue"]:
                        continue
                    if kwargs.get("maxvalue") is not None and converted > kwargs["maxvalue"]:
                        continue
                    return converted
                except (ValueError, TypeError):
                    continue

        return ask
