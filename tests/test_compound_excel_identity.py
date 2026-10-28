"""Synthetic Excel save regressions; no GUI, hardware or experimental files."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

from compound_notes_frame import CompoundNotesFrame, CompoundRecord, DATA_HEADERS
from integrated_full_software import IntegratedFullApp


class CompoundExcelIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "stocks.xlsx"
        self.frame = object.__new__(CompoundNotesFrame)
        self.frame.records = []
        self.frame._deleted_source_rows = set()
        self.frame._deleted_source_records = []
        self.frame._refresh_tree = Mock()
        self.frame._set_associated_workbook_name = Mock()
        self.frame.status_var = Mock()
        self.frame._commit_current_form_to_record = Mock()
        self.frame._commit_pending_form_update = Mock()
        self.frame._commit_pending_quantity_update = Mock()
        self.frame._clear_form = Mock()
        self.frame.tree = Mock()
        self.frame.tree.selection.return_value = ()
        self.frame._form_record_index = None
        self.workbook([
            {"ID": "A", "SMILES": "CCO", "Quantity (mg)": 10, "Nature": "original A", "Outside": "=1+2"},
            {"ID": "B", "SMILES": "CCN", "Quantity (mg)": 20, "Nature": "original B", "Outside": "B note"},
        ])
        self.load()

    def workbook(self, rows):
        book = Workbook()
        sheet = book.active
        sheet.title = "Stocks"
        sheet.append(DATA_HEADERS + ["Outside"])
        for values in rows:
            sheet.append([values.get(header, "") for header in DATA_HEADERS + ["Outside"]])
        book.create_sheet("Other")["A1"] = "untouched"
        book.save(self.path)
        book.close()

    def load(self):
        self.frame._load_excel(self.path)
        self.frame.source_excel = self.path

    def edit_workbook(self, action):
        book = load_workbook(self.path)
        try:
            action(book.active)
            book.save(self.path)
        finally:
            book.close()

    def rows(self):
        book = load_workbook(self.path)
        try:
            sheet = book.active
            headers = self.frame._header_map(sheet)
            return [
                {header: sheet.cell(row, col).value for header, col in headers.items()}
                for row in range(2, sheet.max_row + 1)
            ]
        finally:
            book.close()

    @staticmethod
    def swap(sheet):
        first = [cell.value for cell in sheet[2]]
        second = [cell.value for cell in sheet[3]]
        for col, (left, right) in enumerate(zip(first, second), start=1):
            sheet.cell(2, col).value = right
            sheet.cell(3, col).value = left

    def delete_record(self, index):
        self.frame.tree.selection.return_value = [str(index)]
        self.frame._delete_row()

    def assert_rejected_unchanged(self, pattern=None):
        before = self.path.read_bytes()
        state = copy.deepcopy((self.frame.records, self.frame._deleted_source_records, self.frame._deleted_source_rows))
        with self.assertRaisesRegex(ValueError, pattern or "Save stopped"):
            self.frame._write_excel(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(state, (self.frame.records, self.frame._deleted_source_records, self.frame._deleted_source_rows))

    def test_save_current_after_sort_and_insertion_preserves_external_data(self):
        self.frame.records[0].values["Nature"] = "edited A"
        self.frame.records[0].values["Quantity (mg)"] = "15"

        def external(sheet):
            self.swap(sheet)
            sheet.insert_rows(2)
            for header, value in {"ID": "EXTERNAL", "SMILES": "CCO", "Quantity (mg)": 77, "Outside": "new note"}.items():
                sheet.cell(2, self.frame._header_map(sheet)[header]).value = value
            sheet.cell(4, DATA_HEADERS.index("SMILES") + 1).value = "OCC"
            sheet.cell(4, len(DATA_HEADERS) + 1).fill = PatternFill("solid", fgColor="FF112233")
        self.edit_workbook(external)
        self.assertTrue(self.frame._save_current_excel(show_message=False))
        rows = self.rows()
        self.assertEqual([r["ID"] for r in rows], ["EXTERNAL", "B", "A"])
        self.assertEqual(rows[0]["Quantity (mg)"], 77)
        self.assertEqual(rows[1]["Nature"], "original B")
        self.assertEqual(rows[2]["Nature"], "edited A")
        self.assertEqual(rows[2]["Quantity (mg)"], "15")
        self.assertEqual(rows[2]["Outside"], "=1+2")
        self.assertEqual([r.source_row for r in self.frame.records], [4, 3])
        book = load_workbook(self.path)
        try:
            self.assertEqual(book["Other"]["A1"].value, "untouched")
            self.assertEqual(book.active.cell(4, len(DATA_HEADERS) + 1).fill.fgColor.rgb, "FF112233")
        finally:
            book.close()

    def test_intentional_id_and_structure_change_matches_original_identity(self):
        self.frame.records[0].values.update({"ID": "RENAMED", "SMILES": "CCC", "Nature": "new structure"})
        self.edit_workbook(self.swap)
        self.frame._write_excel(self.path)
        self.assertEqual([(r["ID"], r["SMILES"], r["Outside"]) for r in self.rows()],
                         [("B", "CCN", "B note"), ("RENAMED", "CCC", "=1+2")])
        self.assertEqual(self.frame.records[0].source_values["ID"], "RENAMED")
        self.edit_workbook(self.swap)
        self.frame.records[0].values["Nature"] = "saved again"
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[0]["Nature"], "saved again")

    def test_form_and_sdf_replacements_keep_original_identity(self):
        from compound_notes_frame import SdfImportPlanRow
        self.frame._form_record_index = 0
        self.frame._form_values = lambda: dict(self.frame.records[0].values, ID="RENAMED", SMILES="CCC")
        CompoundNotesFrame._commit_current_form_to_record(self.frame)
        plan = [SdfImportPlanRow(1, "RENAMED", "RENAMED", "CCCC", "58.12", "update", 0)]
        self.frame.tree.exists.return_value = False
        self.frame._apply_sdf_import_plan(plan)
        self.assertEqual(self.frame.records[0].source_values["ID"], "A")
        self.assertEqual(self.frame.records[0].source_values["SMILES"], "CCO")
        self.edit_workbook(self.swap)
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[1]["SMILES"], "CCCC")

    def test_delete_after_external_sort_clears_original_record_only(self):
        self.frame.records[0].values["ID"] = "UNSAVED_RENAME"
        self.delete_record(0)
        self.edit_workbook(self.swap)
        self.frame._write_excel(self.path)
        rows = self.rows()
        self.assertEqual(rows[0]["ID"], "B")
        self.assertTrue(all(rows[1][header] is None for header in DATA_HEADERS))
        self.assertEqual(rows[1]["Outside"], "=1+2")
        self.assertEqual(self.frame._deleted_source_records, [])

    def test_delete_survives_quantity_autosave_moving_another_record_to_old_row(self):
        self.delete_record(0)
        self.edit_workbook(self.swap)
        self.frame.records[0].values["Quantity (mg)"] = "25"
        self.frame._write_quantity_column_to_excel(self.path)
        self.assertEqual(self.frame.records[0].source_row, 2)
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[0]["ID"], "B")
        self.assertIsNone(self.rows()[1]["ID"])

    def test_quantity_autosave_updates_baseline_for_subsequent_full_save(self):
        self.frame.records[0].values["Quantity (mg)"] = "15"
        self.edit_workbook(self.swap)
        self.frame._write_quantity_column_to_excel(self.path)
        self.frame.records[0].values["Quantity (mg)"] = "16"
        self.frame.records[0].values["ID"] = "RENAMED"
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[1]["Quantity (mg)"], "16")

    def test_swapping_local_ids_is_staged_without_overwriting_other_compound(self):
        self.frame.records[0].values["ID"] = "B"
        self.frame.records[1].values["ID"] = "A"
        self.frame._write_excel(self.path)
        self.assertEqual([(r["ID"], r["SMILES"]) for r in self.rows()], [("B", "CCO"), ("A", "CCN")])

    def test_external_duplicate_original_id_is_rejected_even_if_structure_differs(self):
        self.edit_workbook(lambda ws: ws.cell(3, 1, "A"))
        self.assert_rejected_unchanged("missing or duplicated")

    def test_missing_original_id_is_rejected(self):
        self.edit_workbook(lambda ws: ws.cell(3, 1, "OTHER"))
        self.assert_rejected_unchanged("missing or duplicated")

    def test_externally_changed_original_structure_is_rejected(self):
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("SMILES") + 1, "CCC"))
        self.frame.records[0].values["SMILES"] = "CCCC"
        self.assert_rejected_unchanged("different structure")

    def test_new_local_id_collision_with_external_row_is_rejected(self):
        self.frame.records.append(CompoundRecord({"ID": "EXTERNAL", "SMILES": "CCCC"}))
        self.edit_workbook(lambda ws: ws.append(["EXTERNAL"] + [""] * (len(DATA_HEADERS) - 1)))
        self.assert_rejected_unchanged("would be duplicated")

    def test_rename_collision_with_external_row_is_rejected(self):
        self.frame.records[0].values["ID"] = "EXTERNAL"
        self.edit_workbook(lambda ws: ws.append(["EXTERNAL"] + [""] * (len(DATA_HEADERS) - 1)))
        self.assert_rejected_unchanged("would be duplicated")

    def test_deleted_record_changed_externally_is_rejected(self):
        self.delete_record(0)
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("Nature") + 1, "external"))
        self.assert_rejected_unchanged("deleted Chemical ID")

    def test_conflicting_field_edits_are_rejected(self):
        self.frame.records[0].values["Quantity (mg)"] = "15"
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("Quantity (mg)") + 1, 17))
        self.assert_rejected_unchanged("changed both")

    def test_save_current_reports_conflict_without_saving_or_marking_clean(self):
        self.frame.records[0].values["Quantity (mg)"] = "15"
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("Quantity (mg)") + 1, 17))
        before = self.path.read_bytes()
        baseline = copy.deepcopy(self.frame._saved_records_snapshot)
        with patch("compound_notes_frame.messagebox.showerror") as error:
            self.assertFalse(self.frame._save_current_excel(show_message=False))
        self.assertIn("changed both", error.call_args.args[1])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(baseline, self.frame._saved_records_snapshot)

    def test_save_as_reports_failure_and_keeps_original_workbook_association(self):
        output = self.path.with_name("copy.xlsx")
        with patch("compound_notes_frame.filedialog.asksaveasfilename", return_value=str(output)), \
             patch.object(self.frame, "_atomic_save_workbook", side_effect=PermissionError("locked")), \
             patch("compound_notes_frame.messagebox.showerror") as error:
            self.assertFalse(self.frame._save_as_excel())
        self.assertIn("locked", error.call_args.args[1])
        self.assertEqual(self.path, self.frame.source_excel)
        self.assertFalse(output.exists())

    def test_disjoint_external_and_local_edits_are_merged(self):
        self.frame.records[0].values["Quantity (mg)"] = "15"
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("Nature") + 1, "external note"))
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[0]["Nature"], "external note")
        self.assertEqual(self.rows()[0]["Quantity (mg)"], "15")
        self.assertEqual(self.frame.records[0].values["Nature"], "external note")

    def test_merged_external_field_survives_the_next_live_form_commit(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            frame = CompoundNotesFrame(root)
            frame._load_excel(self.path)
            frame.source_excel = self.path
            frame.tree.selection_set("0")
            frame._load_record_into_form(frame.records[0].values, 0)
            frame.vars["Nature"].set("local edit")
            self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("Supplier") + 1, "External supplier"))
            self.assertTrue(frame._save_current_excel(show_message=False))
            self.assertEqual("External supplier", frame.vars["Supplier"].get())
            frame._commit_current_form_to_record()
            self.assertEqual("External supplier", frame.records[0].values["Supplier"])
            self.assertFalse(frame.has_unsaved_changes())
        finally:
            for token in root.tk.splitlist(root.tk.call('after', 'info')):
                root.tk.call('after', 'cancel', token)
            root.destroy()

    def test_same_external_and_local_edit_is_not_a_conflict(self):
        self.frame.records[0].values["Quantity (mg)"] = "15.0"
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("Quantity (mg)") + 1, 15))
        self.frame._write_excel(self.path)
        self.assertEqual(float(self.rows()[0]["Quantity (mg)"]), 15)

    def test_failed_atomic_save_does_not_commit_metadata_or_deletions(self):
        self.delete_record(1)
        self.frame.records[0].values["ID"] = "RENAMED"
        before = self.path.read_bytes()
        state = copy.deepcopy((self.frame.records, self.frame._deleted_source_records, self.frame._deleted_source_rows))
        with patch.object(self.frame, "_atomic_save_workbook", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                self.frame._write_excel(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(state, (self.frame.records, self.frame._deleted_source_records, self.frame._deleted_source_rows))
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[0]["ID"], "RENAMED")

    def test_formula_in_owned_column_is_preserved_when_locally_unchanged(self):
        self.edit_workbook(lambda ws: ws.cell(2, DATA_HEADERS.index("MW") + 1, "=40+6"))
        self.load()
        self.frame.records[0].values["Nature"] = "edited A"
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[0]["MW"], "=40+6")

    def test_duplicate_owned_headers_are_rejected(self):
        self.edit_workbook(lambda ws: ws.cell(1, ws.max_column + 1, "ID"))
        self.assert_rejected_unchanged("duplicate 'ID' columns")

    def test_save_as_uses_original_identity_in_sorted_template(self):
        self.edit_workbook(self.swap)
        original = self.path.read_bytes()
        output = self.path.with_name("copy.xlsx")
        self.frame.records[0].values["ID"] = "RENAMED"
        self.frame._write_excel(output, template_path=self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.path = output
        self.assertEqual(self.rows()[1]["ID"], "RENAMED")

    def test_new_archive_records_without_source_metadata_save_to_new_workbook(self):
        self.frame.records = [CompoundRecord({"ID": "ARCHIVE", "SMILES": "CCO"})]
        self.frame._write_excel(self.path.with_name("archive.xlsx"))
        self.assertEqual(self.frame.records[0].source_values["ID"], "ARCHIVE")

    def test_project_rollback_preserves_original_identity_and_deleted_records(self):
        self.frame.records[0].values["ID"] = "RENAMED"
        self.delete_record(1)
        app = SimpleNamespace(compound_tab=self.frame, _project_payload=Mock(return_value={}))
        state = IntegratedFullApp._capture_import_rollback_state(app)
        self.frame.records = []
        self.frame._deleted_source_records = []
        self.frame.filtered_indices = []
        app._apply_project_data = Mock()
        IntegratedFullApp._restore_import_rollback_state(app, state)
        self.assertEqual(self.frame.records[0].source_values["ID"], "A")
        self.assertEqual(self.frame._deleted_source_records[0].source_values["ID"], "B")
        self.edit_workbook(self.swap)
        self.frame._write_excel(self.path)
        self.assertEqual(self.rows()[1]["ID"], "RENAMED")
        self.assertIsNone(self.rows()[0]["ID"])


if __name__ == "__main__":
    unittest.main()
