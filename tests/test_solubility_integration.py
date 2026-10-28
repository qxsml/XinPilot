import json
import sys
import tempfile
import subprocess
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastsolv_bridge import run_external
from solubility_panel import SolubilityPanel, canonical
from xinpilot_tooltips import Tooltip, install_tooltips


class SolubilityTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.temp = tempfile.TemporaryDirectory()
        self.owner = SimpleNamespace(base_dir=Path(self.temp.name), vars={"SMILES": tk.StringVar(self.root, "CCO")}, tree=ttk.Treeview(self.root))
        self.panel = SolubilityPanel(self.root, self.owner)
        self.panel.pack()

    def tearDown(self):
        self.root.destroy()
        self.temp.cleanup()

    def test_results_follow_structure_and_units(self):
        self.panel.cache = [dict(solute=canonical("CCO"), solvent="O", solvent_name="Water", temperature_c=25, log_s=-2, spread=.1, version="1.0.1")]
        self.panel.refresh()
        values = self.panel.table.item("0", "values")
        self.assertEqual(values[3], "10")  # 0.01 M -> 10 mM
        self.assertAlmostEqual(float(values[4]), .4607, places=3)  # g/L == mg/mL
        self.owner.vars["SMILES"].set("CC")
        self.assertFalse(self.panel.table.get_children())
        self.owner.vars["SMILES"].set("OCC")
        self.assertEqual(len(self.panel.table.get_children()), 1)

    def test_background_result_not_assigned_to_new_selection(self):
        self.owner.vars["SMILES"].set("CC")
        self.panel.jobs.put((dict(mode="predict", solute=canonical("CCO"), solvent="O", solvent_name="Water", temperature_c=25), dict(log_s=-2, spread=.1, version="1.0.1"), None))
        self.panel.poll()
        self.assertFalse(self.panel.table.get_children())
        self.assertEqual(json.loads(self.panel.cache_path.read_text())["results"][0]["solute"], "CCO")

    def test_missing_environment_is_clear(self):
        with self.assertRaisesRegex(ValueError, "python.exe"):
            run_external(str(Path(self.temp.name) / "absent.exe"), {"mode": "check"})

    def test_batch_preserves_other_solvents_and_temperatures(self):
        self.panel.cache = [dict(solute="CCO", solvent="O", solvent_name="Water", temperature_c=t, log_s=-2, spread=.1, version="1.0.1") for t in (25, 50)]
        items = [dict(solute=s, compound_id=str(i), solvent="CO", solvent_name="Methanol", temperature_c=25) for i, s in enumerate(("CCO", "CC"))]
        results = [dict(log_s=-1, spread=.1, version="1.0.1") for _ in items]
        for _ in range(2):
            self.panel.jobs.put(({"mode": "batch", "items": items}, {"results": results}, None))
            self.panel.poll()
        self.assertEqual(len(self.panel.cache), 4)
        self.assertEqual(len(self.panel.table.get_children()), 3)
        self.assertEqual(len(json.loads(self.panel.cache_path.read_text())["results"]), 4)

    def test_multiple_selected_ids_and_current_edit_are_used(self):
        self.owner.records = [SimpleNamespace(values={"ID": "A", "SMILES": "CC"}), SimpleNamespace(values={"ID": "B", "SMILES": "CO"})]
        for i in range(2):
            self.owner.tree.insert("", "end", iid=str(i))
        self.owner.tree.selection_set("0", "1")
        self.owner._form_record_index = 0
        self.assertEqual(self.panel.selected_compounds(), [("A", "CCO"), ("B", "CO")])

    def test_mismatched_batch_response_does_not_mutate_cache(self):
        self.panel.cache = [{"solute": "CCO"}]
        self.panel.jobs.put(({"mode": "batch", "items": [{}, {}]}, {"results": [{}]}, None))
        self.panel.poll()
        self.assertEqual(self.panel.cache, [{"solute": "CCO"}])

    def test_timeout_is_readable_and_does_not_expose_runner_source(self):
        executable = Path(self.temp.name) / "python.exe"
        executable.touch()
        with patch("fastsolv_bridge.subprocess.run", side_effect=subprocess.TimeoutExpired("command", 300)):
            with self.assertRaisesRegex(RuntimeError, "five minutes"):
                run_external(executable, {"mode": "check"})

    def test_tooltip_preserves_command_and_hides(self):
        button = ttk.Button(self.root, text="Export Project")
        button.pack()
        command = button.cget("command")
        install_tooltips(self.root)
        install_tooltips(self.root)
        self.root.update()
        tip = button._xinpilot_tooltip
        tip.show()
        self.assertIsNotNone(tip.popup)
        tip.hide()
        self.assertIsNone(tip.popup)
        self.assertEqual(button.cget("command"), command)


if __name__ == "__main__":
    unittest.main()
