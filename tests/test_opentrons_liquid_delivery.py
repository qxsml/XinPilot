"""Exercise emitted liquid-handling commands, including air vs liquid accounting.

This is not a robot or fluid-dynamics simulation. It catches displaced air being
counted as delivered liquid, residual-liquid routing and settings round trips.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opentrons_frame import OpentronsFrame, OpentronsTransferRow


class Well:
    def __init__(self, alias, name):
        self.key = (alias, name)

    def top(self, z=0):
        return (self.key, "top", z)

    def bottom(self, z=0):
        return (self.key, "bottom", z)


class VolumeTrackingPipette:
    def __init__(self):
        self.flow_rate = SimpleNamespace(aspirate=100, dispense=100)
        self.segments = []
        self.delivered = defaultdict(float)
        self.events = []

    def aspirate(self, volume, location):
        self.segments.append(["liquid", volume])
        self.events.append(("aspirate", volume, location))

    def air_gap(self, volume, height):
        self.segments.append(["air", volume])
        self.events.append(("air_gap", volume, height))

    def dispense(self, volume, location):
        remaining, liquid = volume, 0.0
        while remaining > 1e-8:
            if not self.segments:
                raise AssertionError("Generated protocol dispensed more than was aspirated")
            kind, available = self.segments[-1]
            amount = min(available, remaining)
            if kind == "liquid":
                liquid += amount
            remaining -= amount
            self.segments[-1][1] -= amount
            if self.segments[-1][1] < 1e-8:
                self.segments.pop()
        self.delivered[location[0]] += liquid
        self.events.append(("dispense", volume, location, liquid))

    def blow_out(self, location):
        liquid = sum(volume for kind, volume in self.segments if kind == "liquid")
        self.delivered[location[0]] += liquid
        self.segments.clear()
        self.events.append(("blow_out", liquid, location))


def execute_liquid_commands(script):
    """Run the actual generated loop/helpers; substitute only robot infrastructure."""
    parsed = ast.parse(script)
    assignments = {node.targets[0].id: ast.literal_eval(node.value)
                   for node in parsed.body if isinstance(node, ast.Assign)
                   and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id in {"TRANSFER_ROWS", "LABWARE_CONFIGS"}}
    rows = assignments["TRANSFER_ROWS"]
    pipette = VolumeTrackingPipette()
    labware = {}
    for config in assignments["LABWARE_CONFIGS"]:
        alias = config["alias"]
        labware[alias] = {f"{letter}{column}": Well(alias, f"{letter}{column}")
                          for letter in "ABCDEFGHIJKLMNOP" for column in range(1, 25)}
    run = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == "run")
    ignored = {"ensure_tip_for_row", "finish_tip_for_row", "ensure_nozzle_layout"}
    helpers = [node for node in run.body if isinstance(node, ast.FunctionDef) and node.name not in ignored]
    loop = next(node for node in run.body if isinstance(node, ast.For)
                and "enumerate(TRANSFER_ROWS" in ast.unparse(node.iter))
    noop = lambda *args, **kwargs: None
    namespace = {
        **assignments, "labware": labware, "pipettes": {row["pipette_key"]: pipette for row in rows},
        "default_flow_rates": {row["pipette_key"]: {"aspirate": 100, "dispense": 100} for row in rows},
        "protocol": SimpleNamespace(comment=noop, delay=noop),
        **{name: noop for name in ignored},
    }
    exec(compile(ast.Module(body=helpers + [loop], type_ignores=[]), "<generated-liquid-commands>", "exec"), namespace)
    return pipette, rows


class OpentronsLiquidDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk is unavailable: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.frame = OpentronsFrame(self.root)
        self.root.update()

    def tearDown(self):
        self.frame.destroy()

    @staticmethod
    def row(**changes):
        row = OpentronsFrame._transfer_row_dict(OpentronsTransferRow(
            chemical="REAGENT", source_well="A1", dest_wells="A1,A2", volume_ul=100,
            strategy="Multi-dispense", delay_air_gap_enabled=True, air_gap_enabled=True,
            air_gap_volume_ul="20", dispense_depth_mm="2", dispense_depth_reference="from bottom",
        ))
        row.update(changes)
        return row

    def script(self, **changes):
        self.frame.rows = [self.row(**changes)]
        return self.frame._build_script_text()

    def add_waste(self):
        self.frame.labware_configs.append({
            "alias": "waste", "role": "destination", "load_name": "nest_12_reservoir_15ml",
            "slot": "B1", "map_style": "12 well reservoir",
        })

    def test_multi_dispense_air_gap_is_removed_before_first_liquid_delivery(self):
        pipette, _ = execute_liquid_commands(self.script())
        self.assertEqual(100, pipette.delivered[("dest1", "A1")])
        self.assertEqual(100, pipette.delivered[("dest1", "A2")])
        dispenses = [event for event in pipette.events if event[0] == "dispense"]
        self.assertEqual(("dispense", 20, (("dest1", "A1"), "top", 0), 0), dispenses[0])
        self.assertEqual("bottom", dispenses[1][2][1])
        self.assertFalse(any(event[0] == "blow_out" for event in pipette.events))
        self.assertEqual([], pipette.segments)

    def test_single_transfers_release_air_before_liquid_and_blow_out_each_destination(self):
        pipette, _ = execute_liquid_commands(self.script(strategy="Single transfer", blowout_location="Destination"))
        self.assertEqual(100, pipette.delivered[("dest1", "A1")])
        self.assertEqual(100, pipette.delivered[("dest1", "A2")])
        self.assertEqual(["aspirate", "air_gap", "dispense", "dispense", "blow_out"] * 2,
                         [event[0] for event in pipette.events])
        self.assertEqual([("dest1", "A1"), ("dest1", "A2")],
                         [event[2][0] for event in pipette.events if event[0] == "blow_out"])

    def test_multiple_batches_send_only_extra_liquid_to_waste(self):
        self.add_waste()
        pipette, rows = execute_liquid_commands(self.script(
            dest_wells=",".join(f"A{i}" for i in range(1, 10)), multi_dispense_extra_percent="10",
            blowout_location="Liquid waste", blowout_labware_alias="waste", blowout_well="A1"))
        self.assertLess(rows[0]["batch_size"], 9)
        for column in range(1, 10):
            self.assertEqual(100, pipette.delivered[("dest1", f"A{column}")])
        self.assertEqual(90, pipette.delivered[("waste", "A1")])
        self.assertEqual(0, pipette.delivered[("source1", "A1")])
        self.assertEqual([], pipette.segments)

    def test_explicit_source_blowout_returns_only_extra_liquid(self):
        pipette, _ = execute_liquid_commands(self.script(multi_dispense_extra_percent="10", blowout_location="Source"))
        self.assertEqual(100, pipette.delivered[("dest1", "A1")])
        self.assertEqual(100, pipette.delivered[("dest1", "A2")])
        self.assertEqual(20, pipette.delivered[("source1", "A1")])

    def test_extra_liquid_requires_source_or_waste(self):
        for location in ("No blowout", "Destination", ""):
            with self.subTest(location=location), self.assertRaisesRegex(ValueError, "Choose Source or Liquid waste"):
                self.script(multi_dispense_extra_percent="10", blowout_location=location)

    def test_liquid_waste_rejects_missing_or_reaction_labware_and_bad_well(self):
        self.add_waste()
        for alias, well in (("missing", "A1"), ("dest1", "A12"), ("source1", "A1"),
                            ("waste", "B1"), ("waste", ""), ("waste", "A1,A2")):
            with self.subTest(alias=alias, well=well), self.assertRaises(ValueError):
                self.script(blowout_location="Liquid waste", blowout_labware_alias=alias, blowout_well=well)

    def test_unknown_blowout_choice_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, "invalid blowout"):
            self.script(blowout_location="typo")

    def test_legacy_rows_default_to_no_blowout(self):
        row = self.row(air_gap_enabled=False)
        for key in ("blowout_location", "blowout_labware_alias", "blowout_well"):
            row.pop(key)
        state = self.frame.export_state()
        state["rows"] = [row]
        self.frame.import_state(state)
        pipette, rows = execute_liquid_commands(self.frame._build_script_text())
        self.assertEqual("No blowout", rows[0]["blowout_location"])
        self.assertFalse(any(event[0] == "blow_out" for event in pipette.events))

    def test_blowout_settings_survive_copy_paste_and_project_round_trip(self):
        self.add_waste()
        self.frame.blowout_location_var.set("Liquid waste")
        self.frame.blowout_labware_alias_var.set("waste")
        self.frame.blowout_well_var.set("A1")
        self.frame.rows = [self.row(blowout_location="Liquid waste", blowout_labware_alias="waste", blowout_well="A1")]
        params = self.frame._liquid_parameters_from_form()
        self.frame.blowout_location_var.set("Source")
        self.frame._apply_liquid_parameters(params)
        self.assertEqual("Liquid waste", self.frame.blowout_location_var.get())
        state = self.frame.export_state()
        other = OpentronsFrame(self.root)
        try:
            other.import_state(state)
            self.assertEqual("Liquid waste", other.blowout_location_var.get())
            self.assertEqual("waste", other.rows[0]["blowout_labware_alias"])
            pipette, rows = execute_liquid_commands(other._build_script_text())
            self.assertEqual("A1", rows[0]["blowout_well"])
            self.assertEqual(("waste", "A1"), next(event[2][0] for event in pipette.events if event[0] == "blow_out"))
        finally:
            other.destroy()

    def test_waste_slot_participates_in_single_nozzle_reach_check(self):
        args = dict(row_number=1, source_alias="source1", dest_alias="dest1", pipette_key="right",
                    pipettes={"right": {"tiprack_slots": ["B2"]}}, module_configs_by_key={},
                    labware_locations={"source1": ("deck", "B1"), "dest1": ("deck", "C2"), "waste": ("deck", "A1")})
        self.assertEqual("A1", self.frame._single_nozzle_start_for_row(**args, waste_alias="waste"))
        args["labware_locations"]["dest1"] = ("deck", "D1")
        with self.assertRaisesRegex(ValueError, "both deck rows A and D"):
            self.frame._single_nozzle_start_for_row(**args, waste_alias="waste")


if __name__ == "__main__":
    unittest.main()
