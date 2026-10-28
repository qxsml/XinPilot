from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from copy import copy
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
from urllib.error import HTTPError
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import openpyxl
from xinpilot_theme import COLORS, configure_controls, configure_table_tags
from solubility_panel import SolubilityPanel
from PIL import Image, ImageTk
import io
from rdkit import Chem, rdBase
from rdkit.Chem import Draw, Descriptors
from xinpilot.application.stock_update import stock_updates, structure_key

DATA_HEADERS = [
    "ID", "MW", "Molarity(umol): used in each reaction", "Density", "Volume", "Catalogue NO.", "CAS",
    "Quantity (mg)", "Quantity(umol)", "Quantity input unit", "Conc.", "Per aliquote in reaction (uL)", "Solvent added (uL)",
    "Solvent", "SMILES", "Name", "Supplier", "Nature",
]
DISPLAY_HEADERS = ["ID", "Structure", "MW", "Conc.", "Quantity (mg)", "Quantity(umol)",
                   "Solvent added (uL)", "Volume", "CAS", "Catalogue NO.", "Supplier", "SMILES", "Name", "Nature"]
DISPLAY_HEADER_LABELS = {
    "Name": "Chemical name",
    "Per aliquote in reaction (uL)": "Per aliquot in reaction (uL)",
    "Volume": "Volume left (µL)",
    "Conc.": "Conc. (M)",
    "MW": "MW (g/mol)",
    "Quantity(umol)": "Quantity (µmol)",
}
FIELD_INPUT_LABELS = {
    "Conc.": "Conc. (M)",
}


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

REQ_FIELDS = ["ID", "SMILES", "Quantity (mg)", "Conc.", "Solvent"]
OPT_FIELDS = ["CAS", "Catalogue NO.", "Supplier", "Name", "Nature", "Density", "Volume"]
CALC_FIELDS = ["MW", "Quantity(umol)", "Solvent added (uL)"]
DEFAULT_SOLVENT = "DMA"
DEFAULT_QUANTITY_UNIT = "mg"
QUANTITY_INPUT_OPTIONS = ("Quantity (mg)", "Quantity (umol)")
SDF_TITLE_PROPERTY = "_Name"
SDF_DUPLICATE_SKIP = "Skip matching IDs"
SDF_DUPLICATE_UPDATE = "Update matching IDs"
SDF_DUPLICATE_SUFFIX = "Add with numeric suffix"
SDF_DUPLICATE_POLICIES = (
    SDF_DUPLICATE_SKIP,
    SDF_DUPLICATE_UPDATE,
    SDF_DUPLICATE_SUFFIX,
)
PREVIEW_BOX_WIDTH = 340
PREVIEW_BOX_HEIGHT = 175
PREVIEW_IMAGE_WIDTH = 326
PREVIEW_IMAGE_HEIGHT = 160


@dataclass
class CompoundRecord:
    values: dict
    source_row: int | None = None
    source_values: dict | None = None
    source_cells: dict | None = None

    def __post_init__(self):
        # Keep the last saved identity even when the form changes ID or SMILES.
        # Raw cells also retain formulas whose displayed/cached value differs.
        if self.source_row is not None and self.source_values is None:
            self.source_values = dict(self.values)
        if self.source_values is not None and self.source_cells is None:
            self.source_cells = dict(self.source_values)


@dataclass(frozen=True)
class SdfCompound:
    record_number: int
    smiles: str
    molecular_weight: str
    properties: dict[str, str]


@dataclass(frozen=True)
class SdfReadResult:
    compounds: tuple[SdfCompound, ...]
    invalid_record_numbers: tuple[int, ...]
    total_records: int


@dataclass(frozen=True)
class SdfImportPlanRow:
    record_number: int
    requested_id: str
    final_id: str
    smiles: str
    molecular_weight: str
    action: str
    existing_index: int | None = None


def _normalized_compound_id(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def read_sdf_file(path: Path) -> SdfReadResult:
    """Read valid SDF molecules without standardizing salts or structures."""
    compounds: list[SdfCompound] = []
    invalid_record_numbers: list[int] = []
    total_records = 0
    # Invalid records are reported in the preview instead of being emitted as
    # RDKit console noise (the packaged GUI normally has no visible console).
    with rdBase.BlockLogs():
        supplier = Chem.SDMolSupplier(str(path), sanitize=True, removeHs=True)
        for record_number, mol in enumerate(supplier, start=1):
            total_records = record_number
            if mol is None:
                invalid_record_numbers.append(record_number)
                continue
            try:
                smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
                if not smiles:
                    raise ValueError("empty structure")
                properties: dict[str, str] = {}
                if mol.HasProp(SDF_TITLE_PROPERTY):
                    properties[SDF_TITLE_PROPERTY] = mol.GetProp(SDF_TITLE_PROPERTY).strip()
                for property_name in mol.GetPropNames(includePrivate=False, includeComputed=False):
                    properties[str(property_name)] = mol.GetProp(str(property_name)).strip()
                compounds.append(
                    SdfCompound(
                        record_number=record_number,
                        smiles=smiles,
                        molecular_weight=f"{Descriptors.MolWt(mol):.4f}",
                        properties=properties,
                    )
                )
            except Exception:
                invalid_record_numbers.append(record_number)
    return SdfReadResult(tuple(compounds), tuple(invalid_record_numbers), total_records)


def sdf_identifier_fields(compounds: tuple[SdfCompound, ...] | list[SdfCompound]) -> tuple[str, ...]:
    fields = {
        property_name
        for compound in compounds
        for property_name, value in compound.properties.items()
        if str(value or "").strip()
    }
    ordered = sorted((field for field in fields if field != SDF_TITLE_PROPERTY), key=str.casefold)
    if SDF_TITLE_PROPERTY in fields:
        ordered.insert(0, SDF_TITLE_PROPERTY)
    return tuple(ordered)


def default_sdf_identifier_field(fields: tuple[str, ...] | list[str]) -> str:
    if not fields:
        return ""
    normalized = {
        re.sub(r"[^a-z0-9]+", "", field.casefold()): field
        for field in fields
    }
    for preferred in ("id", "compoundid", "identifier", "catalogueno", "catalogno", "barcode"):
        if preferred in normalized:
            return normalized[preferred]
    if SDF_TITLE_PROPERTY in fields:
        return SDF_TITLE_PROPERTY
    return fields[0]


def plan_sdf_import(
    compounds: tuple[SdfCompound, ...] | list[SdfCompound],
    identifier_field: str,
    existing_ids: tuple[str, ...] | list[str],
    duplicate_policy: str,
) -> tuple[SdfImportPlanRow, ...]:
    if duplicate_policy not in SDF_DUPLICATE_POLICIES:
        raise ValueError(f"Unknown duplicate policy: {duplicate_policy}")

    existing_indices_by_id: dict[str, list[int]] = {}
    for index, value in enumerate(existing_ids):
        normalized_existing = _normalized_compound_id(value)
        if normalized_existing:
            existing_indices_by_id.setdefault(normalized_existing, []).append(index)
    reserved_ids = set(existing_indices_by_id)
    seen_in_sdf: set[str] = set()
    plan: list[SdfImportPlanRow] = []

    for compound in compounds:
        requested_id = re.sub(
            r"\s+",
            " ",
            str(compound.properties.get(identifier_field, "") or "").strip(),
        )
        normalized = _normalized_compound_id(requested_id)
        action = "add"
        final_id = requested_id
        existing_index = None

        if not normalized:
            action = "skip_missing_id"
            final_id = ""
        elif duplicate_policy == SDF_DUPLICATE_SUFFIX:
            if normalized in reserved_ids:
                suffix = 2
                while _normalized_compound_id(f"{requested_id}_{suffix}") in reserved_ids:
                    suffix += 1
                final_id = f"{requested_id}_{suffix}"
                normalized = _normalized_compound_id(final_id)
                action = "add_suffixed"
            reserved_ids.add(normalized)
        elif normalized in seen_in_sdf:
            action = "skip_duplicate_sdf"
        elif normalized in existing_indices_by_id:
            if duplicate_policy == SDF_DUPLICATE_UPDATE:
                matching_indices = existing_indices_by_id[normalized]
                if len(matching_indices) == 1:
                    action = "update"
                    existing_index = matching_indices[0]
                else:
                    action = "skip_ambiguous_existing"
            else:
                action = "skip_existing"
        else:
            reserved_ids.add(normalized)

        if normalized:
            seen_in_sdf.add(_normalized_compound_id(requested_id))
        plan.append(
            SdfImportPlanRow(
                record_number=compound.record_number,
                requested_id=requested_id,
                final_id=final_id,
                smiles=compound.smiles,
                molecular_weight=compound.molecular_weight,
                action=action,
                existing_index=existing_index,
            )
        )
    return tuple(plan)


class CompoundNotesFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        # In PyInstaller one-file mode, __file__ points into a temp _MEI folder.
        # Keep user data (Excel) next to the executable instead.
        if getattr(sys, "frozen", False):
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.base_dir = Path(__file__).resolve().parent

        self.default_excel = self.base_dir / "BB Stock list - Copy (2).xlsx"
        self.source_excel: Path | None = None
        self.excel_loaded = False
        self.settings_path = self.base_dir / "Compound_Stock_GUI_settings.json"
        self.records: list[CompoundRecord] = []
        self._saved_records_snapshot: list[tuple[str, ...]] = []
        self._associated_workbook_name = ""
        self.associated_workbook_name_var = tk.StringVar(value="Not specified")
        self.filtered_indices: list[int] = []
        self.search_var = tk.StringVar(value="")
        self.master_stock_excel_var = tk.StringVar(value="")
        self.vars = {h: tk.StringVar(value="") for h in DATA_HEADERS}
        self.vars["Solvent"].set(DEFAULT_SOLVENT)
        self.vars["Quantity input unit"].set(DEFAULT_QUANTITY_UNIT)
        self.quantity_input_unit_var = tk.StringVar(value=QUANTITY_INPUT_OPTIONS[0])
        self.quantity_input_var = tk.StringVar(value="")
        self._syncing_quantity_input = False
        self.structure_img = None
        self.structure_cache: dict[str, ImageTk.PhotoImage] = {}
        self._loading_record = False
        self._form_record_index: int | None = None
        self._pending_live_update = None
        self._quantity_auto_save_job = None
        self._deleted_source_rows: set[int] = set()
        self._deleted_source_records: list[CompoundRecord] = []
        self._add_row_count = 0
        self._add_row_job = None
        self._add_row_after_index: int | None = None

        # CAS -> SMILES tab state
        self.cas_lookup_var = tk.StringVar(value="")
        self.cas_smiles_var = tk.StringVar(value="")
        self.cas_name_var = tk.StringVar(value="")
        self.cas_mw_var = tk.StringVar(value="")
        self.cas_cid_var = tk.StringVar(value="")
        self.cas_status_var = tk.StringVar(value="")

        self._configure_styles()
        self._load_settings()
        self._build_ui()
        self._attach_live_edit_traces()

        if self.default_excel.exists():
            self.status_var.set("No Excel loaded. Add rows or click 'Load Excel'.")
        else:
            self.status_var.set(f"Default Excel not found: {self.default_excel.name}. Click 'Load Excel'.")

    def _records_snapshot(self) -> list[tuple[str, ...]]:
        return [
            tuple(str(rec.values.get(h, "") or "") for h in DATA_HEADERS)
            for rec in self.records
        ]

    def _mark_saved_snapshot(self):
        self._saved_records_snapshot = self._records_snapshot()

    def has_unsaved_changes(self) -> bool:
        self._commit_pending_form_update()
        if self._quantity_auto_save_job is not None:
            try:
                self.after_cancel(self._quantity_auto_save_job)
            except Exception:
                pass
            self._quantity_auto_save_job = None
            self._commit_quantity_to_current_record()
        return self._records_snapshot() != self._saved_records_snapshot

    def confirm_leave_compound_notes(self) -> bool:
        if not self.has_unsaved_changes():
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved Compound Notes",
            "Compound Notes has unsaved changes.\n\nSave changes before leaving this tab?",
        )
        if choice is None:
            return False
        if choice is False:
            return True
        try:
            return bool(self._save_current_excel(show_message=False))
        except Exception as exc:
            messagebox.showerror("Save Compound Notes failed", str(exc))
            return False

    def _configure_styles(self):
        configure_controls(self.winfo_toplevel())

    def _build_ui(self):
        top = ttk.Frame(self, padding=(8, 6), style="CompoundTop.TFrame")
        top.pack(fill="x")

        tools = ttk.Frame(top, style="CompoundTop.TFrame")
        tools.pack(fill="x")

        compact_button_padding = (6, 4)
        compact_button_gap = 2

        file_tools = ttk.LabelFrame(tools, text="Excel File", padding=(5, 4), style="FileRegion.TLabelframe")
        file_tools.pack(side="left", padx=(0, 4), pady=(0, 2))
        ttk.Button(file_tools, text="Load Excel", command=self._pick_excel, style="FileAction.TButton", padding=compact_button_padding).pack(side="left", padx=(0, compact_button_gap))
        ttk.Button(file_tools, text="Import SDF", command=self._pick_sdf, style="FileAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        ttk.Button(file_tools, text="Save Current", command=self._save_current_excel, style="FileAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        ttk.Button(file_tools, text="Save As", command=self._save_as_excel, style="FileAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        style_region_widgets(file_tools, "FileRegion")

        chemistry_tools = ttk.LabelFrame(tools, text="SMILES + Calculation", padding=(5, 4), style="ChemRegion.TLabelframe")
        chemistry_tools.pack(side="left", padx=(0, 4), pady=(0, 2))
        ttk.Button(chemistry_tools, text="From SMILES", command=self._fetch_from_smiles, style="ChemAction.TButton", padding=compact_button_padding).pack(side="left", padx=(0, compact_button_gap))
        ttk.Button(chemistry_tools, text="Fill Selected", command=self._fill_selected_fields, style="ChemAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        ttk.Button(chemistry_tools, text="Calculate", command=self._auto_calculate, style="ChemAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        style_region_widgets(chemistry_tools, "ChemRegion")

        row_tools = ttk.LabelFrame(tools, text="Rows + Volume", padding=(5, 4), style="RowRegion.TLabelframe")
        row_tools.pack(side="left", padx=(0, 4), pady=(0, 2))
        ttk.Button(row_tools, text="Add Row", command=self._add_blank_row, style="RowAction.TButton", padding=compact_button_padding).pack(side="left", padx=(0, compact_button_gap))
        ttk.Button(row_tools, text="Add Rows", command=self._ask_add_rows, style="RowAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        ttk.Button(row_tools, text="Delete Row", command=self._delete_row, style="Danger.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        ttk.Button(row_tools, text="Update Volume", command=self._update_all_volume_from_solvent, style="RowAction.TButton", padding=compact_button_padding).pack(side="left", padx=compact_button_gap)
        style_region_widgets(row_tools, "RowRegion")

        master_row = ttk.Frame(self, padding=(8, 6, 8, 6), style="CompoundMaster.TFrame")
        master_row.pack(fill="x")
        ttk.Label(master_row, text="Master Stock List:", background=COLORS["bg"], foreground=COLORS["text"]).pack(side="left", padx=(0, 6))
        ttk.Entry(master_row, textvariable=self.master_stock_excel_var, state="readonly", width=72).pack(side="left", fill="x", expand=True)
        ttk.Button(master_row, text="Select...", command=self._select_master_stock_list).pack(side="left", padx=(6, 0))
        ttk.Button(master_row, text="Add to Master List", command=self._append_to_master_stock_list, style="CompoundToolbar.TButton").pack(side="left", padx=(6, 0))

        main = ttk.Frame(self, padding=8, style="CompoundMain.TFrame")
        main.pack(fill="both", expand=True)

        self.split = ttk.Panedwindow(main, orient="horizontal")
        self.split.pack(fill="both", expand=True)

        left = ttk.Frame(self.split, style="CompoundMain.TFrame")
        right = ttk.Frame(self.split, style="CompoundMain.TFrame")

        self.split.add(left, weight=1)
        self.split.add(right, weight=2)

        self.left_panel = left
        self.right_panel = right

        # Left side tabs
        left_tabs = ttk.Notebook(left)
        left_tabs.pack(fill="both", expand=True)

        editor_tab = ttk.Frame(left_tabs, padding=4, style="CompoundEditor.TFrame")
        left_tabs.add(editor_tab, text="Record Editor")

        optional_tab = ttk.Frame(left_tabs, padding=4, style="CompoundEditor.TFrame")
        left_tabs.add(optional_tab, text="Optional Input / Reference")

        req = ttk.LabelFrame(editor_tab, text="Required Input", padding=8, style="CompoundRequired.TLabelframe")
        req.pack(fill="x", pady=(0, 8))
        self._build_fields(req, REQ_FIELDS)

        preview_box = ttk.LabelFrame(editor_tab, text="Structure Preview + CAS -> SMILES", padding=6, style="CompoundPreview.TLabelframe")
        preview_box.pack(fill="x", pady=(0, 8))
        self._build_structure_preview_box(preview_box)

        opt = ttk.LabelFrame(optional_tab, text="Optional Input / Reference", padding=6, style="CompoundOptional.TLabelframe")
        opt.pack(fill="x", pady=(0, 8))
        self._build_fields(opt, OPT_FIELDS)
        for field_widget in opt.winfo_children():
            field_widget.grid_configure(pady=1)
        self.solubility_window = None
        self.solubility_panel = None
        self.solubility_button = ttk.Button(optional_tab, text="Solubility prediction (FASTSOLV)", command=self._open_solubility)
        self.solubility_button.pack(anchor="w", pady=4)

        calc_title = ttk.Frame(right, style="CompoundEditor.TFrame")
        ttk.Label(calc_title, text="Calculated Output", style="CompoundCalc.TLabelframe.Label").pack(side="left")
        ttk.Label(
            calc_title,
            text="  Stock volume at the target concentration",
            style="CalcHint.TLabel",
        ).pack(side="left")
        calc = ttk.LabelFrame(
            right,
            labelwidget=calc_title,
            padding=6,
            style="CompoundCalc.TLabelframe",
        )
        calc.pack(fill="x", pady=(0, 6))
        self._build_calc_strip(calc)

        right_table = ttk.LabelFrame(
            right,
            text="Records Table: Not specified",
            padding=8,
            style="CompoundTable.TLabelframe",
        )
        right_table.pack(fill="both", expand=True)
        self.records_table_frame = right_table

        search_bar = ttk.Frame(right_table)
        search_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(search_bar, text="Text Search (Name/CAS/ID):").pack(side="left", padx=(0, 6))
        search_entry = ttk.Entry(search_bar, textvariable=self.search_var, width=48)
        search_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(search_bar, text="Clear", command=lambda: self.search_var.set("")).pack(side="left", padx=(6, 0))
        self.search_var.trace_add("write", self._on_search_changed)

        wrap = ttk.Frame(right_table)
        wrap.pack(fill="both", expand=True)
        self.records_table_wrap = wrap
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(wrap, columns=DISPLAY_HEADERS, show="headings", selectmode="extended")
        configure_table_tags(self.tree)
        for h in DISPLAY_HEADERS:
            self.tree.heading(h, text=DISPLAY_HEADER_LABELS.get(h, h))
            w = 110
            if h == "Structure":
                w = 80
            elif h in ("SMILES", "Name"):
                w = 220
            self.tree.column(h, width=w, anchor="e" if h in {"MW", "Conc.", "Quantity (mg)", "Quantity(umol)", "Solvent added (uL)", "Volume"} else "w")

        y = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, anchor="w", style="Status.TLabel").pack(fill="x")

        # Set initial split to 1/3 (left) : 2/3 (right).
        self._initial_split_ready = False
        self.split.bind("<Configure>", lambda _event: self._set_initial_split(), add="+")
        self.after_idle(self._set_initial_split)

    def _set_initial_split(self):
        if self._initial_split_ready:
            return
        try:
            total_w = self.split.winfo_width()
            if total_w <= 1:
                return
            self.split.sashpos(0, int(total_w / 3))
            self._initial_split_ready = True
        except Exception:
            pass

    def _attach_live_edit_traces(self):
        for var in self.vars.values():
            var.trace_add("write", self._schedule_live_update)
        self.quantity_input_var.trace_add("write", self._on_quantity_input_changed)
        self.vars["CAS"].trace_add("write", self._sync_preview_cas_from_form)

    @staticmethod
    def _filename_only(value: object) -> str:
        text = str(value or "").strip().replace("\\", "/")
        if not text:
            return ""
        return Path(text).name.strip()

    def _set_associated_workbook_name(self, value: object):
        self._associated_workbook_name = self._filename_only(value)
        display_name = self._associated_workbook_name or "Not specified"
        self.associated_workbook_name_var.set(display_name)
        if hasattr(self, "records_table_frame"):
            self.records_table_frame.configure(text=f"Records Table: {display_name}")

    def associated_workbook_name(self) -> str:
        """Return display-only project metadata; never return a directory path."""
        return self._associated_workbook_name

    def _schedule_live_update(self, *_):
        if self._loading_record:
            return
        if not self.tree.selection():
            return
        if self._pending_live_update is not None:
            self.after_cancel(self._pending_live_update)
        self._pending_live_update = self.after(120, self._apply_live_update)

    def _apply_live_update(self):
        self._pending_live_update = None
        self._commit_current_form_to_record()

    def _schedule_quantity_auto_save(self, *_):
        if self._loading_record:
            return
        if not self.tree.selection():
            return
        if self._quantity_auto_save_job is not None:
            self.after_cancel(self._quantity_auto_save_job)
        self._quantity_auto_save_job = self.after(700, self._auto_save_quantity_column)

    def _auto_save_quantity_column(self):
        self._quantity_auto_save_job = None
        self._commit_quantity_to_current_record()
        quantity_label = self._quantity_input_label()
        if not self.excel_loaded or self.source_excel is None:
            self.status_var.set(f"{quantity_label} updated in table. Click Save Current to choose an Excel file.")
            return
        try:
            self._write_quantity_column_to_excel(self.source_excel)
            self.status_var.set(f"{quantity_label} auto-saved: {self.source_excel.name}")
        except Exception as exc:
            self.status_var.set(f"{quantity_label} auto-save failed: {exc}")

    def _sync_preview_cas_from_form(self, *_):
        if self.cas_lookup_var.get() == self.vars["CAS"].get():
            return
        self.cas_lookup_var.set(self.vars["CAS"].get())

    def _commit_pending_form_update(self):
        if self._pending_live_update is None:
            return
        self.after_cancel(self._pending_live_update)
        self._pending_live_update = None
        self._commit_current_form_to_record()

    def _commit_pending_quantity_update(self):
        if self._quantity_auto_save_job is None:
            return
        self.after_cancel(self._quantity_auto_save_job)
        self._quantity_auto_save_job = None
        self._commit_quantity_to_current_record()

    def _commit_current_form_to_record(self):
        i = self._form_record_index
        if i is None or not (0 <= i < len(self.records)):
            return
        self.records[i] = replace(self.records[i], values=self._form_values())
        if self.tree.exists(str(i)):
            self.tree.item(str(i), values=self._row_values_for_display(self.records[i]))

    def _commit_quantity_to_current_record(self):
        i = self._form_record_index
        if i is None or not (0 <= i < len(self.records)):
            return
        values = dict(self.records[i].values)
        values["Quantity (mg)"] = self.vars["Quantity (mg)"].get().strip()
        values["Quantity(umol)"] = self.vars["Quantity(umol)"].get().strip()
        values["Quantity input unit"] = self._quantity_input_unit()
        self.records[i] = replace(self.records[i], values=values)
        if self.tree.exists(str(i)):
            self.tree.item(str(i), values=self._row_values_for_display(self.records[i]))

    def _ensure_column_visible(self, field: str):
        if field not in DISPLAY_HEADERS:
            return
        total = len(DISPLAY_HEADERS)
        col_index = DISPLAY_HEADERS.index(field)
        # Aim to place focused field near the center of current viewport.
        left_fraction = max(0.0, min(1.0, (col_index - 1) / max(1, total - 1)))
        self.tree.xview_moveto(left_fraction)

    def _build_cas_lookup_tab(self, parent):
        top = ttk.LabelFrame(parent, text="Lookup by CAS Number", padding=10)
        top.pack(fill="x", pady=(0, 8))

        row = ttk.Frame(top)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="CAS Number").pack(side="left", padx=(0, 8))
        cas_entry = ttk.Entry(row, textvariable=self.cas_lookup_var, width=30)
        cas_entry.pack(side="left")
        cas_entry.bind("<Return>", lambda _e: self._fetch_from_cas())
        ttk.Button(row, text="Fetch from PubChem", command=self._fetch_from_cas, style="ChemAction.TButton").pack(side="left", padx=(8, 0))

        results = ttk.Frame(top)
        results.pack(fill="x")
        self._build_readonly_field(results, 0, "SMILES", self.cas_smiles_var, width=58)
        self._build_readonly_field(results, 1, "IUPAC Name", self.cas_name_var, width=58)
        self._build_readonly_field(results, 2, "MW", self.cas_mw_var, width=28)
        self._build_readonly_field(results, 3, "PubChem CID", self.cas_cid_var, width=28)

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Copy SMILES", command=self._copy_cas_smiles).pack(side="left")
        ttk.Button(btns, text="Apply to Form", command=self._apply_cas_to_form, style="ChemAction.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Clear", command=self._clear_cas_lookup).pack(side="left", padx=(8, 0))

        ttk.Label(parent, textvariable=self.cas_status_var, anchor="w").pack(fill="x", padx=4)

        help_box = ttk.LabelFrame(parent, text="Tip", padding=10)
        help_box.pack(fill="x")
        ttk.Label(
            help_box,
            text="Use this tab to quickly resolve CAS → SMILES.\n"
                 "Then click 'Apply to Form' to copy values into the current record editor."
        ).pack(anchor="w")

    def _build_readonly_field(self, parent, row, label, var, width=40):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        ttk.Entry(parent, textvariable=var, width=width, state="readonly").grid(row=row, column=1, sticky="w", pady=2)

    def _build_structure_preview_box(self, parent):
        parent.grid_columnconfigure(1, weight=1)

        ttk.Label(parent, text="CAS").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 4))
        cas_entry = ttk.Entry(parent, textvariable=self.cas_lookup_var, width=18)
        cas_entry.grid(row=0, column=1, sticky="ew", pady=(0, 4))
        cas_entry.bind("<Return>", lambda _e: self._fetch_from_cas())
        ttk.Button(parent, text="Fetch", command=self._fetch_from_cas, style="ChemAction.TButton").grid(row=0, column=2, padx=(6, 0), pady=(0, 4))
        ttk.Button(parent, text="Apply", command=self._apply_cas_to_form, style="ChemAction.TButton").grid(row=0, column=3, padx=(6, 0), pady=(0, 4))

        self.preview_container = tk.Frame(
            parent,
            width=PREVIEW_BOX_WIDTH,
            height=PREVIEW_BOX_HEIGHT,
            relief="sunken",
            borderwidth=1,
            background="#f7f7f7",
        )
        self.preview_container.grid(row=1, column=0, columnspan=4, pady=(2, 4))
        self.preview_container.grid_propagate(False)
        self.preview_container.pack_propagate(False)

        self.structure_label = ttk.Label(self.preview_container, text="Structure Preview", anchor="center")
        self.structure_label.pack(fill="both", expand=True)

    def _build_calc_strip(self, parent):
        compact_labels = {
            "MW": "MW",
            "Quantity(umol)": "Qty (umol)",
            "Solvent added (uL)": "Solvent (uL)",
            "Per aliquote in reaction (uL)": "Aliquot (uL)",
        }
        for i, h in enumerate(CALC_FIELDS):
            label_col = i * 2
            entry_col = label_col + 1
            ttk.Label(parent, text=compact_labels[h]).grid(row=0, column=label_col, sticky="w", padx=((0 if i == 0 else 10), 4))
            field_readonly = h != "MW"
            widget = ttk.Entry(
                parent,
                textvariable=self.vars[h],
                width=12,
                state=("readonly" if field_readonly else "normal"),
            )
            widget.grid(row=0, column=entry_col, sticky="ew")
            parent.grid_columnconfigure(entry_col, weight=1)
            if not field_readonly:
                widget.bind("<FocusIn>", lambda _e, field=h: self._ensure_column_visible(field))

    def _build_fields(self, parent, fields, readonly=False):
        parent.grid_columnconfigure(1, weight=1)
        for i, h in enumerate(fields):
            if h == "Quantity (mg)" and not readonly:
                unit_widget = ttk.Combobox(
                    parent,
                    textvariable=self.quantity_input_unit_var,
                    values=QUANTITY_INPUT_OPTIONS,
                    width=18,
                    state="readonly",
                )
                unit_widget.grid(row=i, column=0, sticky="w", padx=(0, 6), pady=2)
                unit_widget.bind("<<ComboboxSelected>>", self._on_quantity_input_unit_changed)
                widget = ttk.Entry(parent, textvariable=self.quantity_input_var, width=26)
                widget.grid(row=i, column=1, sticky="ew", pady=2)
                widget.bind("<FocusIn>", lambda _e: self._ensure_column_visible(self._quantity_input_field()))
                continue
            label_text = FIELD_INPUT_LABELS.get(h, DISPLAY_HEADER_LABELS.get(h, h))
            ttk.Label(parent, text=label_text).grid(row=i, column=0, sticky="w", padx=(0, 6), pady=2)
            if h == "Solvent" and not readonly:
                widget = ttk.Combobox(parent, textvariable=self.vars[h], values=["DMA", "DMSO", "MeOH", "EtOH", "Water", "ACN", "DMF", "Other"], width=16)
                widget.grid(row=i, column=1, sticky="w", pady=2)
            else:
                field_readonly = readonly and h != "MW"
                widget = ttk.Entry(parent, textvariable=self.vars[h], width=26, state=("readonly" if field_readonly else "normal"))
                widget.grid(row=i, column=1, sticky="ew", pady=2)
            if not readonly or h == "MW":
                widget.bind("<FocusIn>", lambda _e, field=h: self._ensure_column_visible(field))

    @staticmethod
    def _normalize_quantity_input_unit(value: object) -> str:
        text = str(value or "").strip().lower().replace("µ", "u").replace("μ", "u")
        return "umol" if "umol" in text else DEFAULT_QUANTITY_UNIT

    def _quantity_input_unit(self) -> str:
        return self._normalize_quantity_input_unit(self.quantity_input_unit_var.get())

    def _quantity_input_field(self) -> str:
        return "Quantity(umol)" if self._quantity_input_unit() == "umol" else "Quantity (mg)"

    def _quantity_input_label(self) -> str:
        return "Quantity (umol)" if self._quantity_input_unit() == "umol" else "Quantity (mg)"

    def _on_quantity_input_unit_changed(self, _event=None):
        unit = self._quantity_input_unit()
        self.vars["Quantity input unit"].set(unit)
        self._syncing_quantity_input = True
        try:
            self.quantity_input_var.set(self.vars[self._quantity_input_field()].get())
        finally:
            self._syncing_quantity_input = False
        if not self._loading_record:
            self._schedule_live_update()
            self._schedule_quantity_auto_save()

    def _on_quantity_input_changed(self, *_args):
        if self._loading_record or self._syncing_quantity_input:
            return
        selected_field = self._quantity_input_field()
        other_field = "Quantity (mg)" if selected_field == "Quantity(umol)" else "Quantity(umol)"
        self.vars["Quantity input unit"].set(self._quantity_input_unit())
        self.vars[selected_field].set(self.quantity_input_var.get().strip())
        self.vars[other_field].set("")
        self._schedule_quantity_auto_save()

    def _to_float(self, s, field):
        s = str("" if s is None else s).strip()
        if not s:
            raise ValueError(f"{field} is required")
        try:
            value = float(s)
        except ValueError as exc:
            raise ValueError(f"{field} must be a finite number") from exc
        if not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        return value

    def _calculate_record_values(self, values: dict):
        quantity_unit = self._normalize_quantity_input_unit(values.get("Quantity input unit", DEFAULT_QUANTITY_UNIT))
        conc_M = self._to_float(values.get("Conc.", ""), "Conc.")
        if conc_M <= 0:
            raise ValueError("Conc. must be greater than zero")

        if quantity_unit == "umol":
            qty_umol = self._to_float(values.get("Quantity(umol)", ""), "Quantity (umol)")
            mw_text = str(values.get("MW", "") or "").strip()
            mw = self._to_float(mw_text, "MW") if mw_text else None
            if mw is not None and mw <= 0:
                raise ValueError("MW must be greater than zero")
            qty_mg = qty_umol * mw / 1000.0 if mw is not None else None
        else:
            mw = self._to_float(values.get("MW", ""), "MW")
            if mw <= 0:
                raise ValueError("MW must be greater than zero")
            qty_mg = self._to_float(values.get("Quantity (mg)", ""), "Quantity (mg)")
            qty_umol = qty_mg * 1000.0 / mw

        if qty_umol <= 0:
            raise ValueError(f"Quantity ({quantity_unit}) must be greater than zero")
        solvent_added = qty_umol / conc_M
        if not all(math.isfinite(number) and number > 0 for number in
                   (qty_umol, solvent_added, *(() if qty_mg is None else (qty_mg,)))):
            raise ValueError("Calculated quantity or volume is outside the supported numeric range")
        values["Quantity input unit"] = quantity_unit
        values["Quantity (mg)"] = "" if qty_mg is None else f"{qty_mg:.6g}"
        values["Quantity(umol)"] = f"{qty_umol:.6g}"
        values["Solvent added (uL)"] = f"{solvent_added:.1f}"
        # Compound Notes describes stock concentration and available volume.
        # Amount-per-reaction belongs to the selected synthesis editor, where it
        # can be converted to a transfer volume for that specific experiment.
        values["Per aliquote in reaction (uL)"] = ""
        values["Volume"] = f"{solvent_added:.1f}"

    def _selected_record_indices(self):
        indices = []
        for iid in self.tree.selection():
            try:
                idx = int(iid)
            except ValueError:
                continue
            if 0 <= idx < len(self.records):
                indices.append(idx)
        return sorted(set(indices))

    def _on_tree_double_click(self, event):
        column = self.tree.identify_column(event.x)
        region = self.tree.identify_region(event.x, event.y)
        if column != "#1" or region not in {"heading", "cell"}:
            return
        rows = self.tree.get_children()
        if rows:
            self.tree.selection_set(rows)
            self.tree.focus(rows[0])
            self.status_var.set(f"Selected {len(rows)} visible row{'s' if len(rows) != 1 else ''}.")
        return "break"

    def _auto_calculate(self):
        selected = self._selected_record_indices()
        if selected:
            self._commit_pending_form_update()
            selected = self._selected_record_indices()
            errors = []
            for idx in selected:
                try:
                    values = dict(self.records[idx].values)
                    self._calculate_record_values(values)
                    self.records[idx] = replace(self.records[idx], values=values)
                    if self.tree.exists(str(idx)):
                        self.tree.item(str(idx), values=self._row_values_for_display(self.records[idx]))
                except Exception as exc:
                    row_id = self.records[idx].values.get("ID", "") or f"row {idx + 1}"
                    errors.append(f"{row_id}: {exc}")
            first = selected[0]
            if first < len(self.records):
                self._load_record_into_form(self.records[first].values)
            calculated = len(selected) - len(errors)
            self.status_var.set(f"Calculated {calculated} selected row{'s' if calculated != 1 else ''}.")
            if errors:
                messagebox.showwarning(
                    "Some selected rows were not calculated",
                    "These rows need a valid selected Quantity and Conc.; MW is also required when Quantity (mg) is selected:\n\n"
                    + "\n".join(errors[:12])
                    + ("\n..." if len(errors) > 12 else ""),
                )
            return

        try:
            values = self._form_values()
            self._calculate_record_values(values)
            for h in ("Quantity (mg)", "Quantity(umol)", "Solvent added (uL)", "Per aliquote in reaction (uL)", "Volume"):
                self.vars[h].set(values[h])
            self._syncing_quantity_input = True
            try:
                self.quantity_input_var.set(values[self._quantity_input_field()])
            finally:
                self._syncing_quantity_input = False
        except Exception as exc:
            messagebox.showerror("Calculation error", str(exc))

    def _fill_selected_fields(self):
        selected = self._selected_record_indices()
        if not selected:
            messagebox.showwarning("No rows selected", "Select one or more rows to fill.")
            return

        win = tk.Toplevel(self)
        win.title("Fill Selected Rows")
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=f"Update {len(selected)} selected row{'s' if len(selected) != 1 else ''}.",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            body,
            text="Check only the fields that should be replaced.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))

        field_specs = (
            ("Conc.", "Conc. (M)"),
            ("Solvent", "Solvent"),
            ("Supplier", "Supplier"),
        )
        field_vars: dict[str, tk.StringVar] = {}
        use_vars: dict[str, tk.BooleanVar] = {}
        entries: dict[str, ttk.Entry] = {}
        for row, (field, label) in enumerate(field_specs, start=2):
            values = {
                str(self.records[index].values.get(field, "") or "").strip()
                for index in selected
            }
            common_value = values.pop() if len(values) == 1 else ""
            field_vars[field] = tk.StringVar(value=common_value)
            use_vars[field] = tk.BooleanVar(value=(field == "Conc." and bool(common_value)))
            ttk.Checkbutton(body, text=label, variable=use_vars[field]).grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=3
            )
            entry = ttk.Entry(body, textvariable=field_vars[field], width=24)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            entries[field] = entry

            def mark_for_update(*_args, target=field):
                use_vars[target].set(True)

            field_vars[field].trace_add("write", mark_for_update)

        status = ttk.Label(body, text="", foreground="#b00020")
        status.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def apply_fill():
            updates = {
                field: field_vars[field].get().strip()
                for field, _label in field_specs
                if use_vars[field].get()
            }
            if not updates:
                status.configure(text="Check at least one field to update.")
                return
            empty_fields = [label for field, label in field_specs if field in updates and not updates[field]]
            if empty_fields:
                status.configure(text=f"Enter a value for {empty_fields[0]}.")
                return
            self._commit_pending_form_update()
            current_selected = self._selected_record_indices()
            if not current_selected:
                status.configure(text="No rows are selected.")
                return
            self._apply_group_values_to_indices(current_selected, updates)
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Apply", command=apply_fill, style="CompoundToolbar.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=win.destroy, style="CompoundToolbar.TButton").pack(side="left")
        win.bind("<Return>", lambda _e: apply_fill())
        win.bind("<Escape>", lambda _e: win.destroy())
        body.grid_columnconfigure(1, weight=1)

        try:
            self.update_idletasks()
            x = self.winfo_rootx() + 180
            y = self.winfo_rooty() + 90
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        entries["Conc."].focus_set()
        entries["Conc."].selection_range(0, "end")

    def _apply_group_values_to_indices(self, indices, updates: dict[str, str]):
        allowed_fields = {"Conc.", "Solvent", "Supplier"}
        unexpected = set(updates) - allowed_fields
        if unexpected:
            raise ValueError(f"Unsupported group-fill field(s): {', '.join(sorted(unexpected))}")
        for idx in indices:
            record = self.records[idx]
            values = dict(record.values)
            values.update(updates)
            self.records[idx] = replace(record, values=values)
            if self.tree.exists(str(idx)):
                self.tree.item(str(idx), values=self._row_values_for_display(self.records[idx]))
        first = indices[0] if indices else None
        if first is not None and first < len(self.records):
            self._load_record_into_form(self.records[first].values, first)
        fields = ", ".join("Conc." if field == "Conc." else field for field in updates)
        self.status_var.set(
            f"Updated {fields} for {len(indices)} selected row{'s' if len(indices) != 1 else ''}."
        )

    def _fill_conc_to_selected(self):
        self._fill_selected_fields()

    def _apply_conc_to_indices(self, indices, conc: str):
        self._apply_group_values_to_indices(indices, {"Conc.": conc})

    # Compatibility aliases for callers from older XinPilot source revisions.
    # The molarity argument is intentionally ignored: experiment-scale amount is
    # now entered in Tecan, Opentrons, or Manual rather than Compound Notes.
    def _fill_conc_molarity_to_selected(self):
        self._fill_conc_to_selected()

    def _apply_conc_molarity_to_indices(self, indices, conc: str, _molarity: str = ""):
        self._apply_conc_to_indices(indices, conc)

    def _fetch_from_smiles(self):
        try:
            smiles = (self.vars["SMILES"].get() or "").strip()
            if not smiles:
                messagebox.showwarning("SMILES required", "Please enter SMILES first.")
                return

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                messagebox.showerror("Invalid SMILES", "Could not parse SMILES. Please check the structure.")
                return

            # Always compute MW locally first (works even when PubChem has no record).
            local_mw = f"{Descriptors.MolWt(mol):.4f}"
            self.vars["MW"].set(local_mw)

            cid = ""
            pubchem_ok = False
            try:
                s = quote(smiles, safe="")
                prop_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{s}/property/CID,MolecularWeight,IUPACName/JSON"
                data = json.loads(urlopen(prop_url, timeout=20).read().decode("utf-8"))
                props = data["PropertyTable"]["Properties"][0]
                cid = props.get("CID") or ""
                mw = props.get("MolecularWeight")
                if mw:
                    self.vars["MW"].set(str(mw))
                pubchem_ok = True
            except Exception:
                # Non-fatal: keep local MW and continue.
                pass

            if cid and not self.vars["CAS"].get().strip():
                try:
                    syn_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
                    syn = json.loads(urlopen(syn_url, timeout=20).read().decode("utf-8"))
                    lst = syn.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
                    cas = next((x for x in lst if self._is_valid_cas((x or "").strip())), "")
                    if cas:
                        self.vars["CAS"].set((cas or "").strip())
                except Exception:
                    pass

            self._update_structure_preview(smiles)
            if pubchem_ok:
                self.status_var.set("SMILES lookup complete (PubChem + local MW).")
                messagebox.showinfo("Done", "Fetched available MW/CAS from SMILES.")
            else:
                self.status_var.set("SMILES parsed. MW calculated locally (PubChem not found).")
                messagebox.showinfo("Done", "PubChem lookup unavailable for this SMILES. MW was calculated locally.")
        except Exception as exc:
            self.status_var.set("SMILES lookup failed")
            messagebox.showerror("SMILES lookup failed", f"Unexpected error:\n{exc}")

    @staticmethod
    def _canonicalize_cas(value: str) -> str:
        return (value or "").strip()

    @staticmethod
    def _is_valid_cas(value: str) -> bool:
        if not re.fullmatch(r"\d{2,7}-\d{2}-\d", value or ""):
            return False
        digits = value.replace("-", "")
        check_digit = int(digits[-1])
        body = digits[:-1]
        checksum = sum((idx + 1) * int(d) for idx, d in enumerate(reversed(body))) % 10
        return checksum == check_digit

    def _fetch_from_cas(self):
        raw_cas = (self.cas_lookup_var.get() or "").strip()
        if not raw_cas:
            messagebox.showwarning("CAS required", "Please enter a CAS number first.")
            return

        cas = self._canonicalize_cas(raw_cas)
        if not self._is_valid_cas(cas):
            self.cas_status_var.set("Invalid CAS format/checksum")
            messagebox.showwarning("Invalid CAS", "CAS must match format NNNNNNN-NN-N and pass checksum.")
            return

        def _get_json(url: str):
            try:
                return json.loads(urlopen(url, timeout=20).read().decode("utf-8"))
            except HTTPError as e:
                if e.code == 404:
                    return None
                raise

        try:
            cas_q = quote(cas, safe="")

            smiles = ""
            mw = ""
            name = ""
            cid = ""

            # Strict mode: exact CAS RN -> CID candidates.
            cid_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/xref/RN/{cas_q}/cids/JSON"
            cid_data = _get_json(cid_url) or {}
            cids = [str(x) for x in cid_data.get("IdentifierList", {}).get("CID", [])]

            # Verify each CID has the exact CAS in its synonyms before accepting.
            for candidate_cid in cids:
                syn_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{candidate_cid}/synonyms/JSON"
                syn_data = _get_json(syn_url) or {}
                syn_list = syn_data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
                syn_set = {self._canonicalize_cas(s) for s in syn_list if isinstance(s, str)}
                if cas not in syn_set:
                    continue

                prop_by_cid_url = (
                    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
                    f"{candidate_cid}/property/CanonicalSMILES,IsomericSMILES,ConnectivitySMILES,MolecularWeight,IUPACName/JSON"
                )
                data_cid = _get_json(prop_by_cid_url) or {}
                props_cid = (data_cid.get("PropertyTable", {}).get("Properties", [{}]) or [{}])[0]
                candidate_smiles = str(
                    # PubChem's full structure field is IsomericSMILES in
                    # legacy responses and SMILES in current responses. Prefer
                    # it so CAS lookup retains stereochemistry and isotopes.
                    props_cid.get("IsomericSMILES")
                    or props_cid.get("SMILES")
                    or props_cid.get("CanonicalSMILES")
                    or props_cid.get("ConnectivitySMILES")
                    or ""
                )
                if not candidate_smiles:
                    continue

                cid = candidate_cid
                smiles = candidate_smiles
                mw = str(props_cid.get("MolecularWeight", "") or "")
                name = str(props_cid.get("IUPACName", "") or "")
                break

            self.cas_smiles_var.set(smiles)
            self.cas_mw_var.set(mw)
            self.cas_name_var.set(name)
            self.cas_cid_var.set(cid)

            if smiles:
                self._update_structure_preview(smiles)
                self.cas_status_var.set(f"Lookup success for verified CAS {cas}")
                self.cas_lookup_var.set(cas)
            else:
                self.cas_status_var.set(f"CAS {cas} could not be verified from PubChem")
                messagebox.showwarning(
                    "CAS not verified",
                    "No PubChem record could be verified for this CAS.\n"
                    "To avoid mistakes, no result was applied."
                )

        except Exception as exc:
            self.cas_status_var.set("Lookup failed")
            messagebox.showerror("CAS lookup failed", f"Could not fetch from PubChem:\n{exc}")

    def _copy_cas_smiles(self):
        smiles = (self.cas_smiles_var.get() or "").strip()
        if not smiles:
            messagebox.showwarning("No SMILES", "No SMILES available to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(smiles)
        self.cas_status_var.set("SMILES copied to clipboard")

    def _apply_cas_to_form(self):
        smiles = (self.cas_smiles_var.get() or "").strip()
        if not smiles:
            messagebox.showwarning("No result", "Fetch CAS info first.")
            return

        self.vars["CAS"].set((self.cas_lookup_var.get() or "").strip())
        self.vars["SMILES"].set(smiles)
        if not self.vars["Name"].get().strip() and self.cas_name_var.get().strip():
            self.vars["Name"].set(self.cas_name_var.get().strip())
        if self.cas_mw_var.get().strip() and not self.vars["MW"].get().strip():
            self.vars["MW"].set(self.cas_mw_var.get().strip())

        self._update_structure_preview(smiles)
        self.status_var.set("CAS lookup values applied to form")

    def _clear_cas_lookup(self):
        self.cas_lookup_var.set("")
        self.cas_smiles_var.set("")
        self.cas_name_var.set("")
        self.cas_mw_var.set("")
        self.cas_cid_var.set("")
        self.cas_status_var.set("")

    def _update_structure_preview(self, smiles: str):
        smiles = (smiles or "").strip()
        if not smiles:
            self.structure_label.configure(image="", text="Structure Preview")
            return
        cached = self.structure_cache.get(smiles)
        if cached is not None:
            self.structure_img = cached
            self.structure_label.configure(image=self.structure_img, text="")
            return
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ValueError("Invalid SMILES")
            img = Draw.MolToImage(
                mol,
                size=(PREVIEW_IMAGE_WIDTH, PREVIEW_IMAGE_HEIGHT),
                fitImage=True,
            ).convert("RGBA")
            photo = ImageTk.PhotoImage(img)
            self.structure_cache[smiles] = photo
            self.structure_img = photo
            self.structure_label.configure(image=self.structure_img, text="")
        except Exception:
            # Fallback to PubChem render for edge cases RDKit cannot depict.
            try:
                s = quote(smiles, safe="")
                img_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{s}/PNG?image_size=600x600"
                raw = urlopen(img_url, timeout=12).read()
                img = Image.open(io.BytesIO(raw)).convert("RGBA").resize((PREVIEW_IMAGE_WIDTH, PREVIEW_IMAGE_HEIGHT), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.structure_cache[smiles] = photo
                self.structure_img = photo
                self.structure_label.configure(image=self.structure_img, text="")
            except Exception:
                self.structure_label.configure(image="", text="Structure preview unavailable")

    def _form_values(self):
        values = {h: self.vars[h].get().strip() for h in DATA_HEADERS}
        values["Quantity input unit"] = self._quantity_input_unit()
        values[self._quantity_input_field()] = self.quantity_input_var.get().strip()
        return values

    def _clear_form(self):
        self._loading_record = True
        for h in DATA_HEADERS:
            if h == "Solvent":
                value = DEFAULT_SOLVENT
            elif h == "Quantity input unit":
                value = DEFAULT_QUANTITY_UNIT
            else:
                value = ""
            self.vars[h].set(value)
        self.quantity_input_unit_var.set(QUANTITY_INPUT_OPTIONS[0])
        self.quantity_input_var.set("")
        self._loading_record = False
        self._form_record_index = None
        self.structure_label.configure(image="", text="Structure Preview")
        self.tree.selection_remove(self.tree.selection())

    def _row_matches_search(self, rec: CompoundRecord, q: str) -> bool:
        if not q:
            return True
        fields = [
            rec.values.get("ID", ""),
            rec.values.get("Name", ""),
            rec.values.get("CAS", ""),
            rec.values.get("Catalogue NO.", ""),
            rec.values.get("Supplier", ""),
            rec.values.get("SMILES", ""),
            rec.values.get("Nature", ""),
        ]
        haystack = " ".join(str(x or "") for x in fields).lower()
        return all(token in haystack for token in q.split())

    def _on_search_changed(self, *_):
        self._refresh_tree()

    def _row_values_for_display(self, rec: CompoundRecord):
        v = rec.values
        smiles = (v.get("SMILES", "") or "").strip()
        return [
            v.get("ID", ""), "Show" if smiles else "", v.get("MW", ""),
            v.get("Conc.", ""),
            v.get("Quantity (mg)", ""), v.get("Quantity(umol)", ""),
            v.get("Solvent added (uL)", ""), v.get("Volume", ""), v.get("CAS", ""), v.get("Catalogue NO.", ""), v.get("Supplier", ""),
            v.get("SMILES", ""), v.get("Name", ""), v.get("Nature", "")
        ]

    def _refresh_tree(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        configure_table_tags(self.tree)

        q = (self.search_var.get() or "").strip().lower()
        self.filtered_indices = [i for i, rec in enumerate(self.records) if self._row_matches_search(rec, q)]

        for display_i, rec_i in enumerate(self.filtered_indices):
            rec = self.records[rec_i]
            self.tree.insert("", "end", iid=str(rec_i), values=self._row_values_for_display(rec), tags=(("even" if display_i % 2 == 0 else "odd"),))

        if q:
            self.status_var.set(f"Text-filtered: {len(self.filtered_indices)} / {len(self.records)} records")

    def _add_blank_row(self):
        self._queue_blank_rows(1)

    def _queue_blank_rows(self, count: int):
        if count <= 0:
            return
        if self._add_row_count == 0:
            sel = self.tree.selection()
            self._add_row_after_index = int(sel[0]) if sel else None
        self._add_row_count += 1
        if count > 1:
            self._add_row_count += count - 1
        if self._add_row_job is None:
            self._add_row_job = self.after_idle(self._flush_blank_rows)

    def _ask_add_rows(self):
        win = tk.Toplevel(self)
        win.title("Add Rows")
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="How many rows to add?").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        count_var = tk.StringVar(value="10")
        entry = ttk.Entry(body, textvariable=count_var, width=12)
        entry.grid(row=1, column=0, sticky="w")
        status = ttk.Label(body, text="", foreground="#b00020")
        status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def add_rows():
            raw = count_var.get().strip()
            try:
                count = int(raw)
            except ValueError:
                status.configure(text="Enter a whole number.")
                return
            if count <= 0:
                status.configure(text="Enter a number greater than 0.")
                return
            self._queue_blank_rows(count)
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Add", command=add_rows, style="CompoundToolbar.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=win.destroy, style="CompoundToolbar.TButton").pack(side="left")
        entry.bind("<Return>", lambda _e: add_rows())
        win.bind("<Escape>", lambda _e: win.destroy())

        try:
            self.update_idletasks()
            x = self.winfo_rootx() + 160
            y = self.winfo_rooty() + 80
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        entry.focus_set()
        entry.selection_range(0, "end")

    def _flush_blank_rows(self):
        count = self._add_row_count
        after_index = self._add_row_after_index
        self._add_row_count = 0
        self._add_row_job = None
        self._add_row_after_index = None
        if count <= 0:
            return

        self._commit_pending_form_update()

        blank = {h: "" for h in DATA_HEADERS}
        blank["Solvent"] = DEFAULT_SOLVENT
        blank["Quantity input unit"] = DEFAULT_QUANTITY_UNIT
        new_records = [CompoundRecord(dict(blank)) for _ in range(count)]
        if after_index is not None and 0 <= after_index < len(self.records):
            insert_at = after_index + 1
        else:
            insert_at = len(self.records)
        self.records[insert_at:insert_at] = new_records
        last_new_iid = str(insert_at + count - 1)
        self._refresh_tree()

        if self.tree.exists(last_new_iid):
            self.tree.selection_set(last_new_iid)
            self.tree.focus(last_new_iid)
            self.tree.see(last_new_iid)
            self._load_record_into_form(self.records[int(last_new_iid)].values, int(last_new_iid))
        else:
            self._clear_form()
        location = "after selected row" if after_index is not None else "at the end"
        self.status_var.set(f"Added {count} blank row{'s' if count != 1 else ''} {location}.")

    def _delete_row(self):
        self._commit_pending_form_update()
        self._commit_pending_quantity_update()
        selected = sorted({int(iid) for iid in self.tree.selection()}, reverse=True)
        if not selected:
            return
        for index in selected:
            record = self.records[index]
            if record.source_row is not None:
                self._deleted_source_rows.add(record.source_row)
                self._deleted_source_records.append(record)
            del self.records[index]
        self._refresh_tree()
        self._clear_form()
        count = len(selected)
        self.status_var.set(
            "Deleted selected row." if count == 1 else f"Deleted {count} selected rows."
        )

    def _update_all_volume_from_solvent(self):
        self._commit_pending_form_update()
        selected = self._selected_record_indices()
        if not selected:
            messagebox.showwarning("No rows selected", "Select one or more rows before clicking Update Volume.")
            return
        updated = 0
        for idx in selected:
            rec = self.records[idx]
            solvent_added = str(rec.values.get("Solvent added (uL)", "") or "").strip()
            try:
                current_volume = float(str(rec.values.get("Volume", "") or "0").strip() or "0")
            except ValueError:
                current_volume = 0.0
            try:
                solvent_volume = float(solvent_added or "0")
            except ValueError:
                solvent_volume = 0.0
            rec.values["Volume"] = f"{current_volume + solvent_volume:.1f}"
            updated += 1
        self._refresh_tree()
        self.tree.selection_set([str(idx) for idx in selected if self.tree.exists(str(idx))])
        first = selected[0]
        if 0 <= first < len(self.records):
            self._load_record_into_form(self.records[first].values)
        self.status_var.set(f"Added Solvent added to Volume left for {updated} selected row{'s' if updated != 1 else ''}.")

    def _open_solubility(self):
        if self.solubility_window is None:
            self.solubility_window = tk.Toplevel(self)
            self.solubility_window.title("Solubility prediction")
            self.solubility_window.geometry("880x500")
            self.solubility_window.minsize(780, 380)
            self.solubility_window.protocol("WM_DELETE_WINDOW", self.solubility_window.withdraw)
            self.solubility_panel = SolubilityPanel(self.solubility_window, self)
            self.solubility_panel.pack(fill="both", expand=True, padx=10, pady=10)
        self.solubility_panel.refresh()
        self.solubility_window.deiconify()
        self.solubility_window.lift()

    def _on_tree_select(self, _evt):
        self._commit_pending_form_update()
        self._commit_pending_quantity_update()
        sel = self.tree.selection()
        if not sel:
            if self.solubility_panel is not None:
                self.solubility_panel.refresh()
            return
        index = int(sel[0])
        rec = self.records[index].values
        self._load_record_into_form(rec, index)
        if self.solubility_panel is not None:
            self.solubility_panel.refresh()

    def _load_record_into_form(self, rec: dict, record_index: int | None = None):
        self._loading_record = True
        for h in DATA_HEADERS:
            self.vars[h].set(str(rec.get(h, "") or ""))
        quantity_unit = self._normalize_quantity_input_unit(rec.get("Quantity input unit", DEFAULT_QUANTITY_UNIT))
        self.vars["Quantity input unit"].set(quantity_unit)
        self.quantity_input_unit_var.set("Quantity (umol)" if quantity_unit == "umol" else "Quantity (mg)")
        quantity_field = "Quantity(umol)" if quantity_unit == "umol" else "Quantity (mg)"
        self.quantity_input_var.set(str(rec.get(quantity_field, "") or ""))
        self.cas_lookup_var.set(str(rec.get("CAS", "") or ""))
        self._loading_record = False
        if record_index is None:
            selection = self.tree.selection()
            record_index = int(selection[0]) if selection else None
        self._form_record_index = record_index
        if rec.get("SMILES"):
            self._update_structure_preview(rec.get("SMILES"))
        else:
            self.structure_label.configure(image="", text="Structure Preview")

    def _load_excel(self, path: Path, mark_loaded: bool = True):
        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {path}")

        wb = None
        raw_wb = None
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
            ws = wb[wb.sheetnames[0]]
            raw_wb = openpyxl.load_workbook(path, data_only=False)
            raw_ws = raw_wb[raw_wb.sheetnames[0]]

            # Header-driven mapping (robust to column shifts)
            header_to_col = {}
            for c in range(1, ws.max_column + 1):
                v = ws.cell(1, c).value
                if v is None:
                    continue
                name = str(v).strip()
                if name:
                    header_to_col[name] = c

            self.records.clear()
            self._deleted_source_rows.clear()
            self._deleted_source_records = []
            for r in range(2, ws.max_row + 1):
                row_data = {}
                nonempty = False
                for h in DATA_HEADERS:
                    c = header_to_col.get(h)
                    val = ws.cell(r, c).value if c else ""
                    txt = "" if val is None else str(val)
                    row_data[h] = txt
                    if txt.strip():
                        nonempty = True
                if nonempty:
                    # Ignore scratch/demo rows like TEMP1, TEMP2, ... from legacy sheets.
                    row_id = (row_data.get("ID", "") or "").strip().upper()
                    if re.match(r"^TEMP\d*$", row_id):
                        continue
                    source_cells = {
                        h: raw_ws.cell(r, header_to_col[h]).value if h in header_to_col else ""
                        for h in DATA_HEADERS
                    }
                    self.records.append(CompoundRecord(row_data, source_row=r, source_cells=source_cells))

            self._refresh_tree()
            self.status_var.set(f"Loaded {len(self.records)} records from: {path.name}")
            self.excel_loaded = mark_loaded
            self._set_associated_workbook_name(path.name)
            self._mark_saved_snapshot()
        finally:
            if wb is not None:
                wb.close()
            if raw_wb is not None:
                raw_wb.close()

    @staticmethod
    def _atomic_save_workbook(wb, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=path.suffix, dir=path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            wb.save(temp_path)
            # Reopen the temporary workbook before replacing a known-good file.
            check = openpyxl.load_workbook(temp_path, read_only=True, data_only=False)
            check.close()
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _header_map(ws) -> dict[str, int]:
        headers: dict[str, int] = {}
        for column in range(1, ws.max_column + 1):
            value = ws.cell(1, column).value
            if value is not None and str(value).strip():
                headers[str(value).strip()] = column
        return headers

    @staticmethod
    def _copy_row_style(ws, source_row: int, target_row: int, columns: int):
        if source_row < 2:
            return
        for column in range(1, columns + 1):
            source = ws.cell(source_row, column)
            target = ws.cell(target_row, column)
            if source.has_style:
                target._style = copy(source._style)
            if source.number_format:
                target.number_format = source.number_format
        if source_row in ws.row_dimensions:
            ws.row_dimensions[target_row].height = ws.row_dimensions[source_row].height

    def _validate_record_ids(self):
        rows_by_id: dict[str, list[int]] = {}
        for index, rec in enumerate(self.records, start=1):
            record_id = self._normalize_key(rec.values.get("ID", ""))
            if record_id:
                rows_by_id.setdefault(record_id, []).append(index)
        duplicates = {record_id: rows for record_id, rows in rows_by_id.items() if len(rows) > 1}
        if duplicates:
            details = ", ".join(f"{record_id} (records {', '.join(map(str, rows))})" for record_id, rows in sorted(duplicates.items()))
            raise ValueError(f"Compound IDs must be unique before saving: {details}")

    @staticmethod
    def _same_saved_cell(header: str, left, right) -> bool:
        left_text = "" if left is None else str(left).strip()
        right_text = "" if right is None else str(right).strip()
        if header == "ID":
            return _normalized_compound_id(left_text) == _normalized_compound_id(right_text)
        if left_text == right_text:
            return True
        if header == "SMILES":
            if not left_text or not right_text:
                return False
            try:
                return structure_key(left_text) == structure_key(right_text)
            except ValueError:
                return False
        # Excel can store a numeric stock value as either text or a number.
        numeric_headers = {
            "MW", "Molarity(umol): used in each reaction", "Density", "Volume",
            "Quantity (mg)", "Quantity(umol)", "Conc.",
            "Per aliquote in reaction (uL)", "Solvent added (uL)",
        }
        if header in numeric_headers and left_text and right_text:
            try:
                return float(left_text) == float(right_text)
            except ValueError:
                pass
        return False

    def _prepare_preserving_workbook(self, path: Path, template_path: Path | None = None):
        workbook_path = path if path.exists() else template_path
        if workbook_path is not None and workbook_path.exists():
            wb = openpyxl.load_workbook(workbook_path)
            ws = wb[wb.sheetnames[0]]
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Sheet1"

        try:
            self._validate_record_ids()
            headers = self._header_map(ws)
            for header in DATA_HEADERS:
                if sum(str(cell.value or "").strip() == header for cell in ws[1]) > 1:
                    raise ValueError(f"Save stopped: duplicate {header!r} columns in the workbook.")
            existing = {
                row: {h: ws.cell(row, headers[h]).value if h in headers else "" for h in DATA_HEADERS}
                for row in range(2, ws.max_row + 1)
            }
            rows_by_id: dict[str, list[int]] = {}
            for row, values in existing.items():
                rows_by_id.setdefault(self._normalize_key(values["ID"]), []).append(row)
            claimed_rows: set[int] = set()

            def original_row(rec):
                original = rec.source_cells or rec.source_values
                record_id = self._normalize_key(original.get("ID", ""))
                matches = rows_by_id.get(record_id, [])
                if not record_id:
                    # A legacy row without an ID is usable only if its entire
                    # original contents still identify one unambiguous row.
                    matches = [row for row in matches if all(
                        self._same_saved_cell(h, original.get(h, ""), existing[row][h])
                        for h in DATA_HEADERS
                    )]
                if len(matches) != 1:
                    raise ValueError(f"Save stopped: original Chemical ID {original.get('ID', '')!r} is missing or duplicated in the workbook. Reload and review the records.")
                row = matches[0]
                if row in claimed_rows:
                    raise ValueError("Save stopped: multiple records refer to the same original workbook compound.")
                if not self._same_saved_cell("SMILES", original.get("SMILES", ""), existing[row]["SMILES"]):
                    raise ValueError(f"Save stopped: original Chemical ID {original.get('ID', '')!r} has a different structure in the workbook. Reload and review the records.")
                claimed_rows.add(row)
                return row

            targets = []
            deleted_rows = set()
            next_row = ws.max_row + 1
            has_source = workbook_path is not None and workbook_path.exists()
            for rec in self.records:
                if not has_source or rec.source_values is None:
                    row = next_row
                    next_row += 1
                    values = {h: rec.values.get(h, "") for h in DATA_HEADERS}
                    targets.append((rec, row, values, dict(values)))
                    continue
                row = original_row(rec)
                raw_values = {}
                values = dict(rec.values)
                for header in DATA_HEADERS:
                    local = rec.values.get(header, "")
                    old_display = rec.source_values.get(header, "")
                    old_cell = (rec.source_cells or rec.source_values).get(header, "")
                    external = existing[row][header]
                    local_changed = not self._same_saved_cell(header, old_display, local)
                    external_changed = not self._same_saved_cell(header, old_cell, external)
                    if local_changed and external_changed and not self._same_saved_cell(header, local, external):
                        raise ValueError(f"Save stopped: Chemical ID {rec.source_values.get('ID', '')!r}, field {header!r} changed both in XinPilot and in the workbook. Reload and review the records.")
                    if local_changed:
                        raw_values[header] = local
                    else:
                        raw_values[header] = external
                        if isinstance(external, str) and external.startswith("="):
                            if external_changed:
                                raise ValueError(f"Save stopped: the {header!r} formula for Chemical ID {rec.source_values.get('ID', '')!r} changed in the workbook. Reload and review the records.")
                            values[header] = old_display
                        else:
                            values[header] = "" if external is None else str(external)
                targets.append((rec, row, raw_values, values))

            if has_source:
                for rec in getattr(self, "_deleted_source_records", []):
                    row = original_row(rec)
                    original = rec.source_cells or rec.source_values
                    if any(not self._same_saved_cell(h, original.get(h, ""), existing[row][h]) for h in DATA_HEADERS):
                        raise ValueError(f"Save stopped: deleted Chemical ID {original.get('ID', '')!r} changed in the workbook. Reload and review the records.")
                    deleted_rows.add(row)

            # A local rename or new row must not take an externally added ID.
            final_ids = {row: self._normalize_key(values["ID"]) for row, values in existing.items() if row not in deleted_rows}
            final_ids.update({row: self._normalize_key(raw["ID"]) for _rec, row, raw, _values in targets})
            counts: dict[str, int] = {}
            for record_id in final_ids.values():
                if record_id:
                    counts[record_id] = counts.get(record_id, 0) + 1
            for _rec, row, _raw, _values in targets:
                if counts.get(final_ids[row], 0) > 1:
                    raise ValueError(f"Save stopped: Chemical ID {final_ids[row]!r} would be duplicated in the workbook.")

            for header in DATA_HEADERS:
                if header not in headers:
                    column = ws.max_column + 1
                    ws.cell(1, column).value = header
                    headers[header] = column
            for _rec, row, raw_values, _values in targets:
                if row > ws.max_row:
                    self._copy_row_style(ws, ws.max_row, row, ws.max_column)
                for header in DATA_HEADERS:
                    ws.cell(row, headers[header]).value = raw_values[header]
            # Clear only owned cells; unrelated columns, formatting and other
            # worksheets remain attached to the original compound's row.
            for row in deleted_rows:
                for header in DATA_HEADERS:
                    ws.cell(row, headers[header]).value = None
            return wb, ws, headers, targets
        except Exception:
            wb.close()
            raise

    def _write_excel(self, path: Path, template_path: Path | None = None):
        wb = None
        try:
            wb, _ws, _headers, targets = self._prepare_preserving_workbook(path, template_path=template_path)
            self._atomic_save_workbook(wb, path)
            for rec, row, raw_values, values in targets:
                rec.values = values
                rec.source_row = row
                rec.source_values = dict(values)
                rec.source_cells = dict(raw_values)
            self._deleted_source_rows.clear()
            self._deleted_source_records = []
        finally:
            if wb is not None:
                wb.close()

    def _write_quantity_column_to_excel(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(path)
        self._validate_record_ids()
        wb = openpyxl.load_workbook(path)
        try:
            ws = wb[wb.sheetnames[0]]
            quantity_headers = ("Quantity (mg)", "Quantity(umol)", "Quantity input unit")
            quantity_cols: dict[str, int] = {}
            for c in range(1, ws.max_column + 1):
                header = str(ws.cell(1, c).value or "").strip()
                if header in quantity_headers:
                    quantity_cols[header] = c
            for header in quantity_headers:
                if header not in quantity_cols:
                    column = ws.max_column + 1
                    ws.cell(1, column).value = header
                    quantity_cols[header] = column
            id_col = next(
                (column for column in range(1, ws.max_column + 1) if str(ws.cell(1, column).value or "").strip() == "ID"),
                None,
            )
            rows_by_id: dict[str, list[int]] = {}
            if id_col is None:
                raise ValueError("Quantity auto-save requires an ID column. Use Save Current to review and save this workbook.")
            if id_col is not None:
                for row in range(2, ws.max_row + 1):
                    record_id = self._normalize_key(ws.cell(row, id_col).value)
                    if record_id:
                        rows_by_id.setdefault(record_id, []).append(row)
            # Stage every match first; one ambiguous or changed identity must
            # leave the original workbook intact, including its other columns.
            smiles_col = self._header_map(ws).get("SMILES")
            targets = []
            for rec in self.records:
                record_id = self._normalize_key(rec.values.get("ID", ""))
                matches = rows_by_id.get(record_id, []) if record_id else []
                if not matches and rec.source_row is None:
                    continue  # New unsaved rows are created by Save Current.
                if len(matches) != 1:
                    raise ValueError(f"Quantity auto-save stopped: Chemical ID {rec.values.get('ID', '')!r} is missing or duplicated in the workbook. Reload or use Save Current after reviewing the records.")
                row_idx = matches[0]
                existing_smiles = str(ws.cell(row_idx, smiles_col).value or '').strip() if smiles_col else ''
                current_smiles = str(rec.values.get('SMILES') or '').strip()
                if smiles_col and bool(existing_smiles) != bool(current_smiles):
                    raise ValueError(f"Quantity auto-save stopped: Chemical ID {rec.values.get('ID', '')!r} has different structure information in the workbook. Review and save the compound details first.")
                if existing_smiles and current_smiles:
                    from xinpilot.application.stock_update import structure_key
                    if structure_key(existing_smiles) != structure_key(current_smiles):
                        raise ValueError(f"Quantity auto-save stopped: Chemical ID {rec.values.get('ID', '')!r} has a different structure in the workbook. Review and save the compound details first.")
                targets.append((rec, row_idx))
            for rec, row_idx in targets:
                for header, column in quantity_cols.items():
                    ws.cell(row_idx, column).value = rec.values.get(header, "")
            self._atomic_save_workbook(wb, path)
            for rec, row_idx in targets:
                rec.source_row = row_idx
                # Auto-save changes only quantity cells, so retain the saved
                # identity and the baselines for all other editable fields.
                if rec.source_values is not None:
                    rec.source_values = dict(rec.source_values)
                    rec.source_cells = dict(rec.source_cells or rec.source_values)
                    for header in quantity_headers:
                        rec.source_values[header] = rec.values.get(header, "")
                        rec.source_cells[header] = rec.values.get(header, "")
        finally:
            wb.close()

    def _load_settings(self):
        try:
            if not self.settings_path.exists():
                return
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            master_path = str(data.get("master_stock_excel", "") or "").strip()
            if master_path:
                self.master_stock_excel_var.set(master_path)
        except Exception:
            pass

    def _save_settings(self):
        payload = {
            "master_stock_excel": (self.master_stock_excel_var.get() or "").strip(),
        }
        self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_key(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

    @staticmethod
    def _same_display_value(left, right) -> bool:
        left_text = str(left or "").strip()
        right_text = str(right or "").strip()
        try:
            return abs(float(left_text) - float(right_text)) < 1e-9
        except ValueError:
            return left_text == right_text

    def _select_master_stock_list(self):
        p = filedialog.askopenfilename(
            title="Select master stock list",
            filetypes=[("Excel", "*.xlsx")],
        )
        if p:
            self.master_stock_excel_var.set(str(Path(p)))
            try:
                self._save_settings()
            except Exception as exc:
                messagebox.showwarning("Settings not saved", f"Master stock list was selected, but the saved setting failed:\n{exc}")

    def _append_to_master_stock_list(self):
        self._commit_current_form_to_record()
        master_path_text = (self.master_stock_excel_var.get() or "").strip()
        if not master_path_text:
            messagebox.showwarning("Master stock list required", "Please select a master stock list Excel file first.")
            return

        master_path = Path(master_path_text)
        if not master_path.exists():
            messagebox.showerror("Master stock list not found", f"Could not find:\n{master_path}")
            return

        appendable_records = [
            rec for rec in self.records
            if any(str(rec.values.get(h, "") or "").strip() for h in DATA_HEADERS)
        ]
        if not appendable_records:
            messagebox.showwarning("No records", "There are no compound records to add.")
            return

        wb = None
        try:
            wb = openpyxl.load_workbook(master_path)
            ws = wb[wb.sheetnames[0]]

            header_to_col = {}
            for c in range(1, ws.max_column + 1):
                value = ws.cell(1, c).value
                if value is None:
                    continue
                header = str(value).strip()
                if header:
                    header_to_col[header] = c

            if not header_to_col:
                for col_index, header in enumerate(DATA_HEADERS, start=1):
                    ws.cell(1, col_index).value = header
                    header_to_col[header] = col_index
            else:
                next_col = ws.max_column + 1
                for header in DATA_HEADERS:
                    if header not in header_to_col:
                        ws.cell(1, next_col).value = header
                        header_to_col[header] = next_col
                        next_col += 1

            existing_ids = set()
            existing_id_rows = {}
            ambiguous_ids = set()
            existing_names = set()
            id_col = header_to_col.get("ID")
            name_col = header_to_col.get("Name")
            for row in range(2, ws.max_row + 1):
                if id_col:
                    row_id = self._normalize_key(ws.cell(row, id_col).value)
                    if row_id:
                        if row_id in existing_ids:
                            ambiguous_ids.add(row_id)
                        existing_ids.add(row_id)
                        existing_id_rows[row_id] = row
                if name_col:
                    row_name = self._normalize_key(ws.cell(row, name_col).value)
                    if row_name:
                        existing_names.add(row_name)

            added = 0
            updated_stock = 0
            blocked = []
            processed_ids = set()
            skipped_id = 0
            skipped_name = 0
            skipped_blank_id = 0
            for rec in appendable_records:
                row_id = self._normalize_key(rec.values.get("ID", ""))
                row_name = self._normalize_key(rec.values.get("Name", ""))
                if not row_id:
                    skipped_blank_id += 1
                    continue
                if row_id in processed_ids:
                    skipped_id += 1
                    continue
                processed_ids.add(row_id)
                if row_id in existing_ids:
                    master_row = existing_id_rows.get(row_id)
                    if row_id in ambiguous_ids:
                        blocked.append(f"{rec.values.get('ID')}: ID occurs more than once in the master list")
                        continue
                    existing = {h: ws.cell(master_row, c).value for h, c in header_to_col.items()}
                    try:
                        updates = stock_updates(existing, rec.values)
                    except ValueError as exc:
                        blocked.append(f"{rec.values.get('ID')}: {exc}")
                        continue
                    changed = False
                    for header, value in updates.items():
                        if not self._same_display_value(existing.get(header), value):
                            ws.cell(master_row, header_to_col[header]).value = value
                            changed = True
                    if changed:
                        updated_stock += 1
                        if row_name:
                            existing_names.add(row_name)
                    else:
                        skipped_id += 1
                    continue
                if row_name and row_name in existing_names:
                    skipped_name += 1
                    continue

                new_row = ws.max_row + 1
                for header in DATA_HEADERS:
                    ws.cell(new_row, header_to_col[header]).value = rec.values.get(header, "")
                existing_ids.add(row_id)
                existing_id_rows[row_id] = new_row
                if row_name:
                    existing_names.add(row_name)
                added += 1

            self._atomic_save_workbook(wb, master_path)
            self.status_var.set(
                f"Added {added} records to master list; updated {updated_stock} stock record(s); "
                f"skipped {skipped_id + skipped_name + skipped_blank_id}; blocked {len(blocked)}."
            )
            messagebox.showinfo(
                "Master list updated",
                "Master stock list updated.\n\n"
                f"Added: {added}\n"
                f"Updated stock records for existing ID: {updated_stock}\n"
                f"Skipped duplicate ID: {skipped_id}\n"
                f"Skipped duplicate Name: {skipped_name}\n"
                f"Skipped missing ID: {skipped_blank_id}\n"
                f"Blocked identity checks: {len(blocked)}\n\n"
                f"{master_path}"
            )
            if blocked:
                messagebox.showwarning(
                    "Master records not updated",
                    "These IDs were left unchanged. Check their structures and identifiers:\n\n" + "\n".join(blocked),
                )
        except Exception as exc:
            messagebox.showerror("Add to master list failed", f"Could not update:\n{master_path}\n\n{exc}")
            self.status_var.set("Failed to add records to master stock list")
        finally:
            if wb is not None:
                wb.close()

    @staticmethod
    def _sdf_action_label(row: SdfImportPlanRow) -> str:
        return {
            "add": "Add",
            "add_suffixed": f"Add as {row.final_id}",
            "update": "Update matching row",
            "skip_missing_id": "Skip: identifier missing",
            "skip_duplicate_sdf": "Skip: duplicate ID in SDF",
            "skip_existing": "Skip: ID already exists",
            "skip_ambiguous_existing": "Skip: ID exists in multiple rows",
        }.get(row.action, row.action)

    @staticmethod
    def _new_sdf_record_values(row: SdfImportPlanRow) -> dict:
        values = {header: "" for header in DATA_HEADERS}
        values.update(
            {
                "ID": row.final_id,
                "MW": row.molecular_weight,
                "SMILES": row.smiles,
                "Solvent": DEFAULT_SOLVENT,
                "Quantity input unit": DEFAULT_QUANTITY_UNIT,
            }
        )
        return values

    def _apply_sdf_import_plan(self, plan: tuple[SdfImportPlanRow, ...] | list[SdfImportPlanRow]) -> tuple[int, int, int]:
        """Apply a fully prepared plan in one assignment so the import is atomic."""
        staged_records = [replace(rec, values=dict(rec.values)) for rec in self.records]
        changed_indices: list[int] = []
        added = 0
        updated = 0
        skipped = 0

        for row in plan:
            if row.action in {"add", "add_suffixed"}:
                staged_records.append(CompoundRecord(self._new_sdf_record_values(row)))
                changed_indices.append(len(staged_records) - 1)
                added += 1
            elif row.action == "update":
                index = row.existing_index
                if index is None or not (0 <= index < len(staged_records)):
                    raise ValueError(f"The matching row for SDF record {row.record_number} is no longer available.")
                values = dict(staged_records[index].values)
                values["ID"] = row.final_id
                values["SMILES"] = row.smiles
                values["MW"] = row.molecular_weight
                staged_records[index] = replace(staged_records[index], values=values)
                changed_indices.append(index)
                updated += 1
            else:
                skipped += 1

        self.records = staged_records
        self._refresh_tree()
        visible_changed = [index for index in changed_indices if self.tree.exists(str(index))]
        if visible_changed:
            first = visible_changed[0]
            self.tree.selection_set(str(first))
            self.tree.focus(str(first))
            self.tree.see(str(first))
            self._load_record_into_form(self.records[first].values, first)
        elif changed_indices:
            self._clear_form()
        return added, updated, skipped

    def _pick_sdf(self):
        selected = filedialog.askopenfilename(
            title="Import compounds from SDF",
            filetypes=[("SDF structure files", "*.sdf *.sd"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        self._commit_pending_form_update()
        self._commit_pending_quantity_update()
        try:
            result = read_sdf_file(path)
        except Exception as exc:
            messagebox.showerror("SDF import failed", f"Could not read:\n{path}\n\n{exc}")
            self.status_var.set("Failed to read SDF file")
            return

        if not result.compounds:
            messagebox.showwarning(
                "No valid SDF structures",
                f"No valid chemical structures were found in {path.name}.\n\n"
                f"Records read: {result.total_records}\nInvalid structures: {len(result.invalid_record_numbers)}",
            )
            self.status_var.set(f"No valid structures found in {path.name}")
            return

        identifier_fields = sdf_identifier_fields(result.compounds)
        if not identifier_fields:
            messagebox.showwarning(
                "No identifiers in SDF",
                "The valid structures do not contain an SDF title or a non-empty property that can be used as Compound Notes ID.",
            )
            self.status_var.set(f"No usable identifiers found in {path.name}")
            return
        self._show_sdf_import_dialog(path, result, identifier_fields)

    def _show_sdf_import_dialog(
        self,
        path: Path,
        result: SdfReadResult,
        identifier_fields: tuple[str, ...],
    ):
        win = tk.Toplevel(self)
        win.title("Preview SDF Import")
        win.transient(self.winfo_toplevel())
        win.geometry("1000x620")
        win.minsize(760, 460)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)

        ttk.Label(body, text=path.name, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        summary_text = (
            f"SDF records: {result.total_records}   Valid structures: {len(result.compounds)}   "
            f"Invalid structures: {len(result.invalid_record_numbers)}"
        )
        ttk.Label(body, text=summary_text).grid(row=1, column=0, sticky="w", pady=(2, 8))

        controls = ttk.LabelFrame(body, text="Import choices", padding=8)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(3, weight=1)

        property_labels = {
            field: ("SDF title (_Name)" if field == SDF_TITLE_PROPERTY else field)
            for field in identifier_fields
        }
        field_by_label = {label: field for field, label in property_labels.items()}
        default_field = default_sdf_identifier_field(identifier_fields)
        identifier_var = tk.StringVar(value=property_labels[default_field])
        duplicate_var = tk.StringVar(value=SDF_DUPLICATE_SKIP)

        ttk.Label(controls, text="Use as Compound Notes ID:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        identifier_combo = ttk.Combobox(
            controls,
            textvariable=identifier_var,
            values=[property_labels[field] for field in identifier_fields],
            state="readonly",
            width=32,
        )
        identifier_combo.grid(row=0, column=1, sticky="ew", padx=(0, 16))
        ttk.Label(controls, text="When an ID already exists:").grid(row=0, column=2, sticky="w", padx=(0, 6))
        duplicate_combo = ttk.Combobox(
            controls,
            textvariable=duplicate_var,
            values=SDF_DUPLICATE_POLICIES,
            state="readonly",
            width=28,
        )
        duplicate_combo.grid(row=0, column=3, sticky="ew")
        ttk.Label(
            controls,
            text="Update changes only SMILES and MW in the matching row; existing stock quantities and notes are retained.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        preview_frame = ttk.LabelFrame(body, text="Import preview", padding=8)
        preview_frame.grid(row=3, column=0, sticky="nsew")
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        columns = ("record", "identifier", "smiles", "mw", "action")
        preview = ttk.Treeview(preview_frame, columns=columns, show="headings")
        for column, label, width in (
            ("record", "SDF record", 85),
            ("identifier", "Compound Notes ID", 190),
            ("smiles", "Canonical isomeric SMILES", 360),
            ("mw", "MW", 90),
            ("action", "Action", 180),
        ):
            preview.heading(column, text=label)
            preview.column(column, width=width, anchor="w")
        preview.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=preview.yview)
        x_scroll = ttk.Scrollbar(preview_frame, orient="horizontal", command=preview.xview)
        preview.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        footer = ttk.Frame(body)
        footer.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        plan_status_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=plan_status_var).pack(side="left", fill="x", expand=True)
        import_button = ttk.Button(footer, text="Import", style="FileAction.TButton")
        import_button.pack(side="right", padx=(6, 0))
        ttk.Button(footer, text="Cancel", command=win.destroy).pack(side="right")

        current_plan: tuple[SdfImportPlanRow, ...] = ()

        def refresh_preview(_event=None):
            nonlocal current_plan
            identifier_field = field_by_label[identifier_var.get()]
            current_plan = plan_sdf_import(
                result.compounds,
                identifier_field,
                [record.values.get("ID", "") for record in self.records],
                duplicate_var.get(),
            )
            for item in preview.get_children():
                preview.delete(item)
            importable = 0
            for row in current_plan:
                if row.action in {"add", "add_suffixed", "update"}:
                    importable += 1
                preview.insert(
                    "",
                    "end",
                    values=(
                        row.record_number,
                        row.final_id or row.requested_id,
                        row.smiles,
                        row.molecular_weight,
                        self._sdf_action_label(row),
                    ),
                )
            skipped = len(current_plan) - importable
            plan_status_var.set(f"Ready to import: {importable}   Skipped: {skipped}")
            import_button.configure(
                text=f"Import {importable} record{'s' if importable != 1 else ''}",
                state=("normal" if importable else "disabled"),
            )

        def apply_import():
            try:
                added, updated, skipped = self._apply_sdf_import_plan(current_plan)
            except Exception as exc:
                messagebox.showerror("SDF import failed", str(exc), parent=win)
                return
            win.destroy()
            invalid = len(result.invalid_record_numbers)
            self.status_var.set(
                f"SDF import: added {added}, updated {updated}, skipped {skipped}, invalid {invalid}. Save Current to write Excel."
            )
            messagebox.showinfo(
                "SDF import complete",
                f"Added: {added}\nUpdated: {updated}\nSkipped: {skipped}\nInvalid structures: {invalid}\n\n"
                "Imported rows are in Compound Notes. Use Save Current or Save As to write them to Excel.",
            )

        import_button.configure(command=apply_import)
        identifier_combo.bind("<<ComboboxSelected>>", refresh_preview)
        duplicate_combo.bind("<<ComboboxSelected>>", refresh_preview)
        win.bind("<Escape>", lambda _event: win.destroy())
        refresh_preview()

    def _pick_excel(self):
        p = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if not p:
            return

        selected = Path(p)
        try:
            self._load_excel(selected, mark_loaded=True)
            self.source_excel = selected
        except Exception as exc:
            messagebox.showerror("Load Excel failed", f"Could not load file:\n{selected}\n\n{exc}")
            self.status_var.set("Failed to load Excel file")

    def _refresh_saved_excel_values(self):
        """Reflect any safely merged workbook edits before the next form commit."""
        selected = self.tree.selection()
        index = self._form_record_index
        self._refresh_tree()
        self.tree.selection_set([iid for iid in selected if self.tree.exists(iid)])
        if index is not None and 0 <= index < len(self.records):
            self._load_record_into_form(self.records[index].values, index)

    def _save_current_excel(self, show_message: bool = True) -> bool:
        self._commit_current_form_to_record()
        selected_path = self.source_excel
        if not self.excel_loaded or self.source_excel is None:
            out = filedialog.asksaveasfilename(
                title="Save compound notes Excel",
                defaultextension=".xlsx",
                filetypes=[("Excel", "*.xlsx")],
                initialfile="Compound_Notes.xlsx",
            )
            if not out:
                self.status_var.set("Save cancelled.")
                return False
            selected_path = Path(out)

        assert selected_path is not None
        try:
            self._write_excel(selected_path)
        except Exception as exc:
            self.status_var.set("Save stopped; the workbook was not updated.")
            messagebox.showerror("Save Compound Notes failed", str(exc), parent=self)
            return False
        self.source_excel = selected_path
        self.excel_loaded = True
        self._set_associated_workbook_name(selected_path.name)
        self._refresh_saved_excel_values()
        self._mark_saved_snapshot()
        self.status_var.set(f"Saved to: {self.source_excel}")
        if show_message:
            messagebox.showinfo("Saved", f"Saved to:\n{self.source_excel}")
        return True

    def _save_as_excel(self) -> bool:
        self._commit_current_form_to_record()
        out = filedialog.asksaveasfilename(
            title="Save compound notes Excel as",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=self.source_excel.name if self.excel_loaded and self.source_excel is not None else "Compound_Notes.xlsx",
        )
        if out:
            new_path = Path(out)
            old_path = self.source_excel if self.excel_loaded else None
            template_path = old_path if old_path is not None and old_path.resolve() != new_path.resolve() else None
            try:
                self._write_excel(new_path, template_path=template_path)
            except Exception as exc:
                self.status_var.set("Save stopped; the workbook was not updated.")
                messagebox.showerror("Save Compound Notes failed", str(exc), parent=self)
                return False
            self.source_excel = new_path
            self.excel_loaded = True
            self._set_associated_workbook_name(new_path.name)
            self._refresh_saved_excel_values()
            self._mark_saved_snapshot()
            self.status_var.set(f"Saved to: {out}")
            messagebox.showinfo("Saved", f"Saved to:\n{out}")
            return True
        self.status_var.set("Save cancelled.")
        return False

    def _export_json(self):
        self._commit_current_form_to_record()
        out = self.base_dir / "Compound_Notes_Records.json"
        payload = {"saved_at": datetime.now().isoformat(timespec="seconds"), "count": len(self.records), "records": [r.values for r in self.records]}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        messagebox.showinfo("JSON exported", f"Saved:\n{out}")




def create_frame(master):
    return CompoundNotesFrame(master)
