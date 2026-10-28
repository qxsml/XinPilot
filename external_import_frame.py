"""External transfer UI adapter; table interpretation lives in application services."""
from __future__ import annotations

import copy
import json
import zipfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from xinpilot.application import external_import as service
from xinpilot.application.external_stocks import HEADERS, stage_stocks, write_template


class ExternalImportFrame(ttk.Frame):
    def __init__(self, master, *, compound_provider, add_compounds, push_callback):
        super().__init__(master, padding=10)
        self.compound_provider = compound_provider
        self.add_compounds = add_compounds
        self.push_callback = push_callback
        self.table = {}
        self.sources = {}
        self.transfers = []
        self.reviewed_settings = None
        self.stock_originals = []
        self.column_vars = {key: tk.StringVar(self) for key in service.FIELDS}
        self.unit_var = tk.StringVar(self)
        self.format_var = tk.StringVar(self)
        self.destination_var = tk.StringVar(self)
        self.status_var = tk.StringVar(self, value="Import a transfer table, review its columns, then link source stocks to Compound Notes.")
        self.file_var = tk.StringVar(self, value="No transfer file imported")
        self.chemical_var = tk.StringVar(self)
        self.bb_var = tk.BooleanVar(self)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        for label, command in (("Import transfer file", self._choose_file), ("Load mappings", self._load_mappings),
                               ("Save mappings", self._save_mappings)):
            ttk.Button(toolbar, text=label, command=lambda fn=command: self._run(fn)).pack(side="left", padx=(0, 6))
        ttk.Label(self, textvariable=self.file_var).pack(anchor="w", pady=5)
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill="both", expand=True)
        self.columns_page = ttk.Frame(self.pages, padding=8)
        self.sources_page = ttk.Frame(self.pages, padding=8)
        self.preview_page = ttk.Frame(self.pages, padding=8)
        for page, title in ((self.columns_page, "1. Columns and format"), (self.sources_page, "2. Source stocks"),
                            (self.preview_page, "3. Transfer preview")):
            self.pages.add(page, text=title)
        ttk.Label(self.columns_page, text="Confirm each column. Source wells must use labels such as A1. One reaction destination plate per import.", wraplength=900).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.column_boxes = {}
        for number, key in enumerate(service.FIELDS, 1):
            caption = key.replace("_", " ").capitalize()
            if key == "chemical_id":
                caption = "Chemical ID"
            if key in {"chemical_id", "destination_labware"}:
                caption += " (optional column)"
            ttk.Label(self.columns_page, text=caption).grid(row=number, column=0, sticky="w", padx=(0, 15), pady=3)
            box = ttk.Combobox(self.columns_page, textvariable=self.column_vars[key], state="readonly", width=48)
            box.grid(row=number, column=1, sticky="ew", pady=3)
            self.column_boxes[key] = box
        for row, label, var, choices in ((7, "Transfer volume unit (required)", self.unit_var, list(service.UNITS)),
                                         (8, "Destination format (required)", self.format_var, list(service.FORMATS))):
            ttk.Label(self.columns_page, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(self.columns_page, textvariable=var, values=choices, state="readonly").grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(self.columns_page, text="Destination name (if absent from file)").grid(row=9, column=0, sticky="w", pady=3)
        ttk.Entry(self.columns_page, textvariable=self.destination_var).grid(row=9, column=1, sticky="ew", pady=3)
        ttk.Button(self.columns_page, text="Validate and preview transfers", style="FileAction.TButton",
                   command=lambda: self._run(self._preview)).grid(row=10, column=0, columnspan=2, sticky="w", pady=10)
        self.columns_page.columnconfigure(1, weight=1)
        ttk.Label(self.sources_page, text="Select a source, assign its Chemical ID and building-block status, then Apply. New IDs must be added to Compound Notes or imported using the source-stock template.", wraplength=1000).pack(anchor="w", pady=(0, 6))
        self.source_tree = self._table(self.sources_page, ("Source labware", "Source well", "Chemical ID", "Building block", "Match"), 8)
        self.source_tree.bind("<<TreeviewSelect>>", self._source_selected)
        editor = ttk.Frame(self.sources_page)
        editor.pack(fill="x", pady=7)
        ttk.Label(editor, text="Chemical ID").pack(side="left")
        self.chemical_box = ttk.Combobox(editor, textvariable=self.chemical_var, width=30)
        self.chemical_box.pack(side="left", padx=6)
        ttk.Checkbutton(editor, text="Building block", variable=self.bb_var).pack(side="left", padx=6)
        ttk.Button(editor, text="Apply to selected source", command=lambda: self._run(self._apply_source)).pack(side="left", padx=6)
        stocks = ttk.Frame(self.sources_page)
        stocks.pack(fill="x")
        ttk.Button(stocks, text="Generate source-stock Excel template", command=lambda: self._run(self._template)).pack(side="left", padx=(0, 6))
        ttk.Button(stocks, text="Import completed source-stock template", command=lambda: self._run(self._import_stocks)).pack(side="left")
        self.preview_tree = self._table(self.preview_page, ("Source labware", "Source well", "Destination", "Well", "Volume (uL)", "Chemical ID"), 12)
        ttk.Label(self.preview_page, text="All transfers are retained, including repeated rows. Volumes come from the imported file; amounts are calculated only when stock concentration is available.", wraplength=1000).pack(anchor="w", pady=6)
        ttk.Button(self, text="Push All to Cheminformatics", style="FileAction.TButton",
                   command=lambda: self._run(self._push)).pack(anchor="w", pady=8)
        ttk.Label(self, textvariable=self.status_var, wraplength=1100).pack(anchor="w")

    @staticmethod
    def _table(parent, columns, height):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=145, minwidth=80)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _run(self, callback):
        try:
            return callback()
        except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("External Import", str(exc), parent=self)

    def _compounds(self):
        return [dict(record.values) for record in self.compound_provider()]

    def _settings(self):
        return {"columns": {k: v.get() for k, v in self.column_vars.items()}, "unit": self.unit_var.get(),
                "format": self.format_var.get(), "destination": self.destination_var.get()}

    def _read_file(self, path):
        try:
            return service.read_table(path)
        except ValueError as exc:
            if not str(exc).startswith("Choose an Excel worksheet:"):
                raise
            sheet = simpledialog.askstring("Excel worksheet", str(exc), parent=self)
            return service.read_table(path, sheet) if sheet else None

    def _choose_file(self):
        path = filedialog.askopenfilename(parent=self, title="Import transfer table",
                                         filetypes=[("Transfer tables", "*.csv *.tsv *.txt *.xlsx *.xlsm *.json")])
        if not path:
            return
        table = self._read_file(path)
        if table is None:
            return
        if self.table and not messagebox.askyesno("Replace imported transfers", "Replace the current external transfer table? Its previously pushed records remain until you push again.", parent=self):
            return
        self.table = table
        self.sources, self.transfers, self.stock_originals = {}, [], []
        self.reviewed_settings = None
        self.unit_var.set("")
        self.format_var.set("")
        self.destination_var.set("")
        suggestions = service.suggest_columns(table["headers"])
        for key, box in self.column_boxes.items():
            box.configure(values=[""] + table["headers"])
            self.column_vars[key].set(suggestions[key])
        self.file_var.set(f"{table['original']['name']} — {len(table['rows'])} transfer rows")
        self._refresh_sources()
        self._refresh_preview()
        self.pages.select(self.columns_page)
        self.status_var.set("Review suggested columns and select volume unit and destination format.")

    def _preview(self):
        if not self.table:
            raise ValueError("Import a transfer file first.")
        settings = self._settings()
        rows = service.normalize(self.table, settings["columns"], settings["unit"], settings["format"], settings["destination"])
        sources = service.source_rows(rows, self.sources)
        self.transfers, self.sources = rows, sources
        self.reviewed_settings = settings
        self._refresh_sources()
        self._refresh_preview()
        self.pages.select(self.sources_page)
        self.status_var.set(f"Validated {len(rows)} transfers and {len(sources)} source locations. Review every Chemical ID before pushing.")

    def _require_preview(self):
        if not self.transfers or self._settings() != self.reviewed_settings:
            raise ValueError("Validate and preview the current columns and format first.")

    def _refresh_sources(self):
        self.source_tree.delete(*self.source_tree.get_children())
        counts = {}
        for compound in self._compounds():
            cid = str(compound.get("ID", ""))
            counts[cid] = counts.get(cid, 0) + 1
        self.chemical_box.configure(values=sorted(k for k in counts if k))
        self._source_keys = list(self.sources)
        for index, source in enumerate(self.sources.values()):
            count = counts.get(source.get("chemical_id", ""), 0)
            status = "Matched" if count == 1 else "Missing ID" if count == 0 else "Ambiguous ID"
            self.source_tree.insert("", "end", iid=str(index), values=(source["source_labware"], source["source_well"], source.get("chemical_id", ""), "Yes" if source.get("is_building_block") else "No", status))

    def _refresh_preview(self):
        self.preview_tree.delete(*self.preview_tree.get_children())
        # Keep large tables responsive; all rows remain in state and are pushed.
        for row in self.transfers[:1000]:
            stock = self.sources.get(service.source_key(row["source_labware"], row["source_well"]), {})
            self.preview_tree.insert("", "end", values=(row["source_labware"], row["source_well"], row["destination_labware"], row["destination_well"], format(row["volume_ul"], ".9g"), stock.get("chemical_id", "")))

    def _source_selected(self, _event=None):
        selected = self.source_tree.selection()
        if selected:
            source = self.sources[self._source_keys[int(selected[0])]]
            self.chemical_var.set(source.get("chemical_id", ""))
            self.bb_var.set(bool(source.get("is_building_block")))

    def _apply_source(self):
        self._require_preview()
        selected = self.source_tree.selection()
        if not selected:
            raise ValueError("Select a source-stock row first.")
        source = self.sources[self._source_keys[int(selected[0])]]
        source.update(chemical_id=self.chemical_var.get().strip(), is_building_block=self.bb_var.get())
        self._refresh_sources()
        self._refresh_preview()

    def _template(self):
        self._require_preview()
        path = filedialog.asksaveasfilename(parent=self, title="Source-stock template", defaultextension=".xlsx", initialfile="source-stocks.xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            write_template(path, self.sources)
            self.status_var.set("Source-stock template saved. Fill chemical information only; transfers remain in the original imported file.")

    def _import_stocks(self):
        self._require_preview()
        path = filedialog.askopenfilename(parent=self, title="Completed source-stock template", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        table = service.read_table(path, "Source stocks")
        if not set(HEADERS).issubset(table["headers"]):
            raise ValueError("Use the generated source-stock template with its original column headers.")
        updated, additions = stage_stocks(table["rows"], self.sources, self._compounds())
        prompt = f"Apply {len(table['rows'])} source mappings and add {len(additions)} new Compound Notes records? Existing compound records will be preserved."
        if not messagebox.askyesno("Review source stocks", prompt, parent=self):
            return
        self.add_compounds(additions)
        self.sources = updated
        self.stock_originals.append(table["original"])
        self._refresh_sources()
        self._refresh_preview()
        self.status_var.set("Source-stock mappings applied. Review building-block flags, then Push All to Cheminformatics.")

    def rows_for_cheminformatics(self):
        self._require_preview()
        return service.pushed_rows(self.transfers, self.sources, self._compounds(), self.format_var.get())

    def _push(self):
        rows = self.rows_for_cheminformatics()
        self.push_callback(rows)
        self.status_var.set(f"Pushed {len(rows)} transfers. This replaces the previous external push; other sources remain. " + ("Transfer preview displays the first 1,000 rows." if len(rows) > 1000 else ""))

    def _save_mappings(self):
        self._require_preview()
        path = filedialog.asksaveasfilename(parent=self, title="Save reusable mappings", defaultextension=".json", initialfile="external-mappings.json")
        if path:
            Path(path).write_text(json.dumps({"version": 1, **self._settings(), "sources": self.sources}, indent=2), encoding="utf-8")

    def _load_mappings(self):
        if not self.table:
            raise ValueError("Import a transfer file before loading its mappings.")
        path = filedialog.askopenfilename(parent=self, title="Load reusable mappings", filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("sources"), dict):
            raise ValueError("Unsupported mapping file.")
        service.validate_state({"sources": data["sources"], "settings": data})
        for key, var in self.column_vars.items():
            column = data.get("columns", {}).get(key, "")
            var.set(column if column in self.table["headers"] else "")
        self.unit_var.set(data.get("unit", ""))
        self.format_var.set(data.get("format", ""))
        self.destination_var.set(data.get("destination", ""))
        self.sources = data["sources"]
        self.reviewed_settings = None
        self.pages.select(self.columns_page)
        self.status_var.set("Mappings loaded. Validate and review them against this file before pushing.")

    def export_state(self):
        return copy.deepcopy({"table": self.table, "sources": self.sources, "transfers": self.transfers,
                              "settings": self._settings(), "reviewed_settings": self.reviewed_settings,
                              "stock_originals": self.stock_originals})

    def import_state(self, state):
        service.validate_state(state)
        state = copy.deepcopy(state)
        self.table = state.get("table", {})
        self.sources = state.get("sources", {})
        self.transfers = state.get("transfers", [])
        self.reviewed_settings = state.get("reviewed_settings")
        self.stock_originals = state.get("stock_originals", [])
        settings = state.get("settings", {})
        for key, var in self.column_vars.items():
            self.column_boxes[key].configure(values=[""] + self.table.get("headers", []))
            var.set(settings.get("columns", {}).get(key, ""))
        self.unit_var.set(settings.get("unit", ""))
        self.format_var.set(settings.get("format", ""))
        self.destination_var.set(settings.get("destination", ""))
        self.file_var.set(self.table.get("original", {}).get("name", "No transfer file imported"))
        self._refresh_sources()
        self._refresh_preview()
        self.status_var.set("Imported external records restored." if self.table else "Import a transfer table to begin.")
