import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compound_notes_frame import (  # noqa: E402
    CompoundNotesFrame,
    CompoundRecord,
    DATA_HEADERS,
    DISPLAY_HEADERS,
)


class CompoundConcentrationTests(unittest.TestCase):
    def test_stock_calculation_does_not_derive_a_per_reaction_aliquot(self):
        frame = object.__new__(CompoundNotesFrame)
        values = {
            "Quantity input unit": "mg",
            "Quantity (mg)": "100",
            "Quantity(umol)": "",
            "MW": "200",
            "Conc.": "0.5",
            "Molarity(umol): used in each reaction": "10",
            "Per aliquote in reaction (uL)": "legacy value",
        }

        frame._calculate_record_values(values)

        self.assertEqual("500", values["Quantity(umol)"])
        self.assertEqual("1000.0", values["Solvent added (uL)"])
        self.assertEqual("", values["Per aliquote in reaction (uL)"])

    def test_compound_table_no_longer_displays_amount_per_reaction(self):
        self.assertNotIn("Molarity(umol): used in each reaction", DISPLAY_HEADERS)

    def test_corresponding_workbook_is_filename_only_and_does_not_change_save_target(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        try:
            frame = CompoundNotesFrame(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            self.assertEqual("Not specified", frame.associated_workbook_name_var.get())
            self.assertEqual("Records Table: Not specified", frame.records_table_frame.cget("text"))
            frame._set_associated_workbook_name(r"C:\sender\private\Project_A_Compounds.xlsx")

            self.assertEqual("Project_A_Compounds.xlsx", frame.associated_workbook_name())
            self.assertEqual("Project_A_Compounds.xlsx", frame.associated_workbook_name_var.get())
            self.assertEqual(
                "Records Table: Project_A_Compounds.xlsx",
                frame.records_table_frame.cget("text"),
            )
            self.assertNotIn("sender", frame.associated_workbook_name_var.get())

            visible_text = []

            def collect_text(widget):
                for child in widget.winfo_children():
                    try:
                        visible_text.append(str(child.cget("text")))
                    except tk.TclError:
                        pass
                    collect_text(child)

            collect_text(frame)
            self.assertFalse(any("Corresponding Compound Notes" in text for text in visible_text))

            with patch("compound_notes_frame.filedialog.asksaveasfilename", return_value="") as save_dialog:
                self.assertFalse(frame._save_current_excel(show_message=False))

            self.assertEqual("Compound_Notes.xlsx", save_dialog.call_args.kwargs["initialfile"])
            self.assertIsNone(frame.source_excel)
            self.assertFalse(frame.excel_loaded)
            self.assertEqual("Project_A_Compounds.xlsx", frame.associated_workbook_name())
        finally:
            for after_id in root.tk.call("after", "info"):
                try:
                    root.tk.call("after", "cancel", after_id)
                except tk.TclError:
                    pass
            root.destroy()

    def test_toolbar_uses_fill_concentration_wording_only(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        try:
            frame = CompoundNotesFrame(root)
            frame.pack()
            root.update_idletasks()
            labels = set()
            buttons = {}

            def collect(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        label = str(child.cget("text"))
                        labels.add(label)
                        buttons[label] = child
                    collect(child)

            collect(frame)
            self.assertIn("Fill Selected", labels)
            self.assertNotIn("Fill Conc", labels)
            self.assertNotIn("Fill Conc/Molarity...", labels)
            self.assertIn("Load Excel", labels)
            self.assertNotIn("Load Excel...", labels)
            for label in ("Load Excel", "Import SDF", "Save As", "Fill Selected", "Add Row", "Add Rows"):
                padding = tuple(int(str(value)) for value in buttons[label].cget("padding"))
                self.assertEqual((6, 4), padding)

            values = {header: "" for header in DATA_HEADERS}
            values.update({"ID": "A", "Conc.": "0.1", "Solvent": "DMA", "Supplier": "Supplier A"})
            frame.records = [CompoundRecord(values, source_row=7)]
            frame._refresh_tree()
            frame.tree.selection_set("0")
            buttons["Fill Selected"].invoke()
            root.update_idletasks()
            dialogs = []

            def collect_dialogs(widget):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        dialogs.append(child)
                    collect_dialogs(child)

            collect_dialogs(root)
            self.assertEqual(1, len(dialogs))
            self.assertEqual("Fill Selected Rows", dialogs[0].title())
            checkbox_labels = set()

            def collect_checkbuttons(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Checkbutton):
                        checkbox_labels.add(str(child.cget("text")))
                    collect_checkbuttons(child)

            collect_checkbuttons(dialogs[0])
            self.assertEqual({"Conc. (M)", "Solvent", "Supplier"}, checkbox_labels)
        finally:
            for after_id in root.tk.call("after", "info"):
                try:
                    root.tk.call("after", "cancel", after_id)
                except tk.TclError:
                    pass
            root.destroy()

    def test_group_fill_updates_requested_fields_and_preserves_source_rows(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        try:
            frame = CompoundNotesFrame(root)
            records = []
            for index, solvent in enumerate(("DMA", "DMSO"), start=1):
                values = {header: "" for header in DATA_HEADERS}
                values.update(
                    {
                        "ID": f"C{index}",
                        "Conc.": "0.1",
                        "Solvent": solvent,
                        "Supplier": f"Old {index}",
                    }
                )
                records.append(CompoundRecord(values, source_row=index + 10))
            frame.records = records
            frame._refresh_tree()

            frame._apply_group_values_to_indices(
                [0, 1],
                {"Solvent": "MeCN", "Supplier": "New Supplier"},
            )

            self.assertEqual(["MeCN", "MeCN"], [record.values["Solvent"] for record in frame.records])
            self.assertEqual(
                ["New Supplier", "New Supplier"],
                [record.values["Supplier"] for record in frame.records],
            )
            self.assertEqual(["0.1", "0.1"], [record.values["Conc."] for record in frame.records])
            self.assertEqual([11, 12], [record.source_row for record in frame.records])
        finally:
            for after_id in root.tk.call("after", "info"):
                try:
                    root.tk.call("after", "cancel", after_id)
                except tk.TclError:
                    pass
            root.destroy()


if __name__ == "__main__":
    unittest.main()
