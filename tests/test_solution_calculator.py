import json
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from rdkit import Chem

CALCULATOR_DIR = Path(__file__).resolve().parents[1] / "toolkit" / "solution_calculator"
if str(CALCULATOR_DIR) not in sys.path:
    sys.path.insert(0, str(CALCULATOR_DIR))

from solution_calculations import (  # noqa: E402
    check_concentration,
    formula_molecular_weight,
    prepare_stock,
    required_amount,
)
from solution_calculator import (  # noqa: E402
    IMPORT_FORMULA,
    IMPORT_MW,
    IMPORT_SMILES,
    PAYLOAD_SCHEMA,
    SDF_MOLECULE_COLUMN,
    SolutionCalculatorApp,
    build_import_batch_rows,
    load_xinpilot_payload,
    product_to_batch_row,
    read_batch_import_file,
)


class SolutionCalculationTests(unittest.TestCase):
    def test_prepare_stock_from_umol(self):
        result = prepare_stock(
            amount=10,
            amount_unit="umol",
            target_concentration=10,
            concentration_unit="mM",
        )
        self.assertAlmostEqual(1000.0, result.exact_volume_ul)
        self.assertAlmostEqual(10.0, result.achieved_concentration_mm)

    def test_prepare_stock_from_mg_and_rounding(self):
        result = prepare_stock(
            amount=5,
            amount_unit="mg",
            molecular_weight=500,
            mass_purity_percent=80,
            target_concentration=10,
            concentration_unit="mM",
            rounding_increment_ul=50,
        )
        self.assertAlmostEqual(8.0, result.active_umol)
        self.assertAlmostEqual(800.0, result.exact_volume_ul)
        self.assertAlmostEqual(800.0, result.final_volume_ul)

    def test_check_concentration_with_unit_conversion(self):
        result = check_concentration(
            amount=2,
            amount_unit="umol",
            final_volume=500,
            volume_unit="uL",
        )
        self.assertAlmostEqual(4.0, result.concentration_mm)

    def test_required_amount_corrects_known_mass_purity(self):
        result = required_amount(
            target_concentration=20,
            concentration_unit="mM",
            final_volume=2,
            volume_unit="mL",
            molecular_weight=250,
            mass_purity_percent=80,
        )
        self.assertAlmostEqual(40.0, result.active_umol)
        self.assertAlmostEqual(50.0, result.weighed_umol)
        self.assertAlmostEqual(12.5, result.required_mg)

    def test_rejects_missing_mw_for_mg(self):
        with self.assertRaisesRegex(ValueError, "Molecular weight"):
            prepare_stock(
                amount=5,
                amount_unit="mg",
                molecular_weight="",
                target_concentration=10,
                concentration_unit="mM",
            )

    def test_formula_molecular_weight_supports_groups_and_hydrates(self):
        self.assertAlmostEqual(46.069, formula_molecular_weight("C2H6O"), places=3)
        self.assertAlmostEqual(74.092, formula_molecular_weight("Ca(OH)2"), places=3)
        self.assertAlmostEqual(249.684, formula_molecular_weight("CuSO4\u00b75H2O"), places=2)


class SolutionCalculatorPayloadTests(unittest.TestCase):
    def test_temporary_xinpilot_payload_is_loaded_then_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "products.json"
            path.write_text(
                json.dumps({
                    "schema": PAYLOAD_SCHEMA,
                    "delete_after_load": True,
                    "products": [{"reaction_well": "A1", "product_smiles": "CCO"}],
                }),
                encoding="utf-8",
            )
            payload = load_xinpilot_payload(path)
            self.assertEqual("A1", payload["products"][0]["reaction_well"])
            self.assertFalse(path.exists())

    def test_uv254_is_reference_not_mass_purity(self):
        row = product_to_batch_row({
            "product_id": "P1",
            "product_mw": "500",
            "purity": "35%",
            "purity_source": "Modified PyParse UV254",
        })
        self.assertEqual("35%", row["uv_purity_reference"])
        self.assertEqual("100", row["mass_purity"])

    def test_imported_product_populates_batch_without_stock_write_controls(self):
        try:
            app = SolutionCalculatorApp({
                "products": [{
                    "reaction_well": "A1",
                    "product_id": "P1",
                    "product_name": "Product one",
                    "product_smiles": "CCO",
                    "product_formula": "C2H6O",
                    "product_mw": "46.07",
                    "lcms_reference_smiles": "CCO",
                    "purity": "91%",
                }]
            })
        except Exception as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")
        try:
            app.withdraw()
            app.update_idletasks()
            self.assertEqual(1, len(app.batch_rows))
            self.assertEqual("CCO", app.batch_rows[0]["smiles"])
            all_text = " ".join(
                str(child.cget("text"))
                for parent in (app.single_tab, app.batch_tab)
                for child in parent.winfo_children()
                if "text" in child.keys()
            )
            self.assertNotIn("Update Compound Notes", all_text)
            self.assertNotIn("Update stock", all_text)
        finally:
            app.update()
            app.destroy()


class BatchFileImportTests(unittest.TestCase):
    def test_selected_source_is_used_without_smiles_fallback_or_comparison(self):
        records = [{"ID": "P1", "SMILES": "CCO", "Formula": "H2O", "MW": "999"}]
        smiles_row = build_import_batch_rows(
            records,
            id_column="ID",
            source_type=IMPORT_SMILES,
            source_column="SMILES",
            target_mm="10",
            solvent="DMSO",
            amount_unit="mg",
        )[0]
        formula_row = build_import_batch_rows(
            records,
            id_column="ID",
            source_type=IMPORT_FORMULA,
            source_column="Formula",
            target_mm="10",
            solvent="DMSO",
            amount_unit="µmol",
        )[0]
        mw_row = build_import_batch_rows(
            records,
            id_column="ID",
            source_type=IMPORT_MW,
            source_column="MW",
            target_mm="10",
            solvent="MeCN",
            amount_unit="mg",
        )[0]

        self.assertEqual("CCO", smiles_row["smiles"])
        self.assertAlmostEqual(46.069, float(smiles_row["mw"]), places=3)
        self.assertEqual("", formula_row["smiles"])
        self.assertEqual("H2O", formula_row["formula"])
        self.assertAlmostEqual(18.015, float(formula_row["mw"]), places=3)
        self.assertEqual("", mw_row["smiles"])
        self.assertEqual("", mw_row["formula"])
        self.assertEqual("999", mw_row["mw"])
        self.assertEqual("MeCN", mw_row["solvent"])

    def test_invalid_selected_source_does_not_fall_back_to_valid_smiles(self):
        row = build_import_batch_rows(
            [{"ID": "P1", "SMILES": "CCO", "MW": "not-a-number"}],
            id_column="ID",
            source_type=IMPORT_MW,
            source_column="MW",
            target_mm="10",
            solvent="DMSO",
            amount_unit="mg",
        )[0]
        self.assertEqual("", row["smiles"])
        self.assertEqual("", row["mw"])
        self.assertIn("Molecular weight", row["identity_error"])

    def test_reads_csv_excel_and_sdf_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "batch.csv"
            csv_path.write_text("ID,SMILES\nA,CCO\n", encoding="utf-8")
            csv_rows, csv_columns = read_batch_import_file(csv_path)
            self.assertEqual(["ID", "SMILES"], csv_columns)
            self.assertEqual("CCO", csv_rows[0]["SMILES"])

            excel_path = root / "batch.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Compounds"
            sheet.append(["Identifier", "Formula"])
            sheet.append(["B", "H2O"])
            workbook.save(excel_path)
            workbook.close()
            excel_rows, excel_columns = read_batch_import_file(excel_path, "Compounds")
            self.assertEqual(["Identifier", "Formula"], excel_columns)
            self.assertEqual("H2O", excel_rows[0]["Formula"])

            sdf_path = root / "batch.sdf"
            writer = Chem.SDWriter(str(sdf_path))
            molecule = Chem.MolFromSmiles("CCN")
            molecule.SetProp("_Name", "Compound C")
            molecule.SetProp("External ID", "C")
            writer.write(molecule)
            writer.close()
            sdf_rows, sdf_columns = read_batch_import_file(sdf_path)
            self.assertIn(SDF_MOLECULE_COLUMN, sdf_columns)
            self.assertEqual("C", sdf_rows[0]["External ID"])
            self.assertIsNotNone(Chem.MolFromSmiles(sdf_rows[0][SDF_MOLECULE_COLUMN]))

    def test_preview_is_opt_in_persistent_and_tracks_selected_xinpilot_row(self):
        try:
            app = SolutionCalculatorApp({
                "products": [
                    {"product_id": "P1", "product_name": "One", "product_smiles": "CCO", "product_mw": "46.07"},
                    {"product_id": "P2", "product_name": "Two", "product_smiles": "CCN", "product_mw": "45.08"},
                ]
            })
        except Exception as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")
        try:
            app.withdraw()
            app.update()
            self.assertFalse(app.batch_preview_var.get())
            self.assertIn("Import Batch", [app.notebook.tab(tab, "text") for tab in app.notebook.tabs()])
            self.assertEqual(0, app.batch_amount_entry.grid_info()["row"])
            self.assertEqual(1, app.batch_selected_actions.grid_info()["row"])
            self.assertEqual(
                [app.batch_update_selected_button, app.batch_calculate_all_button],
                app.batch_selected_actions.pack_slaves(),
            )

            app.batch_tree.selection_set("0")
            app.batch_preview_var.set(True)
            app._toggle_batch_structure_preview()
            app.update()
            self.assertEqual("One", app._batch_preview_title.cget("text"))

            app.batch_tree.selection_set("1")
            app._load_selected_batch_row()
            app.update()
            self.assertTrue(app.batch_preview_var.get())
            self.assertEqual("Two", app._batch_preview_title.cget("text"))

            app._close_batch_structure_preview()
            self.assertFalse(app.batch_preview_var.get())
        finally:
            app.update()
            app.destroy()


if __name__ == "__main__":
    unittest.main()
