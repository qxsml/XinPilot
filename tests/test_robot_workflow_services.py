"""Behavior contracts for the headless robot workflow boundary.

The Opentrons fixture hashes were captured from Local before extraction. They
verify the entire generated file, including the order of every robot command.
The eight_channel_column hash was updated on 2026-10-12 solely to expand its
source chemical/building-block metadata from anchor A1 to physical wells A1-H1;
all command-generating code and other fixture bytes remained unchanged.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xinpilot.application.opentrons_protocol import OpentronsCompileRequest, compile_protocol
from xinpilot.application.opentrons_validation import (
    optional_nonnegative_float, required_positive_float,
)
from xinpilot.application.tecan_domain import (
    DispenseGroup, TransferBlock, index_to_dest_label, parse_dest_well_expr,
)
from xinpilot.application.tecan_worklist import (
    build_chemical_map, build_gwl_lines, build_volume_map,
)
from xinpilot.application.values import coerce_bool


class HeadlessImportTests(unittest.TestCase):
    def test_robot_services_do_not_load_ui_or_chemistry_dependencies(self):
        code = """
import sys
from xinpilot.application import opentrons_protocol, tecan_worklist
for dependency in ('tkinter', 'webview', 'rdkit', 'openpyxl', 'xinpilot_shared'):
    assert dependency not in sys.modules, dependency
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


class OpentronsCompilerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = json.loads((ROOT / "tests/fixtures/opentrons_compiler_contracts.json").read_text(encoding="utf-8"))

    def request(self, name):
        return deepcopy(next(case["request"] for case in self.contracts if case["name"] == name))

    def test_all_reviewed_protocol_bytes_and_input_snapshots_are_preserved(self):
        for case in self.contracts:
            with self.subTest(case=case["name"]):
                request = OpentronsCompileRequest(**deepcopy(case["request"]))
                before = deepcopy(asdict(request))
                text = compile_protocol(request)
                compile(text, case["name"] + ".py", "exec")
                self.assertEqual(case["sha256"], sha256(text.encode()).hexdigest())
                self.assertEqual(before, asdict(request))
                self.assertEqual(text, compile_protocol(request))

    def test_sequence_order_is_sample_then_group_with_tip_retention(self):
        text = compile_protocol(OpentronsCompileRequest(**self.request("sequence_tip_retention")))
        assignment = next(node for node in ast.parse(text).body if isinstance(node, ast.Assign)
                          and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "TRANSFER_ROWS")
        rows = ast.literal_eval(assignment.value)
        self.assertEqual([(1, "Add"), (1, "Mix"), (2, "Add"), (2, "Mix")],
                         [(row["sequence_sample_index"], row["sequence_group_name"]) for row in rows])
        self.assertEqual(["Keep tip mounted", "Bin tip after row"] * 2,
                         [row["tip_policy"] for row in rows])

    def test_excess_volume_cannot_be_silently_sent_to_destination(self):
        data = self.request("multi_excess_waste")
        data["rows"][0]["blowout_location"] = "Destination"
        with self.assertRaisesRegex(ValueError, "Choose Source or Liquid waste"):
            compile_protocol(OpentronsCompileRequest(**data))

    def test_reaction_labware_cannot_be_used_as_dedicated_waste(self):
        data = self.request("multi_excess_waste")
        data["rows"][0]["blowout_labware_alias"] = "dest1"
        with self.assertRaisesRegex(ValueError, "separate from all source and reaction labware"):
            compile_protocol(OpentronsCompileRequest(**data))

    def test_changed_source_chemical_is_rejected_without_mutating_request(self):
        data = self.request("multi_air_no_blowout")
        data["rows"].append(dict(data["rows"][0], chemical="OTHER"))
        request = OpentronsCompileRequest(**data)
        before = deepcopy(asdict(request))
        with self.assertRaisesRegex(ValueError, "assigned to multiple Chemical IDs"):
            compile_protocol(request)
        self.assertEqual(before, asdict(request))

    def test_unused_mount_stays_in_collision_inventory_but_is_not_loaded(self):
        data = self.request("single_air_destination")
        self.assertIn("D1", data["deck_occupants"])
        text = compile_protocol(OpentronsCompileRequest(**data))
        self.assertNotIn("pipette_left = protocol.load_instrument", text)
        data["rows"][0].update(move_plate=True, move_labware_alias="dest1", move_to_slot="D1")
        with self.assertRaisesRegex(ValueError, "already occupied"):
            compile_protocol(OpentronsCompileRequest(**data))

    def test_nonfinite_numbers_are_rejected_at_service_boundary(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                required_positive_float(value, "Volume")
            with self.subTest(value=value), self.assertRaises(ValueError):
                optional_nonnegative_float(value, "Delay")


class TecanWorklistServiceTests(unittest.TestCase):
    def block(self):
        return TransferBlock(
            source_labware="Vial8Rack_1", source_well=1, source_volume=150,
            dest_labware="DeepPlate1", dest_wells_expr="A1,A2", dest_volume=50,
            chemical_name="BB-1", liquid_class="LC", disp_different_vol=True,
            dispense_groups=[DispenseGroup(volume=25, wells_expr="B1,B2")],
        )

    def test_command_order_group_volumes_wash_and_aliases(self):
        block = self.block()
        before = deepcopy(block)
        lines = build_gwl_lines([block], "96-well horizontal", labware_aliases={
            "Vial8Rack_1": "Stock rack", "DeepPlate1": "Reaction plate",
        })
        self.assertEqual([
            "A;Stock rack;;;1;;150.0;LC;;;",
            "D;Reaction plate;;;1;;50.0;LC;;;",
            "D;Reaction plate;;;9;;50.0;LC;;;",
            "D;Reaction plate;;;2;;25.0;LC;;;",
            "D;Reaction plate;;;10;;25.0;LC;;;",
            "W;",
        ], lines)
        self.assertEqual(before, block)

    def test_maps_accumulate_all_blocks_without_losing_chemical_order(self):
        blocks = [self.block(), self.block()]
        blocks[1].chemical_name = "CATALYST"
        self.assertEqual({well: ["BB-1", "CATALYST"] for well in ("A1", "A2", "B1", "B2")},
                         build_chemical_map(blocks, "96-well horizontal"))
        self.assertEqual({"A1": 100, "A2": 100, "B1": 50, "B2": 50},
                         build_volume_map(blocks, "96-well horizontal"))

    def test_volume_overflow_precision_and_inventory_conflicts_are_preserved(self):
        block = self.block()
        block.source_volume = 149
        with self.assertRaisesRegex(ValueError, "exceeds aspirate volume"):
            build_gwl_lines([block], "96-well horizontal")
        block = self.block()
        block.dest_volume = 0.01
        with self.assertRaisesRegex(ValueError, "rounds to zero"):
            build_gwl_lines([block], "96-well horizontal")
        with self.assertRaisesRegex(ValueError, "Block 1: occupied"):
            build_gwl_lines([self.block()], "96-well horizontal", source_conflicts={1: "occupied"})

    def test_vertical_and_horizontal_mapping_round_trip(self):
        for mode in ("96-well horizontal", "96-well vertical", "HPLC vials horizontal", "HPLC vials vertical"):
            with self.subTest(mode=mode):
                wells = parse_dest_well_expr("A1,B2,A1", mode, "DeepPlate1")
                self.assertEqual(["A1", "B2"], [index_to_dest_label(well, mode, "DeepPlate1") for well in wells])

    def test_checkbox_compatibility_for_legacy_project_values(self):
        for value in (True, 1, 1.5, "TRUE", "yes", "checked", "On"):
            with self.subTest(value=value):
                self.assertTrue(coerce_bool(value))
        for value in (False, 0, "false", "0", "", None):
            with self.subTest(value=value):
                self.assertFalse(coerce_bool(value))


if __name__ == "__main__":
    unittest.main()
