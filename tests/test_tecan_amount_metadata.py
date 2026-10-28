"""Manual extra volumes remain authoritative across new and legacy records."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tecan_frame import TecanFrame, TransferBlock, DispenseGroup
from reaction_summary_frame import ReactionSummaryFrame


class TecanAmountMetadataTests(unittest.TestCase):
    def rows(self):
        frame = object.__new__(TecanFrame)
        block = TransferBlock(dest_wells_expr="A1", dest_volume=50,
                              chemical_name="BB", reaction_umol="10",
                              is_building_block=True, disp_different_vol=True,
                              dispense_groups=[DispenseGroup(5, "C1")])
        return frame._building_block_rows_from_blocks([block], "96-well horizontal")

    def summary(self, rows, concentration):
        frame = object.__new__(ReactionSummaryFrame)
        frame._resolve_compound = lambda chemical: {"Conc.": concentration}
        frame._role_from_building_block_flag = lambda *args, **kwargs: "Building Block"
        result = frame._destination_summary([], rows)
        return [r for group in result[3].values() for r in group]

    def test_extra_metadata_contains_volume_without_inherited_amount(self):
        rows = json.loads(json.dumps(self.rows()))
        self.assertEqual([50, 5], [r["volume_uL"] for r in rows])
        self.assertEqual("10", rows[0]["reaction_umol"])
        self.assertNotIn("reaction_umol", rows[1])
        self.assertEqual([10, 1], [r["umol"] for r in self.summary(rows, "0.2")])

    def test_old_project_amount_is_ignored_in_fallback(self):
        rows = self.rows()
        rows[1]["reaction_umol"] = "10"
        for source in ("Tecan", ""):
            rows[1].update(source=source, gwl="old.gwl")
            self.assertEqual(1, self.summary(rows, "0.2")[1]["umol"])
        self.assertEqual("10", rows[1]["reaction_umol"])

    def test_unknown_concentration_does_not_reuse_stale_amount(self):
        rows = self.rows()
        rows[1]["reaction_umol"] = "10"
        self.assertEqual(0, self.summary(rows, "")[1]["umol"])

    def test_manual_and_opentrons_amounts_are_preserved(self):
        for source in ("Manual", "Opentrons"):
            row = dict(self.rows()[1], source=source, reaction_umol="3")
            self.assertEqual(3, self.summary([row], "0.2")[0]["umol"])


if __name__ == "__main__":
    unittest.main()
