import json
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tecan_frame  # noqa: E402
from tecan_frame import DispenseGroup, LiquidClassDialog, TecanFrame, TransferBlock  # noqa: E402


class TecanUsabilityIsolationTests(unittest.TestCase):
    def test_extra_groups_update_aspiration_with_overall_percentage(self):
        root = tk.Tk()
        root.withdraw()
        try:
            frame = TecanFrame(root, compound_provider=lambda: [], push_callback=None)
            frame.v_dest_labware.set("DeepPlate1")
            frame.mode_var.set("96-well horizontal")
            frame.v_dest_wells.set("A1,A2")
            frame.v_dest_volume.set("50")
            frame.v_extra_aspirate_percent.set("10")
            self.assertEqual(110.0, float(frame.v_source_volume.get()))
            frame.v_diff_vol.set("Yes")
            group = frame.group_rows[0]
            group["vol"].set("25")
            group["wells"].set("B1,B2")
            self.assertEqual(165.0, float(frame.v_source_volume.get()))
            group["vol"].set("50")
            self.assertEqual(220.0, float(frame.v_source_volume.get()))
            group["wells"].set("B1")
            self.assertEqual(165.0, float(frame.v_source_volume.get()))
            frame.v_diff_vol.set("No")
            self.assertEqual(110.0, float(frame.v_source_volume.get()))
            frame.v_diff_vol.set("Yes")
            self.assertEqual(165.0, float(frame.v_source_volume.get()))
            frame._add_group_row("10", "C1")
            self.assertEqual(176.0, float(frame.v_source_volume.get()))
            frame._remove_group_row(frame.group_rows[-1]["frame"])
            self.assertEqual(165.0, float(frame.v_source_volume.get()))
            frame.v_extra_aspirate_percent.set("20")
            self.assertEqual(180.0, float(frame.v_source_volume.get()))
            frame._remove_group_row(group["frame"])
            self.assertEqual(120.0, float(frame.v_source_volume.get()))
        finally:
            root.destroy()

    def test_cheminformatics_rows_preserve_each_blocks_chemical_and_flag_in_shared_wells(self):
        frame = object.__new__(TecanFrame)
        blocks = [
            TransferBlock(
                source_well=1,
                dest_labware="Vial1.5_Rack1",
                dest_wells_expr="A1,A2",
                chemical_name="BB-1",
                is_building_block=True,
            ),
            TransferBlock(
                source_well=2,
                dest_labware="Vial1.5_Rack1",
                dest_wells_expr="A1,A2",
                chemical_name="BB-2",
                is_building_block=True,
            ),
            TransferBlock(
                source_well=3,
                dest_labware="Vial1.5_Rack1",
                dest_wells_expr="A1,A2",
                chemical_name="REAGENT-1",
                is_building_block=False,
            ),
        ]
        chemical_map = {
            "A1": "BB-1 | BB-2 | REAGENT-1",
            "A2": "BB-1 | BB-2 | REAGENT-1",
        }

        rows = frame._building_block_rows_from_blocks(
            blocks,
            "HPLC vials horizontal",
            chem_label_map=chemical_map,
            include_all_chemicals=True,
            gwl_name="mixed-transfers.gwl",
        )

        self.assertEqual(6, len(rows))
        self.assertEqual(
            {
                ("A1", "BB-1", True),
                ("A1", "BB-2", True),
                ("A1", "REAGENT-1", False),
                ("A2", "BB-1", True),
                ("A2", "BB-2", True),
                ("A2", "REAGENT-1", False),
            },
            {(row["well"], row["chemical"], row["is_building_block"]) for row in rows},
        )

    def test_cheminformatics_rows_use_destination_map_when_block_has_no_chemical(self):
        frame = object.__new__(TecanFrame)
        block = TransferBlock(
            source_well=1,
            dest_labware="Vial1.5_Rack1",
            dest_wells_expr="A1",
            chemical_name="",
            is_building_block=False,
        )

        rows = frame._building_block_rows_from_blocks(
            [block],
            "HPLC vials horizontal",
            chem_label_map={"A1": "MAP-CHEMICAL"},
            include_all_chemicals=True,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("MAP-CHEMICAL", rows[0]["chemical"])
        self.assertFalse(rows[0]["is_building_block"])

    def test_representative_gwl_output_remains_byte_for_byte_unchanged(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        try:
            frame = TecanFrame(root, compound_provider=lambda: [], push_callback=None)
            frame.blocks = [
                TransferBlock(
                    source_labware="Vial8Rack_1",
                    source_well=2,
                    source_volume=33.0,
                    dest_labware="DeepPlate1",
                    dest_wells_expr="A1,A2",
                    dest_volume=10.0,
                    liquid_class="XQ_Common_no_gas",
                    chemical_name="CHEM-1",
                    add_wash=True,
                    disp_different_vol=True,
                    dispense_groups=[DispenseGroup(volume=5.0, wells_expr="B1")],
                    is_building_block=True,
                    reaction_umol="1.0",
                    extra_aspirate_percent="10",
                )
            ]
            frame.mode_var.set("96-well horizontal")
            self.assertEqual(
                [
                    "A;Vial8Rack_1;;;2;;33.0;XQ_Common_no_gas;;;",
                    "D;DeepPlate1;;;1;;10.0;XQ_Common_no_gas;;;",
                    "D;DeepPlate1;;;9;;10.0;XQ_Common_no_gas;;;",
                    "D;DeepPlate1;;;2;;5.0;XQ_Common_no_gas;;;",
                    "W;",
                ],
                frame._build_lines(),
            )
        finally:
            root.destroy()


class TecanLiquidClassEditorTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        self.temp_dir = tempfile.TemporaryDirectory()
        settings_path = Path(self.temp_dir.name) / "tecan_liquid_classes.json"
        self.settings_patch = mock.patch.object(tecan_frame, "LIQUID_CLASS_SETTINGS_PATH", settings_path)
        self.settings_patch.start()
        self.frame = TecanFrame(self.root, compound_provider=lambda: [], push_callback=None)
        self.frame.pack(fill="both", expand=True)
        self.root.update_idletasks()

    def tearDown(self):
        self.frame.destroy()
        self.settings_patch.stop()
        self.temp_dir.cleanup()
        self.root.destroy()

    def test_button_order_is_push_then_labware_then_liquid_classes(self):
        widgets = []
        pending = [self.frame]
        while pending:
            widget = pending.pop(0)
            widgets.append(widget)
            pending.extend(widget.winfo_children())
        file_region = next(
            widget
            for widget in widgets
            if isinstance(widget, ttk.LabelFrame)
            and widget.cget("text") == "Exported GWL files from this edition"
        )
        direct_button_texts = [
            str(widget.cget("text"))
            for widget in file_region.winfo_children()
            if isinstance(widget, ttk.Button)
        ]
        self.assertEqual(
            [
                "Push Listed GWLs to Cheminformatics",
                "Edit Tecan Labware Names",
                "Edit Liquid Classes",
            ],
            direct_button_texts,
        )

    def test_dialog_add_edit_delete_refreshes_dropdown_and_persists(self):
        dialog = LiquidClassDialog(self.frame)
        action_labels = {
            str(widget.cget("text"))
            for widget in dialog.winfo_children()[0].winfo_children()[-1].winfo_children()
            if isinstance(widget, ttk.Button)
        }
        self.assertIn("Update Selected", action_labels)
        self.assertNotIn("Edit Selected", action_labels)
        dialog.name_var.set("Lab Water")
        dialog._add()
        self.assertIn("Lab Water", self.frame.liquid_classes)
        self.assertIn("Lab Water", self.frame.liquid_class_combo.cget("values"))

        index = self.frame.liquid_classes.index("Lab Water")
        dialog.listbox.selection_clear(0, "end")
        dialog.listbox.selection_set(index)
        dialog._on_select()
        dialog.name_var.set("Lab Water Fast")
        dialog._edit_selected()
        self.assertNotIn("Lab Water", self.frame.liquid_classes)
        self.assertIn("Lab Water Fast", self.frame.liquid_class_combo.cget("values"))

        index = self.frame.liquid_classes.index("Lab Water Fast")
        dialog.listbox.selection_clear(0, "end")
        dialog.listbox.selection_set(index)
        dialog._delete_selected()
        self.assertNotIn("Lab Water Fast", self.frame.liquid_class_combo.cget("values"))

        saved = json.loads(tecan_frame.LIQUID_CLASS_SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(self.frame.liquid_classes, saved["liquid_classes"])
        dialog.destroy()

    def test_new_transfer_block_uses_first_configured_liquid_class(self):
        self.frame.set_liquid_classes(["Lab Default", "Lab Other"], persist=False)
        self.frame.exported_gwl_files = [
            {"path": "", "name": "New GWL", "content": "", "mode": self.frame.mode_var.get(), "blocks": []}
        ]
        self.frame._refresh_gwl_list()
        self.frame._active_gwl_index = 0
        self.frame.gwl_listbox.selection_set(0)
        self.frame.mode_var.set("96-well horizontal")

        self.frame._add_block()

        self.assertEqual("Lab Default", self.frame.blocks[-1].liquid_class)


if __name__ == "__main__":
    unittest.main()
