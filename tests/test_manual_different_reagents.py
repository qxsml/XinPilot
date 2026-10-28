from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from manual_workflow_frame import ManualWorkflowFrame  # noqa: E402


class ManualDifferentReagentTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(ManualWorkflowFrame)
        self.frame.compound_provider = lambda: [
            SimpleNamespace(values={"ID": "BB-01", "Name": "First", "Conc.": "0.5"}),
            SimpleNamespace(values={"ID": "BB-02", "Name": "Second", "Conc.": "0.5"}),
            SimpleNamespace(values={"ID": "CAT-01", "Name": "Catalyst", "Conc.": "0.1"}),
        ]

    def test_positional_assignments_share_volume_and_keep_per_well_metadata(self):
        rows = self.frame._different_reagent_rows(
            ["A1", "B3", "D5"],
            ["BB-01 - First", "BB-02 - Second", "CAT-01 - Catalyst"],
            [True, True, False],
            transfer_ul="12.5",
            reaction_umol="2.0",
            temperature="25 C",
            duration="1 h",
            notes="Manual batch",
            plate_size="96-well",
        )

        self.assertEqual(["A1", "B3", "D5"], [row["reaction_well"] for row in rows])
        self.assertEqual(["BB-01", "BB-02", "CAT-01"], [row["chemical_id"] for row in rows])
        self.assertEqual(["12.5", "12.5", "12.5"], [row["transfer_ul"] for row in rows])
        self.assertEqual([True, True, False], [row["is_building_block"] for row in rows])
        self.assertTrue(all(row["reaction_umol"] == "2.0" for row in rows))

    def test_assignment_count_must_match_selected_well_count(self):
        with self.assertRaisesRegex(ValueError, "exactly one reagent"):
            self.frame._different_reagent_rows(
                ["A1", "A2"],
                ["BB-01 - First"],
                [True],
                transfer_ul="10",
                plate_size="96-well",
            )

    def test_every_assignment_requires_a_chemical_and_positive_shared_volume(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.frame._different_reagent_rows(
                ["A1"],
                ["BB-01 - First"],
                [True],
                transfer_ul="0",
                plate_size="96-well",
            )
        with self.assertRaisesRegex(ValueError, "reaction well A1"):
            self.frame._different_reagent_rows(
                ["A1"],
                [""],
                [True],
                transfer_ul="10",
                plate_size="96-well",
            )

    def test_new_rows_use_existing_cheminformatics_output_contract(self):
        self.frame.rows = self.frame._different_reagent_rows(
            ["C2", "C4"],
            ["BB-01 - First", "BB-02 - Second"],
            [True, True],
            transfer_ul="8",
            plate_size="96-well",
        )
        pushed = self.frame.rows_for_cheminformatics()
        self.assertEqual(["C2", "C4"], [row["well"] for row in pushed])
        self.assertEqual(["BB-01", "BB-02"], [row["chemical_id"] for row in pushed])
        self.assertTrue(all(row["volume"] == "8" for row in pushed))

    def test_shared_volume_calculates_only_for_matching_known_concentrations(self):
        self.assertEqual(
            "4.0",
            self.frame._shared_assignment_transfer_volume(
                ["BB-01 - First", "BB-02 - Second"],
                "2",
            ),
        )
        self.assertEqual(
            "",
            self.frame._shared_assignment_transfer_volume(
                ["BB-01 - First", "CAT-01 - Catalyst"],
                "2",
            ),
        )
        self.assertEqual(
            "",
            self.frame._shared_assignment_transfer_volume(
                ["BB-01 - First", ""],
                "2",
            ),
        )


class ManualReactionWellMapLayoutTests(unittest.TestCase):
    def test_reaction_well_map_keeps_only_mapping_controls_and_push_action(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        root.withdraw()
        try:
            frame = ManualWorkflowFrame(root, compound_provider=lambda: [], push_callback=lambda _rows: None)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            label_frames = []
            buttons_in_map = {}

            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame):
                        label_frames.append(child.cget("text"))
                    if isinstance(child, ttk.Button):
                        buttons_in_map[child.cget("text")] = child
                    walk(child)

            walk(frame.map_box)
            all_label_frames = []

            def collect_label_frames(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame):
                        all_label_frames.append(child.cget("text"))
                    collect_label_frames(child)

            collect_label_frames(frame)

            self.assertEqual("Reaction well map", frame.map_box.cget("text"))
            self.assertNotIn("Manual reaction mapping", all_label_frames)
            self.assertNotIn("Manual reaction map", all_label_frames)
            self.assertIn("Mapped additions", all_label_frames)
            self.assertNotIn("Addition details and mapped-row actions", all_label_frames)
            self.assertTrue(str(frame.plate_combo).startswith(f"{frame.map_box}."))
            self.assertEqual(("96-well", "48-well", "24-well"), frame.PLATE_OPTIONS)
            for label in (
                "Repeat One Reagent",
                "Assign Different Reagents",
                "Push All to Cheminformatics",
            ):
                self.assertIn(label, buttons_in_map)
            for label in ("Add Chemical", "Remove Selected", "Update Selected", "Export CSV..."):
                self.assertNotIn(label, buttons_in_map)

            repeat_button = buttons_in_map["Repeat One Reagent"]
            push_button = buttons_in_map["Push All to Cheminformatics"]
            self.assertEqual(repeat_button.master, push_button.master)
            self.assertGreater(int(push_button.grid_info()["row"]), int(repeat_button.grid_info()["row"]))

            frame.rows = [{"plate_size": "96-well", "reaction_well": "A1", "chemical_id": "BB-01"}]
            frame._set_selected_wells(["A1"])
            self.assertEqual("#2e7d32", frame.map_cells["A1"].cget("background").lower())
            frame._set_selected_wells([])
            self.assertEqual("#b9dcf4", frame.map_cells["A1"].cget("background").lower())
            self.assertEqual("sunken", frame.map_cells["A1"].cget("relief"))
        finally:
            root.destroy()

    def test_different_reagent_dialog_has_no_compound_notes_quick_select(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        root.withdraw()
        dialog = None
        try:
            compounds = [
                SimpleNamespace(values={"ID": "BB-01", "Name": "First", "Conc.": "0.5"}),
                SimpleNamespace(values={"ID": "BB-02", "Name": "Second", "Conc.": "0.5"}),
                SimpleNamespace(values={"ID": "CAT-01", "Name": "Catalyst", "Conc.": "0.1"}),
            ]
            frame = ManualWorkflowFrame(root, compound_provider=lambda: compounds, push_callback=lambda _rows: None)
            frame.pack(fill="both", expand=True)
            frame.multi_select_wells_var.set(True)
            frame._set_selected_wells(["A1", "B3"])
            frame.reaction_umol_var.set("9")
            frame.transfer_volume_var.set("10")
            frame.temperature_var.set("repeat temperature")
            frame.duration_var.set("repeat duration")
            frame.notes_var.set("repeat notes")
            frame._open_assign_different_reagents_dialog()
            root.update_idletasks()

            def find_toplevel(widget):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        return child
                    found = find_toplevel(child)
                    if found is not None:
                        return found
                return None

            dialog = find_toplevel(root)
            self.assertIsNotNone(dialog)

            label_frames = []
            listboxes = []
            comboboxes = []
            buttons = {}

            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame):
                        label_frames.append(child.cget("text"))
                    if isinstance(child, tk.Listbox):
                        listboxes.append(child)
                    if isinstance(child, ttk.Combobox):
                        comboboxes.append(child)
                    if isinstance(child, ttk.Button):
                        buttons[child.cget("text")] = child
                    walk(child)

            walk(dialog)
            self.assertNotIn("Quick select from Compound Notes", label_frames)
            self.assertEqual([], listboxes)
            self.assertEqual(2, len(comboboxes))

            shared_box = next(
                child for child in dialog.winfo_children()[0].winfo_children()
                if isinstance(child, ttk.LabelFrame) and child.cget("text") == "Shared addition settings"
            )
            shared_entries = {
                child.grid_info()["column"]: child
                for child in shared_box.winfo_children()
                if isinstance(child, ttk.Entry) and int(child.grid_info()["row"]) == 0
            }
            volume_entry = shared_entries[1]
            umol_entry = shared_entries[3]
            self.assertEqual("", volume_entry.get())
            self.assertEqual("", umol_entry.get())

            comboboxes[0].set("BB-01 - First")
            comboboxes[1].set("BB-02 - Second")
            umol_entry.insert(0, "5")
            root.update_idletasks()
            self.assertEqual("10.0", volume_entry.get())
            comboboxes[1].set("CAT-01 - Catalyst")
            root.update_idletasks()
            self.assertEqual("", volume_entry.get())
            comboboxes[1].set("BB-02 - Second")
            root.update_idletasks()
            self.assertEqual("10.0", volume_entry.get())
            buttons["Add 2 Assignments"].invoke()
            root.update_idletasks()
            dialog = None
            self.assertEqual("", frame.reaction_wells_var.get())
            self.assertEqual("#b9dcf4", frame.map_cells["A1"].cget("background").lower())
            self.assertEqual("#b9dcf4", frame.map_cells["B3"].cget("background").lower())
            self.assertEqual("10", frame.transfer_volume_var.get())
            self.assertEqual("9", frame.reaction_umol_var.get())
            self.assertEqual("repeat temperature", frame.temperature_var.get())
            self.assertEqual("repeat duration", frame.duration_var.get())
            self.assertEqual("repeat notes", frame.notes_var.get())

            frame._set_selected_wells(["A4"])
            frame._open_add_reagents_dialog()
            root.update_idletasks()
            dialog = find_toplevel(root)
            self.assertIsNotNone(dialog)
            repeat_field_rows = {}

            def collect_repeat_labels(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Label) and child.cget("text") in {"umol/rxn", "Transfer uL"}:
                        repeat_field_rows[child.cget("text")] = int(child.grid_info()["row"])
                    collect_repeat_labels(child)

            collect_repeat_labels(dialog)
            self.assertLess(repeat_field_rows["umol/rxn"], repeat_field_rows["Transfer uL"])
            dialog.destroy()
            dialog = None
        finally:
            if dialog is not None and dialog.winfo_exists():
                dialog.destroy()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
