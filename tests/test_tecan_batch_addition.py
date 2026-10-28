import json
import sys
import tkinter as tk
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tecan_frame as tecan
from tecan_batch_dialog import TecanBatchDialog, prepare_blocks, source_availability


class TecanBatchTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        records = [SimpleNamespace(values={'ID': f'BB{i}', 'Conc.': '0.2'}) for i in range(1, 9)]
        self.host = tecan.TecanFrame(self.root, compound_provider=lambda: records, push_callback=None)
        self.host.exported_gwl_files = [dict(name='Current', path='', content='', blocks=[])]
        self.host._active_gwl_index = 0
        self.host._refresh_gwl_list()
        self.host.gwl_listbox.selection_set(0)
        self.host.mode_var.set('96-well horizontal')

    def tearDown(self):
        self.root.destroy()

    def rows(self, count=2):
        return [dict(chemical=f'BB{i+1}', source_labware='Vial8Rack_1', source_well=str(i+1),
                     umol='10' if i == 0 else '1', wells=f'A{i+1},B{i+1}', building_block=True)
                for i in range(count)]

    def dialog(self, rows):
        popup = TecanBatchDialog(self.host)
        popup.destination.set('DeepPlate1')
        popup.count.set(str(len(rows)))
        for target, source in zip(popup.rows, rows):
            for key, value in source.items():
                target[key].set(value)
        return popup

    def test_direct_volume_without_concentration_export_and_roundtrip(self):
        popup = self.dialog(self.rows())
        popup.amount_unit.set('uL/well')
        popup.change_amount_unit()
        popup.all_umol.set('12.5')
        popup.apply_all()
        popup.rows[1]['umol'].set('5')
        popup.extra.set('10')
        with mock.patch.object(self.host, '_record_concentration_m', return_value=None):
            popup.apply()
        self.assertEqual([12.5, 5], [b.dest_volume for b in self.host.blocks])
        for block, total in zip(self.host.blocks, [27.5, 11]):
            self.assertAlmostEqual(total, block.source_volume)
            self.assertEqual('', block.reaction_umol)
        lines = self.host._build_lines()
        self.assertEqual(4, sum(line.startswith('D;') for line in lines))
        saved = json.loads(json.dumps([self.host._block_to_dict(b) for b in self.host.blocks]))
        self.assertEqual(self.host.blocks, [self.host._block_from_dict(b) for b in saved])

    def test_unit_switch_clears_amounts_preserves_maps_and_back(self):
        popup = self.dialog(self.rows())
        popup.all_umol.set('10')
        popup.amount_unit.set('uL/well')
        popup.change_amount_unit()
        self.assertEqual('', popup.all_umol.get())
        self.assertTrue(all(row['umol'].get() == '' for row in popup.rows))
        self.assertEqual('A1,B1', popup.rows[0]['wells'].get())
        popup.all_umol.set('20')
        popup.apply_all()
        popup.show_sources()
        popup.next_page()
        self.assertEqual('uL/well', popup.amount_unit.get())
        self.assertEqual('20', popup.rows[0]['umol'].get())
        popup.amount_unit.set('umol/rxn')
        popup.change_amount_unit()
        self.assertEqual('', popup.rows[0]['umol'].get())
        popup.destroy()

    def test_direct_volume_validation_and_precision(self):
        rows = self.rows(1)
        for value in ['nan', 'inf', '0', '-1', 'bad', '0.01']:
            rows[0]['umol'] = value
            with self.assertRaises(ValueError):
                prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class(), amount_unit='uL/well')
        rows[0]['umol'] = '12.34'
        block = prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class(), amount_unit='uL/well')[0]
        self.assertEqual(12.3, block.dest_volume)
        self.assertAlmostEqual(24.6, block.source_volume)

    def test_block_amounts_aspiration_export_and_roundtrip(self):
        popup = self.dialog(self.rows())
        popup.extra.set('10')
        popup.apply()
        self.assertFalse(popup.winfo_exists())
        self.assertEqual([50, 5], [b.dest_volume for b in self.host.blocks])
        for b, expected in zip(self.host.blocks, [110, 11]):
            self.assertAlmostEqual(expected, b.source_volume)
        lines = self.host._build_lines()
        self.assertEqual(4, len([line for line in lines if line.startswith('D;')]))
        self.assertTrue(any(';;5.0;' in line for line in lines))
        saved = json.loads(json.dumps([self.host._block_to_dict(b) for b in self.host.blocks]))
        self.assertEqual(self.host.blocks, [self.host._block_from_dict(b) for b in saved])
        self.assertEqual('BB1', self.host.v_chemical.get())

    def test_failed_last_row_adds_nothing_and_cancel_preserves_editor(self):
        self.host.blocks = [tecan.TransferBlock(chemical_name='BB1')]
        before = self.host._current_gwl_blocks_snapshot()
        rows = self.rows()
        rows[1]['wells'] = 'Z99'
        popup = self.dialog(rows)
        popup.apply()
        self.assertTrue(popup.winfo_exists())
        self.assertIn('Block 2', popup.status.get())
        self.assertEqual(before, self.host._current_gwl_blocks_snapshot())
        popup.destroy()
        self.assertEqual(before, self.host._current_gwl_blocks_snapshot())

    def test_other_gwl_and_pending_occupancy_and_same_chemical_reuse(self):
        block = tecan.TransferBlock(source_well=3, chemical_name='BB2')
        self.host.exported_gwl_files.append(dict(name='Other', path='', content='',
                                               blocks=[self.host._block_to_dict(block)]))
        rows = self.rows()
        blocked, reusable = source_availability(self.host, rows, 0)
        self.assertIn(tecan.source_index_to_label(3, 'Vial8Rack_1'), blocked)
        self.assertIn(tecan.source_index_to_label(2, 'Vial8Rack_1'), blocked)
        rows[0].update(chemical='BB2', source_well='3')
        blocked, reusable = source_availability(self.host, rows, 0)
        self.assertIn(tecan.source_index_to_label(3, 'Vial8Rack_1'), reusable)
        self.assertIn(tecan.source_index_to_label(2, 'Vial8Rack_1'), reusable)
        self.assertEqual(2, len(prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class())))
        rows[0]['chemical'] = 'BB1'
        with self.assertRaisesRegex(ValueError, 'another chemical'):
            prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class())

    def test_apply_all_eight_and_back_preserve_values(self):
        popup = self.dialog(self.rows(8))
        popup.next_page()
        popup.all_umol.set('2')
        popup.apply_all()
        popup.rows[7]['umol'].set('4')
        popup.show_sources()
        popup.next_page()
        popup.apply()
        self.assertEqual(8, len(self.host.blocks))
        self.assertEqual([10] * 7 + [20], [b.dest_volume for b in self.host.blocks])

    def test_invalid_amount_concentration_source_and_percent(self):
        rows = self.rows()
        for value in ['nan', 'inf', '0', '-1', 'bad']:
            rows[0]['umol'] = value
            with self.assertRaises(ValueError):
                prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class())
        rows = self.rows()
        for value in ['-1', 'nan', 'inf', 'bad']:
            with self.assertRaises(ValueError):
                prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class(), value)
        rows[0]['source_well'] = '999'
        with self.assertRaisesRegex(ValueError, 'outside'):
            prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class())
        rows = self.rows()
        with mock.patch.object(self.host, '_record_concentration_m', return_value=None):
            with self.assertRaisesRegex(ValueError, 'concentration'):
                prepare_blocks(self.host, rows, 'DeepPlate1', self.host._default_liquid_class())

    def test_no_gwl_guard_and_changed_gwl_guard(self):
        self.host.gwl_listbox.selection_clear(0, 'end')
        with mock.patch.object(tecan.messagebox, 'showwarning') as warning:
            self.host._open_batch_addition()
            warning.assert_called_once()
        self.host.gwl_listbox.selection_set(0)
        popup = self.dialog(self.rows())
        self.host._active_gwl_index = None
        popup.apply()
        self.assertIn('changed', popup.status.get())
        self.assertEqual([], self.host.blocks)

    def test_source_map_receives_live_and_pending_occupancy(self):
        self.host.blocks = [tecan.TransferBlock(source_well=3, chemical_name='BB2')]
        popup = self.dialog(self.rows())
        fake = SimpleNamespace(result_label=tecan.source_index_to_label(4, 'Vial8Rack_1'))
        with mock.patch.object(tecan, 'SourceWellDialog', return_value=fake) as map_dialog, \
             mock.patch.object(popup, 'wait_window'):
            popup.pick_source(0, popup)
        kwargs = map_dialog.call_args.kwargs
        self.assertIn(tecan.source_index_to_label(3, 'Vial8Rack_1'), kwargs['occupied_labels'])
        self.assertIn(tecan.source_index_to_label(2, 'Vial8Rack_1'), kwargs['occupied_labels'])
        self.assertEqual('4', popup.rows[0]['source_well'].get())

    def test_format_gate_and_blank_destinations(self):
        fresh = tecan.TecanFrame(self.root, compound_provider=lambda: [], push_callback=None)
        self.assertEqual('', fresh.mode_var.get())
        self.assertTrue(fresh.add_block_button.instate(['disabled']))
        self.assertTrue(fresh.batch_addition_button.instate(['disabled']))
        self.host.mode_var.set('')
        self.assertTrue(self.host.batch_addition_button.instate(['disabled']))
        self.host.mode_var.set('HPLC vials horizontal')
        self.assertFalse(self.host.batch_addition_button.instate(['disabled']))
        self.assertEqual((6, 8), tecan.mode_dims_order(self.host.mode_var.get())[:2])
        self.assertIn('48-well', self.host._format_tooltip.text)
        self.host._add_block()
        self.assertEqual('', self.host.blocks[-1].dest_labware)
        self.assertEqual('', self.host.v_dest_labware.get())
        with self.assertRaisesRegex(ValueError, 'destination labware'):
            self.host._build_lines()
        self.host._refresh_dest_labware_options()
        self.assertEqual('', self.host.v_dest_labware.get())
        popup = TecanBatchDialog(self.host)
        self.assertEqual('', popup.destination.get())
        with mock.patch.object(tecan, 'WellMapDialog') as dialog:
            popup.pick_destination(0, popup)
            dialog.assert_not_called()

    def test_new_gwl_resets_format_and_existing_snapshot_restores_it(self):
        existing = tecan.TransferBlock(dest_labware='Vial1.5_Rack1', chemical_name='BB1')
        entry = dict(name='Saved', path='', content='', mode='HPLC vials vertical',
                     blocks=[self.host._block_to_dict(existing)])
        self.host.exported_gwl_files[0] = entry
        self.host._load_gwl_entry(0, entry)
        self.assertEqual('HPLC vials vertical', self.host.mode_var.get())
        self.assertEqual('Vial1.5_Rack1', self.host.v_dest_labware.get())
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(tecan.messagebox, 'showinfo') as info, \
             mock.patch.object(self.host, '_confirm_gwl_switch_if_dirty', return_value=True), \
             mock.patch.object(tecan.simpledialog, 'askstring', return_value='New'), \
             mock.patch.object(tecan.filedialog, 'asksaveasfilename', return_value=str(Path(directory) / 'New.gwl')):
            self.host._new_blank_gwl()
            info.assert_called_once()
            self.assertIn('Add Block and Add Batch', info.call_args.args[1])
        self.assertEqual('', self.host.mode_var.get())
        self.assertTrue(self.host.add_block_button.instate(['disabled']))
        self.assertEqual('HPLC vials vertical', entry['mode'])
        self.host._load_gwl_entry(0, entry)
        self.assertEqual('HPLC vials vertical', self.host.mode_var.get())
        self.assertEqual('Vial1.5_Rack1', self.host.v_dest_labware.get())

    def test_batch_rejects_blank_labware_without_changing_blocks(self):
        popup = self.dialog(self.rows())
        popup.destination.set('')
        popup.apply()
        self.assertIn('destination labware', popup.status.get())
        self.assertEqual([], self.host.blocks)

    def test_blank_format_roundtrip_and_button_placement(self):
        self.host.mode_var.set('')
        saved = json.loads(json.dumps(self.host.export_state()))
        self.host.import_state(saved)
        self.assertEqual('', self.host.mode_var.get())
        self.assertTrue(self.host.add_block_button.instate(['disabled']))
        add = self.host.add_block_button.grid_info()
        batch = self.host.batch_addition_button.grid_info()
        self.assertEqual(add['row'], batch['row'])
        self.assertEqual(int(add['column']) + 1, int(batch['column']))

    def test_empty_gwl_does_not_inherit_another_files_format_on_import(self):
        self.host.exported_gwl_files.append(dict(name='Unconfigured', path='', content='', mode='', blocks=[]))
        self.host.mode_var.set('HPLC vials horizontal')
        saved = json.loads(json.dumps(self.host.export_state()))
        self.host.import_state(saved)
        self.assertEqual('', self.host.exported_gwl_files[1]['mode'])


if __name__ == '__main__':
    unittest.main()
