"""GWL editor selection and lossless supported-command import regressions."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tecan_frame
from tecan_frame import TecanFrame
from xinpilot.application.tecan_worklist import build_gwl_lines, build_volume_map


MODE = "96-well horizontal"
LIQUID = "XQ_Common_no_gas"


def worklist(dispenses, *, aspirate=None):
    """dispenses is an ordered sequence of (destination, well index, volume)."""
    if aspirate is None:
        aspirate = sum(volume for _labware, _well, volume in dispenses)
    lines = [f"A;Vial8Rack_1;;;1;;{aspirate:.1f};{LIQUID};;;"]
    lines.extend(f"D;{labware};;;{well};;{volume:.1f};{LIQUID};;;" for labware, well, volume in dispenses)
    return lines + ["W;"]


class TecanImportReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.frame = TecanFrame(self.root, compound_provider=lambda: [])
        self.addCleanup(self.frame.destroy)
        self.frame.mode_var.set(MODE)
        self.frame.v_save_map.set(False)

    def parse(self, lines):
        return self.frame._blocks_from_gwl_content("\n".join(lines) + "\n", preferred_mode=MODE)[1]

    def load_entry(self, lines, *, name="saved.gwl", path=""):
        blocks = self.parse(lines)
        entry = {
            "name": name, "path": path, "mode": MODE, "content": "\n".join(lines) + "\n",
            "blocks": [self.frame._block_to_dict(block) for block in blocks],
        }
        self.frame.exported_gwl_files = [entry]
        self.frame._refresh_gwl_list(select_path=path)
        self.frame.gwl_listbox.selection_set(0)
        self.frame._on_gwl_select()
        return entry

    def test_same_gwl_reselection_preserves_applied_edits_and_dirty_baseline(self):
        original = worklist([("DeepPlate1", 1, 20)])
        entry = self.load_entry(original)
        snapshot = deepcopy(entry)
        baseline = self.frame._active_gwl_blocks_snapshot
        self.frame.v_dest_volume.set("30")
        self.assertTrue(self.frame._apply_current(silent=True))
        self.assertEqual(30, self.frame.blocks[0].dest_volume)
        self.assertEqual(snapshot, entry)
        self.assertTrue(self.frame._current_gwl_has_unsaved_changes())
        with mock.patch.object(self.frame, "_load_gwl_entry") as load, mock.patch.object(tecan_frame.messagebox, "askyesnocancel") as prompt:
            self.frame._on_gwl_select()
        load.assert_not_called()
        prompt.assert_not_called()
        self.assertEqual(30, self.frame.blocks[0].dest_volume)
        self.assertEqual(baseline, self.frame._active_gwl_blocks_snapshot)
        self.assertTrue(self.frame._current_gwl_has_unsaved_changes())

    def test_switch_to_another_gwl_still_can_cancel_and_keep_edits(self):
        self.load_entry(worklist([("DeepPlate1", 1, 20)]))
        self.frame.v_dest_volume.set("30")
        self.assertTrue(self.frame._apply_current(silent=True))
        second = dict(deepcopy(self.frame.exported_gwl_files[0]), name="second.gwl", path="second.gwl")
        self.frame.exported_gwl_files.append(second)
        self.frame._refresh_gwl_list()
        self.frame.gwl_listbox.selection_set(1)
        with mock.patch.object(tecan_frame.messagebox, "askyesnocancel", return_value=None) as prompt:
            self.frame._on_gwl_select()
        prompt.assert_called_once()
        self.assertEqual((0,), self.frame.gwl_listbox.curselection())
        self.assertEqual(30, self.frame.blocks[0].dest_volume)

    def test_repeated_same_well_dispenses_keep_order_total_and_state(self):
        for commands in (
            [("DeepPlate1", 1, 20), ("DeepPlate1", 1, 20)],
            [("DeepPlate1", 1, 20), ("DeepPlate1", 9, 30), ("DeepPlate1", 1, 20)],
            [("DeepPlate1", 1, 20), ("DeepPlate1", 9, 20), ("DeepPlate1", 1, 20)],
        ):
            with self.subTest(commands=commands):
                lines = worklist(commands)
                blocks = self.parse(lines)
                self.assertEqual(lines, build_gwl_lines(blocks, MODE))
                self.assertEqual(40, build_volume_map(blocks, MODE)["A1"])
                restored = [self.frame._block_from_dict(item) for item in json.loads(json.dumps([
                    self.frame._block_to_dict(block) for block in blocks
                ]))]
                self.assertEqual(lines, build_gwl_lines(restored, MODE))
                self.frame.blocks = restored
                self.frame._refresh_list()
                self.frame.listbox.selection_set(0)
                self.frame._on_select(None)
                self.assertTrue(self.frame._apply_current(silent=True))
                self.assertEqual(lines, self.frame._build_lines())
                self.frame.blocks[0].chemical_name = "REAGENT"
                rows = self.frame._building_block_rows_from_blocks(self.frame.blocks, MODE, include_all_chemicals=True)
                self.assertEqual([volume for _labware, _well, volume in commands], [row["volume_uL"] for row in rows])
                self.assertEqual(40, sum(row["volume_uL"] for row in rows if row["well"] == "A1"))

    def test_varying_volumes_are_not_sorted_or_merged_across_commands(self):
        lines = worklist([("DeepPlate1", 1, 10), ("DeepPlate1", 9, 30), ("DeepPlate1", 2, 10), ("DeepPlate1", 10, 30)])
        self.assertEqual(lines, build_gwl_lines(self.parse(lines), MODE))

    def test_project_state_restore_preserves_repeats_and_order(self):
        lines = worklist([("DeepPlate1", 1, 20), ("DeepPlate1", 9, 30), ("DeepPlate1", 1, 20)])
        self.load_entry(lines)
        state = json.loads(json.dumps(self.frame.export_state()))
        restored = TecanFrame(self.root, compound_provider=lambda: [])
        self.addCleanup(restored.destroy)
        restored.import_state(state)
        self.assertEqual(lines, build_gwl_lines(restored.blocks, MODE))
        restored.gwl_listbox.selection_set(0)
        restored._on_gwl_select()
        self.assertEqual(lines, restored._build_lines())
        self.assertEqual(40, restored._build_volume_map()["A1"])

    def test_repeated_dispenses_count_towards_aspirate_limit(self):
        lines = worklist([("DeepPlate1", 1, 20), ("DeepPlate1", 1, 20)], aspirate=30)
        with self.assertRaisesRegex(ValueError, "40.0.*30.0"):
            build_gwl_lines(self.parse(lines), MODE)

    def test_multiple_destinations_in_one_aspiration_are_rejected(self):
        lines = worklist([("DeepPlate1", 1, 20), ("Green Plate", 9, 20)])
        with self.assertRaisesRegex(ValueError, "multiple destination labware.*DeepPlate1.*Green Plate"):
            self.parse(lines)

    def test_different_destinations_in_separate_blocks_still_import(self):
        lines = worklist([("DeepPlate1", 1, 20)]) + worklist([("Green Plate", 9, 30)])
        self.assertEqual(lines, build_gwl_lines(self.parse(lines), MODE))

    def test_add_existing_rejects_bad_file_without_changing_current_plan(self):
        self.load_entry(worklist([("DeepPlate1", 1, 20)]))
        self.frame.v_dest_volume.set("30")
        self.assertTrue(self.frame._apply_current(silent=True))
        previous = (deepcopy(self.frame.blocks), deepcopy(self.frame.exported_gwl_files), self.frame._active_gwl_index)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed-destinations.gwl"
            path.write_text("\n".join(worklist([("DeepPlate1", 1, 20), ("Green Plate", 9, 20)])), encoding="utf-8")
            with mock.patch.object(tecan_frame.filedialog, "askopenfilenames", return_value=[str(path)]), mock.patch.object(self.frame, "_choose_gwl_import_mode", return_value=MODE), mock.patch.object(tecan_frame.messagebox, "showerror") as error:
                self.frame._add_existing_gwl()
        error.assert_called_once()
        self.assertIn("multiple destination labware", error.call_args.args[1])
        self.assertEqual(previous, (self.frame.blocks, self.frame.exported_gwl_files, self.frame._active_gwl_index))

    def test_save_as_current_path_updates_baseline_without_reloading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "current.gwl"
            original = worklist([("DeepPlate1", 1, 20)])
            path.write_text("\n".join(original) + "\n", encoding="utf-8")
            self.load_entry(original, path=str(path))
            self.frame.v_dest_volume.set("30")
            self.assertTrue(self.frame._apply_current(silent=True))
            content = self.frame._current_gwl_content()
            path.write_text(content, encoding="utf-8")
            with mock.patch.object(self.frame, "_load_gwl_entry") as reload_entry:
                self.frame._track_exported_gwl(path, content)
            reload_entry.assert_not_called()
            self.assertFalse(self.frame._current_gwl_has_unsaved_changes())


    def test_vertical_import_uses_explicit_format_and_keeps_commands(self):
        for mode, labware in [('96-well vertical', 'DeepPlate1'), ('HPLC vials vertical', tecan_frame.DEST_LABWARE_OPTIONS_HPLC[0])]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.frame.exported_gwl_files = []
                self.frame._active_gwl_index = None
                self.frame.blocks = []
                index = tecan_frame.parse_dest_well_expr('B2', mode, labware)[0]
                lines = worklist([(labware, index, 10)])
                path = Path(directory) / 'vertical.gwl'
                path.write_text('\n'.join(lines))
                with mock.patch.object(tecan_frame.filedialog, 'askopenfilenames', return_value=[str(path)]), mock.patch.object(self.frame, '_choose_gwl_import_mode', return_value=mode):
                    self.frame._add_existing_gwl()
                self.assertEqual(self.frame.mode_var.get(), mode)
                self.assertEqual(self.frame.blocks[0].dest_wells_expr, 'B2')
                self.assertEqual(build_gwl_lines(self.frame.blocks, mode), lines)

    def test_cancel_format_leaves_current_worklist_unchanged(self):
        self.load_entry(worklist([('DeepPlate1', 1, 10)]))
        before = deepcopy(self.frame.exported_gwl_files)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'new.gwl'
            path.write_text('\n'.join(worklist([('DeepPlate1', 23, 10)])))
            with mock.patch.object(tecan_frame.filedialog, 'askopenfilenames', return_value=[str(path)]), mock.patch.object(self.frame, '_choose_gwl_import_mode', return_value=None):
                self.frame._add_existing_gwl()
        self.assertEqual(self.frame.exported_gwl_files, before)

    def test_duplicate_name_from_another_directory_is_rejected_before_dialog(self):
        self.load_entry(worklist([('DeepPlate1', 1, 10)]), name='SAVED.GWL', path=str(Path.cwd()/'other'/'SAVED.GWL'))
        before = deepcopy(self.frame.exported_gwl_files)
        with mock.patch.object(tecan_frame.filedialog, 'askopenfilenames', return_value=[str(Path.cwd()/'saved.gwl')]), mock.patch.object(self.frame, '_choose_gwl_import_mode') as chooser, mock.patch.object(tecan_frame.messagebox, 'showerror') as error:
            self.frame._add_existing_gwl()
        chooser.assert_not_called()
        error.assert_called_once()
        self.assertEqual(self.frame.exported_gwl_files, before)

    def test_save_conflict_does_not_write_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'taken.gwl'
            path.write_text('KEEP')
            self.frame.exported_gwl_files = [{'name':'first.gwl','path':''}, {'name':'TAKEN.GWL','path':str(Path(directory)/'other'/'TAKEN.GWL')}]
            with mock.patch.object(tecan_frame.filedialog, 'asksaveasfilename', return_value=str(path)), mock.patch.object(tecan_frame.messagebox, 'showerror'):
                self.assertFalse(self.frame._save_gwl_entry_edits(0))
            self.assertEqual(path.read_text(), 'KEEP')

    def test_existing_project_duplicates_rejected_before_state_changes(self):
        from xinpilot.application.project_state import validate_project_data
        state = {'exported_gwl_files':[{'name':'same.gwl'}, {'name':'SAME.GWL'}]}
        before = self.frame.export_state()
        with self.assertRaisesRegex(ValueError, 'Duplicate GWL filename'):
            self.frame.import_state(state)
        self.assertEqual(self.frame.export_state(), before)
        with self.assertRaisesRegex(ValueError, 'Duplicate GWL filename'):
            validate_project_data({'tecan':state})

    def test_legacy_archive_with_renamed_files_and_ambiguous_pushed_blocks_rejected(self):
        from xinpilot.application.project_state import validate_project_data
        rows = [dict(source='Tecan', gwl='same.gwl', block=1, dest_mode=MODE,
                     summary_block={'source_well':i}) for i in (1,2)]
        with self.assertRaisesRegex(ValueError, 'Ambiguous pushed GWL'):
            validate_project_data({'cheminformatics':{'pushed_rows':rows}})
        validate_project_data({'cheminformatics':{'pushed_rows':[rows[0],dict(rows[0])]}})

    def test_same_path_save_allowed_but_new_duplicate_not_allowed(self):
        path = Path.cwd()/'existing.gwl'
        self.frame.exported_gwl_files = [{'name':path.name,'path':str(path)}]
        self.frame._check_gwl_filename(path, update_same_path=True)
        self.frame._check_gwl_filename(path, replace_index=0)
        with self.assertRaisesRegex(ValueError,'Duplicate GWL filename'):
            self.frame._check_gwl_filename(path)

    def test_import_format_dialog_has_no_assumed_selection(self):
        def accept():
            dialog = next(w for w in self.frame.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == 'GWL destination format')
            box = next(w for w in dialog.winfo_children() if isinstance(w, tecan_frame.ttk.Combobox))
            self.assertEqual(box.get(), '')
            box.set('96-well vertical')
            buttons = [w for frame in dialog.winfo_children() for w in frame.winfo_children() if isinstance(w,tecan_frame.ttk.Button)]
            next(w for w in buttons if w.cget('text')=='Import').invoke()
        self.root.after(100, accept)
        self.assertEqual(self.frame._choose_gwl_import_mode('vertical.gwl'),'96-well vertical')


if __name__ == "__main__":
    unittest.main()
