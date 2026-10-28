"""Local Wildman-Crippen cLogP calculator; source structures are never modified."""
import argparse
import csv
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from rdkit import Chem, rdBase
from rdkit.Chem import Crippen, Draw
from PIL import ImageTk
try:
    from .molecular_properties import assess, EXPORT_KEYS, PROPERTY_KEYS, RULE_KEYS, RULE_METHOD, HELP
except ImportError:
    from molecular_properties import assess, EXPORT_KEYS, PROPERTY_KEYS, RULE_KEYS, RULE_METHOD, HELP

SCHEMA = "xinpilot_clogp_calculator.v1"
METHOD = "Wildman-Crippen (RDKit)"
COLUMNS = ("ID", "Name", "Reaction well", "SMILES", "cLogP (RDKit)", "Status")


def calculate(smiles):
    """Do not silently desalt or neutralize a user's structure."""
    if not str(smiles).strip():
        return "", "Missing SMILES"
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(str(smiles).strip())
    if mol is None or mol.GetNumAtoms() == 0:
        return "", "Invalid SMILES"
    if len(Chem.GetMolFrags(mol)) != 1:
        return "", "Multiple fragments: supply the neutral parent structure"
    if any(atom.GetFormalCharge() for atom in mol.GetAtoms()):
        return "", "Charged structure: neutral-parent cLogP not calculated"
    return f"{Crippen.MolLogP(mol):.3f}", "Calculated"


def load_payload(path):
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") not in (SCHEMA, "rxnpilot_clogp_calculator.v1", "syntrack_clogp_calculator.v1"):
        raise ValueError("Unsupported cLogP transfer file")
    products = payload.get("products")
    if not isinstance(products, list) or any(not isinstance(p, dict) for p in products):
        raise ValueError("Invalid products list")
    if payload.get("delete_after_load"):
        path.unlink(missing_ok=True)
    return products


def product_row(product):
    return [str(product.get(key, "") or "") for key in
            ("product_id", "product_name", "reaction_well", "product_smiles")] + ["", "Not calculated"]


class CLogPCalculator(tk.Tk):
    def __init__(self, products=()):
        super().__init__()
        self.title("Molecular Properties & Alerts Calculator")
        self.results = {}
        self._syncing = False
        self._preview_image = None
        self._alert_items = []
        self.geometry("1100x650")
        self.minsize(780, 480)
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Molecular Properties & Alerts Calculator", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(body, text="Local RDKit estimates and structural flags for review. No automatic desalting or neutralization.",
                  wraplength=740).pack(anchor="w", pady=(8, 12))
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(0, 10))
        for label, command in (("Import CSV", self.import_csv), ("Calculate selected", self.calculate_selected),
                               ("Calculate all", self.calculate_all), ("Export CSV", self.export_csv),
                               ("Delete selected", self.delete_selected)):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 8))
        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)
        compounds = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(compounds, text="Compounds")
        table = ttk.Frame(compounds)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=COLUMNS, show="headings", selectmode="extended")
        for col, width in zip(COLUMNS, (90, 130, 100, 260, 110, 300)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=70)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        editor = ttk.LabelFrame(compounds, text="Add or edit a compound", padding=10)
        editor.pack(fill="x", pady=(12, 0))
        self.fields = [tk.StringVar() for _ in range(4)]
        for i, (label, var) in enumerate(zip(COLUMNS[:4], self.fields)):
            ttk.Label(editor, text=label).grid(row=0, column=i, sticky="w")
            ttk.Entry(editor, textvariable=var).grid(row=1, column=i, sticky="ew", padx=(0, 8))
            editor.columnconfigure(i, weight=3 if i == 3 else 1)
        ttk.Button(editor, text="Add row", command=self.add_row).grid(row=2, column=0, pady=(8, 0), sticky="w")
        ttk.Button(editor, text="Update selected row", command=self.update_row).grid(row=2, column=1, columnspan=2, pady=(8, 0), sticky="w")
        self.tables = [self.tree]
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.selection_changed(self.tree))
        self.build_result_tabs()
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.refresh_preview())
        self.status = tk.StringVar(value="Select rows with Ctrl or Shift. CSV input requires a SMILES column; ID and Name are optional.")
        ttk.Label(body, textvariable=self.status, wraplength=740).pack(anchor="w", pady=(10, 0))
        for product in products:
            self.tree.insert("", "end", values=product_row(product))
        self.refresh_results()

    def result_table(self, parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=140 if col != "Status" else 310, minwidth=70)
        tree.grid(row=0, column=0, sticky="nsew")
        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree.bind("<<TreeviewSelect>>", lambda e: self.selection_changed(tree))
        tree.bind("<Motion>", lambda e: self.heading_help(e, tree))
        tree.bind("<Leave>", lambda e: self.hide_help())
        self.tables.append(tree)
        return tree

    def build_result_tabs(self):
        self._help_window = None
        self._help_text = ""
        properties = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(properties, text="Properties")
        self.property_tree = self.result_table(properties, ("ID", "Name", "Reaction well", "cLogP (RDKit)", *PROPERTY_KEYS, "Status"))
        rules = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(rules, text="Drug-likeness")
        ttk.Label(rules, text="Heuristics for review; passing does not establish efficacy, safety or oral absorption. Hover over headings for definitions.",
                  wraplength=740).pack(anchor="w", pady=(0, 8))
        self.rule_tree = self.result_table(rules, ("ID", "Name", "Reaction well", *RULE_KEYS, "Status"))
        alerts = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(alerts, text="Structural alerts")
        ttk.Label(alerts, text="PAINS and Brenk matches are flags, not proof of interference or toxicity. Select a compound, then an alert to highlight its atoms.",
                  wraplength=740).pack(anchor="w", pady=(0, 8))
        panes = ttk.Panedwindow(alerts, orient="vertical")
        panes.pack(fill="both", expand=True)
        summary = ttk.Frame(panes)
        panes.add(summary, weight=1)
        self.alert_tree = self.result_table(summary, ("ID", "Name", "Reaction well", "PAINS count", "Brenk count", "Status"))
        self.alert_tree.configure(height=4)
        details = ttk.Panedwindow(panes, orient="horizontal")
        panes.add(details, weight=2)
        list_frame = ttk.Frame(details)
        details.add(list_frame, weight=1)
        self.alert_list = tk.Listbox(list_frame, exportselection=False, height=5)
        self.alert_list.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(list_frame, orient="vertical", command=self.alert_list.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(list_frame, orient="horizontal", command=self.alert_list.xview)
        xs.grid(row=1, column=0, sticky="ew")
        self.alert_list.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.alert_list.bind("<<ListboxSelect>>", lambda e: self.draw_preview())
        preview_frame = ttk.Frame(details)
        details.add(preview_frame, weight=2)
        self.preview = ttk.Label(preview_frame, text="Select one compound to view its structure", anchor="center")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda e: self.draw_preview())
        # Keep both the summary and structural preview reachable after resizing.
        def preserve_preview(event):
            if event.height > 160:
                position = panes.sashpos(0)
                upper = max(70, event.height - 125)
                if position < 60 or position > upper:
                    panes.sashpos(0, min(upper, max(60, event.height // 2)))
        panes.bind("<Configure>", preserve_preview)

    def hide_help(self):
        if self._help_window is not None:
            self._help_window.destroy()
        self._help_window = None
        self._help_text = ""

    def heading_help(self, event, tree):
        text = ""
        if tree.identify_region(event.x, event.y) == "heading":
            index = tree.identify_column(event.x)
            if index and int(index[1:]) > 0:
                text = HELP.get(tree["columns"][int(index[1:]) - 1], "")
        if text == self._help_text:
            return
        self.hide_help()
        if text:
            self._help_text = text
            self._help_window = tk.Toplevel(self)
            self._help_window.overrideredirect(True)
            self._help_window.attributes("-topmost", True)
            ttk.Label(self._help_window, text=text, wraplength=360, padding=10).pack()
            self._help_window.geometry(f"+{min(event.x_root + 12, self.winfo_screenwidth() - 390)}+{event.y_root + 20}")

    def selection_changed(self, source):
        if self._syncing:
            return
        selected = source.selection()
        self._syncing = True
        try:
            for tree in self.tables:
                if tree is not source and set(tree.selection()) != set(selected):
                    tree.selection_set(selected)
        finally:
            self._syncing = False
        self.load_row()
        self.refresh_preview()

    def refresh_results(self):
        selected = self.tree.selection()
        self._syncing = True
        try:
            for tree in self.tables[1:]:
                for iid in tree.get_children():
                    if not self.tree.exists(iid):
                        tree.delete(iid)
                for iid in self.tree.get_children():
                    original = self.tree.item(iid, "values")
                    data = dict(zip(COLUMNS, original))
                    data.update(self.results.get(iid, {}))
                    values = [data.get(col, "") for col in tree["columns"]]
                    if tree.exists(iid):
                        tree.item(iid, values=values)
                    else:
                        tree.insert("", "end", iid=iid, values=values)
                if set(tree.selection()) != set(selected):
                    tree.selection_set(selected)
        finally:
            self._syncing = False
        self.refresh_preview()

    def refresh_preview(self):
        self.alert_list.delete(0, "end")
        self._alert_items = []
        selected = self.tree.selection()
        if len(selected) == 1:
            result = self.results.get(selected[0])
            self._alert_items = result.get("alerts", []) if result else []
            for alert in self._alert_items:
                self.alert_list.insert("end", f"{alert['catalog']}: {alert['name']}")
            if not self._alert_items:
                self.alert_list.insert("end", "No catalog matches" if result else "No assessment available; calculate and check Status")
            else:
                self.alert_list.selection_set(0)
        self.draw_preview()

    def draw_preview(self):
        selected = self.tree.selection()
        self._preview_image = None
        self.preview.configure(image="", text="Select one compound to view its structure")
        if len(selected) != 1:
            return
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(self.tree.item(selected[0], "values")[3])
        if mol is None or not mol.GetNumAtoms():
            self.preview.configure(text="No valid structure available")
            return
        indices = self.alert_list.curselection()
        atoms = self._alert_items[indices[0]]["atoms"] if indices and indices[0] < len(self._alert_items) else []
        size = (max(180, min(1000, self.preview.winfo_width() - 10)), max(100, min(650, self.preview.winfo_height() - 10)))
        img = Draw.MolToImage(mol, size=size, highlightAtoms=atoms)
        self._preview_image = ImageTk.PhotoImage(img, master=self)
        self.preview.configure(image=self._preview_image, text="")

    def load_row(self, event=None):
        selected = self.tree.selection()
        if len(selected) == 1:
            for var, value in zip(self.fields, self.tree.item(selected[0], "values")):
                var.set(value)

    def add_row(self):
        self.tree.insert("", "end", values=[v.get().strip() for v in self.fields] + ["", "Not calculated"])
        self.refresh_results()

    def update_row(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("Select one row", "Select one row to edit its identity or structure.", parent=self)
            return
        self.tree.item(selected[0], values=[v.get().strip() for v in self.fields] + ["", "Not calculated"])
        self.results.pop(selected[0], None)
        self.refresh_results()

    def delete_selected(self):
        for iid in self.tree.selection():
            self.results.pop(iid, None)
            self.tree.delete(iid)
        self.refresh_results()

    def calculate_rows(self, ids):
        count = 0
        for iid in ids:
            row = list(self.tree.item(iid, "values"))
            row[4], row[5] = calculate(row[3])
            self.results.pop(iid, None)
            with rdBase.BlockLogs():
                mol = Chem.MolFromSmiles(row[3]) if row[3].strip() else None
            if mol is not None and mol.GetNumAtoms() and len(Chem.GetMolFrags(mol)) == 1:
                try:
                    self.results[iid] = assess(mol, bool(row[4]))
                    if not row[4]:
                        row[5] = "Charged structure: descriptors/alerts only; cLogP, rules and QED not calculated"
                except Exception as exc:
                    row[5] = f"Assessment failed: {exc}"

            count += bool(row[4])
            self.tree.item(iid, values=row)
        self.refresh_results()
        self.status.set(f"Processed {len(ids)} rows; neutral cLogP available for {count}. Review Status for limitations.")

    def calculate_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select rows", "Select one or more compounds to calculate.", parent=self)
            return
        self.calculate_rows(selected)

    def calculate_all(self):
        self.calculate_rows(self.tree.get_children())

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                headers = {str(h).strip().lower(): h for h in (reader.fieldnames or [])}
                if "smiles" not in headers:
                    raise ValueError("CSV must contain a SMILES column.")
                rows = [[r.get(headers.get(k, ""), "") or "" for k in ("id", "name", "reaction well", "smiles")]
                        + ["", "Not calculated"] for r in reader]
            for row in rows:
                self.tree.insert("", "end", values=row)
            self.refresh_results()
            self.status.set(f"Imported {len(rows)} compounds.")
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow([*COLUMNS, *EXPORT_KEYS, "Method", "RDKit version", "Rule definitions"])
                for iid in self.tree.get_children():
                    writer.writerow([*self.tree.item(iid, "values"), *[self.results.get(iid, {}).get(k, "") for k in EXPORT_KEYS], METHOD, rdBase.rdkitVersion, RULE_METHOD])
            self.status.set("Results exported.")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)


def main():
    parser = argparse.ArgumentParser(description="Local molecular properties and structural alerts calculator")
    parser.add_argument("--input")
    args = parser.parse_args()
    products = load_payload(args.input) if args.input else []
    CLogPCalculator(products).mainloop()


if __name__ == "__main__":
    main()
