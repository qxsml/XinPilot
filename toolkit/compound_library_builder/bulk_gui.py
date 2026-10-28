"""Standalone Tk/ttk GUI for bulk virtual reaction enumeration."""

from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from bulk_engine import (
    BuildingBlock,
    EnumerationResult,
    ReactionTemplate,
    estimate_combinations,
    export_results,
    inspect_source,
    load_building_blocks,
    load_reaction_templates,
    enumerate_library,
    single_building_block,
)


APP_TITLE = "Bulk Cheminformatics — Reaction Library Enumerator"
INPUT_FILETYPES = [
    ("Supported structures", "*.csv *.xlsx *.xlsm *.sdf *.sd"),
    ("CSV", "*.csv"),
    ("Excel", "*.xlsx *.xlsm"),
    ("SDF", "*.sdf *.sd"),
    ("All files", "*.*"),
]


class RolePanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc, role_number: int) -> None:
        super().__init__(master, text=f"Building block {role_number}", padding=8)
        self.role_number = role_number
        self.mode = tk.StringVar(value="file")
        self.path = tk.StringVar()
        self.id_field = tk.StringVar(value="ID")
        self.smiles_field = tk.StringVar(value="SMILES")
        self.single_id = tk.StringVar(value=f"BB{role_number}-001")
        self.single_smiles = tk.StringVar()
        self.status = tk.StringVar(value="Choose a CSV, Excel, or SDF file.")
        self._inspection = None

        ttk.Radiobutton(self, text="Load a file", variable=self.mode, value="file", command=self._update_mode).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(self, text="Single building block", variable=self.mode, value="single", command=self._update_mode).grid(row=0, column=1, columnspan=2, sticky="w", padx=(12, 0))

        self.file_entry = ttk.Entry(self, textvariable=self.path)
        self.file_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 4))
        self.browse_button = ttk.Button(self, text="Browse…", command=self._browse)
        self.browse_button.grid(row=1, column=2, sticky="e", padx=(6, 0), pady=(7, 4))

        ttk.Label(self, text="ID column/property").grid(row=2, column=0, sticky="w", pady=(4, 2))
        ttk.Label(self, text="SMILES column").grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(4, 2))
        self.id_combo = ttk.Combobox(self, textvariable=self.id_field, state="readonly", width=20)
        self.id_combo.grid(row=3, column=0, sticky="ew")
        self.smiles_combo = ttk.Combobox(self, textvariable=self.smiles_field, state="readonly", width=20)
        self.smiles_combo.grid(row=3, column=1, sticky="ew", padx=(6, 0))

        ttk.Label(self, text="Single ID").grid(row=4, column=0, sticky="w", pady=(7, 2))
        ttk.Label(self, text="Single SMILES").grid(row=4, column=1, sticky="w", padx=(6, 0), pady=(7, 2))
        self.single_id_entry = ttk.Entry(self, textvariable=self.single_id)
        self.single_id_entry.grid(row=5, column=0, sticky="ew")
        self.single_smiles_entry = ttk.Entry(self, textvariable=self.single_smiles)
        self.single_smiles_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(6, 0))

        self.status_label = ttk.Label(self, textvariable=self.status, foreground="#555555")
        self.status_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(7, 0))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self._update_mode()

    def set_role(self, role_name: str) -> None:
        self.configure(text=f"Building block {self.role_number}: {role_name}")

    def _browse(self) -> None:
        path = filedialog.askopenfilename(title=f"Select building block {self.role_number}", filetypes=INPUT_FILETYPES)
        if not path:
            return
        self.path.set(path)
        try:
            inspection = inspect_source(path)
        except Exception as exc:
            self._inspection = None
            self.status.set(f"Cannot read file: {exc}")
            messagebox.showerror("Input file", str(exc), parent=self)
            return
        self._inspection = inspection
        self.id_combo.configure(values=inspection.fields)
        self.id_field.set(inspection.default_id_field)
        if inspection.kind == "SDF":
            self.smiles_combo.configure(values=("<SDF structure>",), state="disabled")
            self.smiles_field.set("<SDF structure>")
        else:
            self.smiles_combo.configure(values=inspection.fields, state="readonly")
            self.smiles_field.set(inspection.default_smiles_field or "")
        self.status.set(f"{inspection.kind}: {len(inspection.fields)} available columns/properties")

    def _update_mode(self) -> None:
        file_mode = self.mode.get() == "file"
        file_state = "normal" if file_mode else "disabled"
        self.file_entry.configure(state=file_state)
        self.browse_button.configure(state=file_state)
        if file_mode:
            self.id_combo.configure(state="readonly")
            if self._inspection and self._inspection.kind == "SDF":
                self.smiles_combo.configure(state="disabled")
            else:
                self.smiles_combo.configure(state="readonly")
        else:
            self.id_combo.configure(state="disabled")
            self.smiles_combo.configure(state="disabled")
        single_state = "normal" if not file_mode else "disabled"
        self.single_id_entry.configure(state=single_state)
        self.single_smiles_entry.configure(state=single_state)

    def snapshot(self) -> dict[str, Any]:
        """Copy Tk values on the UI thread before background file loading."""
        return {
            "role_number": self.role_number,
            "mode": self.mode.get(),
            "path": self.path.get().strip(),
            "id_field": self.id_field.get().strip(),
            "smiles_field": self.smiles_field.get().strip(),
            "single_id": self.single_id.get().strip(),
            "single_smiles": self.single_smiles.get().strip(),
        }


class BulkCheminformaticsApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(940, 680)

        self.templates = load_reaction_templates()
        self.templates_by_label = {template.label: template for template in self.templates}
        self.reaction_label = tk.StringVar(value=self.templates[0].label)
        self.product_prefix = tk.StringVar(value="PROD-")
        self.start_number = tk.StringVar(value="1")
        self.status = tk.StringVar(value="Ready")
        self.progress_text = tk.StringVar(value="")
        self.result: EnumerationResult | None = None
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._cancel_event: threading.Event | None = None
        self._worker: threading.Thread | None = None

        self._configure_style()
        self._build_ui()
        self._reaction_changed()
        self.after(100, self._poll_queue)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        available = style.theme_names()
        for theme in ("vista", "xpnative", "clam"):
            if theme in available:
                style.theme_use(theme)
                break
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Muted.TLabel", foreground="#5b6470")
        style.configure("Treeview", rowheight=24)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Bulk reaction library", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Enumerate virtual products while retaining every building block ID and source property.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        setup = ttk.Frame(outer)
        setup.pack(fill="x")
        ttk.Label(setup, text="Reaction type").grid(row=0, column=0, sticky="w")
        reaction_combo = ttk.Combobox(
            setup,
            textvariable=self.reaction_label,
            values=[template.label for template in self.templates],
            state="readonly",
            width=42,
        )
        reaction_combo.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        reaction_combo.bind("<<ComboboxSelected>>", lambda _event: self._reaction_changed())
        ttk.Label(setup, text="Product ID prefix").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Entry(setup, textvariable=self.product_prefix, width=18).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(2, 8))
        ttk.Label(setup, text="Start number").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(setup, textvariable=self.start_number, width=12).grid(row=1, column=2, sticky="ew", padx=(12, 0), pady=(2, 8))
        setup.columnconfigure(0, weight=1)

        self.role_container = ttk.Frame(outer)
        self.role_container.pack(fill="x", pady=(2, 8))
        self.role_panels = [RolePanel(self.role_container, index) for index in (1, 2, 3)]
        for index, panel in enumerate(self.role_panels):
            panel.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 4, 0 if index == 2 else 4))
            self.role_container.columnconfigure(index, weight=1, uniform="roles")

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(2, 8))
        self.generate_button = ttk.Button(controls, text="Generate library", command=self._start_generation)
        self.generate_button.pack(side="left")
        self.cancel_button = ttk.Button(controls, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(6, 0))
        self.export_button = ttk.Button(controls, text="Export full results…", command=self._export, state="disabled")
        self.export_button.pack(side="left", padx=(6, 0))
        self.progress = ttk.Progressbar(controls, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(14, 8))
        ttk.Label(controls, textvariable=self.progress_text, width=24, anchor="e").pack(side="right")

        self.results_notebook = ttk.Notebook(outer)
        self.results_notebook.pack(fill="both", expand=True)
        self.product_tree = self._tree_tab("Products")
        self.failure_tree = self._tree_tab("Failures / warnings")

        status_bar = ttk.Frame(outer)
        status_bar.pack(fill="x", pady=(7, 0))
        ttk.Label(status_bar, textvariable=self.status).pack(side="left")
        ttk.Label(status_bar, text="Enumeration only — docking preparation is intentionally separate.", style="Muted.TLabel").pack(side="right")

    def _tree_tab(self, title: str) -> ttk.Treeview:
        frame = ttk.Frame(self.results_notebook, padding=4)
        self.results_notebook.add(frame, text=title)
        tree = ttk.Treeview(frame, show="headings")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    @property
    def current_template(self) -> ReactionTemplate:
        return self.templates_by_label[self.reaction_label.get()]

    def _reaction_changed(self) -> None:
        template = self.current_template
        for index, panel in enumerate(self.role_panels):
            if index < template.reactant_count:
                panel.set_role(template.reactant_labels[index])
                panel.grid()
            else:
                panel.grid_remove()
        self.status.set(f"{template.label}: {template.reactant_count} building block role(s)")

    def _set_busy(self, busy: bool) -> None:
        self.generate_button.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.export_button.configure(state="disabled" if busy or self.result is None else "normal")

    def _start_generation(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        try:
            start = int(self.start_number.get())
            if start < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Start number", "Start number must be a non-negative integer.", parent=self)
            return
        prefix = self.product_prefix.get().strip()
        if not prefix:
            messagebox.showerror("Product IDs", "Enter a product ID prefix.", parent=self)
            return

        self.result = None
        self._cancel_event = threading.Event()
        self._set_busy(True)
        self.progress.configure(value=0)
        self.progress_text.set("Loading inputs…")
        self.status.set("Loading and validating building blocks…")
        template = self.current_template
        role_configs = [panel.snapshot() for panel in self.role_panels[: template.reactant_count]]
        self._worker = threading.Thread(
            target=self._generation_worker,
            args=(template, role_configs, prefix, start),
            daemon=True,
        )
        self._worker.start()

    @staticmethod
    def _load_role(config: dict[str, Any]) -> tuple[list[BuildingBlock], list[dict[str, Any]]]:
        number = config["role_number"]
        if config["mode"] == "single":
            return [single_building_block(config["single_id"], config["single_smiles"])], []
        path = config["path"]
        if not path:
            raise ValueError(f"Choose a file for building block {number}")
        inspection = inspect_source(path)
        id_field = config["id_field"]
        smiles_field = None if inspection.kind == "SDF" else config["smiles_field"]
        if id_field not in inspection.fields:
            raise ValueError(f"Choose a valid ID field for building block {number}")
        if inspection.kind != "SDF" and smiles_field not in inspection.fields:
            raise ValueError(f"Choose a valid SMILES field for building block {number}")
        result = load_building_blocks(path, id_field, smiles_field)
        if not result.records:
            raise ValueError(f"Building block {number} has no valid records")
        return result.records, result.issues

    def _generation_worker(
        self,
        template: ReactionTemplate,
        role_configs: list[dict[str, Any]],
        prefix: str,
        start: int,
    ) -> None:
        try:
            role_records: list[list[BuildingBlock]] = []
            input_issues: list[dict[str, Any]] = []
            for config in role_configs:
                records, issues = self._load_role(config)
                role_records.append(records)
                input_issues.extend(issues)
            total = estimate_combinations(template, role_records)
            self._queue.put(("estimate", total))
            if total > 250_000:
                self._queue.put(("confirm", (template, role_records, input_issues, prefix, start, total)))
                return
            self._run_enumeration(template, role_records, input_issues, prefix, start)
        except Exception as exc:
            self._queue.put(("error", (str(exc), traceback.format_exc())))

    def _run_enumeration(
        self,
        template: ReactionTemplate,
        role_records: list[list[BuildingBlock]],
        issues: list[dict[str, Any]],
        prefix: str,
        start: int,
    ) -> None:
        def report(done: int, total: int, products: int) -> None:
            if done == 1 or done == total or done % max(1, total // 500) == 0:
                self._queue.put(("progress", (done, total, products)))

        try:
            result = enumerate_library(
                template,
                role_records,
                product_prefix=prefix,
                start_number=start,
                prior_failures=issues,
                cancel_event=self._cancel_event,
                progress=report,
            )
            self._queue.put(("complete", result))
        except Exception as exc:
            self._queue.put(("error", (str(exc), traceback.format_exc())))

    def _confirm_large(self, payload: tuple[Any, ...]) -> None:
        template, role_records, issues, prefix, start, total = payload
        proceed = messagebox.askyesno(
            "Large enumeration",
            f"This will process {total:,} compatible combinations. It may use substantial memory and time. Continue?",
            parent=self,
        )
        if not proceed:
            self.status.set("Enumeration cancelled before reaction processing.")
            self.progress_text.set("")
            self._set_busy(False)
            return
        self._worker = threading.Thread(
            target=self._run_enumeration,
            args=(template, role_records, issues, prefix, start),
            daemon=True,
        )
        self._worker.start()

    def _cancel(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()
            self.status.set("Cancelling after the current combination…")

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "estimate":
                    self.status.set(f"Found {payload:,} compatible combinations.")
                elif kind == "confirm":
                    self._confirm_large(payload)
                elif kind == "progress":
                    done, total, products = payload
                    percent = (done / total * 100) if total else 0
                    self.progress.configure(value=percent)
                    self.progress_text.set(f"{done:,}/{total:,} · {products:,} products")
                elif kind == "complete":
                    self._show_result(payload)
                elif kind == "error":
                    message, details = payload
                    self._set_busy(False)
                    self.progress_text.set("")
                    self.status.set("Generation failed.")
                    messagebox.showerror("Generation failed", f"{message}\n\nTechnical details were printed to the console.", parent=self)
                    print(details)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _show_result(self, result: EnumerationResult) -> None:
        self.result = result
        self._set_busy(False)
        self.progress.configure(value=(result.processed_combinations / result.total_combinations * 100) if result.total_combinations else 0)
        self.progress_text.set(f"{result.processed_combinations:,}/{result.total_combinations:,}")
        self._populate_tree(self.product_tree, result.products)
        self._populate_tree(self.failure_tree, result.failures)
        preview_note = " Preview is limited to 1,000 rows; export contains all rows." if len(result.products) > 1000 or len(result.failures) > 1000 else ""
        action = "Cancelled" if result.cancelled else "Complete"
        self.status.set(
            f"{action}: {len(result.products):,} product rows, {result.unique_product_count:,} unique products, "
            f"{len(result.failures):,} failures/warnings.{preview_note}"
        )

    @staticmethod
    def _populate_tree(tree: ttk.Treeview, rows: list[dict[str, Any]], limit: int = 1000) -> None:
        tree.delete(*tree.get_children())
        columns: list[str] = []
        seen: set[str] = set()
        for row in rows[:limit]:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
        tree.configure(columns=columns)
        for column in columns:
            tree.heading(column, text=column)
            width = 210 if "SMILES" in column else 135
            tree.column(column, width=width, minwidth=70, stretch=True)
        for row in rows[:limit]:
            tree.insert("", "end", values=[row.get(column, "") for column in columns])

    def _export(self) -> None:
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(
            title="Export complete results",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx"), ("CSV", "*.csv"), ("SDF", "*.sdf")],
        )
        if not path:
            return
        try:
            outputs = export_results(path, self.result)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        messagebox.showinfo("Export complete", "Saved:\n" + "\n".join(str(item) for item in outputs), parent=self)


def main() -> None:
    app = BulkCheminformaticsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
