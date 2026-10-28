import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from rdkit import Chem

from compound_notes_frame import (
    CompoundNotesFrame,
    CompoundRecord,
    SDF_DUPLICATE_SKIP,
    SDF_DUPLICATE_SUFFIX,
    SDF_DUPLICATE_UPDATE,
    SdfCompound,
    default_sdf_identifier_field,
    plan_sdf_import,
    read_sdf_file,
    sdf_identifier_fields,
)


class _HiddenTree:
    @staticmethod
    def exists(_item):
        return False


def _candidate(record_number, identifier, smiles="CCO"):
    mol = Chem.MolFromSmiles(smiles)
    return SdfCompound(
        record_number=record_number,
        smiles=Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
        molecular_weight="46.0690",
        properties={"Compound ID": identifier},
    )


class CompoundSdfParsingTests(unittest.TestCase):
    def test_reads_properties_stereo_and_disconnected_fragments_without_standardization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "structures.sdf"
            mol = Chem.MolFromSmiles("C[C@H](O)Cl.[Na+]")
            mol.SetProp("_Name", "SDF title")
            mol.SetProp("Compound ID", "CMP-001")
            mol.SetProp("Barcode", "BC-9")
            writer = Chem.SDWriter(str(path))
            writer.write(mol)
            writer.close()

            result = read_sdf_file(path)

        self.assertEqual(1, result.total_records)
        self.assertEqual((), result.invalid_record_numbers)
        self.assertEqual(1, len(result.compounds))
        imported = result.compounds[0]
        self.assertEqual("CMP-001", imported.properties["Compound ID"])
        self.assertEqual("SDF title", imported.properties["_Name"])
        self.assertIn("@", imported.smiles)
        self.assertIn(".", imported.smiles)
        self.assertGreater(float(imported.molecular_weight), 80.0)

    def test_identifier_choices_prefer_explicit_compound_id_over_sdf_title(self):
        compounds = (
            SdfCompound(1, "CCO", "46.0690", {"_Name": "Ethanol", "Barcode": "B1"}),
            SdfCompound(2, "CCN", "45.0850", {"Compound ID": "C2"}),
        )
        fields = sdf_identifier_fields(compounds)
        self.assertEqual("_Name", fields[0])
        self.assertEqual("Compound ID", default_sdf_identifier_field(fields))

    def test_invalid_sdf_record_is_reported_without_blocking_valid_structure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "partly_invalid.sdf"
            valid = Chem.MolFromSmiles("CCO")
            valid.SetProp("_Name", "valid")
            writer = Chem.SDWriter(str(path))
            writer.write(valid)
            writer.close()
            with path.open("a", encoding="utf-8") as handle:
                handle.write("invalid record\n  XinPilot\n\nnot a mol block\n$$$$\n")

            result = read_sdf_file(path)

        self.assertEqual(2, result.total_records)
        self.assertEqual(1, len(result.compounds))
        self.assertEqual((2,), result.invalid_record_numbers)


class CompoundSdfPlanningTests(unittest.TestCase):
    def test_skip_policy_reports_missing_existing_and_duplicate_sdf_ids(self):
        compounds = (
            _candidate(1, "Existing"),
            _candidate(2, "New"),
            _candidate(3, "New"),
            _candidate(4, ""),
        )
        plan = plan_sdf_import(compounds, "Compound ID", ["existing"], SDF_DUPLICATE_SKIP)
        self.assertEqual(
            ["skip_existing", "add", "skip_duplicate_sdf", "skip_missing_id"],
            [row.action for row in plan],
        )

    def test_update_policy_updates_existing_id_but_does_not_import_sdf_duplicates_twice(self):
        compounds = (_candidate(1, "CMP-1", "CCN"), _candidate(2, "CMP-1", "CCC"))
        plan = plan_sdf_import(compounds, "Compound ID", ["cmp-1"], SDF_DUPLICATE_UPDATE)
        self.assertEqual("update", plan[0].action)
        self.assertEqual(0, plan[0].existing_index)
        self.assertEqual("skip_duplicate_sdf", plan[1].action)

    def test_update_policy_skips_ambiguous_existing_duplicate_ids(self):
        plan = plan_sdf_import(
            (_candidate(1, "CMP-1", "CCN"),),
            "Compound ID",
            ["CMP-1", "cmp-1"],
            SDF_DUPLICATE_UPDATE,
        )
        self.assertEqual("skip_ambiguous_existing", plan[0].action)

    def test_suffix_policy_generates_unique_case_insensitive_ids(self):
        compounds = (_candidate(1, "CMP"), _candidate(2, "cmp"), _candidate(3, "CMP_2"))
        plan = plan_sdf_import(compounds, "Compound ID", ["CMP"], SDF_DUPLICATE_SUFFIX)
        self.assertEqual(["CMP_2", "cmp_3", "CMP_2_2"], [row.final_id for row in plan])
        self.assertTrue(all(row.action == "add_suffixed" for row in plan))

    def test_apply_is_atomic_and_update_retains_existing_stock_fields(self):
        frame = CompoundNotesFrame.__new__(CompoundNotesFrame)
        frame.records = [
            CompoundRecord(
                {
                    "ID": "CMP-1",
                    "SMILES": "CCO",
                    "MW": "46.069",
                    "Quantity (mg)": "25",
                    "Conc.": "0.5",
                    "Nature": "existing note",
                },
                source_row=7,
            )
        ]
        frame.tree = _HiddenTree()
        frame._refresh_tree = lambda: None
        frame._clear_form = lambda: None
        plan = plan_sdf_import(
            (_candidate(1, "CMP-1", "CCN"), _candidate(2, "CMP-2", "C[C@H](O)Cl")),
            "Compound ID",
            ["CMP-1"],
            SDF_DUPLICATE_UPDATE,
        )

        added, updated, skipped = frame._apply_sdf_import_plan(plan)

        self.assertEqual((1, 1, 0), (added, updated, skipped))
        self.assertEqual("CCN", frame.records[0].values["SMILES"])
        self.assertEqual("25", frame.records[0].values["Quantity (mg)"])
        self.assertEqual("0.5", frame.records[0].values["Conc."])
        self.assertEqual("existing note", frame.records[0].values["Nature"])
        self.assertEqual(7, frame.records[0].source_row)
        self.assertEqual("CMP-2", frame.records[1].values["ID"])
        self.assertIn("@", frame.records[1].values["SMILES"])

    def test_failed_apply_leaves_all_original_records_unchanged(self):
        frame = CompoundNotesFrame.__new__(CompoundNotesFrame)
        original = CompoundRecord({"ID": "CMP-1", "SMILES": "CCO", "MW": "46.069"}, source_row=3)
        frame.records = [original]
        frame.tree = _HiddenTree()
        frame._refresh_tree = lambda: None
        frame._clear_form = lambda: None
        valid_add = plan_sdf_import(
            (_candidate(1, "CMP-2"),),
            "Compound ID",
            ["CMP-1"],
            SDF_DUPLICATE_SKIP,
        )[0]
        invalid_update = plan_sdf_import(
            (_candidate(2, "CMP-1", "CCN"),),
            "Compound ID",
            ["CMP-1"],
            SDF_DUPLICATE_UPDATE,
        )[0]
        invalid_update = type(invalid_update)(
            record_number=invalid_update.record_number,
            requested_id=invalid_update.requested_id,
            final_id=invalid_update.final_id,
            smiles=invalid_update.smiles,
            molecular_weight=invalid_update.molecular_weight,
            action=invalid_update.action,
            existing_index=99,
        )

        with self.assertRaises(ValueError):
            frame._apply_sdf_import_plan((valid_add, invalid_update))

        self.assertEqual(1, len(frame.records))
        self.assertIs(frame.records[0], original)


class CompoundSdfLayoutTests(unittest.TestCase):
    def test_compound_toolbar_exposes_sdf_import(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        try:
            frame = CompoundNotesFrame(root)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()

            labels = []

            def visit(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        labels.append(str(child.cget("text")))
                    visit(child)

            visit(frame)
            self.assertIn("Import SDF", labels)
        finally:
            for job in root.tk.call("after", "info"):
                frame.after_cancel(job)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
