import unittest
from types import SimpleNamespace

import impurity_analysis
from integrated_full_software import IntegratedFullApp


REACTION_SMARTS = "[C:1][Br:2].[N:3]>>[C:1][N:3]"


def _reaction_row(desired="CCNC", source_id="STEP1_PRODUCT"):
    return {
        "reaction_name": "RXN_A1",
        "reaction": "test_substitution",
        "reaction_well": "A1",
        "pyparse_well": "B1",
        "desired product smiles": desired,
        "selectivity products": [desired],
        "reactant 1 smiles": "CCBr",
        "reactant 1 name": "Step-one product",
        "reactant 1 id": source_id,
        "reactant 2 smiles": "CN",
        "reactant 2 name": "Methylamine",
        "reactant 2 id": "AMINE",
        "reactant 3 smiles": "",
        "reactant 3 name": "",
        "reactant 3 id": "",
    }


def _carried_sources(source_id="STEP1_PRODUCT"):
    return {
        source_id: {
            "compound_id": source_id,
            "source_step": 1,
            "source_reaction_well": "C3",
            "source_lcms_well": "D3",
            "carryover_status": "Purified/worked up before carry-forward",
            "impurities": [{
                "smiles": "CCCBr",
                "name": "Step-one side product",
                "lineage": "Generated in Step 1, RXN well C3",
            }],
        }
    }


class MultistepImpurityChemistryTests(unittest.TestCase):
    def test_matching_carried_material_adds_unchanged_and_descendant_targets(self):
        rows = impurity_analysis.carried_impurity_candidates(
            _reaction_row(),
            REACTION_SMARTS,
            _carried_sources(),
            current_step=2,
        )
        by_category = {row["category"]: row for row in rows}
        self.assertEqual(by_category["Carried impurity"]["smiles"], "CCCBr")
        self.assertEqual(by_category["Descendant impurity"]["smiles"], "CCCNC")
        self.assertIn("Step 1", by_category["Carried impurity"]["origin"])
        self.assertIn("reacted in Step 2", by_category["Descendant impurity"]["lineage"])
        self.assertIn("Purified/worked up", by_category["Carried impurity"]["carryover_status"])

    def test_carried_impurities_follow_only_wells_using_the_promoted_chemical_id(self):
        rows = impurity_analysis.carried_impurity_candidates(
            _reaction_row(source_id="ANOTHER_PRODUCT"),
            REACTION_SMARTS,
            _carried_sources(),
            current_step=2,
        )
        self.assertEqual(rows, [])

    def test_descendant_identical_to_desired_product_is_excluded(self):
        rows = impurity_analysis.carried_impurity_candidates(
            _reaction_row(desired="CCCNC"),
            REACTION_SMARTS,
            _carried_sources(),
            current_step=2,
        )
        self.assertEqual([row["smiles"] for row in rows], ["CCCBr"])

    def test_duplicate_carried_structures_merge_their_lineage(self):
        sources = _carried_sources()
        sources["STEP1_PRODUCT"]["impurities"].append({
            "smiles": "CCCBr",
            "name": "Same structure, second origin",
            "lineage": "Also observed in Step 1, RXN well C4",
        })
        rows = impurity_analysis.carried_impurity_candidates(
            _reaction_row(),
            REACTION_SMARTS,
            sources,
            current_step=2,
        )
        self.assertEqual(len(rows), 2)
        carried = next(row for row in rows if row["category"] == "Carried impurity")
        self.assertIn("RXN well C3", carried["lineage"])
        self.assertIn("RXN well C4", carried["lineage"])


class MultistepImpurityHandoffTests(unittest.TestCase):
    def test_selected_wells_receive_only_their_own_impurity_history(self):
        app = SimpleNamespace(
            cheminformatics_tab=SimpleNamespace(
                _included_impurity_rows=lambda: [
                    {"reaction_well": "A1", "smiles": "CCBr"},
                    {"reaction_well": "A2", "smiles": "CCCBr"},
                ]
            )
        )
        selected = [{"reaction_well": "A2", "lcms_well": "B2"}]
        count = IntegratedFullApp._attach_selected_impurity_history(app, selected)
        self.assertEqual(count, 1)
        self.assertEqual(selected[0]["carried_impurities"][0]["smiles"], "CCCBr")

    def test_promoted_id_becomes_the_next_step_impurity_source_key(self):
        selected = [{
            "reaction_well": "A2",
            "lcms_well": "B2",
            "promoted_compound_id": "P-002_2",
            "carried_impurities": [{"smiles": "CCCBr", "lineage": "Generated in Step 1"}],
        }]
        sources = IntegratedFullApp._carried_impurity_sources(
            selected,
            source_step=1,
            carryover_status="Crude or purification not recorded",
        )
        self.assertEqual(list(sources), ["P-002_2"])
        self.assertEqual(sources["P-002_2"]["source_reaction_well"], "A2")
        self.assertEqual(sources["P-002_2"]["source_lcms_well"], "B2")


if __name__ == "__main__":
    unittest.main()
