"""Custom templates honor stock ion choices and cannot reuse failed products."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rdkit import Chem
from cheminformatics_frame import CheminformaticsFrame


def variable(value):
    return SimpleNamespace(get=lambda *args: value)


def reactant(stock, prepared=None, counterions=()):
    return {
        "chemical": "test reagent", "compound": {"SMILES": stock},
        "smiles": prepared or stock, "kept_counterions": list(counterions),
    }


def frame(template):
    result = object.__new__(CheminformaticsFrame)
    result.custom_template_text = variable(template)
    result.custom_reactant_order_var = variable("Automatic (try all orders)")
    result.logw = Mock()
    return result


def generate(template, rows):
    f = frame(template)
    grouped = {"reactants": rows, **{f"reactant{i}": row for i, row in enumerate(rows, 1)}}
    return f._run_custom_reaction(grouped, f._compile_custom_reaction())


class CustomIonHandlingTests(unittest.TestCase):
    def assertSameMolecule(self, actual, expected):
        self.assertEqual(Chem.MolToSmiles(Chem.MolFromSmiles(expected)), actual)

    def test_two_reactant_template_uses_prepared_neutralized_stock(self):
        product = generate(
            "[C:1](=[O:2])[OH].[NH2:3]>>[C:1](=[O:2])[NH:3]",
            [reactant("CC(=O)O"), reactant("CC[NH3+].[Cl-]", "CCN")],
        )
        self.assertSameMolecule(product, "CCNC(C)=O")

    def test_two_reactant_template_restores_user_retained_counterion(self):
        product = generate(
            "[c:1][Cl,Br,I].[c:2]B(O)O>>[c:1]-[c:2]",
            [reactant("Clc1ccccc1"), reactant("[Na+].O=C([O-])c1ccccc1B(O)O", "O=C([O-])c1ccccc1B(O)O", ["[Na+]"])],
        )
        self.assertSameMolecule(product, "[Na+].O=C([O-])c1ccccc1-c1ccccc1")

    def test_one_reactant_template_retains_counterion_once(self):
        product = generate(
            "[C:1](=[O:2])[O-:3]>>[C:1](=[O:2])[O-:3]",
            [reactant("CC(=O)[O-].[Na+]", "CC(=O)[O-]", ["[Na+]"])],
        )
        self.assertSameMolecule(product, "CC(=O)[O-].[Na+]")

    def test_three_reactant_template_uses_prepared_stock(self):
        product = generate(
            "[C:1]Br.[NH2:2].[C:3](=[O:4])Cl>>[C:1][N:2][C:3](=[O:4])",
            [reactant("CCBr"), reactant("C[NH3+].[Cl-]", "CN"), reactant("CC(=O)Cl")],
        )
        self.assertSameMolecule(product, "CCN(C)C(C)=O")


class CustomResultLifecycleTests(unittest.TestCase):
    def setup_frame(self, template, product):
        f = frame(template)
        f.custom_products = {"A1": {"smiles": "CCO"}, "A2": {"smiles": "CCN"}}
        f.custom_failures = {}
        f.custom_preview = SimpleNamespace(selection=lambda: ("0",))
        f.retained_results_var = variable(False)
        f.custom_output_dir_var = variable("")
        f._custom_grouped_reaction_rows = lambda: [{"well": "A1"}, {"well": "A2"}]
        f._run_custom_reaction = Mock(side_effect=ValueError("Template did not match") if product is None else None, return_value=product)
        f._pyparse_rows = lambda: [
            {"reaction_well": well, "pyparse_well": lcms, "desired product smiles": f.custom_products.get(well, {}).get("smiles", "")}
            for well, lcms in (("A1", "C1"), ("A2", "C2"))
        ]
        f.product_details_generated = True
        f._refresh_product_details_preview = Mock()
        f._refresh_custom_preview = Mock()
        f._product_structure_manual_key = lambda row: row["reaction_well"]
        f.lcms_target_smiles_by_well = {"A1": "CCO", "A2": "CCN"}
        f.lcms_target_summaries_by_well = {"A1": "exact", "A2": "exact"}
        f.modified_pyparse_purity_by_product = {"CCO": {"C1": "70%"}, "CCN": {"C2": "80%"}}
        f.product_peak_overrides = {"CCO": {"C1": {"peak_index": 0}}}
        f.peak_inspection_data = {"wells": {"C1": {"sample": "preserved"}}, "targets": {"CCO": {"C1": {"automatic": {}}}}}
        f.product_structure_manual_notes = {"A1": {"comments": "keep this", "manual_purity": "70"}}
        return f

    def run_selected(self, f):
        with patch("cheminformatics_frame.messagebox.showinfo"), patch("cheminformatics_frame.messagebox.showerror") as errors:
            f._generate_custom_products(selected_only=True)
        errors.assert_not_called()

    def test_failed_regeneration_removes_prior_product_and_analysis_only_for_selected_well(self):
        f = self.setup_frame("[C:1]>>[C:1]", None)
        self.run_selected(f)
        self.assertNotIn("A1", f.custom_products)
        self.assertIn("A1", f.custom_failures)
        self.assertEqual({"smiles": "CCN"}, f.custom_products["A2"])
        self.assertNotIn("CCO", f.modified_pyparse_purity_by_product)
        self.assertEqual({"C2": "80%"}, f.modified_pyparse_purity_by_product["CCN"])
        self.assertEqual({}, f.product_peak_overrides)
        self.assertNotIn("A1", f.lcms_target_smiles_by_well)
        self.assertEqual({"comments": "keep this"}, f.product_structure_manual_notes["A1"])
        self.assertEqual({"sample": "preserved"}, f.peak_inspection_data["wells"]["C1"])
        self.assertTrue(f._analysis_is_invalidated({"reaction_well": "A1"}, "modified"))

    def test_changed_custom_product_detaches_previous_analytical_identity(self):
        f = self.setup_frame("[C:1]>>[C:1]", "CCC")
        self.run_selected(f)
        self.assertEqual("CCC", f.custom_products["A1"]["smiles"])
        self.assertNotIn("CCO", f.modified_pyparse_purity_by_product)
        self.assertTrue(f._analysis_is_invalidated({"reaction_well": "A1"}, "modified"))

    def test_equivalent_custom_product_keeps_valid_analysis(self):
        f = self.setup_frame("[C:1]>>[C:1]", "OCC")
        self.run_selected(f)
        self.assertEqual({"C1": "70%"}, f.modified_pyparse_purity_by_product["CCO"])
        self.assertFalse(f._analysis_is_invalidated({"reaction_well": "A1"}, "modified"))


if __name__ == "__main__":
    unittest.main()
