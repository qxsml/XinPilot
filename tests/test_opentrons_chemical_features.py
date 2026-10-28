from __future__ import annotations

import ast
import inspect
import sys
import tkinter as tk
import unittest
from copy import deepcopy
from pathlib import Path
from tkinter import ttk
from types import MethodType, SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from opentrons_frame import OpentronsFrame, OpentronsTransferRow  # noqa: E402
from xinpilot.application.opentrons_protocol import compile_protocol  # noqa: E402


class OpentronsChemicalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(OpentronsFrame)
        self.frame.rows = [
            {
                "chemical": "CHEM-1",
                "source_labware_alias": "source1",
                "source_well": "A1",
            },
            {
                "chemical": "CHEM-1",
                "source_labware_alias": "source1",
                "source_well": "A2",
                "batch_transfer_kind": "8-channel",
                "batch_source_wells": "A2,B2,C2,D2,E2,F2,G2,H2",
            },
            {
                "chemical": "CHEM-2",
                "source_labware_alias": "source1",
                "source_well": "A3",
            },
        ]

    def test_source_wells_are_reusable_only_for_the_same_chemical(self):
        blocked, reusable = self.frame._source_well_availability("source1", "CHEM-1")
        self.assertEqual({"A1", "A2", "B2", "C2", "D2", "E2", "F2", "G2", "H2"}, reusable)
        self.assertEqual({"A3"}, blocked)

    def test_source_conflict_reports_different_chemical(self):
        self.assertEqual("", self.frame._source_well_conflict("source1", "A1", "CHEM-1"))
        self.assertIn(
            "another Chemical ID",
            self.frame._source_well_conflict("source1", "A1", "CHEM-2"),
        )

    def test_remembered_source_chemicals_are_alias_scoped_and_unambiguous(self):
        self.frame.rows.extend([
            {
                "chemical": "CHEM-1",
                "source_labware_alias": "source1",
                "source_well": "A4",
            },
            {
                "chemical": "CHEM-2",
                "source_labware_alias": "source1",
                "source_well": "A4",
            },
            {
                "chemical": "OTHER-LABWARE",
                "source_labware_alias": "source2",
                "source_well": "A1",
            },
        ])

        assignments = self.frame._source_well_chemical_assignments("source1")

        self.assertEqual("CHEM-1", assignments["A1"])
        self.assertEqual("CHEM-1", assignments["A2"])
        self.assertEqual("CHEM-2", assignments["A3"])
        self.assertNotIn("A4", assignments)

    def test_row_serialization_keeps_chemical_and_new_liquid_features(self):
        transfer = OpentronsTransferRow(
            source_well="A1",
            dest_wells="B1",
            volume_ul=10.0,
            strategy="Single transfer",
            chemical="CHEM-1",
            reaction_umol="2.5",
            is_building_block=True,
            mix_enabled=True,
            mix_volume_ul="8",
            post_source_mix_delay_seconds="2.5",
            delay_air_gap_enabled=True,
            post_aspirate_delay_seconds="2",
            air_gap_enabled=True,
            air_gap_volume_ul="1",
        )
        row = OpentronsFrame._transfer_row_dict(transfer)
        self.assertEqual("CHEM-1", row["chemical"])
        self.assertEqual("2.5", row["reaction_umol"])
        self.assertTrue(row["is_building_block"])
        self.assertTrue(row["mix_enabled"])
        self.assertEqual("2.5", row["post_source_mix_delay_seconds"])
        self.assertTrue(row["delay_air_gap_enabled"])
        self.assertEqual("1", row["air_gap_volume_ul"])

    def test_import_and_protocol_generation_do_not_strip_chemical_ids(self):
        import_source = inspect.getsource(OpentronsFrame.import_state)
        build_source = inspect.getsource(compile_protocol)
        self.assertNotIn('row.pop("chemical"', import_source)
        self.assertIn('row["chemical"]', import_source)
        self.assertIn('"chemical": chemical', build_source)
        self.assertIn("row.get('chemical')", build_source)


class OpentronsLiquidFeatureValidationTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(OpentronsFrame)

    def test_mixing_and_air_gap_validation(self):
        mix = self.frame._validated_mix_settings(
            enabled=True,
            strategy="Single transfer",
            timing="Before and after",
            repetitions="3",
            volume="8",
            post_source_mix_delay="2.5",
            aspirate_rate="20",
            dispense_rate="25",
            aspirate_depth="1",
            aspirate_reference="from bottom",
            dispense_depth="2",
            dispense_reference="from bottom",
        )
        air = self.frame._validated_delay_air_gap_settings(
            post_aspirate_delay="2",
            post_dispense_delay="3",
            pre_move_delay="4",
            air_gap_enabled=True,
            air_gap_volume="1",
            air_gap_height="5",
            air_gap_flow_rate="10",
        )
        self.assertEqual(3, mix["mix_repetitions"])
        self.assertEqual(8.0, mix["mix_volume_ul"])
        self.assertEqual(2.5, mix["post_source_mix_delay_seconds"])
        self.assertEqual(1.0, air["air_gap_volume_ul"])
        self.assertEqual(4.0, air["pre_move_delay_seconds"])

    def test_source_mix_delay_rejects_negative_seconds(self):
        with self.assertRaisesRegex(ValueError, "delay after source mixing must be zero or greater"):
            self.frame._validated_mix_settings(
                enabled=True,
                strategy="Single transfer",
                timing="Before aspirating",
                repetitions="3",
                volume="8",
                post_source_mix_delay="-0.1",
                aspirate_rate="",
                dispense_rate="",
                aspirate_depth="",
                aspirate_reference="from bottom",
                dispense_depth="",
                dispense_reference="from bottom",
            )

    def test_multi_dispense_accepts_destination_mixing_after_warning_layer(self):
        mix = self.frame._validated_mix_settings(
            enabled=True,
            strategy="Multi-dispense",
            timing="Before and after",
            repetitions="3",
            volume="8",
            aspirate_rate="",
            dispense_rate="",
            aspirate_depth="",
            aspirate_reference="from bottom",
            dispense_depth="",
            dispense_reference="from bottom",
        )
        self.assertTrue(mix["mix_enabled"])
        self.assertEqual("Before and after", mix["mix_timing"])
        self.assertTrue(
            self.frame._uses_multi_dispense_destination_mixing(
                strategy="Multi-dispense",
                timing="Before and after",
                enabled=True,
            )
        )

    def test_compound_notes_concentration_field_restores_auto_volume_math(self):
        self.assertEqual(0.5, self.frame._record_concentration_m({"Conc.": "0.5"}))
        self.assertEqual("5", self.frame._volume_from_umol_and_conc("2.5", 0.5))


class OpentronsLogicalBatchTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(OpentronsFrame)

    def test_individual_batch_expands_per_source_umol_and_direct_ul(self):
        self.frame.compound_provider = lambda: [
            SimpleNamespace(values={"ID": "CHEM-1", "Conc.": "0.5"}),
            SimpleNamespace(values={"ID": "CHEM-2", "Conc.": "0.25"}),
        ]
        self.frame.rows = [{
            "batch_transfer_kind": "individual",
            "batch_transfer_version": 4,
            "batch_source_wells": "A1,B1",
            "batch_source_chemicals": {"A1": "CHEM-1", "B1": "CHEM-2"},
            "batch_source_building_blocks": {"A1": True, "B1": True},
            "batch_source_volume_modes": {"A1": "umol", "B1": "ul"},
            "batch_source_umol": {"A1": "2.5", "B1": ""},
            "batch_source_volumes_ul": {"A1": "5", "B1": "6"},
            "batch_destination_sets": [["A2", "B2"]],
            "source_well": "A1",
            "dest_wells": "A2,B2",
            "volume_ul": 5.0,
        }]

        rows = self.frame._expanded_protocol_rows()

        self.assertEqual([5.0, 6.0], [row["volume_ul"] for row in rows])
        self.assertEqual(["2.5", "1.5"], [row["reaction_umol"] for row in rows])

    def test_explicit_eight_channel_source_volumes_must_match(self):
        sources = [f"{row}1" for row in "ABCDEFGH"]
        destinations = [f"{row}2" for row in "ABCDEFGH"]
        volumes = {source: "10" for source in sources}
        volumes["H1"] = "11"
        row = {
            "batch_transfer_kind": "8-channel",
            "batch_transfer_version": 4,
            "batch_source_wells": ",".join(sources),
            "batch_source_chemicals": {source: "" for source in sources},
            "batch_source_building_blocks": {source: False for source in sources},
            "batch_source_volume_modes": {source: "ul" for source in sources},
            "batch_source_umol": {source: "" for source in sources},
            "batch_source_volumes_ul": volumes,
            "batch_destination_sets": [destinations],
            "source_well": "A1",
            "dest_wells": ",".join(destinations),
            "volume_ul": 10.0,
        }
        self.frame.rows = [row]

        with self.assertRaisesRegex(ValueError, "same final dispense volume"):
            self.frame._expanded_protocol_rows()
        self.assertIn("same final dispense volume", self.frame._incomplete_row_reason(row))

    def test_individual_batch_expands_with_one_common_volume(self):
        self.frame.rows = [{
            "batch_transfer_kind": "individual",
            "batch_source_wells": "A1,B1",
            "batch_source_chemicals": {"A1": "CHEM-1", "B1": "CHEM-2"},
            "batch_source_building_blocks": {"A1": True, "B1": False},
            "batch_destination_sets": [["A2", "B2"], ["A3", "B3"]],
            "source_well": "A1",
            "dest_wells": "A2,B2,A3,B3",
            "volume_ul": 20.0,
            "step_name": "Batch",
            "move_plate": True,
        }]
        rows = self.frame._expanded_protocol_rows()
        self.assertEqual(2, len(rows))
        self.assertEqual([20.0, 20.0], [row["volume_ul"] for row in rows])
        self.assertEqual(["CHEM-1", "CHEM-2"], [row["chemical"] for row in rows])
        self.assertEqual([True, False], [row["is_building_block"] for row in rows])
        self.assertEqual(["A2,A3", "B2,B3"], [row["dest_wells"] for row in rows])
        self.assertEqual([False, True], [row["move_plate"] for row in rows])

    def test_individual_batch_expands_more_than_eight_sources(self):
        sources = [f"{row}1" for row in "ABCDEFGH"] + [f"{row}2" for row in "ABCD"]
        first_destinations = [f"{row}3" for row in "ABCDEFGH"] + [f"{row}4" for row in "ABCD"]
        second_destinations = [f"{row}5" for row in "ABCDEFGH"] + [f"{row}6" for row in "ABCD"]
        self.frame.rows = [{
            "batch_transfer_kind": "individual",
            "batch_source_wells": ",".join(sources),
            "batch_source_chemicals": {
                source: f"CHEM-{index + 1}" for index, source in enumerate(sources)
            },
            "batch_source_building_blocks": {source: False for source in sources},
            "batch_destination_sets": [first_destinations, second_destinations],
            "source_well": sources[0],
            "dest_wells": ",".join(first_destinations + second_destinations),
            "volume_ul": 20.0,
        }]

        rows = self.frame._expanded_protocol_rows()

        self.assertEqual(12, len(rows))
        self.assertEqual(sources, [row["source_well"] for row in rows])
        self.assertEqual(
            [f"{first},{second}" for first, second in zip(first_destinations, second_destinations)],
            [row["dest_wells"] for row in rows],
        )

    def test_eight_channel_batch_keeps_per_well_chemical_metadata(self):
        sources = [f"{row}1" for row in "ABCDEFGH"]
        destinations = [f"{row}2" for row in "ABCDEFGH"]
        chemical_map = {source: f"CHEM-{index + 1}" for index, source in enumerate(sources)}
        self.frame.rows = [{
            "batch_transfer_kind": "8-channel",
            "batch_source_wells": ",".join(sources),
            "batch_source_chemicals": chemical_map,
            "batch_source_building_blocks": {source: index % 2 == 0 for index, source in enumerate(sources)},
            "batch_destination_sets": [destinations],
            "source_well": "A1",
            "dest_wells": ",".join(destinations),
            "volume_ul": 15.0,
        }]
        rows = self.frame._expanded_protocol_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(15.0, rows[0]["volume_ul"])
        self.assertEqual(chemical_map, rows[0]["batch_source_chemicals"])
        self.assertTrue(rows[0]["batch_source_building_blocks"]["A1"])
        self.assertFalse(rows[0]["batch_source_building_blocks"]["B1"])

    @staticmethod
    def _sequence_row(sequence_id, name, order, source, destinations, **updates):
        row = {
            "sequence_id": sequence_id,
            "sequence_name": name,
            "sequence_order": order,
            "sequence_version": 1,
            "source_well": source,
            "dest_wells": ",".join(destinations),
            "strategy": "Single transfer",
            "tip_policy": "Keep tip mounted" if order == 1 else "Bin tip after row",
            "move_plate": False,
        }
        row.update(updates)
        return row

    def test_sequence_interleaves_children_sample_major(self):
        self.frame.rows = [
            self._sequence_row("seq-1", "Extraction", 1, "A1", ["B1", "B2", "B3"]),
            self._sequence_row("seq-1", "Extraction", 2, "C1", ["D1", "D2", "D3"]),
            {"source_well": "E1", "dest_wells": "F1,F2"},
        ]

        rows = self.frame._expanded_protocol_rows()

        self.assertEqual(
            [("A1", "B1"), ("C1", "D1"), ("A1", "B2"), ("C1", "D2"), ("A1", "B3"), ("C1", "D3")],
            [(row["source_well"], row["dest_wells"]) for row in rows[:6]],
        )
        self.assertEqual("F1,F2", rows[6]["dest_wells"])
        self.assertEqual([1, 1, 2, 2, 3, 3], [row["sequence_sample_index"] for row in rows[:6]])
        self.assertEqual([1, 2, 1, 2, 1, 2], [row["sequence_child_index"] for row in rows[:6]])

    def test_sequence_requires_equal_sample_counts(self):
        self.frame.rows = [
            self._sequence_row("seq-1", "Extraction", 1, "A1", ["B1", "B2"]),
            self._sequence_row("seq-1", "Extraction", 2, "C1", ["D1"]),
        ]

        with self.assertRaisesRegex(ValueError, "same number of sample positions.*Group 1=2, Group 2=1"):
            self.frame._expanded_protocol_rows()

    def test_sequence_groups_allow_one_twenty_well_row_and_five_four_well_rows(self):
        sequence_id = "partitioned-sequence"
        all_destinations = [f"{row}{column}" for column in range(1, 4) for row in "ABCDEFGH"][:20]
        common = self._sequence_row(
            sequence_id, "Extraction", 1, "A10", all_destinations,
            sequence_group_id="common-group", sequence_group_name="Common", sequence_group_order=1,
            sequence_row_order=1,
        )
        partitioned = []
        for row_index in range(5):
            partitioned.append(self._sequence_row(
                sequence_id,
                "Extraction",
                row_index + 2,
                f"{chr(ord('B') + row_index)}10",
                all_destinations[row_index * 4:(row_index + 1) * 4],
                sequence_group_id="partition-group",
                sequence_group_name="Partitioned",
                sequence_group_order=2,
                sequence_row_order=row_index + 1,
            ))
        self.frame.rows = [common, *partitioned]

        rows = self.frame._expanded_protocol_rows()

        self.assertEqual(40, len(rows))
        self.assertEqual(
            [("A10", all_destinations[0]), ("B10", all_destinations[0])],
            [(rows[0]["source_well"], rows[0]["dest_wells"]), (rows[1]["source_well"], rows[1]["dest_wells"])],
        )
        self.assertEqual("C10", rows[9]["source_well"])
        self.assertEqual(all_destinations[4], rows[9]["dest_wells"])
        self.assertEqual([1, 2], [rows[0]["sequence_group_index"], rows[1]["sequence_group_index"]])
        self.assertEqual(2, rows[9]["sequence_group_member_index"])

    def test_sequence_individual_batch_positions_follow_mapping_order(self):
        common = {
            "batch_transfer_kind": "individual",
            "batch_source_wells": "A1,B1",
            "batch_source_chemicals": {"A1": "ONE", "B1": "TWO"},
            "batch_source_building_blocks": {"A1": False, "B1": True},
            "batch_destination_sets": [["A2", "B2"], ["A3", "B3"]],
        }
        self.frame.rows = [
            self._sequence_row("seq-1", "Batch extraction", 1, "A1", ["A2", "B2", "A3", "B3"], **common),
            self._sequence_row(
                "seq-1",
                "Batch extraction",
                2,
                "C1",
                ["C2", "D2", "C3", "D3"],
                **{
                    **common,
                    "batch_source_wells": "C1,D1",
                    "batch_source_chemicals": {"C1": "THREE", "D1": "FOUR"},
                    "batch_source_building_blocks": {"C1": False, "D1": False},
                    "batch_destination_sets": [["C2", "D2"], ["C3", "D3"]],
                },
            ),
        ]

        rows = self.frame._expanded_protocol_rows()

        self.assertEqual(
            [
                ("A1", "A2"), ("C1", "C2"),
                ("B1", "B2"), ("D1", "D2"),
                ("A1", "A3"), ("C1", "C3"),
                ("B1", "B3"), ("D1", "D3"),
            ],
            [(row["source_well"], row["dest_wells"]) for row in rows],
        )

    def test_sequence_cannot_mix_eight_channel_and_single_nozzle_children(self):
        sources = [f"{row}1" for row in "ABCDEFGH"]
        destinations = [f"{row}2" for row in "ABCDEFGH"]
        eight_channel = self._sequence_row(
            "seq-1",
            "Mixed",
            1,
            "A1",
            destinations,
            batch_transfer_kind="8-channel",
            batch_source_wells=",".join(sources),
            batch_source_chemicals={source: "" for source in sources},
            batch_source_building_blocks={source: False for source in sources},
            batch_destination_sets=[destinations],
        )
        single = self._sequence_row("seq-1", "Mixed", 2, "A3", ["B3"])
        self.frame.rows = [eight_channel, single]

        with self.assertRaisesRegex(ValueError, "cannot mix 8-channel child rows"):
            self.frame._expanded_protocol_rows()

    def test_eight_channel_sequence_interleaves_destination_columns(self):
        sources_one = [f"{row}1" for row in "ABCDEFGH"]
        sources_two = [f"{row}4" for row in "ABCDEFGH"]
        child_one_destinations = [
            [f"{row}2" for row in "ABCDEFGH"],
            [f"{row}3" for row in "ABCDEFGH"],
        ]
        child_two_destinations = [
            [f"{row}5" for row in "ABCDEFGH"],
            [f"{row}6" for row in "ABCDEFGH"],
        ]
        self.frame.rows = [
            self._sequence_row(
                "seq-1", "Columns", 1, "A1", child_one_destinations[0] + child_one_destinations[1],
                batch_transfer_kind="8-channel",
                batch_source_wells=",".join(sources_one),
                batch_source_chemicals={source: "" for source in sources_one},
                batch_source_building_blocks={source: False for source in sources_one},
                batch_destination_sets=child_one_destinations,
            ),
            self._sequence_row(
                "seq-1", "Columns", 2, "A4", child_two_destinations[0] + child_two_destinations[1],
                batch_transfer_kind="8-channel",
                batch_source_wells=",".join(sources_two),
                batch_source_chemicals={source: "" for source in sources_two},
                batch_source_building_blocks={source: False for source in sources_two},
                batch_destination_sets=child_two_destinations,
            ),
        ]

        rows = self.frame._expanded_protocol_rows()

        self.assertEqual(4, len(rows))
        self.assertEqual(
            ["A2", "A5", "A3", "A6"],
            [row["batch_destination_sets"][0][0] for row in rows],
        )
        self.assertTrue(all(row["batch_transfer_kind"] == "8-channel" for row in rows))

    def test_sequence_keep_tip_requires_same_resolved_pipette_and_nozzle(self):
        rows = [
            {
                "sequence_id": "seq-1", "sequence_name": "Extraction",
                "sequence_sample_index": 1, "sequence_child_index": 1,
                "tip_policy": "Keep tip mounted", "pipette_key": "left",
                "pipette_name": "flex_1channel_50", "nozzle_layout": "single", "nozzle_start": "",
            },
            {
                "sequence_id": "seq-1", "sequence_name": "Extraction",
                "sequence_sample_index": 1, "sequence_child_index": 2,
                "tip_policy": "Bin tip after row", "pipette_key": "right",
                "pipette_name": "flex_1channel_1000", "nozzle_layout": "single", "nozzle_start": "",
            },
        ]

        with self.assertRaisesRegex(ValueError, "different physical pipette or nozzle layout"):
            self.frame._validate_sequence_tip_transitions(rows)

    def test_sequence_final_keep_tip_produces_warning(self):
        self.frame.rows = [
            self._sequence_row("seq-1", "Extraction", 1, "A1", ["B1"]),
            self._sequence_row(
                "seq-1", "Extraction", 2, "C1", ["D1"], tip_policy="Keep tip mounted"
            ),
        ]

        warnings = self.frame._sequence_tip_warnings()

        self.assertEqual(1, len(warnings))
        self.assertIn("carry into the next sample", warnings[0])


class OpentronsBatchGuiIntegrationTests(unittest.TestCase):
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
        provider = lambda: [SimpleNamespace(values={"ID": "CHEM-1", "Name": "One", "Conc.": "0.5"})]
        self.frame = OpentronsFrame(self.root, compound_provider=provider)
        self.root.update()

    def tearDown(self):
        self.frame.destroy()

    @staticmethod
    def _protocol_row(volume_ul, *, pipette_key="Auto", **updates):
        row = {
            "chemical": "CHEM-1",
            "source_labware_alias": "source1",
            "dest_labware_alias": "dest1",
            "source_well": "A1",
            "dest_wells": "A2",
            "volume_ul": volume_ul,
            "strategy": "Single transfer",
            "pipette_key": pipette_key,
        }
        row.update(updates)
        return row

    def test_single_auto_volume_and_batch_volume_independence(self):
        self.frame.chemical_var.set("CHEM-1")
        self.frame.reaction_umol_var.set("2.5")
        self.root.update()
        self.assertEqual("5", self.frame.volume_var.get())
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("17")
        self.frame.reaction_umol_var.set("3")
        self.root.update()
        self.assertEqual("17", self.frame.volume_var.get())
        self.assertEqual("disabled", str(self.frame.chemical_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.reaction_umol_entry.cget("state")))

    def test_individual_source_selector_has_no_eight_well_cap(self):
        captured = []
        selected_by_call = [
            "A1,B1,C1,D1,E1,F1,G1,H1,A2",
            "A1,B1,C1,D1,E1,F1,G1,H1",
        ]

        class FakeWellMapDialog:
            def __init__(_dialog, *_args, **kwargs):
                captured.append(kwargs)
                _dialog.back_requested = False
                _dialog.result_labels = selected_by_call[len(captured) - 1]

            def title(_dialog, _title):
                return None

        with patch("opentrons_frame.well_map.WellMapDialog", FakeWellMapDialog):
            with patch.object(self.frame, "wait_window"):
                individual_action, individual_sources = self.frame._batch_source_step(
                    "individual", "source1", [], exclude_row_index=None
                )
                channel_action, channel_sources = self.frame._batch_source_step(
                    "8-channel", "source1", [], exclude_row_index=None
                )

        self.assertEqual("next", individual_action)
        self.assertEqual(9, len(individual_sources))
        self.assertIsNone(captured[0]["selection_limit"])
        self.assertIsNone(captured[0]["required_count"])
        self.assertNotIn("1 to 8", captured[0]["instruction"])
        self.assertEqual("next", channel_action)
        self.assertEqual(8, len(channel_sources))
        self.assertEqual(8, captured[1]["selection_limit"])
        self.assertEqual(8, captured[1]["required_count"])

    def test_reused_single_source_well_restores_its_chemical_id(self):
        self.frame.rows = [{
            "chemical": "CHEM-1",
            "source_labware_alias": "source1",
            "source_well": "A1",
            "dest_labware_alias": "dest1",
            "dest_wells": "A2",
            "volume_ul": 10.0,
        }]
        self.frame.chemical_var.set("")
        captured = {}

        class FakeWellMapDialog:
            def __init__(_dialog, *_args, **kwargs):
                captured.update(kwargs)
                _dialog.result_labels = "A1"

            def title(_dialog, _title):
                return None

        with patch("opentrons_frame.well_map.WellMapDialog", FakeWellMapDialog):
            with patch.object(self.frame, "wait_window"):
                self.frame._pick_source_well()

        self.assertEqual("A1", self.frame.source_well_var.get())
        self.assertEqual("CHEM-1", self.frame.chemical_var.get())
        self.assertIn("A1", captured["highlight_labels"])
        self.assertNotIn("A1", captured["disabled_labels"])

    def test_reused_source_does_not_overwrite_a_different_explicit_chemical_id(self):
        self.frame.rows = [{
            "chemical": "CHEM-1",
            "source_labware_alias": "source1",
            "source_well": "A1",
        }]
        self.frame.chemical_var.set("CHEM-2")
        captured = {}

        class FakeWellMapDialog:
            def __init__(_dialog, *_args, **kwargs):
                captured.update(kwargs)
                _dialog.result_labels = ""

            def title(_dialog, _title):
                return None

        with patch("opentrons_frame.well_map.WellMapDialog", FakeWellMapDialog):
            with patch.object(self.frame, "wait_window"):
                self.frame._pick_source_well()

        self.assertEqual("CHEM-2", self.frame.chemical_var.get())
        self.assertIn("A1", captured["disabled_labels"])

    def test_new_batch_prefills_chemical_ids_from_reused_source_wells(self):
        self.frame.rows = [{
            "chemical": "CHEM-1",
            "source_labware_alias": "source1",
            "source_well": "A1",
            "dest_labware_alias": "dest1",
            "dest_wells": "A2",
            "volume_ul": 10.0,
        }]
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        self.frame.strategy_var.set("Single transfer")
        observed = {}
        self.frame._batch_kind_step = MethodType(
            lambda _self, _initial: ("next", "individual"), self.frame
        )
        self.frame._batch_source_labware_step = MethodType(
            lambda _self, alias, has_existing_mapping=False: (
                observed.update(source_initial_alias=alias) or "next",
                "source1",
            ),
            self.frame,
        )
        self.frame._batch_source_step = MethodType(
            lambda _self, _kind, _alias, _sources, exclude_row_index=None: ("next", ["A1"]),
            self.frame,
        )

        def chemical_step(_self, sources, initial, initial_building_blocks):
            observed["initial"] = dict(initial)
            return "next", dict(initial), {source: False for source in sources}

        self.frame._batch_chemical_step = MethodType(chemical_step, self.frame)
        self.frame._batch_volume_step = MethodType(
            lambda _self, _kind, sources, _chemicals, _building_blocks, _modes, _umol, _volumes: (
                "next",
                {source: "ul" for source in sources},
                {source: "" for source in sources},
                {source: "25" for source in sources},
            ),
            self.frame,
        )
        self.frame._batch_destination_step = MethodType(
            lambda _self, _kind, _sources, alias, _sets, exclude_row_index=None: (
                observed.update(dest_initial_alias=alias) or "next", "dest1", [["A3"]]
            ),
            self.frame,
        )
        self.frame._batch_review_step = MethodType(
            lambda _self, *_args, **_kwargs: "save", self.frame
        )

        self.assertTrue(self.frame._open_batch_transfer())

        self.assertEqual("", observed["source_initial_alias"])
        self.assertEqual("", observed["dest_initial_alias"])
        self.assertEqual({"A1": "CHEM-1"}, observed["initial"])
        self.assertEqual("CHEM-1", self.frame.rows[1]["batch_source_chemicals"]["A1"])

    def test_large_batch_chemical_assignment_dialog_is_scrollable(self):
        sources = [f"{row}1" for row in "ABCDEFGH"] + [f"{row}2" for row in "ABCD"]
        observed = {}

        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        def inspect_and_close(win):
            win.update_idletasks()
            widgets = descendants(win)
            observed["resizable"] = tuple(bool(value) for value in win.resizable())
            observed["canvas_count"] = sum(isinstance(widget, tk.Canvas) for widget in widgets)
            observed["scrollbar_count"] = sum(isinstance(widget, ttk.Scrollbar) for widget in widgets)
            observed["combobox_count"] = sum(isinstance(widget, ttk.Combobox) for widget in widgets)
            win.destroy()

        with patch.object(self.frame, "wait_window", side_effect=inspect_and_close):
            action, assignments, building_blocks = self.frame._batch_chemical_step(
                sources, {}, {}
            )

        self.assertEqual("cancel", action)
        self.assertEqual((True, True), observed["resizable"])
        self.assertEqual(1, observed["canvas_count"])
        self.assertEqual(1, observed["scrollbar_count"])
        self.assertEqual(12, observed["combobox_count"])
        self.assertEqual(set(sources), set(assignments))
        self.assertFalse(any(building_blocks.values()))

    def test_batch_volume_apply_to_all_calculates_building_block_ul(self):
        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        def apply_and_continue(win):
            widgets = descendants(win)
            entries = [widget for widget in widgets if isinstance(widget, ttk.Entry)]
            entry = entries[-1]
            entry.delete(0, "end")
            entry.insert(0, "2.5")
            win.update_idletasks()
            next(
                widget
                for widget in widgets
                if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Apply to all"
            ).invoke()
            next(
                widget
                for widget in widgets
                if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Next"
            ).invoke()

        with patch.object(self.frame, "wait_window", side_effect=apply_and_continue):
            with patch("opentrons_frame.messagebox.showwarning") as warning:
                action, modes, umol, volumes = self.frame._batch_volume_step(
                    "individual",
                    ["A1", "B1"],
                    {"A1": "CHEM-1", "B1": "CHEM-1"},
                    {"A1": True, "B1": True},
                    {},
                    {},
                    {},
                )

        self.assertFalse(warning.called, warning.call_args_list)
        self.assertEqual("next", action)
        self.assertEqual({"A1": "umol", "B1": "umol"}, modes)
        self.assertEqual({"A1": "2.5", "B1": "2.5"}, umol)
        self.assertEqual({"A1": "5", "B1": "5"}, volumes)

    def test_non_building_blocks_can_use_umol_and_apply_it_to_all_sources(self):
        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        observed = {}

        def apply_and_continue(win):
            widgets = descendants(win)
            combo = next(widget for widget in widgets if isinstance(widget, ttk.Combobox))
            observed["mode_state"] = str(combo.cget("state"))
            observed["mode_values"] = tuple(combo.cget("values"))
            entry = [widget for widget in widgets if isinstance(widget, ttk.Entry)][-1]
            entry.delete(0, "end")
            entry.insert(0, "2.5")
            next(
                widget
                for widget in widgets
                if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Apply to all"
            ).invoke()
            next(
                widget
                for widget in widgets
                if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Next"
            ).invoke()

        with patch.object(self.frame, "wait_window", side_effect=apply_and_continue):
            with patch("opentrons_frame.messagebox.showwarning") as warning:
                action, modes, umol, volumes = self.frame._batch_volume_step(
                    "individual",
                    ["A1", "B1"],
                    {"A1": "CHEM-1", "B1": "CHEM-1"},
                    {"A1": False, "B1": False},
                    {"A1": "umol"},
                    {},
                    {},
                )

        self.assertFalse(warning.called, warning.call_args_list)
        self.assertEqual("next", action)
        self.assertEqual("readonly", observed["mode_state"])
        self.assertIn("Target umol (preferred)", observed["mode_values"])
        self.assertIn("Direct uL", observed["mode_values"])
        self.assertEqual({"A1": "umol", "B1": "umol"}, modes)
        self.assertEqual({"A1": "2.5", "B1": "2.5"}, umol)
        self.assertEqual({"A1": "5", "B1": "5"}, volumes)

    def test_batch_volume_next_blocks_missing_concentration_and_eight_channel_mismatch(self):
        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        def try_next_then_cancel(win):
            widgets = descendants(win)
            buttons = {
                str(widget.cget("text")): widget
                for widget in widgets
                if isinstance(widget, ttk.Button)
            }
            buttons["Next"].invoke()
            buttons["Cancel"].invoke()

        with patch.object(self.frame, "wait_window", side_effect=try_next_then_cancel):
            with patch("opentrons_frame.messagebox.showwarning") as warning:
                action, _modes, _umol, volumes = self.frame._batch_volume_step(
                    "individual",
                    ["A1"],
                    {"A1": "UNKNOWN"},
                    {"A1": True},
                    {"A1": "umol"},
                    {"A1": "2.5"},
                    {},
                )

        self.assertEqual("cancel", action)
        self.assertEqual("", volumes["A1"])
        self.assertIn("Missing Compound Notes concentration", warning.call_args.args[1])

        with patch.object(self.frame, "wait_window", side_effect=try_next_then_cancel):
            with patch("opentrons_frame.messagebox.showwarning") as warning:
                action, _modes, _umol, _volumes = self.frame._batch_volume_step(
                    "8-channel",
                    ["A1", "B1"],
                    {"A1": "", "B1": ""},
                    {"A1": False, "B1": False},
                    {"A1": "ul", "B1": "ul"},
                    {},
                    {"A1": "5", "B1": "6"},
                )

        self.assertEqual("cancel", action)
        self.assertIn("same final dispense volume", warning.call_args.args[1])

    def test_individual_batch_per_source_volumes_flow_to_cheminformatics(self):
        row = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1"],
            {"A1": "CHEM-1", "B1": "CHEM-2"},
            "dest1",
            [["A2", "B2"]],
            building_blocks={"A1": True, "B1": False},
            volume_modes={"A1": "umol", "B1": "ul"},
            source_umol={"A1": "2.5", "B1": ""},
            source_volumes_ul={"A1": "5", "B1": "6"},
            exclude_row_index=None,
        )
        self.frame.rows = [row]

        pushed = self.frame.rows_for_cheminformatics()

        self.assertEqual([5.0, 6.0], [item["dispensed_uL"] for item in pushed])
        self.assertEqual(["2.5", ""], [item["dispensed_umol"] for item in pushed])

    def test_more_than_eight_individual_sources_generate_and_push(self):
        sources = [f"{row}1" for row in "ABCDEFGH"] + [f"{row}2" for row in "ABCD"]
        first_destinations = [f"{row}3" for row in "ABCDEFGH"] + [f"{row}4" for row in "ABCD"]
        second_destinations = [f"{row}5" for row in "ABCDEFGH"] + [f"{row}6" for row in "ABCD"]
        self.frame.rows = [{
            "batch_transfer_kind": "individual",
            "batch_source_wells": ",".join(sources),
            "batch_source_chemicals": {
                source: f"CHEM-{index + 1}" for index, source in enumerate(sources)
            },
            "batch_source_building_blocks": {source: False for source in sources},
            "batch_destination_sets": [first_destinations, second_destinations],
            "source_labware_alias": "source1",
            "dest_labware_alias": "dest1",
            "source_well": sources[0],
            "dest_wells": ",".join(first_destinations + second_destinations),
            "volume_ul": 10.0,
            "strategy": "Single transfer",
            "pipette_key": "Auto",
        }]

        script = self.frame._build_script_text()
        compile(script, "generated_opentrons_protocol.py", "exec")
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])
        cheminformatics_rows = self.frame.rows_for_cheminformatics()

        self.assertEqual(12, len(generated_rows))
        self.assertEqual(sources, [row["source_well"] for row in generated_rows])
        self.assertTrue(all(len(row["dest_wells"]) == 2 for row in generated_rows))
        self.assertEqual(24, len(cheminformatics_rows))

    def test_single_selection_loads_and_autosaves_without_an_edit_button(self):
        self.frame.rows = [self._protocol_row(10, dest_wells="A2")]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        self.root.update()

        self.assertEqual(0, self.frame._editing_transfer_row_index)
        self.assertEqual("A2", self.frame.dest_wells_var.get())
        self.assertTrue(self.frame._row_editor_enabled)
        self.frame.dest_wells_var.set("A3")
        self.root.update()
        self.assertEqual("A3", self.frame.rows[0]["dest_wells"])

    def test_create_single_appends_and_selects_a_fresh_incomplete_draft(self):
        self.frame.rows = [self._protocol_row(10, dest_wells="A2")]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        self.root.update()
        self.frame.dest_wells_var.set("A3")
        self.root.update()
        self.frame._create_single_row()

        self.assertEqual(2, len(self.frame.rows))
        self.assertEqual("A3", self.frame.rows[0]["dest_wells"])
        self.assertTrue(self.frame.rows[1]["_draft"])
        self.assertEqual("", self.frame.rows[1]["dest_wells"])
        self.assertEqual(("1",), self.frame.tree.selection())
        self.assertEqual(1, self.frame._editing_transfer_row_index)

    def test_create_batch_immediately_adds_and_selects_a_draft_without_opening_map(self):
        with patch.object(self.frame, "_open_batch_transfer") as mapper:
            self.frame._create_batch_row()

        mapper.assert_not_called()
        self.assertEqual(1, len(self.frame.rows))
        self.assertTrue(self.frame.rows[0]["_draft"])
        self.assertEqual("individual", self.frame.rows[0]["batch_transfer_kind"])
        self.assertEqual(("0",), self.frame.tree.selection())
        self.assertEqual(0, self.frame._editing_transfer_row_index)
        self.assertIn("mapping required", self.frame.batch_chemical_summary_var.get())

    def test_edit_batch_arms_selected_row_without_opening_mapping_until_map(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1"],
            {"A1": "CHEM-1"},
            "dest1",
            [["A2"]],
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        calls = []
        self.frame._open_batch_transfer = lambda edit_index=None: calls.append(edit_index) or True

        self.frame._edit_selected_transfer()

        self.assertEqual([], calls)
        self.assertEqual(0, self.frame._editing_transfer_row_index)
        self.assertEqual("ChemRegion.LiveEdit.TLabel", self.frame.transfer_mode_status_label.cget("style"))

        self.frame._pick_source_well()

        self.assertEqual([0], calls)
        self.assertEqual(0, self.frame._editing_transfer_row_index)

        self.frame._start_new_transfer(announce=False)
        self.assertEqual("ChemRegion.LiveEdit.TLabel", self.frame.transfer_mode_status_label.cget("style"))

    def test_batch_map_updates_the_selected_row(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1"],
            {"A1": "CHEM-1"},
            "dest1",
            [["A2"]],
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        calls = []
        self.frame._open_batch_transfer = lambda edit_index=None: calls.append(edit_index) or True

        self.frame._pick_dest_wells()

        self.assertEqual([0], calls)
        self.assertEqual(0, self.frame._editing_transfer_row_index)

    def test_batch_preview_displays_every_source_well(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1", "C1"],
            {"A1": "CHEM-1", "B1": "CHEM-2", "C1": "CHEM-3"},
            "dest1",
            [["A2", "B2", "C2"]],
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")

        self.frame._on_transfer_row_select()

        self.assertEqual("A1,B1,C1", self.frame.source_well_var.get())
        self.assertEqual("A1", self.frame.rows[0]["source_well"])

    def test_umol_wording_and_dispense_entry_alignment(self):
        self.assertEqual("umol per rxn", self.frame.reaction_umol_label.cget("text"))
        self.assertEqual("Dispense volume/uL", self.frame.volume_label.cget("text"))
        self.root.update_idletasks()
        self.assertLess(
            self.frame.reaction_umol_entry.winfo_rootx(),
            self.frame.volume_label.winfo_rootx(),
        )
        self.assertLess(
            self.frame.volume_label.winfo_rootx(),
            self.frame.volume_entry.winfo_rootx(),
        )

    def test_liquid_handling_controls_have_a_subtle_section_border(self):
        panel = self.frame.liquid_handling_panel
        self.assertIsInstance(panel, ttk.LabelFrame)
        self.assertEqual("Liquid handling for this row", panel.cget("text"))
        self.assertEqual("ChemRegion.TLabelframe", panel.cget("style"))
        self.assertGreater(
            int(panel.grid_info()["row"]),
            int(self.frame.transfer_fields_panel.grid_info()["row"]),
        )

    def test_opentrons_uses_two_column_scrollable_lower_workspace(self):
        self.assertEqual(2, len(self.frame.plan_panes.panes()))
        self.assertEqual("horizontal", str(self.frame.lower_plan_panes.cget("orient")))
        self.assertEqual(2, len(self.frame.lower_plan_panes.panes()))
        self.assertLess(
            int(self.frame.transfer_fields_panel.grid_info()["row"]),
            int(self.frame.liquid_handling_panel.grid_info()["row"]),
        )
        self.assertLess(
            int(self.frame.liquid_handling_panel.grid_info()["row"]),
            int(self.frame.move_plate_panel.grid_info()["row"]),
        )
        self.assertEqual("vertical", str(self.frame.transfer_row_scrollbar.cget("orient")))
        self.assertEqual("horizontal", str(self.frame.plan_x_scrollbar.cget("orient")))
        self.assertTrue(str(self.frame.tree.cget("xscrollcommand")))

    def test_row_editor_is_disabled_until_a_row_is_created_or_selected(self):
        self.assertEqual("Create Single", self.frame.create_single_button.cget("text"))
        self.assertEqual("Create Batch", self.frame.create_batch_button.cget("text"))
        self.assertLess(
            int(self.frame.row_action_toolbar.grid_info()["row"]),
            int(self.frame.transfer_fields_panel.grid_info()["row"]),
        )
        self.assertFalse(self.frame._row_editor_enabled)
        self.assertEqual("disabled", str(self.frame.chemical_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.source_map_button.cget("state")))
        self.assertEqual("disabled", str(self.frame.volume_entry.cget("state")))
        self.assertEqual("disabled", str(self.frame.remove_row_button.cget("state")))

        self.frame._create_single_row()

        self.assertTrue(self.frame._row_editor_enabled)
        self.assertEqual("normal", str(self.frame.chemical_combo.cget("state")))
        self.assertEqual("normal", str(self.frame.source_map_button.cget("state")))
        self.assertEqual("normal", str(self.frame.volume_entry.cget("state")))
        self.assertEqual("normal", str(self.frame.remove_row_button.cget("state")))

    def test_single_draft_autosaves_partial_values_and_becomes_complete(self):
        self.frame._create_single_row()
        self.assertTrue(self.frame.rows[0]["_draft"])
        self.assertIn("Incomplete", self.frame.tree.item("0", "values")[0])

        self.frame.source_well_var.set("A1")
        self.frame.dest_wells_var.set("A2")
        self.frame.volume_var.set("10")
        self.root.update()

        self.assertNotIn("_draft", self.frame.rows[0])
        self.assertEqual("A1", self.frame.rows[0]["source_well"])
        self.assertEqual("A2", self.frame.rows[0]["dest_wells"])
        self.assertEqual(10.0, self.frame.rows[0]["volume_ul"])
        self.assertNotIn("Incomplete", self.frame.tree.item("0", "values")[0])

    def test_incomplete_draft_blocks_generation_with_row_specific_guidance(self):
        self.frame._create_single_row()

        with self.assertRaisesRegex(
            ValueError,
            r"Row 1: select a source well; select destination wells; enter a positive dispense volume",
        ):
            self.frame._build_script_text()

    def test_batch_selection_shows_per_source_chemical_summary_not_single_id(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1"],
            {"A1": "CHEM-1", "B1": ""},
            "dest1",
            [["A2", "B2"]],
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame._select_transfer_row(0)
        self.frame._on_transfer_row_select()

        self.assertEqual({}, self.frame.chemical_combo.grid_info())
        self.assertTrue(self.frame.batch_chemical_summary_button.grid_info())
        self.assertIn("1 assigned, 1 blank", self.frame.batch_chemical_summary_var.get())

    def test_incomplete_batch_draft_round_trips_and_import_starts_disabled(self):
        self.frame._create_batch_row()
        self.assertEqual("", self.frame.rows[0]["source_labware_alias"])
        self.assertEqual("", self.frame.rows[0]["dest_labware_alias"])
        self.assertEqual("", self.frame.source_labware_alias_var.get())
        self.assertEqual("", self.frame.dest_labware_alias_var.get())
        self.frame.volume_var.set("25")
        self.root.update()
        state = self.frame.export_state()

        imported = OpentronsFrame(self.root)
        try:
            imported.import_state(state)
            self.assertEqual(1, len(imported.rows))
            self.assertTrue(imported.rows[0]["_draft"])
            self.assertEqual("", imported.rows[0]["source_labware_alias"])
            self.assertEqual("", imported.rows[0]["dest_labware_alias"])
            self.assertEqual("", str(imported.rows[0]["volume_ul"]))
            self.assertEqual({}, imported.rows[0]["batch_source_volumes_ul"])
            self.assertFalse(imported.tree.selection())
            self.assertFalse(imported._row_editor_enabled)
            self.assertEqual("disabled", str(imported.source_map_button.cget("state")))
        finally:
            imported.destroy()

    def test_legacy_batch_import_migrates_common_volume_to_each_source(self):
        state = self.frame.export_state()
        state["rows"] = [{
            **self._protocol_row(12),
            "chemical": "",
            "batch_transfer_kind": "individual",
            "batch_transfer_version": 3,
            "batch_source_wells": "A1,B1",
            "batch_source_chemicals": {"A1": "CHEM-1", "B1": "CHEM-2"},
            "batch_source_building_blocks": {"A1": True, "B1": False},
            "batch_destination_sets": [["A2", "B2"]],
            "dest_wells": "A2,B2",
        }]

        self.frame.import_state(state)

        row = self.frame.rows[0]
        self.assertEqual(4, row["batch_transfer_version"])
        self.assertEqual({"A1": "ul", "B1": "ul"}, row["batch_source_volume_modes"])
        self.assertEqual({"A1": "12", "B1": "12"}, row["batch_source_volumes_ul"])
        self.assertEqual([12.0, 12.0], [item["volume_ul"] for item in self.frame._expanded_protocol_rows()])

    def test_import_preserves_umol_mode_for_non_building_block_source(self):
        state = self.frame.export_state()
        state["rows"] = [{
            **self._protocol_row(5),
            "chemical": "",
            "batch_transfer_kind": "individual",
            "batch_transfer_version": 4,
            "batch_source_wells": "A1",
            "batch_source_chemicals": {"A1": "CHEM-1"},
            "batch_source_building_blocks": {"A1": False},
            "batch_source_volume_modes": {"A1": "umol"},
            "batch_source_umol": {"A1": "2.5"},
            "batch_source_volumes_ul": {"A1": "5"},
            "batch_destination_sets": [["A2"]],
            "dest_wells": "A2",
        }]

        self.frame.import_state(state)

        row = self.frame.rows[0]
        self.assertEqual({"A1": False}, row["batch_source_building_blocks"])
        self.assertEqual({"A1": "umol"}, row["batch_source_volume_modes"])
        self.assertEqual("2.5", self.frame._batch_reaction_umol_for_source(row, "A1"))

    def test_legacy_incomplete_row_imports_as_a_visible_draft(self):
        state = self.frame.export_state()
        state["rows"] = [self._protocol_row(10, dest_wells="")]

        self.frame.import_state(state)

        self.assertTrue(self.frame.rows[0]["_draft"])
        self.assertIn("Incomplete", self.frame.tree.item("0", "values")[0])
        self.assertFalse(self.frame._row_editor_enabled)

    def test_removing_the_last_selected_row_disables_the_editor(self):
        self.frame._create_single_row()
        self.assertTrue(self.frame._row_editor_enabled)

        self.frame._remove_selected()

        self.assertEqual([], self.frame.rows)
        self.assertFalse(self.frame.tree.selection())
        self.assertFalse(self.frame._row_editor_enabled)
        self.assertEqual("disabled", str(self.frame.volume_entry.cget("state")))

    def test_auto_only_requires_the_50_ul_tiprack_when_only_the_50_ul_pipette_is_used(self):
        self.frame.rows = [self._protocol_row(10)]
        self.frame.right_tiprack_slots_var.set("")

        script = self.frame._build_script_text()
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])

        self.assertEqual("left", generated_rows[0]["pipette_key"])
        self.assertIn("pipette_left = protocol.load_instrument", script)
        self.assertNotIn("pipette_right = protocol.load_instrument", script)

    def test_auto_only_requires_the_1000_ul_tiprack_when_only_the_1000_ul_pipette_is_used(self):
        self.frame.rows = [self._protocol_row(100)]
        self.frame.left_tiprack_slots_var.set("")

        script = self.frame._build_script_text()
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])

        self.assertEqual("right", generated_rows[0]["pipette_key"])
        self.assertNotIn("pipette_left = protocol.load_instrument", script)
        self.assertIn("pipette_right = protocol.load_instrument", script)

    def test_auto_requires_both_tipracks_when_both_pipettes_are_selected(self):
        self.frame.rows = [
            self._protocol_row(10, dest_wells="A2"),
            self._protocol_row(100, source_well="A3", dest_wells="A4"),
        ]
        self.frame.right_tiprack_slots_var.set("")

        with self.assertRaisesRegex(ValueError, r"right flex_1channel_1000 .*rows 2"):
            self.frame._build_script_text()

        self.frame.right_tiprack_slots_var.set("D2")
        script = self.frame._build_script_text()
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])
        self.assertEqual(["left", "right"], [row["pipette_key"] for row in generated_rows])
        self.assertIn("pipette_left = protocol.load_instrument", script)
        self.assertIn("pipette_right = protocol.load_instrument", script)

    def test_auto_tiprack_requirement_uses_air_gap_capacity(self):
        self.frame.rows = [self._protocol_row(
            45,
            delay_air_gap_enabled=True,
            air_gap_enabled=True,
            air_gap_volume_ul="10",
        )]
        self.frame.right_tiprack_slots_var.set("")

        with self.assertRaisesRegex(ValueError, r"right flex_1channel_1000 .*rows 1"):
            self.frame._build_script_text()

    def test_explicit_mount_ignores_the_unused_pipette_tiprack(self):
        self.frame.rows = [self._protocol_row(10, pipette_key="left")]
        self.frame.right_tiprack_var.set("not_a_tiprack")
        self.frame.right_tiprack_slots_var.set("")

        script = self.frame._build_script_text()

        self.assertIn("pipette_left = protocol.load_instrument", script)
        self.assertNotIn("pipette_right = protocol.load_instrument", script)

    def test_selected_batch_uses_map_for_labware_and_no_selection_disables_editor(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1"],
            {"A1": "CHEM-1", "B1": "CHEM-2"},
            "dest1",
            [["A2", "B2"]],
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame._select_transfer_row(0)
        self.frame._on_transfer_row_select()

        self.assertEqual(0, self.frame._editing_transfer_row_index)
        self.assertEqual("source1", self.frame.source_labware_alias_var.get())
        self.assertEqual("dest1", self.frame.dest_labware_alias_var.get())
        self.assertEqual("disabled", str(self.frame.source_labware_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.dest_labware_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.volume_entry.cget("state")))
        self.assertEqual("normal", str(self.frame.source_map_button.cget("state")))
        self.assertEqual("RowAction.TButton", str(self.frame.source_map_button.cget("style")))
        self.assertEqual("RowAction.TButton", str(self.frame.dest_map_button.cget("style")))

        self.frame._start_new_transfer(announce=False)

        self.assertIsNone(self.frame._editing_transfer_row_index)
        self.assertFalse(self.frame.tree.selection())
        self.assertFalse(self.frame._row_editor_enabled)
        self.assertEqual("disabled", str(self.frame.source_labware_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.dest_labware_combo.cget("state")))
        self.assertEqual("TButton", str(self.frame.source_map_button.cget("style")))

    def test_source_labware_step_warns_before_clearing_staged_mapping(self):
        self.frame.labware_configs.append({
            "alias": "source2",
            "role": "source",
            "load_name": "nest_96_wellplate_2ml_deep",
            "slot": "B1",
            "map_style": "96 well",
        })

        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        def choose_source2(win):
            widgets = descendants(win)
            combo = next(widget for widget in widgets if isinstance(widget, ttk.Combobox))
            combo.set("source2")
            next_button = next(
                widget
                for widget in widgets
                if isinstance(widget, ttk.Button) and str(widget.cget("text")) == "Next"
            )
            next_button.invoke()

        with patch.object(self.frame, "wait_window", side_effect=choose_source2):
            with patch("opentrons_frame.messagebox.askyesno", return_value=True) as warning:
                action, alias = self.frame._batch_source_labware_step(
                    "source1", has_existing_mapping=True
                )

        warning.assert_called_once()
        self.assertEqual("next", action)
        self.assertEqual("source2", alias)

    def test_new_batch_labware_choosers_start_empty_and_require_selection(self):
        observed = []

        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        def try_next_then_cancel(win):
            widgets = descendants(win)
            combo = next(widget for widget in widgets if isinstance(widget, ttk.Combobox))
            observed.append(combo.get())
            buttons = {
                str(widget.cget("text")): widget
                for widget in widgets
                if isinstance(widget, ttk.Button)
            }
            buttons["Next"].invoke()
            buttons["Cancel"].invoke()

        with patch.object(self.frame, "wait_window", side_effect=try_next_then_cancel):
            with patch("opentrons_frame.messagebox.showwarning") as warning:
                source_action, source_alias = self.frame._batch_source_labware_step(
                    "", has_existing_mapping=False
                )
                dest_action, dest_alias = self.frame._batch_destination_labware_step(
                    "", has_existing_mapping=False
                )

        self.assertEqual(["", ""], observed)
        self.assertEqual(("cancel", ""), (source_action, source_alias))
        self.assertEqual(("cancel", ""), (dest_action, dest_alias))
        self.assertEqual(2, warning.call_count)
        self.assertIn("Select valid source labware", warning.call_args_list[0].args[1])
        self.assertIn("Select valid destination labware", warning.call_args_list[1].args[1])

    def test_destination_labware_change_warns_and_clears_staged_sets(self):
        self.frame.labware_configs.append({
            "alias": "dest2",
            "role": "destination",
            "load_name": "corning_96_wellplate_360ul_flat",
            "slot": "B2",
            "map_style": "96 well",
        })
        observed = []

        class FakeWellMapDialog:
            def __init__(_dialog, *_args, **kwargs):
                observed.append({
                    "labware": kwargs.get("labware_value"),
                    "groups": [list(group) for group in kwargs.get("initial_groups", [])],
                })
                _dialog.back_requested = False
                if len(observed) == 1:
                    _dialog.labware_change_requested = True
                    _dialog.requested_labware = "dest2"
                    _dialog.result_groups = [["A2", "B2"]]
                else:
                    _dialog.labware_change_requested = False
                    _dialog.requested_labware = "dest2"
                    _dialog.result_groups = [["A3", "B3"]]

            def title(_dialog, _title):
                return None

        with patch("opentrons_frame.well_map.WellMapDialog", FakeWellMapDialog):
            with patch.object(self.frame, "wait_window"):
                with patch("opentrons_frame.messagebox.askyesno", return_value=True) as warning:
                    action, alias, groups = self.frame._batch_destination_step(
                        "individual",
                        ["A1", "B1"],
                        "dest1",
                        [["A2", "B2"]],
                    )

        warning.assert_called_once()
        self.assertEqual("next", action)
        self.assertEqual("dest2", alias)
        self.assertEqual([["A3", "B3"]], groups)
        self.assertEqual([], observed[1]["groups"])

    def test_source_labware_batch_edit_is_atomic_and_remaps_every_dependency(self):
        self.frame.labware_configs.append({
            "alias": "source2",
            "role": "source",
            "load_name": "nest_96_wellplate_2ml_deep",
            "slot": "B1",
            "map_style": "96 well",
        })
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        original = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1"],
            {"A1": "CHEM-1", "B1": "CHEM-2"},
            "dest1",
            [["A2", "B2"]],
            building_blocks={"A1": True, "B1": False},
            exclude_row_index=None,
        )
        self.frame.rows = [original]
        saved_original = deepcopy(original)
        observed = {}
        self.frame._batch_kind_step = MethodType(
            lambda _self, initial: ("next", initial), self.frame
        )
        self.frame._batch_source_labware_step = MethodType(
            lambda _self, _alias, has_existing_mapping=False: ("next", "source2"), self.frame
        )

        def source_step(_self, _kind, alias, sources, exclude_row_index=None):
            observed["source_alias"] = alias
            observed["initial_sources"] = list(sources)
            return "next", ["A3", "B3"]

        def chemical_step(_self, _sources, initial, initial_bb):
            observed["initial_chemicals"] = dict(initial)
            observed["initial_building_blocks"] = dict(initial_bb)
            return "next", {"A3": "CHEM-3", "B3": "CHEM-4"}, {"A3": False, "B3": True}

        def destination_step(_self, _kind, _sources, alias, groups, exclude_row_index=None):
            observed["initial_destination_sets"] = [list(group) for group in groups]
            return "next", alias, [["A4", "B4"]]

        self.frame._batch_source_step = MethodType(source_step, self.frame)
        self.frame._batch_chemical_step = MethodType(chemical_step, self.frame)
        self.frame._batch_volume_step = MethodType(
            lambda _self, _kind, sources, _chemicals, _building_blocks, _modes, _umol, _volumes: (
                "next",
                {source: "ul" for source in sources},
                {source: "" for source in sources},
                {source: "25" for source in sources},
            ),
            self.frame,
        )
        self.frame._batch_destination_step = MethodType(destination_step, self.frame)
        self.frame._batch_review_step = MethodType(
            lambda _self, *_args, **_kwargs: "cancel", self.frame
        )

        self.assertFalse(self.frame._open_batch_transfer(edit_index=0))
        self.assertEqual(saved_original, self.frame.rows[0])

        self.frame._batch_review_step = MethodType(
            lambda _self, *_args, **_kwargs: "save", self.frame
        )
        self.assertTrue(self.frame._open_batch_transfer(edit_index=0))

        updated = self.frame.rows[0]
        self.assertEqual("source2", observed["source_alias"])
        self.assertEqual([], observed["initial_sources"])
        self.assertEqual({"A3": "", "B3": ""}, observed["initial_chemicals"])
        self.assertEqual({"A3": False, "B3": False}, observed["initial_building_blocks"])
        self.assertEqual([], observed["initial_destination_sets"])
        self.assertEqual("source2", updated["source_labware_alias"])
        self.assertEqual("A3,B3", updated["batch_source_wells"])
        self.assertEqual({"A3": "CHEM-3", "B3": "CHEM-4"}, updated["batch_source_chemicals"])
        self.assertEqual({"A3": False, "B3": True}, updated["batch_source_building_blocks"])
        self.assertEqual([["A4", "B4"]], updated["batch_destination_sets"])
        protocol_rows = self.frame._expanded_protocol_rows()
        self.assertEqual(2, len(protocol_rows))
        self.assertTrue(all(row["source_labware_alias"] == "source2" for row in protocol_rows))
        script = self.frame._build_script_text()
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])
        self.assertTrue(all(row["source_labware_alias"] == "source2" for row in generated_rows))

    def test_mix_dialog_exposes_user_settable_source_delay(self):
        self.frame.mix_enabled_var.set(True)
        self.frame._open_mix_dialog()
        dialog = next(
            child for child in self.frame.winfo_children() if isinstance(child, tk.Toplevel)
        )

        def descendants(widget):
            found = []
            for child in widget.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        labels = {
            str(widget.cget("text"))
            for widget in descendants(dialog)
            if isinstance(widget, ttk.Label)
        }
        self.assertIn("Delay after source mixing (s)", labels)
        dialog.destroy()

    def test_source_mix_delay_state_round_trip_and_legacy_default(self):
        self.frame.post_source_mix_delay_seconds_var.set("2.5")
        state = self.frame.export_state()
        self.assertEqual("2.5", state["post_source_mix_delay_seconds"])

        legacy_row = OpentronsFrame._transfer_row_dict(
            OpentronsTransferRow(
                source_well="A1",
                dest_wells="A2",
                volume_ul=10.0,
                strategy="Single transfer",
            )
        )
        legacy_row.pop("post_source_mix_delay_seconds")
        state.pop("post_source_mix_delay_seconds")
        state["rows"] = [legacy_row]

        self.frame.import_state(state)

        self.assertEqual("", self.frame.post_source_mix_delay_seconds_var.get())
        self.assertEqual("", self.frame.rows[0]["post_source_mix_delay_seconds"])

    def test_multi_dispense_destination_mix_warning_can_cancel_or_continue(self):
        self.frame.strategy_var.set("Multi-dispense")
        self.frame.mix_enabled_var.set(True)
        self.frame.mix_timing_var.set("After dispensing")

        with patch("opentrons_frame.messagebox.askokcancel", return_value=False) as warning:
            self.frame._on_strategy_changed()
        warning.assert_called_once()
        self.assertEqual("Before aspirating", self.frame.mix_timing_var.get())

        self.frame.mix_timing_var.set("Before and after")
        with patch("opentrons_frame.messagebox.askokcancel", return_value=True) as warning:
            self.frame._on_strategy_changed()
        warning.assert_called_once()
        self.assertEqual("Before and after", self.frame.mix_timing_var.get())

    def test_multi_dispense_destination_mixing_is_generated_with_safe_batch_capacity(self):
        self.frame.rows = [{
            "chemical": "CHEM-1",
            "source_labware_alias": "source1",
            "dest_labware_alias": "dest1",
            "source_well": "A1",
            "dest_wells": "A2,A3,A4,A5",
            "volume_ul": 10.0,
            "strategy": "Multi-dispense",
            "pipette_key": "Auto",
            "mix_enabled": True,
            "mix_timing": "After dispensing",
            "mix_repetitions": "3",
            "mix_volume_ul": "30",
        }]

        script = self.frame._build_script_text()
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])
        self.assertEqual(3, generated_rows[0]["batch_size"])
        self.assertEqual("After dispensing", generated_rows[0]["mix_timing"])

        multi_dispense_block = script.split("if row['strategy'] == 'Multi-dispense':", 1)[1].split(
            "        else:", 1
        )[0]
        self.assertIn("mix_after_dispensing(pipette, target, row)", multi_dispense_block)

    def test_source_mix_delay_is_generated_between_source_mix_and_aspiration(self):
        self.frame.rows = [
            {
                "chemical": "CHEM-1",
                "source_labware_alias": "source1",
                "dest_labware_alias": "dest1",
                "source_well": "A1",
                "dest_wells": destinations,
                "volume_ul": 10.0,
                "strategy": strategy,
                "pipette_key": "Auto",
                "mix_enabled": True,
                "mix_timing": "Before aspirating",
                "mix_repetitions": "3",
                "mix_volume_ul": "8",
                "post_source_mix_delay_seconds": "2.5",
            }
            for strategy, destinations in (
                ("Single transfer", "A2"),
                ("Multi-dispense", "A3,A4"),
            )
        ]

        script = self.frame._build_script_text()
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])
        self.assertEqual([2.5, 2.5], [row["post_source_mix_delay_seconds"] for row in generated_rows])

        helper = script.split("def mix_before_aspirating", 1)[1].split(
            "def mix_after_dispensing", 1
        )[0]
        self.assertIn("row.get('mix_enabled')", helper)
        self.assertLess(
            helper.index("mix_well(pipette, source_well, row)"),
            helper.index("timed_delay(row.get('post_source_mix_delay_seconds'))"),
        )
        self.assertEqual(2, script.count("mix_before_aspirating(pipette, src, row)"))

    def test_batch_creation_and_edit_replace_one_logical_item_atomically(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        self.frame.strategy_var.set("Single transfer")
        self.frame._batch_kind_step = MethodType(lambda _self, _initial: ("next", "individual"), self.frame)
        self.frame._batch_source_labware_step = MethodType(
            lambda _self, alias, has_existing_mapping=False: ("next", alias), self.frame
        )
        self.frame._batch_source_step = MethodType(
            lambda _self, _kind, _alias, _sources, exclude_row_index=None: ("next", ["A1", "B1"]),
            self.frame,
        )
        self.frame._batch_chemical_step = MethodType(
            lambda _self, _sources, _initial, _initial_bb: (
                "next",
                {"A1": "CHEM-1", "B1": "CHEM-2"},
                {"A1": True, "B1": False},
            ),
            self.frame,
        )
        self.frame._batch_volume_step = MethodType(
            lambda _self, _kind, sources, _chemicals, _building_blocks, _modes, _umol, _volumes: (
                "next",
                {source: "ul" for source in sources},
                {source: "" for source in sources},
                {source: "25" for source in sources},
            ),
            self.frame,
        )
        self.frame._batch_destination_step = MethodType(
            lambda _self, _kind, _sources, _alias, _sets, exclude_row_index=None: (
                "next", "dest1", [["A2", "B2"]]
            ),
            self.frame,
        )
        self.frame._batch_review_step = MethodType(lambda _self, *_args, **_kwargs: "save", self.frame)
        self.frame._open_batch_transfer()
        self.assertEqual(1, len(self.frame.rows))
        self.assertEqual(0, self.frame._editing_transfer_row_index)
        self.assertEqual(("0",), self.frame.tree.selection())
        self.assertEqual("disabled", str(self.frame.source_labware_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.dest_labware_combo.cget("state")))
        self.assertEqual(2, len(self.frame._expanded_protocol_rows()))
        self.assertTrue(all(row["volume_ul"] == 25.0 for row in self.frame._expanded_protocol_rows()))
        self.assertEqual({"A1": True, "B1": False}, self.frame.rows[0]["batch_source_building_blocks"])
        self.assertEqual("1/2 BB", self.frame._transfer_row_values(self.frame.rows[0], 0)[2])
        self.assertEqual(
            {("A1", "A2", "CHEM-1"), ("B1", "B2", "CHEM-2")},
            {
                (row["source_well"], row["well"], row["chemical"])
                for row in self.frame.rows_for_cheminformatics()
            },
        )
        self.assertEqual(
            {("CHEM-1", True), ("CHEM-2", False)},
            {(row["chemical"], row["is_building_block"]) for row in self.frame.rows_for_cheminformatics()},
        )

        self.frame._batch_destination_step = MethodType(
            lambda _self, _kind, _sources, _alias, _sets, exclude_row_index=None: (
                "next", "dest1", [["A3", "B3"], ["A4", "B4"]]
            ),
            self.frame,
        )
        self.frame._open_batch_transfer(edit_index=0)
        self.assertEqual(1, len(self.frame.rows))
        self.assertEqual(
            [["A3", "B3"], ["A4", "B4"]],
            self.frame.rows[0]["batch_destination_sets"],
        )
        self.assertEqual(4, len(self.frame.rows_for_cheminformatics()))

    def test_eight_channel_auto_keeps_visible_preference_and_uses_resolved_mount(self):
        self.frame._set_transfer_type(True)
        self.frame.left_pipette_var.set("flex_8channel_50")
        self.frame.right_pipette_var.set("flex_1channel_1000")
        self.frame.row_pipette_var.set("Auto")
        self.frame.volume_var.set("25")
        sources = [f"{row}1" for row in "ABCDEFGH"]
        destinations = [f"{row}2" for row in "ABCDEFGH"]

        batch = self.frame._build_logical_batch_row(
            "8-channel",
            sources,
            {},
            "dest1",
            [destinations],
            exclude_row_index=None,
        )

        self.assertEqual("Auto", self.frame.row_pipette_var.get())
        self.assertEqual("Auto", batch["pipette_key"])
        self.assertEqual("left", batch["batch_pipette_mount"])
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        self.root.update()
        self.assertEqual("Auto", self.frame.row_pipette_var.get())
        self.assertEqual("left", self.frame._expanded_protocol_rows()[0]["pipette_key"])

    def test_batch_common_liquid_settings_autosave_without_reopening_mapping(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1"],
            {"A1": "CHEM-1", "B1": "CHEM-2"},
            "dest1",
            [["A2", "B2"]],
            building_blocks={"A1": True, "B1": False},
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        original_mapping = {
            key: batch[key]
            for key in (
                "source_labware_alias",
                "dest_labware_alias",
                "batch_source_wells",
                "batch_source_chemicals",
                "batch_source_building_blocks",
                "batch_source_volume_modes",
                "batch_source_umol",
                "batch_source_volumes_ul",
                "batch_destination_sets",
            )
        }
        self.frame._refresh_table()

        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        self.root.update()

        self.frame.volume_var.set("29")
        self.root.update()
        self.assertEqual(25.0, self.frame.rows[0]["volume_ul"])

        self.frame.volume_var.set("31")
        self.frame.strategy_var.set("Single transfer")
        self.frame.mix_volume_var.set("8")
        self.frame.mix_enabled_var.set(True)
        self.frame.post_source_mix_delay_seconds_var.set("2.5")
        self.frame.post_aspirate_delay_seconds_var.set("2")
        self.frame.delay_air_gap_enabled_var.set(True)
        self.root.update()

        saved = self.frame.rows[0]
        self.assertEqual(25.0, saved["volume_ul"])
        self.assertEqual("Single transfer", saved["strategy"])
        self.assertTrue(saved["mix_enabled"])
        self.assertEqual("8.0", saved["mix_volume_ul"])
        self.assertEqual("2.5", saved["post_source_mix_delay_seconds"])
        self.assertTrue(saved["delay_air_gap_enabled"])
        self.assertEqual("2", saved["post_aspirate_delay_seconds"])
        for key, value in original_mapping.items():
            self.assertEqual(value, saved[key])
        self.assertEqual("disabled", str(self.frame.source_labware_combo.cget("state")))
        self.assertEqual("disabled", str(self.frame.dest_labware_combo.cget("state")))
        self.assertFalse(hasattr(self.frame, "transfer_mode_notebook"))
        self.assertEqual("Create Single", self.frame.create_single_button.cget("text"))
        self.assertEqual("Create Batch", self.frame.create_batch_button.cget("text"))

    def test_starting_new_from_batch_clears_batch_well_text(self):
        self.frame._set_transfer_type(True)
        self.frame.volume_var.set("25")
        batch = self.frame._build_logical_batch_row(
            "individual",
            ["A1", "B1"],
            {"A1": "CHEM-1", "B1": "CHEM-2"},
            "dest1",
            [["A2", "B2"]],
            exclude_row_index=None,
        )
        self.frame.rows = [batch]
        self.frame._refresh_table()
        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        self.root.update()
        self.assertEqual("A2,B2", self.frame.dest_wells_var.get())

        self.frame._start_new_transfer(announce=False)

        self.assertEqual("", self.frame.source_well_var.get())
        self.assertEqual("", self.frame.dest_wells_var.get())

    def test_destination_map_highlights_wells_used_by_other_rows(self):
        self.frame.rows = [
            {
                "batch_transfer_kind": "individual",
                "batch_source_wells": "A1,B1",
                "batch_destination_sets": [["A2", "B2"]],
                "dest_labware_alias": "dest1",
                "dest_wells": "A2,B2",
            },
            {
                "dest_labware_alias": "dest1",
                "dest_wells": "C3,D3",
            },
        ]
        captured = {}

        class FakeWellMapDialog:
            def __init__(_dialog, *_args, **kwargs):
                captured.update(kwargs)
                _dialog.result_labels = ""

        with patch("opentrons_frame.well_map.WellMapDialog", FakeWellMapDialog):
            with patch.object(self.frame, "wait_window"):
                self.frame._pick_dest_wells()

        self.assertEqual({"A2", "B2", "C3", "D3"}, captured["highlight_labels"])
        self.assertIn("destination wells", captured["highlight_hint"])

    def test_create_sequence_groups_rows_and_child_editing_preserves_metadata(self):
        self.frame.rows = [
            self._protocol_row(10, source_well="A1", dest_wells="B1,B2", step_name="Organic"),
            self._protocol_row(20, source_well="C1", dest_wells="D1,D2", step_name="Aqueous"),
        ]
        self.frame._refresh_table()
        self.frame.tree.selection_set(("0", "1"))

        with patch("opentrons_frame.simpledialog.askstring", return_value="Extraction"):
            self.frame._create_sequence_from_selected()

        sequence_id = self.frame.rows[0]["sequence_id"]
        self.assertEqual(sequence_id, self.frame.rows[1]["sequence_id"])
        self.assertEqual([1, 2], [row["sequence_order"] for row in self.frame.rows])
        self.assertEqual(2, len({row["sequence_group_id"] for row in self.frame.rows}))
        self.assertTrue(self.frame.tree.exists(f"sequence:{sequence_id}"))
        group_iids = self.frame.tree.get_children(f"sequence:{sequence_id}")
        self.assertEqual(2, len(group_iids))
        self.assertTrue(all(iid.startswith("group:") for iid in group_iids))
        self.assertEqual(("0",), self.frame.tree.get_children(group_iids[0]))
        self.assertEqual(("1",), self.frame.tree.get_children(group_iids[1]))

        self.frame.tree.selection_set("0")
        self.frame.tree.focus("0")
        self.frame._on_transfer_row_select()
        self.frame.volume_var.set("12")
        self.root.update()

        self.assertEqual(12.0, self.frame.rows[0]["volume_ul"])
        self.assertEqual(sequence_id, self.frame.rows[0]["sequence_id"])
        self.assertEqual("Extraction", self.frame.rows[0]["sequence_name"])

    def test_generated_sequence_rows_are_sample_major_and_compile(self):
        sequence_id = "generate-sequence"
        self.frame.rows = [
            self._protocol_row(
                10, source_well="A1", dest_wells="B1,B2", step_name="First",
                tip_policy="Keep tip mounted", sequence_id=sequence_id,
                sequence_name="Extraction", sequence_order=1, sequence_version=1,
            ),
            self._protocol_row(
                10, source_well="C1", dest_wells="D1,D2", step_name="Second",
                tip_policy="Bin tip after row", sequence_id=sequence_id,
                sequence_name="Extraction", sequence_order=2, sequence_version=1,
            ),
        ]

        script = self.frame._build_script_text()
        compile(script, "generated_sequence.py", "exec")
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])

        self.assertEqual(
            [["B1"], ["D1"], ["B2"], ["D2"]],
            [row["dest_wells"] for row in generated_rows],
        )
        self.assertEqual([1, 1, 2, 2], [row["sequence_sample_index"] for row in generated_rows])
        self.assertIn("Group {row.get('sequence_group_index')}", script)

    def test_generated_partitioned_groups_compile_in_sample_major_order(self):
        sequence_id = "generated-partition"
        destinations = [f"{row}{column}" for column in range(1, 4) for row in "ABCDEFGH"][:20]
        common = self._protocol_row(
            10, source_well="A10", dest_wells=",".join(destinations), step_name="Common",
            tip_policy="Keep tip mounted", sequence_id=sequence_id, sequence_name="Partition",
            sequence_order=1, sequence_version=2, sequence_group_id="common",
            sequence_group_name="Common", sequence_group_order=1, sequence_row_order=1,
        )
        partitioned = [
            self._protocol_row(
                10, source_well=f"{chr(ord('B') + index)}10",
                dest_wells=",".join(destinations[index * 4:(index + 1) * 4]),
                step_name=f"Partition {index + 1}", tip_policy="Bin tip after row",
                sequence_id=sequence_id, sequence_name="Partition", sequence_order=index + 2,
                sequence_version=2, sequence_group_id="partitioned",
                sequence_group_name="Partitioned", sequence_group_order=2, sequence_row_order=index + 1,
            )
            for index in range(5)
        ]
        self.frame.rows = [common, *partitioned]

        script = self.frame._build_script_text()
        compile(script, "generated_partitioned_sequence.py", "exec")
        transfer_rows_line = next(
            line for line in script.splitlines() if line.startswith("TRANSFER_ROWS = ")
        )
        generated_rows = ast.literal_eval(transfer_rows_line.split(" = ", 1)[1])

        self.assertEqual(40, len(generated_rows))
        self.assertEqual(
            [("A10", destinations[0]), ("B10", destinations[0]), ("A10", destinations[4]), ("C10", destinations[4])],
            [
                (generated_rows[index]["source_well"], generated_rows[index]["dest_wells"][0])
                for index in (0, 1, 8, 9)
            ],
        )
        self.assertEqual([1, 2, 1, 2], [generated_rows[index]["sequence_group_index"] for index in (0, 1, 8, 9)])

    def test_sequence_reorder_rename_ungroup_and_persistence(self):
        sequence_id = "saved-sequence"
        self.frame.rows = [
            self._protocol_row(
                10, source_well="A1", dest_wells="B1,B2", step_name="First",
                sequence_id=sequence_id, sequence_name="Extraction", sequence_order=1, sequence_version=1,
            ),
            self._protocol_row(
                20, source_well="C1", dest_wells="D1,D2", step_name="Second",
                sequence_id=sequence_id, sequence_name="Extraction", sequence_order=2, sequence_version=1,
            ),
        ]
        self.frame._refresh_table()
        group_iids = self.frame.tree.get_children(f"sequence:{sequence_id}")
        self.frame.tree.selection_set(group_iids[1])
        self.frame.tree.focus(group_iids[1])
        self.frame._move_selected_sequence_group(-1)
        self.assertEqual(["Second", "First"], [row["step_name"] for row in self.frame.rows])
        self.assertEqual([1, 2], [row["sequence_order"] for row in self.frame.rows])

        self.frame.tree.selection_set(f"sequence:{sequence_id}")
        self.frame.tree.focus(f"sequence:{sequence_id}")
        with patch("opentrons_frame.simpledialog.askstring", return_value="Renamed"):
            self.frame._rename_selected_sequence()
        self.assertEqual(["Renamed", "Renamed"], [row["sequence_name"] for row in self.frame.rows])

        state = self.frame.export_state()
        imported = OpentronsFrame(self.root)
        try:
            imported.import_state(state)
            self.assertEqual(sequence_id, imported.rows[0]["sequence_id"])
            self.assertEqual([1, 2], [row["sequence_order"] for row in imported.rows])
            self.assertTrue(all(row["sequence_version"] == 2 for row in imported.rows))
            self.assertTrue(imported.tree.exists(f"sequence:{sequence_id}"))
        finally:
            imported.destroy()

        self.frame.tree.selection_set(f"sequence:{sequence_id}")
        self.frame._ungroup_selected_sequence()
        self.assertTrue(all("sequence_id" not in row for row in self.frame.rows))
        self.assertEqual(("0", "1"), self.frame.tree.get_children(""))

    def test_place_rows_can_complete_partition_group_and_insert_exactly(self):
        sequence_id = "placement-sequence"
        destinations = [f"{row}{column}" for column in range(1, 4) for row in "ABCDEFGH"][:20]
        common = self._protocol_row(
            10, source_well="A10", dest_wells=",".join(destinations), step_name="Common",
            sequence_id=sequence_id, sequence_name="Placement", sequence_order=1, sequence_version=2,
            sequence_group_id="common-group", sequence_group_name="Common", sequence_group_order=1,
            sequence_row_order=1,
        )
        first_partition = self._protocol_row(
            10, source_well="B10", dest_wells=",".join(destinations[:4]), step_name="Part 1",
            sequence_id=sequence_id, sequence_name="Placement", sequence_order=2, sequence_version=2,
            sequence_group_id="partition-group", sequence_group_name="Partitioned", sequence_group_order=2,
            sequence_row_order=1,
        )
        additions = [
            self._protocol_row(
                10,
                source_well=f"{chr(ord('C') + index)}10",
                dest_wells=",".join(destinations[(index + 1) * 4:(index + 2) * 4]),
                step_name=f"Part {index + 2}",
            )
            for index in range(4)
        ]
        self.frame.rows = [common, first_partition, *additions]

        moved = self.frame._place_rows_in_sequence(
            [2, 3, 4, 5], sequence_id, "group_end", target_group_id="partition-group"
        )

        self.assertEqual([2, 3, 4, 5], moved)
        self.assertEqual(20, self.frame._sequence_group_position_count("partition-group"))
        self.assertEqual([1, 2, 3, 4, 5], [row["sequence_row_order"] for row in self.frame.rows[1:]])
        self.assertEqual(40, len(self.frame._expanded_protocol_rows()))

        extra = self._protocol_row(10, source_well="H10", dest_wells="A4", step_name="Inserted")
        self.frame.rows.append(extra)
        target_row = self.frame.rows[3]
        self.frame._place_rows_in_sequence(
            [6], sequence_id, "group_before_row",
            target_group_id="partition-group", target_row_index=3,
        )
        group_rows = [self.frame.rows[idx] for idx in self.frame._sequence_group_row_indices("partition-group")]
        target_position = next(index for index, row in enumerate(group_rows) if row is target_row)
        self.assertEqual("Inserted", group_rows[target_position - 1]["step_name"])
        self.assertEqual(21, self.frame._sequence_group_position_count("partition-group"))
        self.assertEqual(20, self.frame._sequence_expected_position_count(sequence_id))

    def test_tree_drag_drop_adds_an_ungrouped_row_to_an_exact_group(self):
        sequence_id = "drag-sequence"
        self.frame.rows = [
            self._protocol_row(
                10, source_well="A1", dest_wells="B1,B2", step_name="First",
                sequence_id=sequence_id, sequence_name="Drag", sequence_order=1, sequence_version=2,
                sequence_group_id="group-one", sequence_group_name="Group 1", sequence_group_order=1,
                sequence_row_order=1,
            ),
            self._protocol_row(
                10, source_well="C1", dest_wells="D1,D2", step_name="Second",
                sequence_id=sequence_id, sequence_name="Drag", sequence_order=2, sequence_version=2,
                sequence_group_id="group-two", sequence_group_name="Group 2", sequence_group_order=2,
                sequence_row_order=1,
            ),
            self._protocol_row(10, source_well="E1", dest_wells="F1", step_name="Dragged"),
        ]
        self.frame.pack(fill="both", expand=True)
        self.root.deiconify()
        self.root.geometry("1200x760+0+0")
        self.frame._refresh_table()
        self.root.update()
        source_bbox = self.frame.tree.bbox("2")
        target_bbox = self.frame.tree.bbox("group:group-two")
        self.assertTrue(source_bbox)
        self.assertTrue(target_bbox)
        start = SimpleNamespace(x=source_bbox[0] + 4, y=source_bbox[1] + source_bbox[3] // 2)
        target = SimpleNamespace(x=target_bbox[0] + 4, y=target_bbox[1] + target_bbox[3] // 2)

        self.frame._on_plan_drag_start(start)
        self.frame._on_plan_drag_motion(target)
        self.frame._on_plan_drag_release(target)

        dragged = next(row for row in self.frame.rows if row.get("step_name") == "Dragged")
        self.assertEqual("group-two", dragged["sequence_group_id"])
        self.assertEqual(2, dragged["sequence_row_order"])
        self.assertEqual(3, self.frame._sequence_group_position_count("group-two"))
        self.root.withdraw()

    def test_legacy_sequence_import_migrates_each_child_to_its_own_group(self):
        state = self.frame.export_state()
        state["rows"] = [
            self._protocol_row(
                10, source_well="A1", dest_wells="B1,B2", step_name="First",
                sequence_id="legacy", sequence_name="Legacy", sequence_order=1, sequence_version=1,
            ),
            self._protocol_row(
                10, source_well="C1", dest_wells="D1,D2", step_name="Second",
                sequence_id="legacy", sequence_name="Legacy", sequence_order=2, sequence_version=1,
            ),
        ]
        imported = OpentronsFrame(self.root)
        try:
            imported.import_state(state)
            self.assertEqual(2, len(imported._sequence_group_ids("legacy")))
            self.assertTrue(all(row["sequence_version"] == 2 for row in imported.rows))
            self.assertEqual([1, 1], [row["sequence_row_order"] for row in imported.rows])
            self.assertEqual(4, len(imported._expanded_protocol_rows()))
        finally:
            imported.destroy()


if __name__ == "__main__":
    unittest.main()
