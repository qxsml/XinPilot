"""Regeneration compares real products; remapping preserves sample evidence."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_chemical_identity_consistency as identity_tests


class ProductRegenerationAndRemapTests(unittest.TestCase):
    setUpClass = classmethod(identity_tests.ChemicalIdentityTests.setUpClass.__func__)
    tearDownClass = classmethod(identity_tests.ChemicalIdentityTests.tearDownClass.__func__)
    setUp = identity_tests.ChemicalIdentityTests.setUp
    prepare = identity_tests.ChemicalIdentityTests.prepare
    import_csv = identity_tests.ChemicalIdentityTests.import_csv

    def select_reaction(self, reaction_id):
        reaction = next(r for r in self.f.reactions if r["id"] == reaction_id)
        self.f.reaction_var.set(reaction["label"])
        self.f._on_reaction_type_selected()

    def prepare_unary(self):
        self.records[:] = [{"ID": "SUBSTRATE", "SMILES": "CC=CC=O"}]
        self.f.push_from_external([{"chemical": "SUBSTRATE", "chemical_id": "SUBSTRATE",
                                    "well": "A1", "is_building_block": True,
                                    "dest_mode": "96-well horizontal"}])
        self.f.pyparse_wells = {"A1": "C1"}
        self.select_reaction("alkene_hydrogenation")
        self.f._generate()
        row = self.f._pyparse_rows()[0]
        self.assertTrue(row["desired product smiles"])
        self.seed_analysis([row])
        return row

    def seed_analysis(self, rows):
        targets = {}
        wells = {}
        for index, row in enumerate(rows):
            sample = row["pyparse_well"]
            product = row["desired product smiles"]
            self.f.pyparse_purity_by_well[sample] = f"{81 + index}%"
            self.f.modified_pyparse_purity_by_product.setdefault(product, {})[sample] = f"{83 + index}%"
            self.f.product_structure_manual_notes[f"lcms:{sample}"] = {"manual_purity": "77", "comments": f"Note {sample}"}
            self.f.lcms_target_smiles_by_well[row["reaction_well"]] = product
            targets.setdefault(product, {})[sample] = {"name": f"Product{index + 1}", "automatic_purity": 83 + index, "ranges": [[1, 2]]}
            wells[sample] = {"peaks": [{"time": 1.5, "pStart": 1, "pEnd": 2, "area": 100, "areaAbs": 100,
                                        "MS+": [[100, 100]], "MS-": []}],
                             "trace": {"uv": [[0, 1, 2, 3], [0, 100, 50, 0]]}, "exclude_ranges": []}
        self.f.peak_inspection_data = {"version": 1, "targets": targets, "wells": wells}

    def test_changed_reaction_hides_pending_results_then_invalidates_changed_product(self):
        original = self.prepare_unary()
        samples = copy.deepcopy(self.f.peak_inspection_data["wells"])
        self.select_reaction("carbonyl_reduction")
        pending = self.f._pyparse_rows()[0]
        self.assertEqual(original["desired product smiles"], self.f.pending_product_identity_rows["A1"]["desired product smiles"])
        for source in ("pyparse", "modified", "manual"):
            self.assertEqual("", self.f._product_structure_purity_for_row(pending, source))
        self.assertIsNone(self.f._peak_context(pending)[2])
        self.f._generate()
        current = self.f._pyparse_rows()[0]
        self.assertNotEqual(original["desired product smiles"], current["desired product smiles"])
        self.assertFalse(self.f.pending_product_identity_rows)
        for source in ("pyparse", "modified", "manual"):
            self.assertEqual("", self.f._product_structure_purity_for_row(current, source))
        self.assertEqual({"comments": "Note C1"}, self.f.product_structure_manual_notes["lcms:C1"])
        self.assertEqual(samples, self.f.peak_inspection_data["wells"])

    def test_unchanged_regeneration_keeps_manual_and_target_override(self):
        original = self.prepare_unary()
        self.f.lcms_target_smiles_by_well["A1"] = "CCCCO"
        self.f.modified_pyparse_purity_by_product["CCCCO"] = {"C1": "61%"}
        self.select_reaction("alkene_hydrogenation")
        self.f._generate()
        current = self.f._pyparse_rows()[0]
        self.assertEqual(original["desired product smiles"], current["desired product smiles"])
        self.assertEqual("CCCCO", self.f._lcms_target_for_row(current))
        self.assertEqual("81%", self.f._product_structure_purity_for_row(current, "pyparse"))
        self.assertEqual("61%", self.f._product_structure_purity_for_row(current, "modified"))
        self.assertEqual("77", self.f._product_structure_purity_for_row(current, "manual"))
        self.assertFalse(self.f.pending_product_identity_rows)

    def test_pending_baseline_survives_saved_project_before_regeneration(self):
        original = self.prepare_unary()
        self.select_reaction("carbonyl_reduction")
        state = json.loads(json.dumps(self.f.export_state()))
        self.f.import_state(state)
        self.assertEqual(original["desired product smiles"], self.f.pending_product_identity_rows["A1"]["desired product smiles"])
        self.assertEqual("", self.f._product_structure_purity_for_row(self.f._pyparse_rows()[0], "manual"))
        self.f._generate()
        self.assertEqual("", self.f._product_structure_purity_for_row(self.f._pyparse_rows()[0], "pyparse"))
        self.assertFalse(self.f.pending_product_identity_rows)

    def test_clear_custom_template_compares_the_regenerated_builtin_product(self):
        for same_product in (True, False):
            with self.subTest(same_product=same_product):
                self.f.clear_for_next_synthesis_step()
                original = self.prepare_unary()
                custom = original["desired product smiles"] if same_product else "CCO"
                self.f.custom_template_text.insert("1.0", "[C:1]>>[C:1]")
                self.f.custom_products["A1"] = {"smiles": custom, "source": "custom_template"}
                row = self.f._pyparse_rows()[0]
                self.seed_analysis([row])
                with patch("cheminformatics_frame.messagebox.askyesno", return_value=True), \
                     patch("cheminformatics_frame.KETCHER_TEMPLATE_PATH", Path(self.temp.name) / "none.rxn"):
                    self.f._clear_custom_input_reaction()
                self.assertTrue(self.f.pending_product_identity_rows)
                self.assertEqual("", self.f._product_structure_purity_for_row(self.f._pyparse_rows()[0], "pyparse"))
                self.f._generate()
                self.assertFalse(self.f.pending_product_identity_rows)
                current = self.f._pyparse_rows()[0]
                self.assertEqual("81%" if same_product else "", self.f._product_structure_purity_for_row(current, "pyparse"))

    def test_swapped_lcms_mapping_preserves_automatic_evidence_without_manual_migration(self):
        for incoming in ("A1,C2,CCO\nA2,C1,CCO\n", "A2,C1,CCO\nA1,C2,CCO\n"):
            with self.subTest(incoming=incoming):
                self.f.clear_for_next_synthesis_step()
                self.import_csv("A1,C1,CCO\nA2,C2,CCO\n")
                rows = self.f._pyparse_rows()
                self.seed_analysis(rows)
                self.f.product_peak_overrides = {"CCO": {"C1": {"peak_index": 0}, "C2": {"peak_index": 0}}}
                evidence = copy.deepcopy(self.f.peak_inspection_data)
                self.import_csv(incoming)
                rows = self.f._pyparse_rows()
                self.assertEqual(["C2", "C1"], [row["pyparse_well"] for row in rows])
                self.assertEqual(["84%", "83%"], [self.f._modified_pyparse_purity_for_row(row) for row in rows])
                self.assertEqual(evidence, self.f.peak_inspection_data)
                self.assertEqual({}, self.f.product_peak_overrides)
                for row in rows:
                    self.assertEqual("", self.f._product_structure_purity_for_row(row, "manual"))
                    self.assertEqual("", self.f._product_structure_purity_for_row(row, "pyparse"))
                self.assertEqual({"comments": "Note C1"}, self.f.product_structure_manual_notes["lcms:C1"])
                self.assertEqual({"comments": "Note C2"}, self.f.product_structure_manual_notes["lcms:C2"])

    def test_partial_remap_reuses_destination_and_preserves_unaffected_result(self):
        self.import_csv("A1,C1,CCO\nA2,C2,CCN\n")
        self.seed_analysis(self.f._pyparse_rows())
        self.f.modified_pyparse_purity_by_product["CCO"]["D1"] = "15%"
        original_c2 = copy.deepcopy(self.f.peak_inspection_data["targets"]["CCN"]["C2"])
        self.import_csv("A1,D1,CCO\nA2,C2,CCN\n")
        rows = self.f._pyparse_rows()
        self.assertEqual(["15%", "84%"], [self.f._modified_pyparse_purity_for_row(row) for row in rows])
        self.assertEqual("77", self.f._product_structure_purity_for_row(rows[1], "manual"))
        self.assertEqual(original_c2, self.f.peak_inspection_data["targets"]["CCN"]["C2"])


if __name__ == "__main__":
    unittest.main()
