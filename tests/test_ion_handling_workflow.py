from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ion_handling
from cheminformatics_frame import CheminformaticsFrame


class IonHandlingTests(unittest.TestCase):
    def test_protonated_amine_salt_is_neutralizable(self):
        analysis = ion_handling.analyze_smiles("CC[NH3+].[Cl-]")
        self.assertEqual(["[Cl-]"], analysis["counterion_smiles"])
        self.assertEqual("protonated_amine", analysis["sites"][0]["chemotype"])
        self.assertTrue(analysis["sites"][0]["neutralizable"])

        result = ion_handling.apply_rule(
            "CC[NH3+].[Cl-]",
            ion_handling.default_rule(analysis),
        )
        self.assertEqual("CCN", result["reaction_smiles"])
        self.assertEqual([], result["kept_counterions"])

    def test_permanent_quaternary_ammonium_is_preserved(self):
        analysis = ion_handling.analyze_smiles("C[N+](C)(C)C.[Cl-]")
        site = analysis["sites"][0]
        self.assertEqual("quaternary_ammonium", site["chemotype"])
        self.assertTrue(site["permanent"])
        result = ion_handling.automatic_lcms_target("C[N+](C)(C)C.[Cl-]")
        self.assertEqual("C[N+](C)(C)C", result["target_smiles"])
        self.assertEqual(1, result["permanent_count"])
        self.assertEqual(1, result["counterion_count"])

    def test_multiple_charge_sites_can_be_assigned_independently(self):
        smiles = "C[NH+](C)CC(=O)[O-]"
        analysis = ion_handling.analyze_smiles(smiles)
        amine = next(site for site in analysis["sites"] if site["chemotype"] == "protonated_amine")
        carboxylate = next(site for site in analysis["sites"] if site["chemotype"] == "carboxylate")
        rule = ion_handling.default_rule(analysis)
        rule["site_actions"] = {
            str(amine["atom_index"]): "keep",
            str(carboxylate["atom_index"]): "neutralize",
        }
        result = ion_handling.apply_rule(smiles, rule)
        transformed = ion_handling.analyze_smiles(result["reaction_smiles"])
        self.assertEqual(1, transformed["parent_formal_charge"])
        self.assertEqual(["protonated_amine"], [site["chemotype"] for site in transformed["sites"]])

    def test_keep_counterion_preserves_stoichiometry(self):
        smiles = "[NH3+]CC[NH2+]CC.[Cl-].[Cl-]"
        analysis = ion_handling.analyze_smiles(smiles)
        rule = ion_handling.default_rule(analysis)
        rule["counterion_action"] = "keep"
        rule["site_actions"] = {str(site["atom_index"]): "keep" for site in analysis["sites"]}
        result = ion_handling.apply_rule(smiles, rule)
        self.assertEqual(2, result["product_form_smiles"].count("[Cl-]"))
        self.assertEqual(2, len(result["kept_counterions"]))

    def test_automatic_lcms_preparation_removes_counterion_and_neutralizes(self):
        result = ion_handling.automatic_lcms_target("CC[NH3+].[Cl-]")
        self.assertEqual("CCN", result["target_smiles"])
        self.assertTrue(result["changed"])
        self.assertEqual(1, result["counterion_count"])
        self.assertEqual(1, result["neutralizable_count"])


class LcmsPlatemapTests(unittest.TestCase):
    def test_lcms_target_mz_uses_target_charge_state(self):
        neutral = CheminformaticsFrame._lcms_target_mz_text("CCN")
        self.assertIn("44.05", neutral)
        self.assertIn("46.07", neutral)

        permanent_cation = CheminformaticsFrame._lcms_target_mz_text("C[N+](C)(C)C")
        self.assertEqual("ES+ [M]+ 74.10", permanent_cation)

    def test_product_summary_keeps_product_mass_and_adds_lcms_target_mz(self):
        class FakeVar:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class FakeTree:
            @staticmethod
            def selection():
                return ("0",)

        frame = CheminformaticsFrame.__new__(CheminformaticsFrame)
        frame.product_structure_table = FakeTree()
        frame.product_structure_meta_var = FakeVar()
        frame.lcms_target_smiles_by_well = {"A1": "CCN"}
        frame.lcms_target_summaries_by_well = {
            "A1": "Removed 1 counterion fragment; neutralized 1 charge site"
        }
        frame._pyparse_rows = lambda: [{
            "reaction_name": "RXN-1",
            "reaction_well": "A1",
            "pyparse_well": "B1",
            "desired product smiles": "CC[NH3+].[Cl-]",
            "desired product exact mass": "81.0345",
            "selectivity products": [],
        }]
        frame._save_current_product_structure_manual_fields = lambda: None
        frame._biology_hit_summary_for_row = lambda _row: ""
        frame._refresh_product_structure_purity_display = lambda _row: None
        frame._sync_product_structure_uv_source_for_row = lambda _row: None
        frame._load_product_structure_manual_fields = lambda _row: None
        frame._refresh_product_structure_trace_display = lambda _row: None
        frame._render_product_structure = lambda _smiles: None
        frame._render_lcms_target_structure = lambda _smiles: None
        frame._sync_biology_hit_dialog_to_row = lambda _row: None

        frame._on_product_structure_select()

        displayed = frame.product_structure_meta_var.value
        self.assertIn("Exact mass: 81.03", displayed)
        self.assertIn("LCMS target exact mass: 45.06", displayed)
        self.assertIn("LCMS target m/z:", displayed)
        self.assertIn("44.05", displayed)
        self.assertIn("46.07", displayed)
        self.assertNotIn("LCMS preparation", displayed)
        self.assertNotIn("Removed 1 counterion", displayed)

    def test_saved_building_block_rule_changes_reaction_smiles_without_changing_stock(self):
        compound = {"ID": "BB-1", "SMILES": "CC[NH3+].[Cl-]", "Name": "amine hydrochloride"}
        frame = CheminformaticsFrame.__new__(CheminformaticsFrame)
        frame.compound_provider = lambda: [SimpleNamespace(values=compound)]
        frame.pushed_rows = {
            ("A1", "bb-1", "plate"): {
                "well": "A1",
                "chemical": "BB-1",
                "dest_labware": "plate",
                "is_building_block": True,
            }
        }
        analysis = ion_handling.analyze_smiles(compound["SMILES"])
        frame.building_block_ion_rules = {
            frame._building_block_ion_key(compound): ion_handling.default_rule(analysis)
        }
        row = frame._custom_current_rows()[0]
        self.assertEqual("CCN", row["smiles"])
        self.assertEqual("CC[NH3+].[Cl-]", row["original_smiles"])
        self.assertEqual("CC[NH3+].[Cl-]", compound["SMILES"])

    def test_incomplete_charge_rule_is_not_accepted(self):
        analysis = ion_handling.analyze_smiles("CC[NH3+].[Cl-]")
        self.assertFalse(CheminformaticsFrame._ion_rule_is_complete(analysis, {}))
        self.assertFalse(CheminformaticsFrame._ion_rule_is_complete(analysis, {
            "counterion_action": "remove",
            "site_actions": {},
        }))
        self.assertTrue(CheminformaticsFrame._ion_rule_is_complete(
            analysis,
            ion_handling.default_rule(analysis),
        ))

    def test_platemap_uses_lcms_target_without_changing_product_row(self):
        frame = CheminformaticsFrame.__new__(CheminformaticsFrame)
        frame.product_structure_manual_notes = {}
        frame.pyparse_purity_by_well = {}
        frame.modified_pyparse_purity_by_well = {}
        frame.modified_pyparse_purity_by_product = {}
        frame.product_structure_uv_source_by_key = {}
        frame.product_structure_row_colors = {}
        frame.product_structure_biology_hits = {}
        frame.lcms_target_smiles_by_well = {"A1": "CCN"}
        frame.lcms_target_summaries_by_well = {"A1": "removed counterion; neutralized amine"}
        row = {
            "reaction_name": "RXN-1",
            "reaction": "test",
            "reaction_well": "A1",
            "pyparse_well": "B1",
            "product_id": "P1",
            "desired product name": "P1",
            "desired product smiles": "CC[NH3+].[Cl-]",
            "desired product exact mass": "81.0345",
            "desired product mw": "81.54",
            "desired product formula": "C2H8ClN",
            "desired product mh": "82.0",
            "desired product mna": "104.0",
            "desired product negative mass": "80.0",
            "limiting reactant smiles": "",
            "limiting reactant name": "",
            "limiting reactant id": "",
            "excess reactant smiles": "",
            "excess reactant name": "",
            "excess reactant id": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "platemap.csv"
            frame._write_pyparse_platemap(output, [row])
            with output.open(encoding="utf-8", newline="") as handle:
                written = next(csv.DictReader(handle))
        self.assertEqual("CCN", written["desired product smiles"])
        self.assertEqual("45.057849", written["desired product exact mass"])
        self.assertEqual("CC[NH3+].[Cl-]", row["desired product smiles"])

    def test_modified_pyparse_results_use_lcms_target_identity(self):
        frame = CheminformaticsFrame.__new__(CheminformaticsFrame)
        frame.lcms_target_smiles_by_well = {"A1": "CCN"}
        frame.modified_pyparse_purity_by_product = {
            "CCN": {"B1": "72.50%"},
        }
        row = {
            "reaction_well": "A1",
            "pyparse_well": "B1",
            "desired product smiles": "CC[NH3+]",
        }

        self.assertEqual("72.50%", frame._modified_pyparse_purity_for_row(row))

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "compoundtable.csv").write_text(
                "name,g_smiles,best_well,purity_by_well\n"
                "Product1,CCN,B1,{'B1': 72.5}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                "Product1",
                frame._pyparse_product_trace_token(output, row, "B1"),
            )

    def test_modified_pyparse_result_identity_falls_back_for_legacy_projects(self):
        frame = CheminformaticsFrame.__new__(CheminformaticsFrame)
        frame.modified_pyparse_purity_by_product = {
            "CCO": {"A2": "41.00%"},
        }
        row = {
            "reaction_well": "A2",
            "pyparse_well": "A2",
            "desired product smiles": "CCO",
        }

        self.assertEqual("41.00%", frame._modified_pyparse_purity_for_row(row))


if __name__ == "__main__":
    unittest.main()
