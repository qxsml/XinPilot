"""Regressions for tip capacity, GWL precision and physical source identity."""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import sys
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xinpilot.application.opentrons_protocol import OpentronsCompileRequest, compile_protocol
from xinpilot.application.opentrons_domain import all_channel_source_wells
from xinpilot.application.tecan_domain import TransferBlock, DispenseGroup
from xinpilot.application.tecan_worklist import build_gwl_lines, build_volume_map
from opentrons_frame import OpentronsFrame, OpentronsTransferRow
from tecan_frame import TecanFrame


def transfer(**changes):
    row = OpentronsFrame._transfer_row_dict(OpentronsTransferRow(
        source_well="A1", dest_wells="A1,A2,A3", volume_ul=20,
        strategy="Multi-dispense", pipette_key="left", chemical="REAGENT",
    ))
    row.update(changes)
    return row


def request(rows=None, tip_capacity=50):
    return OpentronsCompileRequest(
        robot="Flex", api_level="2.20", rows=rows or [transfer()],
        pipettes={"left": {"name": "flex_1channel_1000",
                            "tiprack": f"opentrons_flex_96_tiprack_{tip_capacity}ul",
                            "tiprack_slots": ["B2"], "tip_start_column": "1", "tip_start_well": "A1"}},
        labware_configs=[
            {"alias": "source1", "role": "source", "load_name": "nest_12_reservoir_15ml", "slot": "C1", "map_style": "12 well reservoir"},
            {"alias": "dest1", "role": "destination", "load_name": "corning_96_wellplate_360ul_flat", "slot": "D1", "map_style": "96 well"},
        ], module_configs=[], deck_occupants={},
    )


def emitted_rows(req):
    tree = ast.parse(compile_protocol(req))
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", "") == "TRANSFER_ROWS")


class RobotCapacityAndGeometryTests(unittest.TestCase):
    def test_smaller_tips_reject_oversize_single_transfers_and_limit_batches(self):
        for capacity, volume in ((50, 20), (200, 80)):
            for pipette in ("flex_1channel_1000", "flex_8channel_1000"):
                with self.subTest(capacity=capacity, pipette=pipette):
                    req = request([transfer(volume_ul=capacity + 1, strategy="Single transfer")], capacity)
                    req.pipettes["left"]["name"] = pipette
                    with self.assertRaisesRegex(ValueError, "pipette/tip capacity"):
                        compile_protocol(req)
            rows = emitted_rows(request([transfer(volume_ul=volume)], capacity))
            self.assertEqual(2, rows[0]["batch_size"])

    def test_auto_can_select_mount_with_larger_tips(self):
        req = request([transfer(volume_ul=100, pipette_key="Auto", strategy="Single transfer")])
        req.pipettes["right"] = dict(req.pipettes["left"], tiprack="opentrons_flex_96_tiprack_1000ul", tiprack_slots=["B3"])
        self.assertEqual("right", emitted_rows(req)[0]["pipette_key"])

    def test_auto_prefers_smaller_pipette_when_tip_capacities_tie(self):
        req = request([transfer(volume_ul=1, pipette_key="Auto", strategy="Single transfer")])
        req.pipettes["right"] = dict(req.pipettes["left"], name="flex_1channel_50", tiprack_slots=["B3"])
        row = emitted_rows(req)[0]
        self.assertEqual("right", row["pipette_key"])
        self.assertFalse(row["below_recommended_min"])

    def test_air_extra_and_mixing_reserve_share_the_actual_tip_capacity(self):
        cases = [
            (dict(delay_air_gap_enabled=True, air_gap_enabled=True, air_gap_volume_ul="15"), 1),
            (dict(multi_dispense_extra_percent="25", blowout_location="Source"), 2),
            (dict(mix_enabled=True, mix_timing="After dispensing", mix_repetitions="2", mix_volume_ul="30"), 2),
            (dict(mix_enabled=True, mix_timing="After dispensing", mix_repetitions="2", mix_volume_ul="30",
                  delay_air_gap_enabled=True, air_gap_enabled=True, air_gap_volume_ul="10"), 1),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertEqual(expected, emitted_rows(request([transfer(**changes)]))[0]["batch_size"])
        for changes in (
            dict(volume_ul=40, delay_air_gap_enabled=True, air_gap_enabled=True, air_gap_volume_ul="15"),
            dict(mix_enabled=True, mix_repetitions="2", mix_volume_ul="60"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "pipette/tip capacity"):
                compile_protocol(request([transfer(**changes)]))

    def test_ot2_filter_tips_also_limit_capacity(self):
        req = request([transfer(volume_ul=250, strategy="Single transfer")], 200)
        req.pipettes["left"].update(name="p300_single_gen2", tiprack="opentrons_96_filtertiprack_200ul", tiprack_slots=["3"])
        req.labware_configs[0]["slot"] = "1"
        req.labware_configs[1]["slot"] = "2"
        with self.assertRaisesRegex(ValueError, "200 uL"):
            compile_protocol(replace(req, robot="OT-2"))

    def test_all_channel_physical_sources_and_common_reservoirs(self):
        self.assertEqual([f"{row}1" for row in "ABCDEFGH"], all_channel_source_wells("A1", "96 well", "nest_96_wellplate_2ml_deep"))
        self.assertEqual([f"{row}2" for row in "BDFHJLNP"], all_channel_source_wells("B2", "384 well", "biorad_384_wellplate_50ul"))
        self.assertEqual(["A3"], all_channel_source_wells("A3", "12 well reservoir", "nest_12_reservoir_15ml"))
        self.assertEqual(["A1"], all_channel_source_wells("A1", "1 well", "agilent_1_reservoir_290ml"))
        self.assertEqual([f"{row}1" for row in "ABCDEFGH"], all_channel_source_wells("A1", "8 well reservoir", "nest_8_reservoir_22ml"))
        with self.assertRaises(ValueError):
            all_channel_source_wells("B1", "8 well reservoir", "nest_8_reservoir_22ml")

    def test_ordinary_all_channel_conflicts_are_rejected_in_both_orders(self):
        column = transfer(dest_wells=",".join(f"{letter}1" for letter in "ABCDEFGH"), strategy="Single transfer")
        second = transfer(source_well="B1", dest_wells="A2", pipette_key="right", chemical="OTHER")
        req = request([column, second], 1000)
        req.pipettes["left"]["name"] = "flex_8channel_1000"
        req.pipettes["right"] = dict(req.pipettes["left"], name="flex_1channel_1000", tiprack_slots=["B3"])
        req.labware_configs[0].update(load_name="nest_96_wellplate_2ml_deep", map_style="96 well")
        for rows in ([column, second], [second, column]):
            with self.subTest(order=rows), self.assertRaisesRegex(ValueError, "source1:B1.*multiple Chemical IDs"):
                compile_protocol(replace(req, rows=rows))
        second["chemical"] = "REAGENT"
        rows = emitted_rows(req)
        self.assertEqual({f"{letter}1": "REAGENT" for letter in "ABCDEFGH"}, rows[0]["source_chemical_ids"])

    def test_tecan_checks_emitted_precision_even_for_legacy_raw_values(self):
        block = TransferBlock(source_volume=60.2, dest_volume=20.06, dest_wells_expr="A1,A2,A3")
        with self.assertRaisesRegex(ValueError, "60.3.*60.2"):
            build_gwl_lines([block], "96-well horizontal")
        self.assertEqual({"A1": 20.1, "A2": 20.1, "A3": 20.1}, build_volume_map([block], "96-well horizontal"))


class RobotControllerReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def opentrons(self):
        frame = OpentronsFrame(self.root)
        self.addCleanup(frame.destroy)
        frame.labware_configs = request().labware_configs
        frame.left_pipette_var.set("flex_8channel_1000")
        frame.left_tiprack_var.set("opentrons_flex_96_tiprack_1000ul")
        frame.left_tiprack_slots_var.set("B2")
        frame.right_pipette_var.set("None")
        frame.labware_configs[0].update(load_name="nest_96_wellplate_2ml_deep", map_style="96 well")
        frame.rows = [transfer(dest_wells=",".join(f"{letter}1" for letter in "ABCDEFGH"), strategy="Single transfer")]
        return frame

    def test_ordinary_columns_reserve_and_report_each_physical_source(self):
        frame = self.opentrons()
        self.assertIn("another Chemical ID", frame._source_well_conflict("source1", "B1", "OTHER"))
        self.assertEqual({f"{letter}1": "REAGENT" for letter in "ABCDEFGH"}, frame._source_well_chemical_assignments("source1"))
        rows = frame.rows_for_cheminformatics()
        self.assertEqual([f"{letter}1" for letter in "ABCDEFGH"], [row["source_well"] for row in rows])
        self.assertEqual("source1:B1", rows[1]["building_block_location"])
        frame._build_script_text()

    def test_shared_reservoir_and_forced_single_keep_the_same_source(self):
        frame = self.opentrons()
        frame.labware_configs[0].update(load_name="nest_12_reservoir_15ml", map_style="12 well reservoir")
        self.assertEqual(["A1"] * 8, [row["source_well"] for row in frame.rows_for_cheminformatics()])
        self.assertEqual("", frame._source_well_conflict("source1", "A2", "OTHER"))
        frame.labware_configs[0].update(load_name="nest_96_wellplate_2ml_deep", map_style="96 well")
        frame.eight_channel_mode_var.set("Force single tip")
        self.assertEqual(["A1"] * 8, [row["source_well"] for row in frame.rows_for_cheminformatics()])

    def test_384_source_provenance_uses_alternating_wells(self):
        frame = self.opentrons()
        frame.labware_configs[0].update(load_name="biorad_384_wellplate_50ul", map_style="384 well")
        frame.rows[0]["source_well"] = "B2"
        self.assertEqual([f"{letter}2" for letter in "BDFHJLNP"], [row["source_well"] for row in frame.rows_for_cheminformatics()])

    def test_tecan_editor_snapshots_and_metadata_use_emitted_volumes(self):
        frame = TecanFrame(self.root)
        self.addCleanup(frame.destroy)
        frame.mode_var.set("96-well horizontal")
        frame._updating_form = True
        frame.v_dest_labware.set("DeepPlate1")
        frame.v_dest_wells.set("A1,A2,A3")
        frame.v_dest_volume.set("20.06")
        frame.v_extra_aspirate_percent.set("0")
        frame.v_chemical.set("REAGENT")
        frame.v_is_building_block.set(True)
        frame._updating_form = False
        frame._sync_source_volume_to_dispense_total()
        self.assertEqual("60.3", frame.v_source_volume.get())
        block = frame._collect_form_block()
        self.assertEqual(20.1, block.dest_volume)
        self.assertEqual(60.3, block.source_volume)
        frame.blocks = [block]
        lines = frame._build_lines()
        self.assertIn(";;60.3;", lines[0])
        self.assertEqual([20.1] * 3, [row["volume_uL"] for row in frame.get_building_block_table()])
        raw = dict(frame._block_to_dict(block), dest_volume=20.06)
        raw["dispense_groups"] = [{"volume": 10.06, "wells_expr": "B1"}]
        restored = frame._block_from_dict(raw)
        self.assertEqual(20.1, restored.dest_volume)
        self.assertEqual(10.1, restored.dispense_groups[0].volume)
        self.assertEqual(20.1, frame._block_to_dict(restored)["dest_volume"])


if __name__ == "__main__":
    unittest.main()
