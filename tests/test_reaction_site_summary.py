from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from xinpilot_shared import Chem  # noqa: E402
from cheminformatics_frame import CheminformaticsFrame  # noqa: E402
from reaction_summary_frame import ReactionSummaryFrame  # noqa: E402


class GeneralReactionSiteTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(CheminformaticsFrame)
        self.frame._reaction_site_options_cache = {}
        self.frame.reaction_site_selections = {}
        self.reaction = {
            "id": "carbonyl_reduction",
            "label": "Carbonyl Reduction to Alcohol",
            "smarts": "[C:1]=[O:2]>>[C:1][O:2]",
        }
        self.reactants = [{"chemical": "ASYMMETRIC-DICARBONYL"}]
        self.mols = (Chem.MolFromSmiles("CC(=O)CCC=O"),)

    def test_non_halide_reaction_exposes_distinct_product_generating_sites(self):
        signature, options = self.frame._reaction_site_options(
            self.reaction,
            self.reactants,
            self.mols,
        )
        self.assertTrue(signature)
        self.assertEqual(2, len(options))
        self.assertEqual(2, len({tuple(option["products"]) for option in options}))
        self.assertTrue(all(len(option["site_matches"]) == 1 for option in options))

    def test_keep_all_and_one_site_apply_different_product_sets(self):
        signature, options = self.frame._reaction_site_options(
            self.reaction,
            self.reactants,
            self.mols,
        )
        all_products = sorted({product for option in options for product in option["products"]})
        grouped = {
            "reactants": self.reactants,
            "ordered_mols": self.mols,
            "candidate_products": all_products,
            "status": "Ambiguous",
        }

        self.frame.reaction_site_selections[signature] = {"choice": "all"}
        self.frame._apply_saved_reaction_site_selection(grouped, self.reaction)
        self.assertEqual("all", grouped["reaction_site_choice"])
        self.assertEqual(all_products, grouped["candidate_products"])

        selected_matches = options[0]["site_matches"]
        self.frame.reaction_site_selections[signature] = {
            "choice": "site",
            "site_matches": selected_matches,
        }
        self.frame._apply_saved_reaction_site_selection(grouped, self.reaction)
        self.assertEqual("site", grouped["reaction_site_choice"])
        self.assertEqual(options[0]["products"], grouped["candidate_products"])

    def test_keep_all_flows_into_product_summary_rows_even_with_different_masses(self):
        possible_products = ["CCO", "CCCl"]
        grouped = {
            "well": "A1",
            "reactants": [{"compound": {"ID": "CHEM-1", "Name": "One", "SMILES": "CC=O"}}],
            "candidate_products": possible_products,
            "reaction_site_choice": "all",
            "status": "Ready: keeping all 2 possible products",
        }
        self.frame.product_details_generated = True
        self.frame.imported_product_details = {}
        self.frame.pyparse_wells = {}
        self.frame.reaction_names = {}
        self.frame._reaction = MethodType(
            lambda _self: {"id": "test", "reactant_count": 1},
            self.frame,
        )
        self.frame._grouped_reaction_rows = MethodType(lambda _self: [grouped], self.frame)
        self.frame._raw_grouped_reaction_rows = MethodType(lambda _self: [grouped], self.frame)
        self.frame._custom_grouped_reaction_rows = MethodType(lambda _self: [], self.frame)
        self.frame._custom_product_for_well = MethodType(lambda _self, _well: "", self.frame)

        rows = self.frame._pyparse_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(sorted(possible_products), rows[0]["selectivity products"])
        self.assertEqual(sorted(possible_products)[0], rows[0]["desired product smiles"])
        self.assertEqual("", rows[0]["pyparse_well"])
        self.assertEqual("Assign a valid LCMS well", rows[0]["status"])


class ReactionSummaryMultipleProductTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(ReactionSummaryFrame)
        self.products = ["CC(O)CCC=O", "CC(=O)CCCO"]
        self.frame.compound_provider = lambda: [
            SimpleNamespace(values={
                "ID": "CHEM-1",
                "SMILES": "CC(=O)CCC=O",
                "Type": "Reactant1",
            })
        ]
        self.frame.product_provider = lambda: [{
            "reaction_well": "A1",
            "product_id": "RXN_A1",
            "desired product smiles": self.products[0],
            "selectivity products": list(self.products),
        }]
        self.frame.reaction_provider = lambda: {}
        self.frame.other_chemicals_var = SimpleNamespace(get=lambda: "")
        self.frame.temperature_var = SimpleNamespace(get=lambda: "")
        self.frame.duration_var = SimpleNamespace(get=lambda: "")

    def test_scheme_row_preserves_every_retained_product(self):
        rows = self.frame._scheme_rows_from_pushed([{
            "well": "A1",
            "chemical_id": "CHEM-1",
            "volume_uL": 20,
            "is_building_block": True,
        }])
        self.assertEqual(1, len(rows))
        self.assertEqual(self.products, rows[0]["products"])
        self.assertEqual(self.products[0], rows[0]["product"])

    def test_scheme_renderer_draws_every_product_card(self):
        drawn_products = []

        def record_molecule(_self, _img, _draw, smiles, _label, _box, _font, _small_font):
            drawn_products.append(smiles)

        self.frame._draw_centered_mol = MethodType(record_molecule, self.frame)
        row = {
            "well": "A1",
            "product_id": "RXN_A1",
            "chemicals": [],
            "products": list(self.products),
        }
        with patch("reaction_summary_frame.ImageTk.PhotoImage", side_effect=lambda image: image):
            image = self.frame._scheme_image(row)
        self.assertEqual(self.products, drawn_products)
        self.assertGreater(image.width, 940)


class ReactionSummarySourceOfTruthTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(ReactionSummaryFrame)
        self.frame.compound_provider = lambda: []
        self.frame.opentrons_provider = None
        self.pushed = [
            {"source": "Tecan", "gwl": "tecan.gwl", "well": "A1", "chemical": "TECAN-CHEM", "volume_uL": 10},
            {"source": "Manual workflow", "well": "A2", "chemical": "MANUAL-CHEM", "volume_uL": 20},
            {
                "source": "Opentrons", "well": "A3", "chemical": "OT-CHEM", "volume_uL": 30,
                "dest_labware": "nest_96_wellplate_200ul_flat", "dest_map_style": "96 well",
            },
        ]
        self.frame.pushed_provider = lambda: list(self.pushed)

    @staticmethod
    def _block(chemical, well, volume, source):
        return {
            "file_name": source,
            "mode": "96-well horizontal",
            "chem_label_map": {},
            "from_snapshot": True,
            "block": SimpleNamespace(
                dest_labware="96 Well Microplate",
                dest_wells_expr=well,
                dest_volume=volume,
                disp_different_vol=False,
                dispense_groups=[],
                chemical_name=chemical,
                is_building_block=True,
            ),
        }

    def test_only_pushed_snapshots_are_used_even_when_native_sources_exist(self):
        tecan_blocks = [self._block("TECAN-CHEM", "A1", 10, "tecan.gwl")]
        manual_blocks = [self._block("MANUAL-CHEM", "A2", 20, "Manual workflow")]
        native_opentrons = [{
            "source": "Opentrons", "well": "A3", "chemical": "OT-CHEM", "volume_uL": 30,
            "dest_labware": "nest_96_wellplate_200ul_flat", "dest_map_style": "96 well",
        }]

        rows = self.frame._summary_transfer_rows(
            tecan_blocks,
            manual_blocks,
            opentrons_rows=native_opentrons,
        )

        self.assertEqual(self.pushed, rows)

    def test_combined_summary_keeps_each_pushed_source(self):
        tecan_blocks = [self._block("TECAN-CHEM", "A1", 10, "tecan.gwl")]
        manual_blocks = [self._block("MANUAL-CHEM", "A2", 20, "Manual workflow")]
        native_opentrons = [{
            "source": "Opentrons", "well": "A3", "chemical": "OT-CHEM", "volume_uL": 30,
            "dest_labware": "nest_96_wellplate_200ul_flat", "dest_map_style": "96 well",
            "is_building_block": True,
        }]
        summary_rows = self.frame._summary_transfer_rows(
            tecan_blocks,
            manual_blocks,
            opentrons_rows=native_opentrons,
        )

        _mode, _labware, _wells, tables = self.frame._destination_summary(
            [],
            summary_rows,
        )
        transfers = [row for group_rows in tables.values() for row in group_rows]

        self.assertEqual(3, len(transfers))
        self.assertEqual(
            {("A1", "TECAN-CHEM"), ("A2", "MANUAL-CHEM"), ("A3", "OT-CHEM")},
            {(row["well"], row["chemical"]) for row in transfers},
        )

    def test_legacy_pushed_rows_are_kept_when_native_source_is_missing(self):
        rows = self.frame._summary_transfer_rows([], [], opentrons_rows=[])
        self.assertEqual(self.pushed, rows)

    def test_source_less_legacy_gwl_row_is_treated_as_tecan(self):
        self.frame.pushed_provider = lambda: [{
            "source": "", "gwl": "legacy.gwl", "well": "A1", "chemical": "TECAN-CHEM",
        }]
        tecan_blocks = [self._block("TECAN-CHEM", "A1", 10, "legacy.gwl")]
        self.assertEqual(self.frame.pushed_provider(), self.frame._summary_transfer_rows(tecan_blocks, [], opentrons_rows=[]))


if __name__ == "__main__":
    unittest.main()
