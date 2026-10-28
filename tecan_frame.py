from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from xinpilot.application.tecan_domain import (
    SOURCE_LABWARE_OPTIONS,
    LIQUID_CLASS_OPTIONS,
    PLATE_MODES,
    DEST_LABWARE_OPTIONS_96,
    DEST_LABWARE_OPTIONS_HPLC,
    WELL_LABEL_RE,
    classify_source_well_usage,
    SOURCE_LAYOUTS,
    KNOWN_LABWARE_OPTIONS,
    normalize_liquid_class_names,
    default_labware_aliases,
    mode_dims_order,
    row_label_to_number,
    row_number_to_label,
    index_to_label,
    label_to_index,
    parse_well_expr,
    parse_dest_well_expr,
    index_to_dest_label,
    source_label_to_index,
    source_index_to_label,
    _validate_gwl_volume,
    rounded_gwl_volume,
    gwl_a_line,
    gwl_d_line,
    DispenseGroup,
    TransferBlock,
    validate_gwl_names,
)
from xinpilot.application.tecan_worklist import build_gwl_lines, build_chemical_map, build_volume_map
from typing import List, Tuple, Dict, Optional, Set
import csv
import math
import json
import os
import re

try:
    from PIL import ImageTk
    from rdkit import Chem
    from rdkit.Chem import Draw
except Exception:
    ImageTk = None
    Chem = None
    Draw = None


APPDATA_ROOT = Path(os.environ.get("APPDATA") or Path.home())
LABWARE_NAME_SETTINGS_PATH = APPDATA_ROOT / "XinPilot" / "tecan_labware_names.json"
RXNPILOT_LABWARE_NAME_SETTINGS_PATH = APPDATA_ROOT / "RxnPilot" / "tecan_labware_names.json"
RXNPILOT_LIQUID_CLASS_SETTINGS_PATH = APPDATA_ROOT / "RxnPilot" / "tecan_liquid_classes.json"
LEGACY_LABWARE_NAME_SETTINGS_PATH = APPDATA_ROOT / "OneClick Synthesis" / "tecan_labware_names.json"
LIQUID_CLASS_SETTINGS_PATH = APPDATA_ROOT / "XinPilot" / "tecan_liquid_classes.json"


def style_region_widgets(widget, region_prefix: str):
    frame_style = f"{region_prefix}.TFrame"
    label_style = f"{region_prefix}.TLabel"
    muted_style = f"{region_prefix}.Muted.TLabel"
    check_style = f"{region_prefix}.TCheckbutton"
    for child in widget.winfo_children():
        if isinstance(child, ttk.Frame):
            current = child.cget("style")
            if not current:
                child.configure(style=frame_style)
        elif isinstance(child, ttk.Label):
            current = child.cget("style")
            explicit_bg = str(child.cget("background") or "")
            if explicit_bg:
                style_region_widgets(child, region_prefix)
                continue
            if current == "Muted.TLabel":
                child.configure(style=muted_style)
            elif not current:
                child.configure(style=label_style)
        elif isinstance(child, ttk.Checkbutton):
            current = child.cget("style")
            if not current:
                child.configure(style=check_style)
        style_region_widgets(child, region_prefix)


def _position_toplevel_near(dialog: tk.Toplevel, anchor: Optional[tk.Widget] = None):
    if anchor is None:
        return
    try:
        dialog.update_idletasks()
        anchor.update_idletasks()
        root = anchor.winfo_toplevel()
        x = anchor.winfo_rootx() + anchor.winfo_width() + 8
        y = anchor.winfo_rooty() - 8
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        if x + width + 16 > screen_w:
            x = anchor.winfo_rootx() - width - 8
        x = max(0, min(x, screen_w - width - 8))
        y = max(0, min(y, screen_h - height - 40))
        dialog.geometry(f"+{x}+{y}")
        dialog.transient(root)
    except Exception:
        pass


class WellMapDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        rows: int,
        cols: int,
        initial_labels: str = "",
        vertical_view: bool = False,
        anchor: Optional[tk.Widget] = None,
        single_select: bool = False,
        highlight_labels: Optional[Set[str]] = None,
        disabled_labels: Optional[Set[str]] = None,
        highlight_hint: str = "Light blue wells already contain one or more dispensed reagents.",
        disabled_hint: str = "Gray wells are unavailable.",
    ):
        super().__init__(master)
        self.title("Select Source Well" if single_select else "Select Destination Wells")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)

        self.rows, self.cols = rows, cols
        self.vertical_view = bool(vertical_view)
        self.single_select = bool(single_select)
        self.disabled = {str(label).strip().upper() for label in (disabled_labels or set()) if str(label).strip()}
        self.highlighted = {
            str(label).strip().upper()
            for label in (highlight_labels or set())
            if str(label).strip()
        } - self.disabled
        self.highlight_hint = str(highlight_hint or "").strip()
        self.disabled_hint = str(disabled_hint or "").strip()
        self.result_labels = ""
        labels = [x.strip().upper() for x in (initial_labels or "").split(",") if x.strip()]
        self.selected = set(labels[-1:] if self.single_select else labels)
        self.drag_state = None

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        def display_to_label(dr: int, dc: int) -> str:
            if not self.vertical_view:
                return f"{row_number_to_label(dr)}{dc}"
            # Rotate visual layout for vertical mode while keeping canonical labels.
            logical_row = dc
            logical_col = self.cols - dr + 1
            return f"{row_number_to_label(logical_row)}{logical_col}"

        disp_rows = self.cols if self.vertical_view else self.rows
        disp_cols = self.rows if self.vertical_view else self.cols

        self.cells = {}
        for dr in range(1, disp_rows + 1):
            side_label = str(self.cols - dr + 1) if self.vertical_view else row_number_to_label(dr)
            ttk.Label(frame, text=side_label, width=3, anchor="center").grid(row=dr, column=0, padx=1, pady=1)
        for dc in range(1, disp_cols + 1):
            top_label = row_number_to_label(dc) if self.vertical_view else str(dc)
            ttk.Label(frame, text=top_label, width=5, anchor="center").grid(row=0, column=dc, padx=1, pady=1)

        for dr in range(1, disp_rows + 1):
            for dc in range(1, disp_cols + 1):
                lbl = display_to_label(dr, dc)
                cell = tk.Label(frame, text=lbl, width=6, relief="groove", bg="white")
                cell.grid(row=dr, column=dc, padx=1, pady=1)
                cell.bind("<Button-1>", lambda e, x=lbl: self._on_press(x))
                cell.bind("<Enter>", lambda e, x=lbl: self._on_enter(x))
                cell.bind("<B1-Motion>", self._on_motion)
                cell.bind("<ButtonRelease-1>", self._on_release)
                self.cells[lbl] = cell

        footer_row = disp_rows + 1
        if self.highlighted and self.highlight_hint:
            ttk.Label(
                frame,
                text=self.highlight_hint,
            ).grid(row=footer_row, column=0, columnspan=disp_cols + 1, sticky="w", pady=(6, 0))
            footer_row += 1
        if self.disabled and self.disabled_hint:
            ttk.Label(
                frame,
                text=self.disabled_hint,
            ).grid(row=footer_row, column=0, columnspan=disp_cols + 1, sticky="w", pady=(6, 0))
            footer_row += 1

        btns = ttk.Frame(frame)
        btns.grid(row=footer_row, column=0, columnspan=disp_cols + 1, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Clear", command=self.clear).pack(side="left")
        ttk.Button(btns, text="Use Selection", command=self.accept).pack(side="right")

        self._paint()
        _position_toplevel_near(self, anchor)

    def _on_press(self, label: str):
        if label in self.disabled:
            return
        if self.single_select:
            self.selected = {label}
            self.drag_state = None
            self._paint()
            return
        self.drag_state = label not in self.selected
        self._apply_drag_to_label(label)

    def _on_enter(self, label: str):
        if self.drag_state is not None:
            self._apply_drag_to_label(label)

    def _on_motion(self, event):
        if self.drag_state is None:
            return
        # Make drag-select robust even when <Enter> is missed.
        w = self.winfo_containing(event.x_root, event.y_root)
        if w is None:
            return
        for lbl, cell in self.cells.items():
            if cell == w:
                self._apply_drag_to_label(lbl)
                break

    def _on_release(self, _event):
        self.drag_state = None

    def _apply_drag_to_label(self, label: str):
        if label in self.disabled:
            return
        if self.drag_state is True:
            self.selected.add(label)
        elif self.drag_state is False and label in self.selected:
            self.selected.remove(label)
        self._paint()

    def clear(self):
        self.selected.clear()
        self._paint()

    def _paint(self):
        for lbl, w in self.cells.items():
            if lbl in self.disabled:
                w.configure(bg="#D8D8D8", fg="#777777", relief="sunken")
            elif lbl in self.selected:
                w.configure(bg="#2E7D32", fg="white")
            elif lbl in self.highlighted:
                w.configure(bg="#DCEAF7", fg="#17324D")
            else:
                w.configure(bg="SystemButtonFace", fg="black")

    def accept(self):
        self.selected.difference_update(self.disabled)
        def key(lbl: str):
            m = WELL_LABEL_RE.match(lbl)
            return (row_label_to_number(m.group(1)), int(m.group(2))) if m else (999, 999)
        ordered = sorted(self.selected, key=key)
        self.result_labels = ",".join(ordered)
        self.destroy()


class SourceWellDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        labware: str,
        initial_label: str = "",
        anchor: Optional[tk.Widget] = None,
        occupied_labels: Optional[Set[str]] = None,
        reusable_labels: Optional[Set[str]] = None,
    ):
        super().__init__(master)
        self.title(f"Select Source Well - {labware}")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)

        cfg = SOURCE_LAYOUTS.get(labware)
        if not cfg:
            messagebox.showerror("Unsupported labware", f"No source map defined for {labware}", parent=self)
            self.result_label = ""
            self.after(50, self.destroy)
            return

        rows, cols, style = cfg["rows"], cfg["cols"], cfg["style"]
        self.result_label = ""
        self.selected = (initial_label or "").strip().upper()
        self.occupied = {str(label).strip().upper() for label in (occupied_labels or set()) if str(label).strip()}
        self.reusable = {
            str(label).strip().upper()
            for label in (reusable_labels or set())
            if str(label).strip()
        } - self.occupied

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        if style == "rowcol":
            for r in range(1, rows + 1):
                ttk.Label(frame, text=row_number_to_label(r), width=3, anchor="center").grid(row=r, column=0)
            for c in range(1, cols + 1):
                ttk.Label(frame, text=str(c), width=5, anchor="center").grid(row=0, column=c)
        else:
            for r in range(1, rows + 1):
                ttk.Label(frame, text=str(rows - r + 1), width=3, anchor="center").grid(row=r, column=0)
            for c in range(1, cols + 1):
                ttk.Label(frame, text=row_number_to_label(c), width=5, anchor="center").grid(row=0, column=c)

        self.cells = {}
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                if style == "rowcol":
                    lbl = f"{row_number_to_label(r)}{c}"
                else:
                    lbl = f"{row_number_to_label(c)}{rows - r + 1}"
                b = tk.Label(frame, text=lbl, width=6, relief="groove", bg="white")
                b.grid(row=r, column=c, padx=1, pady=1)
                b.bind("<Button-1>", lambda _e, x=lbl: self._pick(x))
                self.cells[lbl] = b

        hint = (
            "Single selection only. Light blue wells are already used by this Chemical ID and can be reused; "
            "gray wells are assigned to another Chemical ID."
        )
        ttk.Label(frame, text=hint).grid(row=rows + 1, column=0, columnspan=cols + 1, sticky="w", pady=(6, 4))
        ttk.Button(frame, text="Use Selected", command=self._accept).grid(row=rows + 2, column=0, columnspan=cols + 1, sticky="e")
        self._paint()
        _position_toplevel_near(self, anchor)

    def _pick(self, label: str):
        if label in self.occupied:
            return
        self.selected = label
        self._paint()

    def _paint(self):
        for lbl, w in self.cells.items():
            if lbl in self.occupied:
                w.configure(bg="#D8D8D8", fg="#777777", relief="sunken")
            elif lbl == self.selected:
                w.configure(bg="#2E7D32", fg="white")
            elif lbl in self.reusable:
                w.configure(bg="#DCEAF7", fg="#17324D", relief="groove")
            else:
                w.configure(bg="SystemButtonFace", fg="black", relief="groove")

    def _accept(self):
        if self.selected in self.occupied:
            return
        self.result_label = self.selected
        self.destroy()


class LabwareMapPreview(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.title_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.title_var).pack(anchor="w", pady=(0, 4))
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(anchor="w")

    def clear(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()

    def show_source(self, logical_name: str, export_name: str):
        self.clear()
        cfg = SOURCE_LAYOUTS.get(logical_name)
        self.title_var.set(f"Source map: {logical_name} -> {export_name or logical_name}")
        if not cfg:
            ttk.Label(self.grid_frame, text="No source map defined for this labware.").grid(row=0, column=0, sticky="w")
            return
        rows, cols, style = cfg["rows"], cfg["cols"], cfg["style"]
        if style == "rowcol":
            row_headers = [row_number_to_label(r) for r in range(1, rows + 1)]
            col_headers = [str(c) for c in range(1, cols + 1)]
            label_at = lambda r, c: f"{row_number_to_label(r)}{c}"
        else:
            row_headers = [str(rows - r + 1) for r in range(1, rows + 1)]
            col_headers = [row_number_to_label(c) for c in range(1, cols + 1)]
            label_at = lambda r, c: f"{row_number_to_label(c)}{rows - r + 1}"
        self._draw_grid(rows, cols, row_headers, col_headers, label_at)

    def show_destination(self, logical_name: str, export_name: str, mode: str):
        self.clear()
        if logical_name in DEST_LABWARE_OPTIONS_HPLC and "hplc" not in (mode or "").lower():
            mode = "HPLC vials horizontal"
        elif logical_name in DEST_LABWARE_OPTIONS_96 and "hplc" in (mode or "").lower():
            mode = "96-well horizontal"
        rows, cols, _order = mode_dims_order(mode)
        vertical = "vertical" in (mode or "").lower()
        disp_rows = cols if vertical else rows
        disp_cols = rows if vertical else cols
        row_headers = [str(cols - r + 1) for r in range(1, disp_rows + 1)] if vertical else [row_number_to_label(r) for r in range(1, disp_rows + 1)]
        col_headers = [row_number_to_label(c) for c in range(1, disp_cols + 1)] if vertical else [str(c) for c in range(1, disp_cols + 1)]

        def label_at(dr: int, dc: int) -> str:
            if not vertical:
                return f"{row_number_to_label(dr)}{dc}"
            logical_row = dc
            logical_col = cols - dr + 1
            return f"{row_number_to_label(logical_row)}{logical_col}"

        self.title_var.set(f"Destination map: {logical_name} -> {export_name or logical_name} ({mode})")
        self._draw_grid(disp_rows, disp_cols, row_headers, col_headers, label_at)

    def _draw_grid(self, rows: int, cols: int, row_headers: List[str], col_headers: List[str], label_at):
        for c, label in enumerate(col_headers, start=1):
            ttk.Label(self.grid_frame, text=label, width=5, anchor="center").grid(row=0, column=c, padx=1, pady=1)
        for r, label in enumerate(row_headers, start=1):
            ttk.Label(self.grid_frame, text=label, width=3, anchor="center").grid(row=r, column=0, padx=1, pady=1)
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                tk.Label(
                    self.grid_frame,
                    text=label_at(r, c),
                    width=6,
                    relief="groove",
                    bg="white",
                ).grid(row=r, column=c, padx=1, pady=1)


class LabwareNameDialog(tk.Toplevel):
    def __init__(self, master: "TecanFrame"):
        super().__init__(master)
        self.owner = master
        self.title("Tecan Labware Names")
        self.grab_set()
        self.geometry("980x560")
        self.minsize(900, 520)
        self.resizable(True, True)
        self.edits = dict(master.labware_aliases)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Edit the exact Tecan worktable names exported to GWL. Logical labware keeps the same map/layout.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        table_frame = ttk.Frame(body)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_frame, columns=("kind", "logical", "export"), show="headings", height=16)
        self.tree.heading("kind", text="Use")
        self.tree.heading("logical", text="Logical labware")
        self.tree.heading("export", text="Exported Tecan name")
        self.tree.column("kind", width=90, anchor="w")
        self.tree.column("logical", width=170, anchor="w")
        self.tree.column("export", width=220, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        ybar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=ybar.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        edit_frame = ttk.Frame(body)
        edit_frame.grid(row=1, column=1, sticky="nsew")
        edit_frame.columnconfigure(1, weight=1)
        self.selected_kind = tk.StringVar(value="")
        self.selected_logical = tk.StringVar(value="")
        self.export_name_var = tk.StringVar(value="")
        ttk.Label(edit_frame, text="Selected").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(edit_frame, textvariable=self.selected_logical).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(edit_frame, text="Use").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Label(edit_frame, textvariable=self.selected_kind).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(edit_frame, text="Tecan name").grid(row=2, column=0, sticky="w", pady=3)
        entry = ttk.Entry(edit_frame, textvariable=self.export_name_var)
        entry.grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Button(edit_frame, text="Apply Name", command=self._apply_name).grid(row=2, column=2, sticky="w", padx=(6, 0), pady=3)

        self.preview = LabwareMapPreview(edit_frame)
        self.preview.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        edit_frame.rowconfigure(3, weight=1)

        btns = ttk.Frame(body)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Reset Defaults", command=self._reset_defaults).pack(side="left")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Save Names", command=self._save).pack(side="right", padx=(0, 8))

        self._populate()
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])
            self._on_select()
        entry.bind("<Return>", lambda _event=None: self._apply_name())

    def _rows(self):
        for logical in SOURCE_LABWARE_OPTIONS:
            yield "Source", logical
        for logical in DEST_LABWARE_OPTIONS_96 + DEST_LABWARE_OPTIONS_HPLC:
            yield "Destination", logical

    def _item_id(self, kind: str, logical: str) -> str:
        return f"{kind}|{logical}"

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        for kind, logical in self._rows():
            export = self.edits.get(logical, logical) or logical
            self.tree.insert("", "end", iid=self._item_id(kind, logical), values=(kind, logical, export))

    def _selected(self) -> Tuple[str, str]:
        sel = self.tree.selection()
        if not sel:
            return "", ""
        values = self.tree.item(sel[0], "values")
        if len(values) < 2:
            return "", ""
        return str(values[0]), str(values[1])

    def _on_select(self, _event=None):
        kind, logical = self._selected()
        if not logical:
            return
        export = self.edits.get(logical, logical) or logical
        self.selected_kind.set(kind)
        self.selected_logical.set(logical)
        self.export_name_var.set(export)
        if kind == "Source":
            self.preview.show_source(logical, export)
        else:
            self.preview.show_destination(logical, export, self.owner.mode_var.get())

    def _apply_name(self):
        kind, logical = self._selected()
        if not logical:
            return
        export = self.export_name_var.get().strip() or logical
        self.edits[logical] = export
        item_id = self._item_id(kind, logical)
        if self.tree.exists(item_id):
            self.tree.item(item_id, values=(kind, logical, export))
        self._on_select()

    def _reset_defaults(self):
        self.edits = default_labware_aliases()
        self._populate()
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])
            self._on_select()

    def _save(self):
        self._apply_name()
        self.owner.set_labware_aliases(self.edits, persist=True)
        self.destroy()


class LiquidClassDialog(tk.Toplevel):
    def __init__(self, master: "TecanFrame"):
        super().__init__(master)
        self.owner = master
        self.title("Tecan Liquid Classes")
        self.grab_set()
        self.geometry("560x420")
        self.minsize(480, 360)
        self.resizable(True, True)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(
            body,
            text="Add, edit, or delete the liquid-class names shown in the Tecan dropdown menu.",
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        list_frame = ttk.Frame(body)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(list_frame, exportselection=False)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        ybar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        ybar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=ybar.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        editor = ttk.Frame(body)
        editor.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        editor.columnconfigure(1, weight=1)
        self.name_var = tk.StringVar(value="")
        ttk.Label(editor, text="Liquid class name").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.name_entry = ttk.Entry(editor, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(editor, text="Add", command=self._add).grid(row=0, column=2, sticky="w", padx=(8, 0))

        actions = ttk.Frame(body)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Update Selected", command=self._edit_selected).pack(side="left")
        ttk.Button(actions, text="Delete Selected", command=self._delete_selected, style="Danger.TButton").pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")

        self._populate()
        self.name_entry.bind("<Return>", lambda _event=None: self._add())

    def _populate(self, selected_name: str = ""):
        self.listbox.delete(0, "end")
        for name in self.owner.liquid_classes:
            self.listbox.insert("end", name)
        if selected_name:
            wanted = selected_name.casefold()
            for index, name in enumerate(self.owner.liquid_classes):
                if name.casefold() == wanted:
                    self.listbox.selection_set(index)
                    self.listbox.activate(index)
                    self.listbox.see(index)
                    self._on_select()
                    break

    def _selected_index(self) -> int | None:
        selected = self.listbox.curselection()
        return int(selected[0]) if selected else None

    def _on_select(self, _event=None):
        index = self._selected_index()
        if index is not None:
            self.name_var.set(str(self.listbox.get(index)))

    def _add(self):
        name = self.name_var.get().strip()
        if not name:
            return
        names = list(self.owner.liquid_classes)
        existing = next((value for value in names if value.casefold() == name.casefold()), "")
        if existing:
            self._populate(existing)
            return
        names.append(name)
        self.owner.set_liquid_classes(names, persist=True)
        self._populate(name)

    def _edit_selected(self):
        index = self._selected_index()
        name = self.name_var.get().strip()
        if index is None or not name:
            return
        names = list(self.owner.liquid_classes)
        if index >= len(names):
            return
        if any(i != index and value.casefold() == name.casefold() for i, value in enumerate(names)):
            return
        old_name = names[index]
        names[index] = name
        selected_name = name if self.owner.v_liquid_class.get().strip().casefold() == old_name.casefold() else None
        self.owner.set_liquid_classes(names, persist=True, selected_name=selected_name)
        self._populate(name)

    def _delete_selected(self):
        index = self._selected_index()
        if index is None:
            return
        names = list(self.owner.liquid_classes)
        if index >= len(names):
            return
        del names[index]
        self.owner.set_liquid_classes(names, persist=True)
        self.name_var.set("")
        self._populate()
        if names:
            next_index = min(index, len(names) - 1)
            self.listbox.selection_set(next_index)
            self.listbox.activate(next_index)
            self._on_select()


class TecanFrame(ttk.Frame):
    def __init__(self, master, compound_provider=None, push_callback=None):
        super().__init__(master)
        self.compound_provider = compound_provider
        self.push_callback = push_callback
        self.blocks: List[TransferBlock] = []
        self.exported_gwl_files: List[Dict[str, str]] = []
        self.copied_block: TransferBlock | None = None
        self._updating_form = False
        self._active_gwl_index: int | None = None
        self._active_gwl_snapshot = ""
        self._active_gwl_blocks_snapshot = ""
        self._switching_gwl_selection = False
        self.structure_window: tk.Toplevel | None = None
        self.structure_image_label: ttk.Label | None = None
        self.structure_title_label: ttk.Label | None = None
        self.structure_photo = None
        self.labware_aliases = self._load_labware_aliases()
        self.liquid_classes = self._load_liquid_classes()

        self.mode_var = tk.StringVar(value="")
        self._build_ui()
        self.mode_var.trace_add("write", self._on_mode_changed)
        self._refresh_dest_labware_options()
        self._on_mode_changed()

    def _build_ui(self):
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        mid = ttk.Frame(body)
        mid.pack(fill="both", expand=True)

        self.v_save_map = tk.BooleanVar(value=True)

        left = ttk.LabelFrame(mid, text="Exported GWL files from this edition", padding=8, style="FileRegion.TLabelframe")
        left.pack(side="left", fill="y", padx=(0, 10))

        gwl_actions = ttk.Frame(left)
        gwl_actions.pack(fill="x", pady=(0, 8))
        for c in range(2):
            gwl_actions.columnconfigure(c, weight=1)
        self.new_gwl_button = ttk.Button(gwl_actions, text="New GWL", command=self._new_blank_gwl, style="ChemAction.TButton")
        self.new_gwl_button.grid(row=0, column=0, padx=(0, 3), pady=(0, 4), sticky="ew")
        self.save_gwl_as_button = ttk.Button(gwl_actions, text="Save As New GWL...", command=self._save, style="FileAction.TButton")
        self.save_gwl_as_button.grid(row=0, column=1, padx=(3, 0), pady=(0, 4), sticky="ew")
        self.add_existing_gwl_button = ttk.Button(gwl_actions, text="Add Existing .gwl", command=self._add_existing_gwl, style="FileAction.TButton")
        self.add_existing_gwl_button.grid(row=1, column=0, padx=(0, 3), pady=4, sticky="ew")
        self.save_gwl_edits_button = ttk.Button(gwl_actions, text="Save Current GWL", command=self._save_selected_gwl_edits, style="FileAction.TButton")
        self.save_gwl_edits_button.grid(row=1, column=1, padx=(3, 0), pady=4, sticky="ew")
        ttk.Button(gwl_actions, text="Preview GWL", command=self._preview, style="FileAction.TButton").grid(row=2, column=0, padx=(0, 3), pady=4, sticky="ew")
        ttk.Button(gwl_actions, text="Remove", command=self._remove_selected_gwl, style="Danger.TButton").grid(row=2, column=1, padx=(3, 0), pady=4, sticky="ew")
        ttk.Checkbutton(gwl_actions, text="Chemical map (.csv)", variable=self.v_save_map).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.gwl_listbox = tk.Listbox(left, width=42, height=12, exportselection=False)
        self.gwl_listbox.pack(fill="both", expand=True)
        self.gwl_listbox.bind("<<ListboxSelect>>", self._on_gwl_select)
        ttk.Label(
            left,
            text="Select a listed GWL to edit it, then use Save Current GWL to write those edits.",
            style="Muted.TLabel",
            wraplength=285,
            justify="left",
        ).pack(fill="x", pady=(6, 0))
        self.push_all_cheminformatics_button = ttk.Button(
            left,
            text="Push Listed GWLs to Cheminformatics",
            command=self._push_all_gwls_to_cheminformatics,
            style="ChemAction.TButton",
        )
        self.push_all_cheminformatics_button.pack(fill="x", pady=(8, 0))
        ttk.Button(
            left,
            text="Edit Tecan Labware Names",
            command=self._open_labware_name_dialog,
            style="FileAction.TButton",
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            left,
            text="Edit Liquid Classes",
            command=self._open_liquid_class_dialog,
            style="FileAction.TButton",
        ).pack(fill="x", pady=(8, 0))
        style_region_widgets(left, "FileRegion")

        editor = ttk.Frame(mid)
        editor.pack(side="left", fill="both", expand=True)
        editor.columnconfigure(0, weight=0)
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(0, weight=1)

        right = ttk.LabelFrame(editor, text="Edit", padding=8, style="ChemRegion.TLabelframe")
        right.grid(row=0, column=0, sticky="nsew")
        edit_heading = ttk.Frame(editor)
        ttk.Label(edit_heading, text="Edit", font=("Segoe UI", 10, "bold")).pack(side="left")
        right.configure(labelwidget=edit_heading)
        right.rowconfigure(12, weight=1)

        self.v_source_labware = tk.StringVar(value=SOURCE_LABWARE_OPTIONS[0])
        self.v_source_well = tk.StringVar(value="1")
        self.v_source_volume = tk.StringVar(value="20.0")
        self.v_dest_labware = tk.StringVar(value="")
        self.v_dest_wells = tk.StringVar(value="")
        self.v_dest_volume = tk.StringVar(value="20.0")
        self.v_liquid_class = tk.StringVar(value=self._default_liquid_class())
        self.v_chemical = tk.StringVar(value="")
        self.v_reaction_umol = tk.StringVar(value="")
        self.v_extra_aspirate_percent = tk.StringVar(value="")
        self.v_is_building_block = tk.BooleanVar(value=False)
        self.v_wash = tk.BooleanVar(value=True)
        self.v_diff_vol = tk.StringVar(value="No")
        self.v_show_structure = tk.BooleanVar(value=False)
        self.group_rows = []
        self.groups_window = None
        self.groups_open_button = None

        r = 0
        ttk.Label(right, text="Destination format", font=("Segoe UI", 10, "bold"),
                  foreground="#28669c").grid(row=r, column=0, sticky="w", pady=2)
        self.mode_combo = ttk.Combobox(right, textvariable=self.mode_var, values=PLATE_MODES, width=24, state="readonly")
        self.mode_combo.grid(row=r, column=1, sticky="w", pady=2)
        block_actions = ttk.Frame(right, style="ChemRegion.TFrame")
        block_actions.grid(row=r, column=2, columnspan=2, sticky="w", padx=(6, 0), pady=2)
        self.add_block_button = ttk.Button(block_actions, text="Add Block", command=self._add_block,
                                           style="ChemAction.TButton", width=0)
        self.add_block_button.grid(row=0, column=0, sticky="w")
        self.batch_addition_button = ttk.Button(block_actions, text="Add Batch", command=self._open_batch_addition,
                                               style="ChemAction.TButton", width=0)
        self.batch_addition_button.grid(row=0, column=1, sticky="w", padx=(4, 0))
        from xinpilot_tooltips import Tooltip
        self._format_tooltip = Tooltip(self.mode_combo, "Select a destination format before adding blocks.")
        r += 1

        ttk.Label(right, text="Chemical ID").grid(row=r, column=0, sticky="w", pady=2)
        self.chemical_combo = ttk.Combobox(right, textvariable=self.v_chemical, width=24, postcommand=self._refresh_compound_options)
        self.chemical_combo.grid(row=r, column=1, sticky="w", pady=2)
        self.chemical_combo.bind("<<ComboboxSelected>>", self._on_chemical_selected)
        ttk.Checkbutton(right, text="Show structure", variable=self.v_show_structure).grid(row=r, column=2, sticky="w", padx=(6, 12), pady=2)
        r += 1

        ttk.Checkbutton(right, text="This is a building block", variable=self.v_is_building_block).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=2
        )
        r += 1

        ttk.Label(right, text="umol/rxn").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.v_reaction_umol, width=12).grid(row=r, column=1, sticky="w", pady=2)
        r += 1

        ttk.Label(right, text="Source Labware").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.v_source_labware, values=SOURCE_LABWARE_OPTIONS, width=23).grid(row=r, column=1, sticky="w", pady=2)
        r += 1

        ttk.Label(right, text="Source Well Index").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.v_source_well, width=12).grid(row=r, column=1, sticky="w", pady=2)
        self.source_map_button = ttk.Button(right, text="Map Select")
        self.source_map_button.configure(command=lambda b=self.source_map_button: self._pick_source_well_on_map(anchor=b))
        self.source_map_button.grid(row=r, column=2, padx=(6, 12), sticky="w")
        r += 1

        ttk.Label(right, text="Aspirate Volume (uL)").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.v_source_volume, width=12).grid(row=r, column=1, sticky="w", pady=2)
        ttk.Label(right, text="Extra aspirate (%)").grid(row=r, column=2, sticky="w", padx=(6, 4), pady=2)
        ttk.Entry(right, textvariable=self.v_extra_aspirate_percent, width=8).grid(row=r, column=3, sticky="w", pady=2)
        r += 1

        ttk.Label(right, text="Destination Labware").grid(row=r, column=0, sticky="w", pady=2)
        self.dest_labware_combo = ttk.Combobox(right, textvariable=self.v_dest_labware, width=23)
        self.dest_labware_combo.grid(row=r, column=1, sticky="w", pady=2)
        r += 1

        ttk.Label(right, text="Destination Wells").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.v_dest_wells, width=24).grid(row=r, column=1, sticky="w", pady=2)
        self.dest_map_button = ttk.Button(right, text="Map Select")
        self.dest_map_button.configure(command=lambda b=self.dest_map_button: self._pick_wells_on_map(anchor=b))
        self.dest_map_button.grid(row=r, column=2, padx=(6, 12), sticky="w")
        r += 1

        ttk.Label(right, text="Dispense Volume (each well, uL)").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self.v_dest_volume, width=12).grid(row=r, column=1, sticky="w", pady=2)
        r += 1

        ttk.Label(right, text="Disp Different Vol?").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(right, textvariable=self.v_diff_vol, values=["No", "Yes"], width=10, state="readonly").grid(row=r, column=1, sticky="w", pady=2)
        self.groups_open_button = ttk.Button(right, text="Edit", command=self._show_group_window, style="RowAction.TButton")
        self.groups_open_button.grid(row=r, column=2, padx=(6, 12), sticky="w")
        r += 1

        self._build_group_window()

        ttk.Label(right, text="Liquid Class").grid(row=r, column=0, sticky="w", pady=2)
        self.liquid_class_combo = ttk.Combobox(
            right,
            textvariable=self.v_liquid_class,
            values=self.liquid_classes,
            width=23,
            state="readonly",
        )
        self.liquid_class_combo.grid(row=r, column=1, sticky="w", pady=2)
        self.liquid_class_combo.bind("<MouseWheel>", self._block_combobox_mousewheel)
        self.liquid_class_combo.bind("<Button-4>", self._block_combobox_mousewheel)
        self.liquid_class_combo.bind("<Button-5>", self._block_combobox_mousewheel)
        r += 1

        ttk.Frame(right, style="ChemRegion.TFrame").grid(row=r, column=0, columnspan=3, sticky="nsew")
        r += 1

        ttk.Checkbutton(right, text="Add W; wash line after this block", variable=self.v_wash).grid(row=r, column=0, columnspan=3, sticky="w", pady=(1, 3))
        r += 1

        ttk.Label(
            right,
            text="Selected block fields normally save automatically.",
            style="Muted.TLabel",
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(3, 1))
        r += 1
        self.apply_block_button = ttk.Button(
            right,
            text="Validate / Apply Block Now",
            command=self._apply_current,
        )
        self.apply_block_button.grid(row=r, column=0, columnspan=3, sticky="w", pady=(1, 6))
        r += 1
        style_region_widgets(right, "ChemRegion")

        self._block_editor_controls = []
        pending = list(right.winfo_children())
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            if widget in {self.mode_combo, self.add_block_button, self.batch_addition_button, self.push_all_cheminformatics_button}:
                continue
            if isinstance(widget, (ttk.Entry, ttk.Combobox, ttk.Button, ttk.Checkbutton)):
                self._block_editor_controls.append((widget, str(widget.cget("state") or "normal")))
        self._set_block_editor_enabled(False)

        blocks_panel = ttk.LabelFrame(
            editor,
            text="Transfer blocks (no more than 8 blocks in each gwl.)",
            padding=6,
            style="RowRegion.TLabelframe",
        )
        blocks_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        blocks_panel.columnconfigure(0, weight=1)
        blocks_panel.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(blocks_panel, width=32, height=16, exportselection=False)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Control-c>", self._copy_selected_block)
        self.listbox.bind("<Control-C>", self._copy_selected_block)
        self.listbox.bind("<Control-v>", self._paste_block)
        self.listbox.bind("<Control-V>", self._paste_block)
        self.listbox.bind("<Delete>", self._delete_selected_event)

        row_btn = ttk.Frame(blocks_panel)
        row_btn.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(row_btn, text="Move Up", command=self._move_up, style="RowAction.TButton").pack(side="left", padx=3)
        ttk.Button(row_btn, text="Move Down", command=self._move_down, style="RowAction.TButton").pack(side="left", padx=3)
        ttk.Button(row_btn, text="Delete", command=self._delete_selected, style="Danger.TButton").pack(side="left", padx=3)
        style_region_widgets(blocks_panel, "RowRegion")

        for v in [
            self.v_source_labware,
            self.v_source_well,
            self.v_source_volume,
            self.v_dest_labware,
            self.v_dest_wells,
            self.v_dest_volume,
            self.v_liquid_class,
            self.v_chemical,
            self.v_reaction_umol,
            self.v_extra_aspirate_percent,
        ]:
            v.trace_add("write", self._on_form_change_autosave)
        self.v_is_building_block.trace_add("write", self._on_form_change_autosave)
        self.v_wash.trace_add("write", self._on_form_change_autosave)
        self.v_diff_vol.trace_add("write", self._on_diff_toggle)
        self.v_show_structure.trace_add("write", self._on_show_structure_toggle)
        self.v_chemical.trace_add("write", self._on_structure_source_changed)
        self.v_reaction_umol.trace_add("write", lambda *_args: self._calculate_dispense_volume_from_umol())
        self.v_dest_wells.trace_add("write", lambda *_args: self._sync_source_volume_to_dispense_total())
        self.v_dest_volume.trace_add("write", lambda *_args: self._sync_source_volume_to_dispense_total())
        self.v_extra_aspirate_percent.trace_add("write", lambda *_args: self._sync_source_volume_to_dispense_total())
        self._add_group_row()
        self._render_group_visibility()

        self.preview = None

    def _load_labware_aliases(self) -> Dict[str, str]:
        aliases = default_labware_aliases()
        try:
            settings_path = LABWARE_NAME_SETTINGS_PATH
            if not settings_path.exists() and RXNPILOT_LABWARE_NAME_SETTINGS_PATH.exists():
                settings_path = RXNPILOT_LABWARE_NAME_SETTINGS_PATH
            if not settings_path.exists() and LEGACY_LABWARE_NAME_SETTINGS_PATH.exists():
                settings_path = LEGACY_LABWARE_NAME_SETTINGS_PATH
            if settings_path.exists():
                data = json.loads(settings_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    raw_aliases = data.get("labware_aliases", data)
                    if isinstance(raw_aliases, dict):
                        for logical, export_name in raw_aliases.items():
                            logical = str(logical)
                            if logical in aliases:
                                aliases[logical] = str(export_name or logical).strip() or logical
        except Exception:
            pass
        return aliases

    def _save_labware_aliases(self):
        try:
            LABWARE_NAME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {"labware_aliases": self.labware_aliases}
            LABWARE_NAME_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showwarning("Labware names", f"Could not save labware names:\n{exc}")

    def set_labware_aliases(self, aliases: Dict[str, str], persist: bool = False):
        merged = default_labware_aliases()
        for logical, export_name in (aliases or {}).items():
            logical = str(logical)
            if logical in merged:
                merged[logical] = str(export_name or logical).strip() or logical
        self.labware_aliases = merged
        if persist:
            self._save_labware_aliases()
        if hasattr(self, "listbox"):
            self._refresh_list()

    def _open_labware_name_dialog(self):
        LabwareNameDialog(self)

    def _load_liquid_classes(self) -> List[str]:
        try:
            settings_path = LIQUID_CLASS_SETTINGS_PATH
            if not settings_path.exists():
                settings_path = RXNPILOT_LIQUID_CLASS_SETTINGS_PATH
            if settings_path.exists():
                data = json.loads(settings_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("liquid_classes"), list):
                    return normalize_liquid_class_names(data["liquid_classes"])
        except Exception:
            pass
        return list(LIQUID_CLASS_OPTIONS)

    def _save_liquid_classes(self):
        try:
            LIQUID_CLASS_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {"liquid_classes": list(self.liquid_classes)}
            LIQUID_CLASS_SETTINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showwarning("Liquid classes", f"Could not save liquid classes:\n{exc}")

    def _default_liquid_class(self) -> str:
        return self.liquid_classes[0] if self.liquid_classes else ""

    def set_liquid_classes(self, names, persist: bool = False, selected_name: str | None = None):
        current_name = self.v_liquid_class.get().strip() if hasattr(self, "v_liquid_class") else ""
        self.liquid_classes = normalize_liquid_class_names(names)
        if hasattr(self, "liquid_class_combo"):
            self.liquid_class_combo.configure(values=self.liquid_classes)
        if hasattr(self, "v_liquid_class"):
            available = {name.casefold(): name for name in self.liquid_classes}
            requested = str(selected_name or "").strip()
            if requested.casefold() in available:
                next_name = available[requested.casefold()]
            elif current_name.casefold() in available:
                next_name = available[current_name.casefold()]
            else:
                next_name = self._default_liquid_class()
            if self.v_liquid_class.get() != next_name:
                self.v_liquid_class.set(next_name)
        if persist:
            self._save_liquid_classes()

    def _open_liquid_class_dialog(self):
        LiquidClassDialog(self)

    def _labware_export_name(self, logical_name: str) -> str:
        logical_name = str(logical_name or "").strip()
        return (self.labware_aliases.get(logical_name, logical_name) or logical_name).strip()

    def _labware_display_name(self, logical_name: str) -> str:
        export_name = self._labware_export_name(logical_name)
        return export_name if export_name == logical_name else f"{logical_name}->{export_name}"

    def _canonical_labware_name(self, name: str) -> str:
        text = str(name or "").strip()
        if text in KNOWN_LABWARE_OPTIONS:
            return text
        text_lower = text.lower()
        for logical, export_name in self.labware_aliases.items():
            if text_lower == str(export_name or "").strip().lower():
                return logical
        return text

    def _get_dest_labware_options_for_mode(self) -> List[str]:
        mode = (self.mode_var.get() or "").lower()
        if "hplc" in mode:
            return DEST_LABWARE_OPTIONS_HPLC
        return DEST_LABWARE_OPTIONS_96

    def _refresh_dest_labware_options(self):
        options = self._get_dest_labware_options_for_mode()
        self.dest_labware_combo.configure(values=options)
        # Suggestions must not select labware on the user's behalf or replace
        # saved/custom labware when an existing block is opened.

    def _on_mode_changed(self, *_args):
        self._refresh_dest_labware_options()
        selected = self.mode_var.get() in PLATE_MODES
        for button in (self.add_block_button, self.batch_addition_button):
            button.configure(state="normal" if selected else "disabled")
        self._format_tooltip.hide()
        self._format_tooltip.text = (
            "48-well layout (6 × 8)." if "HPLC vials" in self.mode_var.get()
            else "Select a destination format before adding blocks."
        )

    def _compound_records(self):
        if not callable(self.compound_provider):
            return []
        try:
            return list(self.compound_provider() or [])
        except Exception:
            return []

    @staticmethod
    def _parse_float(value) -> float:
        try:
            txt = str(value or "").strip()
            if not txt:
                return 0.0
            return float(txt)
        except Exception:
            return 0.0

    def _volume_left_by_chemical_id(self) -> Dict[str, float]:
        volumes: Dict[str, float] = {}
        for rec in self._compound_records():
            data = getattr(rec, "values", {}) or {}
            cid = str(data.get("ID", "") or "").strip().upper()
            if cid:
                volumes[cid] = self._parse_float(data.get("Volume"))
        return volumes

    def _refresh_compound_options(self):
        values = []
        seen = set()
        for rec in self._compound_records():
            data = getattr(rec, "values", {}) or {}
            text = (data.get("ID", "") or "").strip()
            if text and text.lower() not in seen:
                values.append(text)
                seen.add(text.lower())
        if hasattr(self, "chemical_combo"):
            self.chemical_combo.configure(values=values)

    def _compound_for_chemical_label(self, label: str):
        wanted = (label or "").strip().casefold()
        if not wanted:
            return None
        for rec in self._compound_records():
            data = getattr(rec, "values", {}) or {}
            for candidate in (data.get("ID", ""), data.get("Name", "")):
                if str(candidate or "").strip().casefold() == wanted:
                    return data
        return None

    @staticmethod
    def _record_concentration_m(data: Dict[str, object]) -> Optional[float]:
        for key in ("Conc.", "Concentration", "concentration", "conc"):
            value = str(data.get(key, "") or "").strip()
            if not value:
                continue
            match = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([mun]?m)?\s*$", value, re.IGNORECASE)
            if not match:
                continue
            concentration = float(match.group(1))
            unit = (match.group(2) or "M").lower()
            if unit == "mm":
                concentration /= 1000.0
            elif unit in {"um", "µm"}:
                concentration /= 1_000_000.0
            elif unit == "nm":
                concentration /= 1_000_000_000.0
            if concentration > 0:
                return concentration
        return None

    @staticmethod
    def _volume_from_umol_and_conc(umol: object, concentration_m: Optional[float]) -> str:
        if not concentration_m:
            return ""
        try:
            amount = float(str(umol or "").strip())
        except ValueError:
            return ""
        if amount <= 0:
            return ""
        return f"{amount / concentration_m:.1f}"

    def _calculate_dispense_volume_from_umol(self):
        data = self._compound_for_chemical_label(self.v_chemical.get())
        if not data:
            return
        volume = self._volume_from_umol_and_conc(self.v_reaction_umol.get(), self._record_concentration_m(data))
        if not volume:
            return
        self.v_dest_volume.set(volume)
        self._sync_source_volume_to_dispense_total()

    def _extra_aspirate_fraction(self) -> float:
        text = str(self.v_extra_aspirate_percent.get() or "").strip().rstrip("%").strip()
        if not text:
            return 0.0
        try:
            percent = float(text)
        except ValueError:
            return 0.0
        if percent <= 0:
            return 0.0
        return percent / 100.0

    def _sync_source_volume_to_dispense_total(self):
        if self._updating_form:
            return
        try:
            dest_vol = rounded_gwl_volume(float(self.v_dest_volume.get().strip()))
            wells = parse_dest_well_expr(self.v_dest_wells.get().strip(), self.mode_var.get(), self.v_dest_labware.get().strip())
            total = dest_vol * len(wells)
            if self.v_diff_vol.get().strip().lower() == "yes":
                for group in self.group_rows:
                    volume_text = group["vol"].get().strip()
                    wells_text = group["wells"].get().strip()
                    if not volume_text and not wells_text:
                        continue
                    group_volume = rounded_gwl_volume(float(volume_text))
                    if group_volume <= 0 or not wells_text:
                        return
                    group_wells = parse_dest_well_expr(
                        wells_text, self.mode_var.get(), self.v_dest_labware.get().strip()
                    )
                    total += group_volume * len(group_wells)
            if total <= 0:
                return
            aspirate = total * (1.0 + self._extra_aspirate_fraction())
            current = float(self.v_source_volume.get().strip() or "0")
            if abs(current - aspirate) > 1e-6:
                self.v_source_volume.set(f"{aspirate:.1f}")
        except Exception:
            return

    def _on_show_structure_toggle(self, *_args):
        if self.v_show_structure.get():
            self._refresh_structure_window()
        else:
            self._close_structure_window()

    def _on_structure_source_changed(self, *_args):
        if self._updating_form:
            return
        if self.v_show_structure.get():
            self.after_idle(self._refresh_structure_window)

    def _close_structure_window(self):
        win = self.structure_window
        self.structure_window = None
        self.structure_image_label = None
        self.structure_title_label = None
        self.structure_photo = None
        if win is not None and win.winfo_exists():
            try:
                win.destroy()
            except Exception:
                pass

    def _on_structure_window_closed(self):
        self.v_show_structure.set(False)
        self._close_structure_window()

    def _ensure_structure_window(self):
        if self.structure_window is not None and self.structure_window.winfo_exists():
            return
        win = tk.Toplevel(self)
        win.title("Chemical Structure")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._on_structure_window_closed)
        try:
            win.transient(self.winfo_toplevel())
        except Exception:
            pass
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        self.structure_title_label = ttk.Label(frame, text="", anchor="center")
        self.structure_title_label.pack(fill="x", pady=(0, 6))
        self.structure_image_label = ttk.Label(frame, text="", anchor="center")
        self.structure_image_label.pack(fill="both", expand=True)
        self.structure_window = win
        try:
            _position_toplevel_near(win, self.chemical_combo)
        except Exception:
            pass

    def _refresh_structure_window(self):
        if not self.v_show_structure.get():
            return
        self._ensure_structure_window()
        if self.structure_window is None or not self.structure_window.winfo_exists():
            return
        label = self.v_chemical.get().strip()
        data = self._compound_for_chemical_label(label)
        title = label or "No Chemical ID"
        smiles = str((data or {}).get("SMILES", "") or "").strip()
        display_name = str((data or {}).get("Name", "") or "").strip()
        if display_name and display_name.casefold() != title.casefold():
            title = f"{title} - {display_name}" if label else display_name
        if self.structure_title_label is not None:
            self.structure_title_label.configure(text=title)
        if self.structure_image_label is None:
            return
        self.structure_photo = None
        if not smiles:
            self.structure_image_label.configure(image="", text="Structure not found")
            return
        if Chem is None or Draw is None or ImageTk is None:
            self.structure_image_label.configure(image="", text="Structure renderer unavailable")
            return
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.structure_image_label.configure(image="", text="Invalid SMILES")
            return
        try:
            img = Draw.MolToImage(mol, size=(300, 220))
            self.structure_photo = ImageTk.PhotoImage(img)
            self.structure_image_label.configure(image=self.structure_photo, text="")
        except Exception as exc:
            self.structure_image_label.configure(image="", text=f"Structure render failed: {exc}")

    def _on_chemical_selected(self, _event=None):
        data = self._compound_for_chemical_label(self.v_chemical.get())
        if not data:
            if self.v_show_structure.get():
                self._refresh_structure_window()
            return
        self._calculate_dispense_volume_from_umol()
        if self.v_show_structure.get():
            self._refresh_structure_window()
        self._apply_current(silent=True)

    def _block_combobox_mousewheel(self, _event=None):
        return "break"

    def _warn_low_volume_for_clld(self) -> bool:
        volumes = self._volume_left_by_chemical_id()
        if not volumes:
            return True
        warnings = []
        for idx, block in enumerate(self.blocks, start=1):
            chemical_id = str(block.chemical_name or "").strip().upper()
            if not chemical_id:
                continue
            volume_left = volumes.get(chemical_id)
            if volume_left is None or volume_left >= 500:
                continue
            liquid_class = str(block.liquid_class or "")
            if "no_clld" in liquid_class.lower():
                continue
            warnings.append(f"Block {idx}: {chemical_id}, Volume left {volume_left:.1f} uL, Liquid Class {liquid_class}")
        if not warnings:
            return True
        return messagebox.askyesno(
            "Low volume left",
            "These Chemical IDs have less than 500 uL left.\n"
            "Please choose a no-cLLD liquid class before saving the GWL.\n\n"
            + "\n".join(warnings[:12])
            + ("\n..." if len(warnings) > 12 else "")
            + "\n\nContinue saving anyway?",
        )

    def _warn_stock_may_be_insufficient_after_aspirate(self):
        volumes = self._volume_left_by_chemical_id()
        if not volumes:
            return
        warnings = []
        for idx, block in enumerate(self.blocks, start=1):
            chemical_id = str(block.chemical_name or "").strip().upper()
            if not chemical_id:
                continue
            volume_left = volumes.get(chemical_id)
            if volume_left is None or volume_left < 400:
                continue
            remaining = volume_left - float(block.source_volume or 0.0)
            if remaining >= 400:
                continue
            warnings.append(
                f"Block {idx}: {chemical_id}, Volume left {volume_left:.1f} uL, "
                f"Aspirate {float(block.source_volume or 0.0):.1f} uL, remaining {remaining:.1f} uL"
            )
        if warnings:
            messagebox.showwarning(
                "Stock solution may be low",
                "After this GWL aspirates stock solution, these Chemical IDs may not have enough stock solution for Tecan.\n\n"
                + "\n".join(warnings[:12])
                + ("\n..." if len(warnings) > 12 else ""),
            )

    def _push_all_gwls_to_cheminformatics(self):
        try:
            validate_gwl_names(self.exported_gwl_files)
        except ValueError as exc:
            messagebox.showerror("GWL filenames", str(exc), parent=self)
            return
        if not self.exported_gwl_files:
            messagebox.showwarning(
                "No GWL files",
                "No GWL files are listed in 'Exported GWL files from this edition'.",
            )
            return
        if self.listbox.curselection() and not self._apply_current(silent=False, show_success=False):
            return

        rows: List[Dict[str, object]] = []
        errors: List[str] = []
        for idx, entry in enumerate(self.exported_gwl_files):
            try:
                mode, blocks, chem_label_map = self._blocks_for_exported_gwl_entry(idx, entry)
                rows.extend(
                    self._building_block_rows_from_blocks(
                        blocks,
                        mode,
                        chem_label_map=chem_label_map,
                        include_all_chemicals=True,
                        gwl_name=entry.get("name", "") or Path(entry.get("path", "")).name or f"GWL {idx + 1}",
                    )
                )
            except Exception as exc:
                label = entry.get("name", "") or Path(entry.get("path", "")).name or f"GWL {idx + 1}"
                errors.append(f"{label}: {exc}")

        if not rows:
            detail = "\n\n" + "\n".join(errors[:6]) if errors else ""
            messagebox.showwarning(
                "No GWL chemicals",
                "No Chemical IDs could be pushed from the listed GWL files." + detail,
            )
            return

        if callable(self.push_callback):
            try:
                self.push_callback(rows)
            except TypeError:
                self.push_callback()
        else:
            messagebox.showinfo("Pushed", f"Pushed {len(rows)} chemical well row(s) from listed GWL files.")

        if errors:
            messagebox.showwarning(
                "Some GWLs skipped",
                "Some GWL files could not be read for Cheminformatics push:\n\n"
                + "\n".join(errors[:8])
                + ("\n..." if len(errors) > 8 else ""),
            )

    @staticmethod
    def _chemical_names_from_text(text: object) -> List[str]:
        names: List[str] = []
        for part in re.split(r"\s*\|\s*", str(text or "").strip()):
            value = part.strip()
            if value and value not in names:
                names.append(value)
        return names

    def _building_block_rows_from_blocks(
        self,
        blocks: List[TransferBlock],
        mode: str,
        *,
        chem_label_map: Optional[Dict[str, str]] = None,
        include_all_chemicals: bool = False,
        gwl_name: str = "",
    ) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        chem_label_map = chem_label_map or {}
        for block_index, b in enumerate(blocks, start=1):
            block_chemicals = self._chemical_names_from_text(b.chemical_name)
            if not include_all_chemicals and (not b.is_building_block or not block_chemicals):
                continue

            def add_rows(wells_expr: str, volume: float, *, extra_group: bool = False):
                for idx in parse_dest_well_expr(wells_expr, mode, b.dest_labware):
                    well = index_to_dest_label(idx, mode, b.dest_labware)
                    mapped_chemicals = self._chemical_names_from_text(chem_label_map.get(well, ""))
                    # A block's chemical assignment is the authoritative source for
                    # that transfer.  A destination-level chemical map can contain
                    # every chemical delivered to the well, so preferring it here
                    # would cross-join those chemicals with every block and mix up
                    # per-block metadata such as the building-block flag.  Keep the
                    # map as a fallback for imported GWLs whose blocks have no
                    # chemical assignment of their own.
                    chemicals = block_chemicals or mapped_chemicals
                    for chemical in chemicals:
                        rows.append(
                            {
                                "block": block_index,
                                "gwl": gwl_name,
                                "dest_mode": mode,
                                "summary_block": TecanFrame._block_to_dict(None, b),
                                "source": "Tecan",
                                "chemical": chemical,
                                "well": well,
                                "volume_uL": rounded_gwl_volume(volume),
                                # Extra groups have independently entered volumes,
                                # not the main group's requested amount.
                                **({} if extra_group else {"reaction_umol": b.reaction_umol}),
                                "is_building_block": bool(b.is_building_block),
                                "dest_labware": b.dest_labware,
                                "source_labware": b.source_labware,
                                "source_well": b.source_well,
                            }
                        )

            add_rows(b.dest_wells_expr, b.dest_volume)
            if b.disp_different_vol and b.dispense_groups:
                for group in b.dispense_groups:
                    add_rows(group.wells_expr, group.volume, extra_group=True)
        return rows

    def get_building_block_table(self) -> List[Dict[str, object]]:
        return self._building_block_rows_from_blocks(self.blocks, self.mode_var.get())

    def _blocks_for_exported_gwl_entry(
        self,
        idx: int,
        entry: Dict[str, str],
    ) -> Tuple[str, List[TransferBlock], Dict[str, str]]:
        raw_path = (entry.get("path") or "").strip()
        path = Path(raw_path) if raw_path else None
        mode = str(entry.get("mode", "") or self.mode_var.get() or PLATE_MODES[0])
        if mode not in PLATE_MODES:
            mode = PLATE_MODES[0]
        chem_label_map: Dict[str, str] = {}
        if path:
            csv_guess = path.with_name(path.stem + "_chemical_map.csv")
            if csv_guess.exists():
                chem_label_map = self._read_chemical_map_csv(csv_guess)

        if idx == self._active_gwl_index:
            return self.mode_var.get(), list(self.blocks), chem_label_map

        snapshot_blocks = [
            self._block_from_dict(block_data)
            for block_data in (entry.get("blocks", []) or [])
            if isinstance(block_data, dict)
        ]
        if snapshot_blocks:
            return mode, snapshot_blocks, chem_label_map

        content = str(entry.get("content", "") or "")
        if path and path.exists() and path.is_file():
            content = self._read_text_file(path)
        if not content.strip():
            return mode, [], chem_label_map
        parsed_mode, parsed_blocks = self._blocks_from_gwl_content(
            content,
            source_path=path if path and path.exists() else None,
            ask_mode=False,
            ask_csv=False,
            preferred_mode=mode,
        )
        return parsed_mode, parsed_blocks, chem_label_map

    def _iter_displayed_gwl_blocks(self):
        """Yield every block represented by the GWL files visible in the left list."""
        for entry_index, entry in enumerate(self.exported_gwl_files):
            try:
                mode, blocks, _chem_label_map = self._blocks_for_exported_gwl_entry(entry_index, entry)
            except Exception:
                # A malformed external GWL should remain loadable/reportable elsewhere;
                # it cannot safely contribute inferred occupancy here.
                continue
            for block_index, block in enumerate(blocks):
                yield entry_index, block_index, mode, block

    def _selected_block_identity(self) -> Tuple[int | None, int | None]:
        selected = self.listbox.curselection()
        block_index = selected[0] if selected and 0 <= selected[0] < len(self.blocks) else None
        return self._active_gwl_index, block_index

    def _source_label_availability(
        self,
        labware: str,
        chemical_id: object,
        *,
        exclude_entry_index: int | None = None,
        exclude_block_index: int | None = None,
    ) -> Tuple[Set[str], Set[str]]:
        canonical = self._canonical_labware_name(labware)
        usages: List[Tuple[object, object]] = []
        for entry_index, block_index, _mode, block in self._iter_displayed_gwl_blocks():
            if entry_index == exclude_entry_index and block_index == exclude_block_index:
                continue
            if self._canonical_labware_name(block.source_labware) != canonical:
                continue
            label = source_index_to_label(int(block.source_well), canonical)
            if label:
                usages.append((label, block.chemical_name))
        return classify_source_well_usage(usages, chemical_id)

    def _occupied_source_labels(
        self,
        labware: str,
        *,
        exclude_entry_index: int | None = None,
        exclude_block_index: int | None = None,
    ) -> Set[str]:
        blocked, reusable = self._source_label_availability(
            labware,
            "",
            exclude_entry_index=exclude_entry_index,
            exclude_block_index=exclude_block_index,
        )
        return blocked | reusable

    def _source_well_conflict(
        self,
        labware: str,
        well: int,
        chemical_id: object = "",
        *,
        exclude_entry_index: int | None = None,
        exclude_block_index: int | None = None,
    ) -> str:
        canonical = self._canonical_labware_name(labware)
        desired_chemical = str(chemical_id or "").strip().casefold()
        for entry_index, block_index, _mode, block in self._iter_displayed_gwl_blocks():
            if entry_index == exclude_entry_index and block_index == exclude_block_index:
                continue
            if self._canonical_labware_name(block.source_labware) != canonical or int(block.source_well) != int(well):
                continue
            used_chemical = str(block.chemical_name or "").strip().casefold()
            if desired_chemical and used_chemical == desired_chemical:
                continue
            entry = self.exported_gwl_files[entry_index]
            gwl_name = entry.get("name") or Path(entry.get("path", "")).name or f"GWL {entry_index + 1}"
            label = source_index_to_label(int(well), canonical) or str(well)
            return f"{self._labware_display_name(canonical)} well {label} is already used by block {block_index + 1} in '{gwl_name}'."
        return ""

    def _first_available_source_well(self, labware: str, chemical_id: object = "") -> int | None:
        canonical = self._canonical_labware_name(labware)
        cfg = SOURCE_LAYOUTS.get(canonical)
        if not cfg:
            return None
        blocked, reusable = self._source_label_availability(canonical, chemical_id)
        used = blocked | reusable
        if reusable:
            for well in range(1, int(cfg["rows"]) * int(cfg["cols"]) + 1):
                label = source_index_to_label(well, canonical)
                if label and label.upper() in reusable:
                    return well
        for well in range(1, int(cfg["rows"]) * int(cfg["cols"]) + 1):
            label = source_index_to_label(well, canonical)
            if label and label.upper() not in used:
                return well
        return None

    def _dispensed_destination_labels(self, labware: str) -> Set[str]:
        canonical = self._canonical_labware_name(labware)
        occupied: Set[str] = set()
        for _entry_index, _block_index, mode, block in self._iter_displayed_gwl_blocks():
            if self._canonical_labware_name(block.dest_labware) != canonical:
                continue
            expressions = [block.dest_wells_expr]
            if block.disp_different_vol:
                expressions.extend(group.wells_expr for group in block.dispense_groups)
            for expression in expressions:
                try:
                    indexes = parse_dest_well_expr(expression, mode, block.dest_labware)
                except Exception:
                    continue
                for index in indexes:
                    try:
                        occupied.add(index_to_dest_label(index, mode, block.dest_labware).upper())
                    except Exception:
                        continue
        return occupied

    def _pick_source_well_on_map(self, anchor: Optional[tk.Widget] = None):
        lab = self.v_source_labware.get().strip()
        if not lab:
            messagebox.showwarning("Source labware required", "Please select source labware first.")
            return
        initial = source_index_to_label(int(self.v_source_well.get() or "1"), lab)
        entry_index, block_index = self._selected_block_identity()
        blocked, reusable = self._source_label_availability(
            lab,
            self.v_chemical.get(),
            exclude_entry_index=entry_index,
            exclude_block_index=block_index,
        )
        dlg = SourceWellDialog(
            self,
            lab,
            initial,
            anchor=anchor,
            occupied_labels=blocked,
            reusable_labels=reusable,
        )
        self.wait_window(dlg)
        if getattr(dlg, "result_label", ""):
            self.v_source_well.set(str(source_label_to_index(dlg.result_label, lab)))

    def _pick_wells_on_map(self, anchor: Optional[tk.Widget] = None):
        rows, cols, order = mode_dims_order(self.mode_var.get())
        highlighted = self._dispensed_destination_labels(self.v_dest_labware.get().strip())
        dlg = WellMapDialog(
            self,
            rows,
            cols,
            self.v_dest_wells.get(),
            vertical_view=("vertical" in self.mode_var.get().lower()),
            anchor=anchor,
            highlight_labels=highlighted,
        )
        self.wait_window(dlg)
        if getattr(dlg, "result_labels", ""):
            self.v_dest_wells.set(dlg.result_labels)

    def _build_group_window(self):
        if self.groups_window is not None:
            return
        window = tk.Toplevel(self)
        self.groups_window = window
        window.title("Extra dispense groups - Pinned")
        window.geometry("560x180")
        window.minsize(430, 120)
        window.resizable(True, True)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", self._hide_group_window)

        body = ttk.Frame(window, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="Extra dispense groups for the selected block").grid(row=0, column=0, sticky="w")
        self.groups_frame = ttk.LabelFrame(body, text="Groups", padding=6)
        self.groups_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 8))
        self.groups_frame.columnconfigure(0, weight=1)
        self.groups_frame.rowconfigure(0, weight=1)
        self.groups_canvas = tk.Canvas(self.groups_frame, highlightthickness=0)
        self.groups_scrollbar = ttk.Scrollbar(self.groups_frame, orient="vertical", command=self.groups_canvas.yview)
        self.groups_canvas.configure(yscrollcommand=self.groups_scrollbar.set)
        self.groups_canvas.grid(row=0, column=0, sticky="nsew")
        self.groups_scrollbar.grid(row=0, column=1, sticky="ns")
        self.groups_rows_frame = ttk.Frame(self.groups_canvas)
        self.groups_rows_frame.columnconfigure(0, weight=1)
        self.groups_canvas_window = self.groups_canvas.create_window((0, 0), window=self.groups_rows_frame, anchor="nw")
        self.groups_rows_frame.bind("<Configure>", self._sync_group_scroll_region)
        self.groups_canvas.bind("<Configure>", self._sync_group_canvas_width)
        self.groups_canvas.bind("<Enter>", lambda _event: self.groups_canvas.bind_all("<MouseWheel>", self._group_mousewheel))
        self.groups_canvas.bind("<Leave>", lambda _event: self.groups_canvas.unbind_all("<MouseWheel>"))
        body.rowconfigure(1, weight=1)
        ttk.Button(body, text="+ Add Volume Group", command=self._add_group_row).grid(row=2, column=0, sticky="w")
        window.withdraw()

    def _hide_group_window(self):
        if self.groups_window is None:
            return
        try:
            self.groups_window.withdraw()
        except tk.TclError:
            pass

    def _show_group_window(self):
        if self.groups_window is None:
            self._build_group_window()
        if self.v_diff_vol.get().strip().lower() != "yes":
            return
        try:
            sel = self.listbox.curselection()
            suffix = f" - Block {sel[0] + 1}" if sel else ""
            self.groups_window.title(f"Extra dispense groups{suffix} - Pinned")
            self.groups_window.attributes("-topmost", True)
            self.groups_window.deiconify()
            self.groups_window.lift()
        except tk.TclError:
            pass

    def _sync_group_scroll_region(self, _event=None):
        try:
            self.groups_canvas.configure(scrollregion=self.groups_canvas.bbox("all"))
        except tk.TclError:
            pass

    def _sync_group_canvas_width(self, event):
        try:
            width = max(1, event.width - 4)
            self.groups_canvas.itemconfigure(self.groups_canvas_window, width=width)
            self._sync_group_scroll_region()
        except tk.TclError:
            pass

    def _group_mousewheel(self, event):
        try:
            if self.groups_scrollbar.get() == (0.0, 1.0):
                return
            self.groups_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass

    def _add_group_row(self, volume: str = "", wells: str = ""):
        row = ttk.Frame(self.groups_rows_frame)
        rv = tk.StringVar(value=volume or "")
        rw = tk.StringVar(value=wells or "")
        ttk.Label(row, text=f"V{len(self.group_rows)+2} (uL)").pack(side="left")
        ttk.Entry(row, textvariable=rv, width=8).pack(side="left", padx=(4, 6))
        ttk.Entry(row, textvariable=rw, width=20).pack(side="left", padx=(0, 6))
        map_btn = ttk.Button(row, text="Map")
        map_btn.configure(command=lambda v=rw, b=map_btn: self._pick_group_wells_on_map(v, anchor=b))
        map_btn.pack(side="left", padx=(0, 4))
        ttk.Button(row, text="Remove", command=lambda f=row: self._remove_group_row(f)).pack(side="left")
        row.grid(row=len(self.group_rows), column=0, sticky="ew", pady=2)
        rv.trace_add("write", self._on_group_change)
        rw.trace_add("write", self._on_group_change)
        self.group_rows.append({"frame": row, "vol": rv, "wells": rw})
        if volume or wells:
            self._on_group_change()
        self.groups_rows_frame.after_idle(self._sync_group_scroll_region)
        self.groups_canvas.after_idle(lambda: self.groups_canvas.yview_moveto(1.0))

    def _remove_group_row(self, frame):
        for i, g in enumerate(self.group_rows):
            if g["frame"] == frame:
                g["frame"].destroy()
                del self.group_rows[i]
                break
        for i, g in enumerate(self.group_rows):
            g["frame"].grid_configure(row=i)
        self.groups_rows_frame.after_idle(self._sync_group_scroll_region)
        self._on_group_change()

    def _pick_group_wells_on_map(self, target_var: tk.StringVar, anchor: Optional[tk.Widget] = None):
        rows, cols, _order = mode_dims_order(self.mode_var.get())
        highlighted = self._dispensed_destination_labels(self.v_dest_labware.get().strip())
        dlg = WellMapDialog(
            self,
            rows,
            cols,
            target_var.get(),
            vertical_view=("vertical" in self.mode_var.get().lower()),
            anchor=anchor,
            highlight_labels=highlighted,
        )
        self.wait_window(dlg)
        if getattr(dlg, "result_labels", ""):
            target_var.set(dlg.result_labels)

    def _render_group_visibility(self):
        state = (self.v_diff_vol.get().strip().lower() == "yes")
        if state:
            if self.groups_open_button is not None:
                self.groups_open_button.grid()
            self._show_group_window()
        else:
            if self.groups_open_button is not None:
                self.groups_open_button.grid_remove()
            self._hide_group_window()

    def _on_diff_toggle(self, *_args):
        if self._updating_form:
            return
        self._render_group_visibility()
        self._on_group_change()

    def _on_group_change(self, *_args):
        self._sync_source_volume_to_dispense_total()
        self._on_form_change_autosave()

    def _set_block_editor_enabled(self, enabled: bool):
        for widget, active_state in getattr(self, "_block_editor_controls", []):
            try:
                widget.configure(state=active_state if enabled else "disabled")
            except tk.TclError:
                continue
        if not enabled:
            self._hide_group_window()

    def _open_batch_addition(self):
        from tecan_batch_dialog import TecanBatchDialog
        idx, entry = self._selected_gwl_entry()
        if entry is None or idx != self._active_gwl_index:
            messagebox.showwarning("No GWL selected", "Create or select a GWL before adding a batch.", parent=self)
            return
        if self.mode_var.get() not in PLATE_MODES:
            messagebox.showwarning("Destination format required", "Select a destination format first.", parent=self)
            return
        dialog = TecanBatchDialog(self)
        self.wait_window(dialog)

    def _add_block(self):
        selected_gwl = self.gwl_listbox.curselection()
        if (
            self._active_gwl_index is None
            or self._active_gwl_index < 0
            or self._active_gwl_index >= len(self.exported_gwl_files)
            or not selected_gwl
            or selected_gwl[0] != self._active_gwl_index
        ):
            messagebox.showwarning(
                "No GWL selected",
                "Create a new GWL or select an existing GWL before adding a transfer block.",
            )
            return
        if self.mode_var.get() not in PLATE_MODES:
            messagebox.showwarning("Destination format required", "Select a destination format first.", parent=self)
            return
        default_dest = ""
        source_labware = SOURCE_LABWARE_OPTIONS[0]
        source_well = self._first_available_source_well(source_labware)
        if source_well is None:
            for candidate in SOURCE_LABWARE_OPTIONS[1:]:
                candidate_well = self._first_available_source_well(candidate)
                if candidate_well is not None:
                    source_labware = candidate
                    source_well = candidate_well
                    break
        if source_well is None:
            messagebox.showwarning(
                "No source wells available",
                "Every source well in the configured source labware is already used by a displayed GWL block.",
            )
            return
        self.blocks.append(
            TransferBlock(
                source_labware=source_labware,
                source_well=source_well,
                dest_labware=default_dest,
                liquid_class=self._default_liquid_class(),
            )
        )
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set("end")
        self._on_select(None)

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for i, b in enumerate(self.blocks, start=1):
            src_lbl = source_index_to_label(b.source_well, b.source_labware) or str(b.source_well)
            try:
                idxs = parse_dest_well_expr(b.dest_wells_expr, self.mode_var.get(), b.dest_labware)
                lbls = [index_to_dest_label(x, self.mode_var.get(), b.dest_labware) for x in idxs[:6]]
                dest = ",".join(lbls) + (",..." if len(idxs) > 6 else "")
            except Exception:
                dest = "(invalid)"
            src_display = self._labware_display_name(b.source_labware)
            dest_display = self._labware_display_name(b.dest_labware)
            self.listbox.insert("end", f"{i:02d} | {src_display}:{src_lbl} -> {dest_display} [{dest}]")
        self._set_block_editor_enabled(False)

    def _on_select(self, _evt):
        sel = self.listbox.curselection()
        if not sel:
            self._set_block_editor_enabled(False)
            return
        self._set_block_editor_enabled(True)
        b = self.blocks[sel[0]]
        self._updating_form = True
        try:
            self.v_source_labware.set(b.source_labware)
            self.v_source_well.set(str(b.source_well))
            self.v_source_volume.set(f"{b.source_volume:.15g}")
            self.v_dest_labware.set(b.dest_labware)
            self._refresh_dest_labware_options()
            self.v_dest_wells.set(b.dest_wells_expr)
            self.v_dest_volume.set(f"{b.dest_volume:.15g}")
            self.v_liquid_class.set(b.liquid_class)
            self.v_chemical.set(b.chemical_name)
            self.v_reaction_umol.set(str(getattr(b, "reaction_umol", "") or ""))
            self.v_extra_aspirate_percent.set(str(getattr(b, "extra_aspirate_percent", "") or ""))
            self.v_is_building_block.set(b.is_building_block)
            self.v_wash.set(b.add_wash)
            self.v_diff_vol.set("Yes" if b.disp_different_vol else "No")
            for g in self.group_rows:
                g["frame"].destroy()
            self.group_rows = []
            for grp in b.dispense_groups:
                self._add_group_row(str(grp.volume), grp.wells_expr)
            if not self.group_rows:
                self._add_group_row()
            self._render_group_visibility()
        finally:
            self._updating_form = False
        if self.v_show_structure.get():
            self._refresh_structure_window()

    def _on_form_change_autosave(self, *_args):
        if self._updating_form:
            return
        self._apply_current(silent=True)

    def _apply_current(self, silent: bool = False, show_success: bool = True):
        sel = self.listbox.curselection()
        if not sel:
            if not silent:
                messagebox.showwarning("No block selected", "Please select a transfer block first.")
            return False
        i = sel[0]
        try:
            src_lab = self._canonical_labware_name(self.v_source_labware.get().strip())
            src_well = int(self.v_source_well.get().strip())
            src_vol = rounded_gwl_volume(float(self.v_source_volume.get().strip()))
            dst_lab = self._canonical_labware_name(self.v_dest_labware.get().strip())
            dst_expr = self.v_dest_wells.get().strip()
            dst_vol = rounded_gwl_volume(float(self.v_dest_volume.get().strip()))
            liquid = self.v_liquid_class.get().strip()
            chem = self.v_chemical.get().strip()
            reaction_umol = self.v_reaction_umol.get().strip()
            extra_aspirate_percent = self.v_extra_aspirate_percent.get().strip()
            wash = bool(self.v_wash.get())
            diff_vol = self.v_diff_vol.get().strip().lower() == "yes"

            if not src_lab:
                raise ValueError("Source labware required")
            if src_well <= 0:
                raise ValueError("Source well must be > 0")
            if src_vol <= 0:
                raise ValueError("Aspirate volume must be greater than 0 uL")
            if dst_vol <= 0:
                raise ValueError("Dispense volume must be greater than 0 uL")
            if src_lab in SOURCE_LAYOUTS:
                max_src = SOURCE_LAYOUTS[src_lab]["rows"] * SOURCE_LAYOUTS[src_lab]["cols"]
                if src_well > max_src:
                    raise ValueError(f"Source well out of range for {src_lab}: 1..{max_src}")
            conflict = self._source_well_conflict(
                src_lab,
                src_well,
                chem,
                exclude_entry_index=self._active_gwl_index,
                exclude_block_index=i,
            )
            if conflict:
                raise ValueError(conflict + " Choose an unused source well or use the same Chemical ID.")
            if not dst_lab or not liquid:
                raise ValueError("Destination labware and liquid class are required")

            # Destination labware can be selected from defaults or typed manually.
            # Keep defaults as suggestions, but do not hard-restrict to the preset list.
            parse_dest_well_expr(dst_expr, self.mode_var.get(), dst_lab)

            groups: List[DispenseGroup] = []
            base_wells = parse_dest_well_expr(dst_expr, self.mode_var.get(), dst_lab)
            total_dispense = dst_vol * len(base_wells)
            if diff_vol:
                for g in self.group_rows:
                    vtxt = g["vol"].get().strip()
                    wtxt = g["wells"].get().strip()
                    if not vtxt and not wtxt:
                        continue
                    if not vtxt or not wtxt:
                        raise ValueError("Each extra group needs both volume and wells")
                    gvol = rounded_gwl_volume(float(vtxt))
                    if gvol <= 0:
                        raise ValueError("Each extra-group dispense volume must be greater than 0 uL")
                    gwells = parse_dest_well_expr(wtxt, self.mode_var.get(), dst_lab)
                    total_dispense += gvol * len(gwells)
                    groups.append(DispenseGroup(volume=gvol, wells_expr=wtxt))

            if (not silent) and total_dispense > src_vol + 1e-9:
                raise ValueError(f"Total dispense volume ({total_dispense:.1f} uL) exceeds aspirate volume ({src_vol:.1f} uL)")

            self.blocks[i] = TransferBlock(
                src_lab,
                src_well,
                src_vol,
                dst_lab,
                dst_expr,
                dst_vol,
                liquid,
                chem,
                wash,
                diff_vol,
                groups,
                bool(self.v_is_building_block.get()),
                reaction_umol,
                extra_aspirate_percent,
            )
            self._refresh_list()
            self.listbox.selection_set(i)
            self._on_select(None)
            if (not silent) and show_success:
                messagebox.showinfo("Applied", f"Block {i+1} updated.")
            return True
        except Exception as exc:
            if not silent:
                messagebox.showerror("Validation error", str(exc))
            return False

    def _block_to_dict(self, block: TransferBlock) -> Dict[str, object]:
        return {
            "source_labware": block.source_labware,
            "source_well": block.source_well,
            "source_volume": rounded_gwl_volume(block.source_volume),
            "dest_labware": block.dest_labware,
            "dest_wells_expr": block.dest_wells_expr,
            "dest_volume": rounded_gwl_volume(block.dest_volume),
            "liquid_class": block.liquid_class,
            "chemical_name": block.chemical_name,
            "add_wash": block.add_wash,
            "disp_different_vol": block.disp_different_vol,
            "dispense_groups": [
                {"volume": rounded_gwl_volume(group.volume), "wells_expr": group.wells_expr}
                for group in block.dispense_groups
            ],
            "is_building_block": block.is_building_block,
            "reaction_umol": block.reaction_umol,
            "extra_aspirate_percent": block.extra_aspirate_percent,
        }

    def _block_from_dict(self, data: Dict[str, object]) -> TransferBlock:
        groups = [
            DispenseGroup(
                volume=rounded_gwl_volume(float(group.get("volume", 20.0))),
                wells_expr=str(group.get("wells_expr", "")),
            )
            for group in data.get("dispense_groups", []) or []
            if isinstance(group, dict)
        ]
        return TransferBlock(
            source_labware=self._canonical_labware_name(str(data.get("source_labware", SOURCE_LABWARE_OPTIONS[0]))),
            source_well=int(data.get("source_well", 1) or 1),
            source_volume=rounded_gwl_volume(float(data.get("source_volume", 20.0) or 20.0)),
            dest_labware=self._canonical_labware_name(str(data.get("dest_labware", "DeepPlate1"))),
            dest_wells_expr=str(data.get("dest_wells_expr", "")),
            dest_volume=rounded_gwl_volume(float(data.get("dest_volume", 20.0) or 20.0)),
            liquid_class=str(data.get("liquid_class", self._default_liquid_class())),
            chemical_name=str(data.get("chemical_name", "")),
            add_wash=bool(data.get("add_wash", True)),
            disp_different_vol=bool(data.get("disp_different_vol", False)),
            dispense_groups=groups,
            is_building_block=bool(data.get("is_building_block", False)),
            reaction_umol=str(data.get("reaction_umol", "") or data.get("umol", "") or ""),
            extra_aspirate_percent=str(data.get("extra_aspirate_percent", "") or ""),
        )

    def _hydrate_exported_gwl_snapshots(self):
        current_blocks_snapshot = [self._block_to_dict(block) for block in self.blocks]
        current_content = ""
        if self.blocks:
            try:
                current_content = "\n".join(self._build_lines()) + "\n"
            except Exception:
                current_content = ""
        for entry in self.exported_gwl_files:
            if not entry.get("mode") and (entry.get("blocks") or entry.get("content")):
                entry["mode"] = self.mode_var.get()
            raw_path = (entry.get("path") or "").strip()
            path = Path(raw_path) if raw_path else None
            entry_content = str(entry.get("content", "") or "")
            if path and path.exists() and path.is_file():
                try:
                    entry_content = self._read_text_file(path)
                    entry["content"] = entry_content
                except Exception:
                    pass
            if not entry.get("blocks") and current_blocks_snapshot:
                if (not entry_content.strip()) or self._normalize_gwl_content(entry_content) == self._normalize_gwl_content(current_content):
                    entry["blocks"] = [dict(block) for block in current_blocks_snapshot]
            if not entry.get("blocks") and entry_content.strip():
                try:
                    mode, blocks = self._blocks_from_gwl_content(
                        entry_content,
                        source_path=path if path and path.exists() else None,
                        ask_mode=False,
                        ask_csv=False,
                        preferred_mode=str(entry.get("mode", "") or "") or None,
                    )
                    entry["mode"] = mode
                    entry["blocks"] = [self._block_to_dict(block) for block in blocks]
                except Exception:
                    pass

    def export_state(self) -> Dict[str, object]:
        if self.listbox.curselection():
            self._apply_current(silent=True)
        self._hydrate_exported_gwl_snapshots()
        return {
            "mode": self.mode_var.get(),
            "save_chemical_map": bool(self.v_save_map.get()),
            "labware_aliases": dict(self.labware_aliases),
            "blocks": [self._block_to_dict(block) for block in self.blocks],
            "exported_gwl_files": list(self.exported_gwl_files),
        }

    def import_state(self, data: Dict[str, object]):
        validate_gwl_names(data.get("exported_gwl_files", []) or [])
        self.mode_var.set(str(data.get("mode", PLATE_MODES[0]) or (PLATE_MODES[0] if data.get("blocks") else "")))
        if "labware_aliases" in data:
            self.set_labware_aliases(data.get("labware_aliases", {}) or {}, persist=False)
        self.blocks = [
            self._block_from_dict(item)
            for item in data.get("blocks", []) or []
            if isinstance(item, dict)
        ]
        self.v_save_map.set(bool(data.get("save_chemical_map", True)))
        self.exported_gwl_files = [
            {
                "path": str(item.get("path", "")),
                "name": str(item.get("name", "") or Path(str(item.get("path", ""))).name),
                "content": str(item.get("content", "")),
                "mode": str(item.get("mode", "") or ""),
                "blocks": list(item.get("blocks", []) or []),
                "portable_path": str(item.get("portable_path", "") or ""),
                "portable_source_path": str(item.get("portable_source_path", "") or ""),
                "portable_chemical_map_path": str(item.get("portable_chemical_map_path", "") or ""),
                "portable_chemical_map_source_path": str(item.get("portable_chemical_map_source_path", "") or ""),
                "requires_save_as": bool(item.get("requires_save_as", False)),
            }
            for item in data.get("exported_gwl_files", []) or []
            if isinstance(item, dict)
        ]
        self._hydrate_exported_gwl_snapshots()
        self._refresh_dest_labware_options()
        self._refresh_list()
        self._refresh_gwl_list()
        if self.blocks:
            self.listbox.selection_set(0)
            self._on_select(None)
        else:
            self._active_gwl_index = None
            self._active_gwl_snapshot = ""
            self._active_gwl_blocks_snapshot = ""
            self._updating_form = True
            try:
                self.v_source_labware.set(SOURCE_LABWARE_OPTIONS[0])
                self.v_source_well.set("1")
                self.v_source_volume.set("20.0")
                self.v_dest_labware.set("")
                self.v_dest_wells.set("")
                self.v_dest_volume.set("20.0")
                self.v_liquid_class.set(self._default_liquid_class())
                self.v_chemical.set("")
                self.v_reaction_umol.set("")
                self.v_extra_aspirate_percent.set("")
                self.v_is_building_block.set(False)
                self.v_wash.set(True)
                self.v_diff_vol.set("No")
            finally:
                self._updating_form = False
            self._render_group_visibility()

    def _check_gwl_filename(self, path: Path, *, replace_index=None, update_same_path=False):
        if update_same_path and replace_index is None:
            target = str(path).replace("\\", "/").casefold()
            replace_index = next((i for i, entry in enumerate(self.exported_gwl_files)
                                  if str(entry.get("path", "")).replace("\\", "/").casefold() == target), None)
        entries = [entry for i, entry in enumerate(self.exported_gwl_files) if i != replace_index]
        validate_gwl_names(entries + [{"name": path.name}])

    def _track_exported_gwl(self, path: Path, content: str, *, mode: str | None = None, blocks: Optional[List[TransferBlock]] = None):
        self._check_gwl_filename(path, update_same_path=True)
        path_text = str(path)
        entry = {
            "path": path_text,
            "name": path.name,
            "content": content,
            "mode": mode or self.mode_var.get(),
            "blocks": [self._block_to_dict(block) for block in (blocks if blocks is not None else self.blocks)],
        }
        for i, existing in enumerate(self.exported_gwl_files):
            if str(existing.get("path", "")).replace("\\", "/").casefold() == path_text.replace("\\", "/").casefold():
                self.exported_gwl_files[i] = entry
                if blocks is None and i == self._active_gwl_index:
                    # Save As can target the current filename. Reselection is
                    # now a no-op, so record the successful save explicitly.
                    self._active_gwl_snapshot = content
                    self._active_gwl_blocks_snapshot = self._current_gwl_blocks_snapshot()
                break
        else:
            self.exported_gwl_files.append(entry)
        self._refresh_gwl_list(select_path=path_text)

    def _refresh_gwl_list(self, select_path: str = ""):
        self.gwl_listbox.delete(0, "end")
        selected = None
        for i, entry in enumerate(self.exported_gwl_files):
            label = entry.get("name") or Path(entry.get("path", "")).name or f"GWL {i + 1}"
            self.gwl_listbox.insert("end", label)
            if select_path and entry.get("path") == select_path:
                selected = i
        if selected is not None:
            self.gwl_listbox.selection_set(selected)
            self._on_gwl_select()

    def _default_gwl_directory(self) -> Path | None:
        selected = self.gwl_listbox.curselection()
        indexes = list(selected) + list(range(len(self.exported_gwl_files)))
        seen = set()
        for idx in indexes:
            if idx in seen or idx < 0 or idx >= len(self.exported_gwl_files):
                continue
            seen.add(idx)
            raw_path = (self.exported_gwl_files[idx].get("path") or "").strip()
            if not raw_path:
                continue
            try:
                parent = Path(raw_path).expanduser().parent
            except Exception:
                continue
            if parent.exists() and parent.is_dir():
                return parent
        return None

    def _new_blank_gwl(self):
        # Resolve edits to the current GWL before asking for the new file name or
        # clearing the editor.  In particular, the Save branch must still point
        # at the current entry so it cannot overwrite that entry with a blank
        # workspace.
        if not self._confirm_gwl_switch_if_dirty(-1, action="creating a new GWL"):
            return

        default_dir = self._default_gwl_directory()
        name = simpledialog.askstring(
            "New GWL",
            "Name for the new GWL:",
            parent=self.winfo_toplevel(),
        )
        if name is None:
            return
        name = (name or "").strip()
        if not name:
            messagebox.showwarning("New GWL", "Please enter a GWL name.")
            return
        if not name.lower().endswith(".gwl"):
            name += ".gwl"

        dialog_options = {
            "title": "Choose New GWL Location",
            "defaultextension": ".gwl",
            "initialfile": name,
            "filetypes": [("GWL", "*.gwl"), ("All files", "*.*")],
        }
        if default_dir is not None:
            dialog_options["initialdir"] = str(default_dir)
        out = filedialog.asksaveasfilename(**dialog_options)
        if not out:
            return

        path = Path(out)
        if not path.is_absolute():
            messagebox.showerror("Choose a save location", "Please choose a full folder and filename for the new GWL. No GWL was added.")
            return
        if path.suffix.lower() != ".gwl":
            path = path.with_suffix(".gwl")
        try:
            self._check_gwl_filename(path)
        except ValueError as exc:
            messagebox.showerror("GWL filenames", str(exc), parent=self)
            return
        entry = {"path": str(path), "name": path.name, "content": "", "mode": "", "blocks": []}
        path_text = str(path)
        for i, existing in enumerate(self.exported_gwl_files):
            if existing.get("path") == path_text:
                self.exported_gwl_files[i] = entry
                break
        else:
            self.exported_gwl_files.append(entry)

        self._active_gwl_index = None
        self._active_gwl_snapshot = ""
        self._active_gwl_blocks_snapshot = ""
        self.blocks = []
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        if self.v_show_structure.get():
            self.v_chemical.set("")
            self._refresh_structure_window()
        self._refresh_gwl_list(select_path=path_text)

        messagebox.showinfo(
            "Select destination format",
            "Select a Destination format to enable Add Block and Add Batch.",
            parent=self.winfo_toplevel(),
        )
        self.mode_combo.focus_set()

    def _selected_gwl_entry(self) -> Tuple[int, Dict[str, str]] | Tuple[None, None]:
        sel = self.gwl_listbox.curselection()
        if not sel:
            return None, None
        idx = sel[0]
        if idx < 0 or idx >= len(self.exported_gwl_files):
            return None, None
        return idx, self.exported_gwl_files[idx]

    def _normalize_gwl_content(self, content: str) -> str:
        return "\n".join((content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()).strip()

    def _current_gwl_blocks_snapshot(self) -> str:
        payload = {
            "mode": self.mode_var.get(),
            "blocks": [self._block_to_dict(block) for block in self.blocks],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _current_gwl_content(self, apply_form: bool = True) -> str:
        if apply_form and self.listbox.curselection():
            self._apply_current(silent=True)
        if not self.blocks:
            return ""
        return "\n".join(self._build_lines()) + "\n"

    def _current_gwl_has_unsaved_changes(self) -> bool:
        if self._active_gwl_index is None:
            return False
        if self._active_gwl_index < 0 or self._active_gwl_index >= len(self.exported_gwl_files):
            return False
        selected = self.listbox.curselection()
        if selected:
            idx = selected[0]
            if 0 <= idx < len(self.blocks):
                try:
                    if self._collect_form_block() != self.blocks[idx]:
                        return True
                except Exception:
                    # Partially typed or invalid form values are still work that
                    # must not disappear without a save/discard decision.
                    return True
        try:
            current = self._current_gwl_content(apply_form=True)
        except Exception:
            return True
        if self._normalize_gwl_content(current) != self._normalize_gwl_content(self._active_gwl_snapshot):
            return True
        return self._current_gwl_blocks_snapshot() != self._active_gwl_blocks_snapshot

    def _set_gwl_list_selection(self, idx: int | None):
        self._switching_gwl_selection = True
        try:
            self.gwl_listbox.selection_clear(0, "end")
            if idx is not None and 0 <= idx < len(self.exported_gwl_files):
                self.gwl_listbox.selection_set(idx)
                self.gwl_listbox.activate(idx)
        finally:
            self._switching_gwl_selection = False

    def _save_gwl_entry_edits(self, idx: int, show_success: bool = True) -> bool:
        if idx < 0 or idx >= len(self.exported_gwl_files):
            return False
        entry = self.exported_gwl_files[idx]
        raw_path = (entry.get("path") or "").strip()
        requires_save_as = bool(entry.get("requires_save_as", False))
        path = Path(raw_path) if raw_path and not requires_save_as and Path(raw_path).is_absolute() else None
        if path is None:
            default_dir = self._default_gwl_directory()
            dialog_options = {
                "title": "Choose a local location for the imported GWL" if requires_save_as else "Save GWL edits",
                "defaultextension": ".gwl",
                "filetypes": [("GWL", "*.gwl"), ("All files", "*.*")],
                "initialfile": entry.get("name") or "",
            }
            if default_dir is not None:
                dialog_options["initialdir"] = str(default_dir)
            out = filedialog.asksaveasfilename(**dialog_options)
            if not out:
                return False
            path = Path(out)
            if not path.is_absolute():
                messagebox.showerror("Choose a save location", "Please choose a full folder and filename. No GWL was saved.")
                return False
        if path.suffix.lower() != ".gwl":
            path = path.with_suffix(".gwl")
        try:
            self._check_gwl_filename(path, replace_index=idx)
        except ValueError as exc:
            messagebox.showerror("GWL filenames", str(exc), parent=self)
            return False
        if self.listbox.curselection() and not self._apply_current(silent=False, show_success=False):
            return False
        try:
            content = self._current_gwl_content(apply_form=False)
        except Exception as exc:
            messagebox.showerror("Save GWL edits", str(exc))
            return False
        path.write_text(content, encoding="utf-8")
        msg = [f"Saved edits:\n{path}"]
        if self.v_save_map.get():
            csv_path = path.with_name(path.stem + "_chemical_map.csv")
            self._write_chemical_map_csv(csv_path)
            msg.append(f"\nSaved chemical map:\n{csv_path}")
        self.exported_gwl_files[idx] = {
            "path": str(path),
            "name": path.name,
            "content": content,
            "mode": self.mode_var.get(),
            "blocks": [self._block_to_dict(block) for block in self.blocks],
            "portable_path": "",
            "portable_source_path": "",
            "portable_chemical_map_path": "",
            "portable_chemical_map_source_path": "",
            "requires_save_as": False,
        }
        if idx == self._active_gwl_index:
            self._active_gwl_snapshot = content
            self._active_gwl_blocks_snapshot = self._current_gwl_blocks_snapshot()
        if show_success:
            messagebox.showinfo("GWL saved", "\n".join(msg))
        return True

    def _confirm_gwl_switch_if_dirty(self, target_idx: int, action: str = "opening another GWL") -> bool:
        if self._active_gwl_index is None or target_idx == self._active_gwl_index:
            return True
        if not self._current_gwl_has_unsaved_changes():
            return True
        current = self.exported_gwl_files[self._active_gwl_index]
        label = current.get("name") or Path(current.get("path", "")).name or "current GWL"
        answer = messagebox.askyesnocancel(
            "Save GWL changes?",
            f"You changed blocks in '{label}'.\n\nSave changes before {action}?",
        )
        if answer is None:
            return False
        if answer is True:
            return self._save_gwl_entry_edits(self._active_gwl_index, show_success=False)
        return True

    def confirm_leave_current_gwl(self) -> bool:
        return self._confirm_gwl_switch_if_dirty(-1, action="leaving the Tecan GWL Builder tab")

    def _load_gwl_entry(self, idx: int, entry: Dict[str, str]):
        content = entry.get("content", "")
        raw_path = (entry.get("path") or "").strip()
        path = Path(raw_path) if raw_path else None
        if path and path.exists() and path.is_file():
            try:
                content = self._read_text_file(path)
                entry["content"] = content
            except Exception:
                pass
        snapshot_blocks = [
            self._block_from_dict(block_data)
            for block_data in (entry.get("blocks", []) or [])
            if isinstance(block_data, dict)
        ]
        if snapshot_blocks:
            mode = str(entry.get("mode", "") or self.mode_var.get() or PLATE_MODES[0])
            if mode not in PLATE_MODES:
                mode = PLATE_MODES[0]
            self.mode_var.set(mode)
            self.blocks = snapshot_blocks
            self._refresh_dest_labware_options()
            self._refresh_list()
            self.listbox.selection_clear(0, "end")
            if self.blocks:
                self.listbox.selection_set(0)
                self._on_select(None)
            self._active_gwl_index = idx
            try:
                self._active_gwl_snapshot = self._current_gwl_content(apply_form=False)
            except Exception:
                self._active_gwl_snapshot = content
            self._active_gwl_blocks_snapshot = self._current_gwl_blocks_snapshot()
            return
        if not content.strip():
            self.blocks = []
            self.mode_var.set(str(entry.get("mode", "") or ""))
            self.v_dest_labware.set("")
            self._refresh_list()
            self.listbox.selection_clear(0, "end")
            self._active_gwl_index = idx
            self._active_gwl_snapshot = ""
            self._active_gwl_blocks_snapshot = self._current_gwl_blocks_snapshot()
            if self.v_show_structure.get():
                self.v_chemical.set("")
                self._refresh_structure_window()
            return
        preferred_mode = str(entry.get("mode", "") or "") or None
        mode, blocks = self._blocks_from_gwl_content(
            content,
            source_path=path if path and path.exists() else None,
            ask_mode=False,
            ask_csv=False,
            preferred_mode=preferred_mode,
        )
        self.mode_var.set(mode)
        self.blocks = blocks
        self._refresh_dest_labware_options()
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        if self.blocks:
            self.listbox.selection_set(0)
            self._on_select(None)
        self._active_gwl_index = idx
        try:
            self._active_gwl_snapshot = self._current_gwl_content(apply_form=False)
        except Exception:
            self._active_gwl_snapshot = content
        self._active_gwl_blocks_snapshot = self._current_gwl_blocks_snapshot()

    def _on_gwl_select(self, _event=None, *, force_reload: bool = False):
        if self._switching_gwl_selection:
            return
        idx, entry = self._selected_gwl_entry()
        if not entry:
            return
        if idx is None:
            return
        # The desktop renderer sends selection events even for the highlighted
        # row. Reopening its saved snapshot would discard live block edits.
        if idx == self._active_gwl_index and not force_reload:
            return
        previous_idx = self._active_gwl_index
        if not self._confirm_gwl_switch_if_dirty(idx):
            self._set_gwl_list_selection(previous_idx)
            return
        try:
            self._load_gwl_entry(idx, entry)
        except Exception as exc:
            self._set_gwl_list_selection(previous_idx)
            messagebox.showerror("GWL load error", str(exc))

    def _choose_gwl_import_mode(self, filename):
        """GWL numeric addresses do not encode plate size or orientation."""
        dialog = tk.Toplevel(self)
        dialog.title("GWL destination format")
        dialog.transient(self.winfo_toplevel())
        result = [None]
        selection = tk.StringVar(master=dialog, value="")
        ttk.Label(dialog, text=f"Select the destination format used to generate {filename}.\n"
                  "GWL files contain numeric positions, not plate size or orientation.",
                  padding=12, wraplength=480).pack(fill="x")
        box = ttk.Combobox(dialog, textvariable=selection, values=PLATE_MODES, state="readonly", width=30)
        box.pack(padx=12, pady=8, fill="x")
        def accept():
            if selection.get() not in PLATE_MODES:
                messagebox.showwarning("Destination format", "Select a plate size and orientation.", parent=dialog)
                return
            result[0] = selection.get()
            dialog.destroy()
        buttons = ttk.Frame(dialog, padding=12)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Import", command=accept).pack(side="right", padx=8)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        box.focus_set()
        self.wait_window(dialog)
        return result[0]

    def _add_existing_gwl(self):
        paths = filedialog.askopenfilenames(filetypes=[("GWL", "*.gwl"), ("All files", "*.*")])
        if not paths:
            return
        last_path = None
        for p in paths:
            path = Path(p)
            try:
                self._check_gwl_filename(path)
            except ValueError as exc:
                messagebox.showerror("GWL filenames", str(exc), parent=self)
                continue
            content = self._read_text_file(path)
            mode = self._choose_gwl_import_mode(path.name)
            if mode is None:
                continue
            blocks: List[TransferBlock] = []
            if content.strip():
                try:
                    mode, blocks = self._blocks_from_gwl_content(
                        content,
                        source_path=path,
                        ask_mode=False,
                        ask_csv=False,
                        preferred_mode=mode,
                    )
                except ValueError as exc:
                    messagebox.showerror("GWL import error", f"{path.name}:\n{exc}", parent=self)
                    continue
            self._track_exported_gwl(path, content, mode=mode, blocks=blocks)
            last_path = str(path)
        if last_path:
            self._refresh_gwl_list(select_path=last_path)

    def _save_selected_gwl_edits(self):
        idx, entry = self._selected_gwl_entry()
        if entry is None:
            messagebox.showwarning("No GWL selected", "Select a GWL file from the list first.")
            return
        if self._save_gwl_entry_edits(idx, show_success=True):
            saved_path = self.exported_gwl_files[idx].get("path", "")
            self._refresh_gwl_list(select_path=saved_path)

    def _reload_selected_gwl(self):
        _idx, entry = self._selected_gwl_entry()
        if entry is None:
            return
        path = Path(entry.get("path", ""))
        if not path.exists():
            messagebox.showwarning("Missing file", f"File not found:\n{path}")
            return
        entry["content"] = self._read_text_file(path)
        self._on_gwl_select(force_reload=True)

    def _remove_selected_gwl(self):
        idx, _entry = self._selected_gwl_entry()
        if idx is None:
            return
        del self.exported_gwl_files[idx]
        if self._active_gwl_index == idx:
            self._active_gwl_index = None
            self._active_gwl_snapshot = ""
            self._active_gwl_blocks_snapshot = ""
        elif self._active_gwl_index is not None and self._active_gwl_index > idx:
            self._active_gwl_index -= 1
        self._refresh_gwl_list()

    def _copy_selected_block(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return "break"
        b = self.blocks[sel[0]]
        self.copied_block = TransferBlock(
            source_labware=b.source_labware,
            source_well=b.source_well,
            source_volume=b.source_volume,
            dest_labware=b.dest_labware,
            dest_wells_expr=b.dest_wells_expr,
            dest_volume=b.dest_volume,
            liquid_class=b.liquid_class,
            chemical_name=b.chemical_name,
            add_wash=b.add_wash,
            disp_different_vol=b.disp_different_vol,
            dispense_groups=[DispenseGroup(volume=g.volume, wells_expr=g.wells_expr) for g in b.dispense_groups],
            is_building_block=b.is_building_block,
            reaction_umol=b.reaction_umol,
            extra_aspirate_percent=b.extra_aspirate_percent,
        )
        return "break"

    def _paste_block(self, _event=None):
        if self.copied_block is None:
            return "break"

        b = self.copied_block
        source_well = self._first_available_source_well(b.source_labware, b.chemical_name)
        if source_well is None:
            messagebox.showwarning(
                "No source well available",
                f"All wells in {self._labware_display_name(b.source_labware)} are already used by displayed GWL blocks.",
            )
            return "break"
        new_block = TransferBlock(
            source_labware=b.source_labware,
            source_well=source_well,
            source_volume=b.source_volume,
            dest_labware=b.dest_labware,
            dest_wells_expr=b.dest_wells_expr,
            dest_volume=b.dest_volume,
            liquid_class=b.liquid_class,
            chemical_name=b.chemical_name,
            add_wash=b.add_wash,
            disp_different_vol=b.disp_different_vol,
            dispense_groups=[DispenseGroup(volume=g.volume, wells_expr=g.wells_expr) for g in b.dispense_groups],
            is_building_block=b.is_building_block,
            reaction_umol=b.reaction_umol,
            extra_aspirate_percent=b.extra_aspirate_percent,
        )

        sel = self.listbox.curselection()
        insert_at = sel[0] + 1 if sel else len(self.blocks)
        self.blocks.insert(insert_at, new_block)
        self._refresh_list()
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(insert_at)
        self._on_select(None)
        return "break"

    def _move_up(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        self.blocks[i-1], self.blocks[i] = self.blocks[i], self.blocks[i-1]
        self._refresh_list()
        self.listbox.selection_set(i-1)
        self._on_select(None)

    def _move_down(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.blocks)-1:
            return
        i = sel[0]
        self.blocks[i+1], self.blocks[i] = self.blocks[i], self.blocks[i+1]
        self._refresh_list()
        self.listbox.selection_set(i+1)
        self._on_select(None)

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        del self.blocks[sel[0]]
        self._refresh_list()

    def _delete_selected_event(self, _event=None):
        self._delete_selected()
        return "break"

    def _clear_all_blocks(self):
        if not self.blocks:
            return
        if messagebox.askyesno("Clear all", "Remove all transfer blocks?"):
            self.blocks.clear()
            self._refresh_list()

    def _build_lines(self) -> List[str]:
        conflicts = {
            index: self._source_well_conflict(
                block.source_labware, block.source_well, block.chemical_name,
                exclude_entry_index=self._active_gwl_index,
                exclude_block_index=index - 1,
            )
            for index, block in enumerate(self.blocks, start=1)
        }
        return build_gwl_lines(
            self.blocks, self.mode_var.get(),
            labware_aliases=self.labware_aliases, source_conflicts=conflicts,
        )

    def _build_chemical_map(self) -> Dict[str, List[str]]:
        return build_chemical_map(self.blocks, self.mode_var.get())

    def _build_volume_map(self) -> Dict[str, float]:
        return build_volume_map(self.blocks, self.mode_var.get())

    def _write_chemical_map_csv(self, out_path: Path):
        rows, cols, _ = mode_dims_order(self.mode_var.get())
        chem_map = self._build_chemical_map()
        vol_map = self._build_volume_map()
        lines = []

        # Table 1: Chemical names
        lines.append("Chemical Map")
        lines.append(",".join(["Row\\Col"] + [str(c) for c in range(1, cols+1)]))
        for r in range(1, rows+1):
            rlab = row_number_to_label(r)
            vals = []
            for c in range(1, cols+1):
                key = f"{rlab}{c}"
                vals.append(" | ".join(chem_map.get(key, [])))
            quoted = [f'"{v}"' if ("," in v or "|" in v) else v for v in vals]
            lines.append(",".join([rlab] + quoted))

        # Table 2: Total dispense volume per well
        lines.append("")
        lines.append("Dispense Volume (uL)")
        lines.append(",".join(["Row\\Col"] + [str(c) for c in range(1, cols+1)]))
        for r in range(1, rows+1):
            rlab = row_number_to_label(r)
            vals = []
            for c in range(1, cols+1):
                key = f"{rlab}{c}"
                v = vol_map.get(key, 0.0)
                vals.append("") if abs(v) < 1e-12 else vals.append(f"{v:g}")
            lines.append(",".join([rlab] + vals))

        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _preview(self):
        try:
            lines = self._build_lines()
            win = tk.Toplevel(self.winfo_toplevel())
            win.title("GWL Preview")
            win.geometry("900x520")
            txt = tk.Text(win, wrap="none")
            y = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
            x = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
            txt.configure(yscrollcommand=y.set, xscrollcommand=x.set)
            txt.grid(row=0, column=0, sticky="nsew")
            y.grid(row=0, column=1, sticky="ns")
            x.grid(row=1, column=0, sticky="ew")
            win.rowconfigure(0, weight=1)
            win.columnconfigure(0, weight=1)
            txt.insert("1.0", "\n".join(lines) + ("\n" if lines else ""))
            txt.configure(state="disabled")
        except Exception as exc:
            messagebox.showerror("Preview error", str(exc))

    def _collect_form_block(self) -> TransferBlock:
        src_lab = self._canonical_labware_name(self.v_source_labware.get().strip())
        src_well = int(self.v_source_well.get().strip())
        src_vol = rounded_gwl_volume(float(self.v_source_volume.get().strip()))
        dst_lab = self._canonical_labware_name(self.v_dest_labware.get().strip())
        dst_expr = self.v_dest_wells.get().strip()
        dst_vol = rounded_gwl_volume(float(self.v_dest_volume.get().strip()))
        liquid = self.v_liquid_class.get().strip()
        chem = self.v_chemical.get().strip()
        reaction_umol = self.v_reaction_umol.get().strip()
        extra_aspirate_percent = self.v_extra_aspirate_percent.get().strip()
        is_building_block = bool(self.v_is_building_block.get())
        wash = bool(self.v_wash.get())
        diff_vol = self.v_diff_vol.get().strip().lower() == "yes"
        groups: List[DispenseGroup] = []
        if diff_vol:
            for g in self.group_rows:
                vtxt = g["vol"].get().strip()
                wtxt = g["wells"].get().strip()
                if not vtxt and not wtxt:
                    continue
                if not vtxt or not wtxt:
                    raise ValueError("Each extra group needs both volume and wells")
                groups.append(DispenseGroup(volume=rounded_gwl_volume(float(vtxt)), wells_expr=wtxt))
        return TransferBlock(src_lab, src_well, src_vol, dst_lab, dst_expr, dst_vol, liquid, chem, wash, diff_vol, groups, is_building_block, reaction_umol, extra_aspirate_percent)

    def _save(self):
        try:
            # Heads-up if the currently selected block has unsaved form edits.
            sel = self.listbox.curselection()
            if sel:
                i = sel[0]
                try:
                    form_block = self._collect_form_block()
                    if self.blocks[i] != form_block:
                        go_on = messagebox.askyesno(
                            "Unapplied changes",
                            "You changed fields in the selected block but did not click 'Apply Changes to This Block'.\n\n"
                            "Save anyway using the last applied block values?"
                        )
                        if not go_on:
                            return
                except Exception:
                    # If form values are partially invalid, still warn before saving applied data only.
                    go_on = messagebox.askyesno(
                        "Unapplied/invalid edits",
                        "Current form has unapplied or invalid edits.\n"
                        "Save anyway using last applied block values?"
                    )
                    if not go_on:
                        return

            lines = self._build_lines()
            if not lines:
                messagebox.showwarning("No data", "No blocks to export.")
                return
            if not self._warn_low_volume_for_clld():
                return
            self._warn_stock_may_be_insufficient_after_aspirate()
            out = filedialog.asksaveasfilename(defaultextension=".gwl", filetypes=[("GWL", "*.gwl"), ("All files", "*.*")])
            if not out:
                return
            out_path = Path(out)
            self._check_gwl_filename(out_path, update_same_path=True)
            gwl_content = "\n".join(lines) + "\n"
            out_path.write_text(gwl_content, encoding="utf-8")
            self._track_exported_gwl(out_path, gwl_content)
            msg = [f"Saved GWL:\n{out_path}"]
            if self.v_save_map.get():
                csv_path = out_path.with_name(out_path.stem + "_chemical_map.csv")
                self._write_chemical_map_csv(csv_path)
                msg.append(f"\nSaved chemical map:\n{csv_path}")
            messagebox.showinfo("Done", "\n".join(msg))
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))

    def _read_chemical_map_csv(self, csv_path: Path) -> Dict[str, str]:
        label_to_name: Dict[str, str] = {}
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))

        # Find each table by locating a header row like: Row\Col,1,2,3,...
        header_idxs: List[int] = []
        for i, row in enumerate(rows):
            if len(row) < 2:
                continue
            first = (row[0] or "").strip().lower()
            if first in {"row\\col", "row/col"}:
                numeric_cols = [((c or "").strip().isdigit()) for c in row[1:]]
                if any(numeric_cols):
                    header_idxs.append(i)

        if not header_idxs:
            return label_to_name

        def _preceding_title(header_idx: int) -> str:
            for prev in range(header_idx - 1, -1, -1):
                row = rows[prev]
                if not any((c or "").strip() for c in row):
                    continue
                return " ".join((c or "").strip() for c in row if (c or "").strip()).lower()
            return ""

        def _table_looks_like_volume(table_rows: List[List[str]]) -> bool:
            values = []
            for tr in table_rows:
                values.extend((cell or "").strip() for cell in tr[1:] if (cell or "").strip())
            return bool(values) and all(re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", value) for value in values)

        # Prefer the explicit "Chemical Map" table written by this tool. Chemical IDs may be
        # numeric-only, so do not require letters in cells.
        selected_header_idx = None
        for hidx in header_idxs:
            title = _preceding_title(hidx)
            if "chemical" in title and "volume" not in title:
                selected_header_idx = hidx
                break

        # Older hand-edited maps may not have a title; choose the first non-volume-looking table.
        if selected_header_idx is None:
            for pos, hidx in enumerate(header_idxs):
                end = header_idxs[pos + 1] if pos + 1 < len(header_idxs) else len(rows)
                body = [r for r in rows[hidx + 1:end] if any((c or "").strip() for c in r)]
                if not _table_looks_like_volume(body):
                    selected_header_idx = hidx
                    break

        if selected_header_idx is None and header_idxs:
            selected_header_idx = header_idxs[0]

        if selected_header_idx is None:
            return label_to_name

        # Parse selected table.
        pos = header_idxs.index(selected_header_idx)
        end = header_idxs[pos + 1] if pos + 1 < len(header_idxs) else len(rows)
        header = rows[selected_header_idx]
        col_nums = [int((h or "").strip()) if (h or "").strip().isdigit() else None for h in header[1:]]

        for row in rows[selected_header_idx + 1:end]:
            if not any((c or "").strip() for c in row):
                continue
            row_label = (row[0] or "").strip().upper()
            if not re.fullmatch(r"[A-Z]+", row_label):
                continue
            for i, cell in enumerate(row[1:]):
                col = col_nums[i] if i < len(col_nums) else None
                if not col:
                    continue
                value = (cell or "").strip()
                if value:
                    label_to_name[f"{row_label}{col}"] = value
        return label_to_name

    def _read_text_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def _blocks_from_gwl_content(
        self,
        content: str,
        source_path: Path | None = None,
        ask_mode: bool = False,
        ask_csv: bool = False,
        preferred_mode: str | None = None,
    ) -> Tuple[str, List[TransferBlock]]:
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        parsed = []
        cur = None
        max_well = 0

        for ln in lines:
            if ln == "W;":
                if cur:
                    cur["add_wash"] = True
                continue

            parts = ln.split(";")
            if len(parts) < 8:
                raise ValueError(f"Invalid v2 line: {ln}")
            op = parts[0].strip().upper()
            labware = self._canonical_labware_name(parts[1].strip())
            well = int(parts[4].strip())
            vol = float(parts[6].strip())
            liquid = parts[7].strip()

            if op == "A":
                if cur:
                    parsed.append(cur)
                cur = {
                    "source_labware": labware,
                    "source_well": well,
                    "source_volume": vol,
                    "dest_labware": "DeepPlate1",
                    "dispenses": [],
                    "liquid_class": liquid,
                    "add_wash": False,
                }
            elif op == "D":
                if not cur:
                    raise ValueError("Found D before A")
                if cur["dispenses"] and labware != cur["dest_labware"]:
                    raise ValueError(
                        "One aspiration dispenses to multiple destination labware "
                        f"({cur['dest_labware']} and {labware}). Split those transfers "
                        "into separate aspiration blocks before importing."
                    )
                cur["dest_labware"] = labware
                cur["dispenses"].append((well, vol))
                max_well = max(max_well, well)
            else:
                raise ValueError(f"Unsupported operation line: {ln}")

        if cur:
            parsed.append(cur)
        if not parsed:
            raise ValueError("No blocks parsed")

        dest_labwares = {str(item.get("dest_labware", "") or "") for item in parsed if isinstance(item, dict)}
        if preferred_mode in PLATE_MODES:
            guessed_mode = str(preferred_mode)
        elif any(lab in DEST_LABWARE_OPTIONS_96 for lab in dest_labwares):
            guessed_mode = "96-well horizontal"
        elif any(lab in DEST_LABWARE_OPTIONS_HPLC for lab in dest_labwares):
            guessed_mode = "HPLC vials horizontal"
        else:
            guessed_mode = "HPLC vials horizontal" if max_well <= 48 else "96-well horizontal"
        mode = guessed_mode
        if ask_mode and not messagebox.askyesno("Import mode", f"Detected max destination well {max_well}.\nUse '{guessed_mode}' destination format?"):
            mode = self.mode_var.get()

        chem_label_map: Dict[str, str] = {}
        if source_path:
            csv_guess = source_path.with_name(source_path.stem + "_chemical_map.csv")
            if csv_guess.exists():
                chem_label_map = self._read_chemical_map_csv(csv_guess)
            elif ask_csv and messagebox.askyesno("Import Chemical IDs", "Do you want to also import a companion chemical-map CSV?"):
                csv_pick = filedialog.askopenfilename(
                    title="Select companion chemical map CSV",
                    initialdir=str(source_path.parent),
                    initialfile=csv_guess.name,
                    filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
                )
                if csv_pick:
                    chem_label_map = self._read_chemical_map_csv(Path(csv_pick))

        blocks: List[TransferBlock] = []
        for b in parsed:
            # The editor renders the base group followed by the extra groups.
            # Keep that order identical to the imported commands. Repeated
            # wells start a new group because a single well expression selects
            # each well only once; folding repeats into it would lose volume.
            groups: List[Tuple[float, List[int]]] = []
            for well, volume in b["dispenses"]:
                if groups and groups[-1][0] == volume and well not in groups[-1][1]:
                    groups[-1][1].append(well)
                else:
                    groups.append((volume, [well]))

            base_vol, base_wells = groups[0] if groups else (b["source_volume"], [])
            extra_groups: List[DispenseGroup] = []
            for volume, wells in groups[1:]:
                labels = [index_to_dest_label(well, mode, b["dest_labware"]) for well in wells]
                extra_groups.append(DispenseGroup(volume=volume, wells_expr=",".join(labels)))

            labels = [index_to_dest_label(w, mode, b["dest_labware"]) for w in base_wells]
            all_labels = list(labels)
            for grp in extra_groups:
                all_labels.extend([x.strip() for x in grp.wells_expr.split(",") if x.strip()])

            chem_names = [chem_label_map.get(lbl, "").strip() for lbl in all_labels if chem_label_map.get(lbl, "").strip()]
            unique_chem = []
            for name in chem_names:
                if name not in unique_chem:
                    unique_chem.append(name)

            blocks.append(
                TransferBlock(
                    source_labware=b["source_labware"],
                    source_well=b["source_well"],
                    source_volume=b["source_volume"],
                    dest_labware=b["dest_labware"],
                    dest_wells_expr=",".join(labels),
                    dest_volume=float(base_vol),
                    liquid_class=b["liquid_class"],
                    chemical_name=" | ".join(unique_chem),
                    add_wash=b["add_wash"],
                    disp_different_vol=bool(extra_groups),
                    dispense_groups=extra_groups,
                )
            )

        return mode, blocks

    def _import_v2_gwl(self):
        p = filedialog.askopenfilename(filetypes=[("GWL", "*.gwl"), ("All files", "*.*")])
        if not p:
            return
        path = Path(p)
        mode = self._choose_gwl_import_mode(path.name)
        if mode is None:
            return
        try:
            mode, blocks = self._blocks_from_gwl_content(self._read_text_file(path), source_path=path, ask_mode=False, ask_csv=True, preferred_mode=mode)
            self.mode_var.set(mode)
            self.blocks = blocks
            self._refresh_dest_labware_options()
            self._refresh_list()
            if self.blocks:
                self.listbox.selection_set(0)
                self._on_select(None)
            messagebox.showinfo("Import complete", f"Imported {len(self.blocks)} block(s).")
        except Exception as exc:
            messagebox.showerror("Import error", str(exc))


def create_frame(master, compound_provider=None, push_callback=None):
    return TecanFrame(master, compound_provider=compound_provider, push_callback=push_callback)
