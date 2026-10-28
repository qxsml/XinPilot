"""Optional local solubility reference, independent of stock records."""
import json
import math
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from rdkit import Chem
from rdkit.Chem import Descriptors
from fastsolv_bridge import run_external
from xinpilot_tooltips import Tooltip

SOLVENTS = {
    "DMA": "CC(=O)N(C)C", "DMSO": "CS(C)=O", "DMF": "CN(C)C=O",
    "Acetonitrile": "CC#N", "Methanol": "CO", "Ethanol": "CCO",
    "Isopropanol": "CC(O)C", "Acetone": "CC(C)=O", "Ethyl acetate": "CCOC(C)=O",
    "THF": "C1CCOC1", "1,4-Dioxane": "C1COCCO1", "Toluene": "Cc1ccccc1",
    "Dichloromethane": "ClCCl", "Hexane": "CCCCCC", "Heptane": "CCCCCCC", "Water": "O",
}


def canonical(smiles):
    mol = Chem.MolFromSmiles(str(smiles).strip())
    if mol is None or not mol.GetNumAtoms():
        raise ValueError("Select a compound with valid SMILES.")
    return Chem.MolToSmiles(mol, isomericSmiles=True)


class SolubilityPanel(ttk.LabelFrame):
    def __init__(self, parent, owner):
        super().__init__(parent, text="Predicted solubility", padding=6)
        self.owner = owner
        self.config_path = owner.base_dir / "fastsolv_local.json"
        self.cache_path = owner.base_dir / "outputs" / "fastsolv_predictions.json"
        self.cache = self._read(self.cache_path).get("results", [])
        if not isinstance(self.cache, list):
            self.cache = []
        default_python = owner.base_dir.parent / "FASTSOLV" / ".venv" / "Scripts" / "python.exe"
        self.python = tk.StringVar(self, value=self._read(self.config_path).get("python", str(default_python) if default_python.exists() else ""))
        self.solvent = tk.StringVar(self, value="DMA")
        self.temperature = tk.StringVar(self, value="25")
        self.status = tk.StringVar(self, value="Select a compound, then Predict.")
        self.jobs = queue.Queue()
        self.busy = False
        self.columnconfigure(0, weight=1)
        settings = ttk.Frame(self)
        settings.grid(row=0, column=0, sticky="ew")
        settings.columnconfigure(0, weight=1)
        path = ttk.Entry(settings, textvariable=self.python, width=18)
        path.grid(row=0, column=0, sticky="ew")
        Tooltip(path, "Select python.exe inside your separate FASTSOLV environment. Models stay in that installation; predictions run locally.")
        ttk.Button(settings, text="Browse...", command=self.browse).grid(row=0, column=1, padx=(4, 0))
        self.check_button = ttk.Button(settings, text="Check", command=lambda: self.start(True))
        self.check_button.grid(row=0, column=2, padx=(4, 0))
        controls = ttk.Frame(self)
        controls.grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Label(controls, text="Solvent").pack(side="left")
        ttk.Combobox(controls, textvariable=self.solvent, values=list(SOLVENTS), state="readonly", width=13).pack(side="left", padx=4)
        ttk.Label(controls, text="°C").pack(side="left")
        ttk.Entry(controls, textvariable=self.temperature, width=5).pack(side="left", padx=4)
        self.predict_button = ttk.Button(controls, text="Predict All selected", command=self.start, style="ChemAction.TButton")
        self.predict_button.pack(side="left")
        self.batch_button = self.predict_button  # Compatibility for existing preview scripts.
        Tooltip(self.predict_button, "Run FASTSOLV for all selected Compound Notes rows, including a single selected row, at the chosen solvent and temperature. Results are local references; stock concentration is unchanged.")
        ttk.Style(self).configure("Solubility.Treeview", rowheight=23)
        self.table = ttk.Treeview(self, columns=("compound", "solvent", "temp", "mM", "mgml"), show="headings", height=10, style="Solubility.Treeview")
        for name, heading, width in (("compound", "Compound ID", 180), ("solvent", "Solvent", 150), ("temp", "°C", 70), ("mM", "mM", 100), ("mgml", "mg/mL", 100)):
            self.table.heading(name, text=heading)
            self.table.column(name, width=width, minwidth=35, anchor="w" if name in ("compound", "solvent") else "e")
        self.table.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.table.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.rowconfigure(2, weight=1)
        Tooltip(self.table, "Predicted saturation concentration, not a measured stock concentration. Results match the exact current structure. Select a result to see logS and model spread.")
        label = ttk.Label(self, textvariable=self.status, wraplength=345, justify="left", style="Status.TLabel")
        label.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(100, e.width)))
        self.table.bind("<<TreeviewSelect>>", self.show_detail)
        owner.vars["SMILES"].trace_add("write", lambda *_: self.refresh())
        self.bind("<Destroy>", self.closed, add="+")
        self.poll_id = None

    @staticmethod
    def _read(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def browse(self):
        path = filedialog.askopenfilename(parent=self, title="Select FASTSOLV Python executable", filetypes=[("Python executable", "*.exe")])
        if path:
            self.python.set(path)

    def selected_compounds(self):
        if not hasattr(self.owner, "records"):
            return [("", self.owner.vars["SMILES"].get())]
        selection = self.owner.tree.selection()
        compounds = []
        for iid in selection:
            index = int(iid)
            if 0 <= index < len(self.owner.records):
                record = self.owner.records[index].values
                # Include current form edits only for the record actually in the editor.
                smiles = self.owner.vars["SMILES"].get() if index == getattr(self.owner, "_form_record_index", None) else record.get("SMILES", "")
                compounds.append((str(record.get("ID") or f"Row {index + 1}"), smiles))
        return compounds

    def start(self, check=False, all_selected=True):
        if self.busy:
            return
        try:
            request = {"mode": "check"}
            if not check:
                if not self.owner.tree.selection():
                    raise ValueError("Select a compound row first.")
                compounds = self.selected_compounds()
                if not all_selected and len(compounds) != 1:
                    raise ValueError("Select one compound, or use Predict all selected.")
                temp = float(self.temperature.get())
                if not math.isfinite(temp) or temp <= -273.15:
                    raise ValueError("Enter a finite temperature above -273.15 °C.")
                items = []
                for compound_id, smiles in compounds:
                    try:
                        smiles = canonical(smiles)
                    except ValueError:
                        raise ValueError(f"{compound_id}: invalid or missing SMILES. Correct it or deselect this row.") from None
                    items.append(dict(mode="predict", compound_id=compound_id, solute=smiles, solvent=SOLVENTS[self.solvent.get()], temperature_c=temp, solvent_name=self.solvent.get()))
                if not items:
                    raise ValueError("Select a compound row first.")
                request = {"mode": "batch", "items": items} if all_selected else items[0]
            python = self.python.get().strip()
            if not Path(python).is_file():
                raise ValueError("Browse to the python.exe in your FASTSOLV environment.")
            self.config_path.write_text(json.dumps({"python": python}, indent=2), encoding="utf-8")
        except (ValueError, KeyError, OSError) as exc:
            messagebox.showerror("FASTSOLV", str(exc), parent=self)
            return
        self.busy = True
        self.check_button.state(["disabled"])
        self.predict_button.state(["disabled"])
        self.progress.start(12)
        self.status.set("Checking local installation…" if check else f"Predicting {len(items)} selected compound(s) locally… You can continue browsing.")
        def work():
            try:
                self.jobs.put((request, run_external(python, request), None))
            except Exception as exc:
                self.jobs.put((request, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.poll_id = self.after(150, self.poll)

    def poll(self):
        self.poll_id = None
        try:
            request, result, error = self.jobs.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.check_button.state(["!disabled"])
            self.predict_button.state(["!disabled"])
            self.progress.stop()
            if error:
                self.status.set("FASTSOLV failed. Check the installation path and models.")
                messagebox.showerror("FASTSOLV", error, parent=self)
            elif request["mode"] == "check":
                self.status.set(f"FASTSOLV {result['version']} ready; four verified local models.")
            else:
                requests = request["items"] if request["mode"] == "batch" else [request]
                results = result["results"] if request["mode"] == "batch" else [result]
                if len(requests) != len(results):
                    self.status.set("Prediction failed: result count does not match the selected compounds.")
                    return
                for entry, prediction in zip(requests, results):
                    item = dict(entry, **prediction, created=datetime.now(timezone.utc).isoformat())
                    self.cache = [r for r in self.cache if isinstance(r, dict) and (r.get("solute"), r.get("solvent"), r.get("temperature_c")) != (item["solute"], item["solvent"], item["temperature_c"])]
                    self.cache.append(item)
                try:
                    self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.cache_path.with_suffix(".tmp")
                    temporary.write_text(json.dumps({"results": self.cache}, indent=2, allow_nan=False), encoding="utf-8")
                    temporary.replace(self.cache_path)
                    self.refresh()
                except OSError as exc:
                    self.refresh()
                    self.status.set(f"Prediction available this session; could not save reference: {exc}")
        if self.busy:
            self.poll_id = self.after(150, self.poll)

    def refresh(self):
        self.table.delete(*self.table.get_children())
        self.visible = []
        compounds = {}
        for compound_id, raw_smiles in self.selected_compounds():
            try:
                smiles = canonical(raw_smiles)
                compounds.setdefault(smiles, []).append(compound_id)
            except ValueError:
                pass
        for row in self.cache:
            if not isinstance(row, dict) or row.get("solute") not in compounds:
                continue
            try:
                mw = Descriptors.MolWt(Chem.MolFromSmiles(row["solute"]))
                molar = 10 ** float(row["log_s"])
                if not math.isfinite(molar) or molar <= 0:
                    continue
                idx = len(self.visible)
                self.visible.append(row)
                self.table.insert("", "end", iid=str(idx), values=(", ".join(compounds[row["solute"]]), row["solvent_name"], f"{row['temperature_c']:g}", f"{molar*1000:.3g}", f"{molar*mw:.3g}"))
            except (KeyError, ValueError, OverflowError, TypeError):
                continue
        if not self.busy:
            self.status.set("Predicted reference only. Select a result for details." if self.visible else "No predictions for this structure. Changed structures need a new prediction.")

    def show_detail(self, event=None):
        selection = self.table.selection()
        if selection:
            row = self.visible[int(selection[0])]
            self.status.set(f"logS (mol/L): {row['log_s']:.3f}; model spread: {row['spread']:.3f} log units (not a confidence interval). FASTSOLV {row['version']}.")

    def closed(self, event):
        if event.widget is self and self.poll_id:
            self.after_cancel(self.poll_id)
            self.poll_id = None
