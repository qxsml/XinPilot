import json
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from integrated_full_software import IntegratedFullApp
from tecan_frame import TecanFrame, TransferBlock


class PushedSummaryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = IntegratedFullApp()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        for timer in cls.app.tk.call('after', 'info'):
            cls.app.tk.call('after', 'cancel', timer)
        cls.app.destroy()

    def setUp(self):
        self.chem = self.app.cheminformatics_tab
        self.chem.clear_for_next_synthesis_step()
        self.summary = self.app.reaction_summary_tab
        self.summary.temperature_var.set('25')

    def row(self, source, volume=10, block=1, building=False):
        return dict(source=source, block=block, well='A1', chemical='TEST',
                    volume_uL=volume, dest_labware='DeepPlate1',
                    dest_mode='96-well horizontal', is_building_block=building)

    def test_push_all_sources_repeat_and_clear(self):
        self.assertEqual([], self.summary._summary_transfer_rows([], [], opentrons_rows=[self.row('Opentrons')]))
        self.chem.push_from_tecan([self.row('Tecan')])
        self.chem.push_from_manual([self.row('Manual workflow', 20)])
        self.chem.push_from_opentrons([self.row('Opentrons', 30)])
        self.chem.push_from_tecan([self.row('Tecan', 15)])
        rows = self.summary._summary_transfer_rows([], [])
        self.assertEqual(3, len(rows))
        self.assertEqual(65, sum(r['volume_uL'] for r in rows))
        self.assertTrue(all(not r['is_building_block'] for r in rows))
        with patch.object(self.chem, '_ask_clear_pushed', return_value='all'):
            self.chem._clear_pushed_rows()
        self.assertEqual([], self.summary._summary_transfer_rows([], []))
        self.assertEqual('25', self.summary.temperature_var.get())

    def test_changed_plan_notice_and_building_block_filter(self):
        self.chem.push_from_manual([self.row('Manual workflow')])
        self.assertEqual('', self.app._pushed_plan_status())
        original = list(self.app.manual_tab.rows)
        try:
            self.app.manual_tab.rows.append(dict(reaction_well='A9', chemical_id='NEW', transfer_ul='2'))
            self.assertIn('Changed since last push', self.app._pushed_plan_status())
            self.assertEqual(1, len(self.summary._pushed_rows()))
        finally:
            self.app.manual_tab.rows = original
        building = self.row('Tecan', building=True)
        reagent = {**self.row('Manual workflow'), 'chemical': 'REAGENT'}
        selected = self.chem._unique_building_rows([building, dict(building), reagent])
        self.assertEqual(1, len(selected))
        self.assertEqual(20, selected[0]['volume_uL'])

    def test_repeated_additions_same_source_preserved_and_roundtrip(self):
        rows = [self.row('Manual workflow', 10), self.row('Manual workflow', 10)]
        self.chem.push_from_manual(rows)
        self.chem.push_from_manual(rows)
        self.assertEqual(2, len(self.chem.pushed_rows))
        self.chem.import_state(json.loads(json.dumps(self.chem.export_state())))
        pushed = self.summary._summary_transfer_rows([], [])
        self.assertEqual(2, len(pushed))
        _, _, _, tables = self.summary._destination_summary([], pushed)
        self.assertEqual(20, sum(r['volume'] for group in tables.values() for r in group))

    def test_tecan_snapshot_preserves_maps_without_native_reads(self):
        block = TransferBlock(chemical_name='TEST', dest_labware='DeepPlate1',
                              dest_wells_expr='A1,A2', dest_volume=5, source_volume=11)
        rows = self.app.tecan_tab._building_block_rows_from_blocks([block], '96-well horizontal',
                                                              include_all_chemicals=True, gwl_name='test.gwl')
        self.chem.push_from_tecan(rows)
        with patch.object(self.summary, '_exported_blocks', side_effect=AssertionError('Native read')):
            self.summary.refresh()
        blocks = self.summary._pushed_source_blocks(self.summary._pushed_rows())
        self.assertEqual(1, len(blocks))
        self.assertEqual(11, blocks[0]['block'].source_volume)

    def test_cancel_keep_results_roundtrip_then_clear_all(self):
        fixture = Path(__file__).parent / 'fixtures/peak-inspection-portable.zip'
        with ZipFile(fixture) as z:
            data = json.loads(z.read('project.json'))
        self.app._apply_project_data(data)
        self.chem.push_from_manual([self.row('Manual workflow')])
        # Import fixture again to use its generated products and numerical analysis.
        self.app._apply_project_data(data)
        if not self.chem.pushed_rows:
            item = self.row('Manual workflow')
            self.chem.pushed_rows[self.chem._pushed_key(item)] = item
        products = self.chem._pyparse_rows()
        self.assertTrue(products)
        peaks = json.loads(json.dumps(self.chem.peak_inspection_data))
        before = self.chem.export_state()
        with patch.object(self.chem, '_ask_clear_pushed', return_value=None):
            self.chem._clear_pushed_rows()
        self.assertEqual(before, self.chem.export_state())
        plans = self.app.manual_tab.export_state()
        with patch.object(self.chem, '_ask_clear_pushed', return_value='inputs'):
            self.chem._clear_pushed_rows()
        self.assertEqual({}, self.chem.pushed_rows)
        self.assertEqual(products, self.chem._pyparse_rows())
        self.assertEqual(peaks, self.chem.peak_inspection_data)
        state = json.loads(json.dumps(self.chem.export_state()))
        self.chem.import_state(state)
        self.assertEqual(products, self.chem._pyparse_rows())
        self.assertIn('previous inputs', self.chem.retained_results_var.get())
        with patch.object(self.chem, '_ask_clear_pushed', return_value='all'):
            self.chem._clear_pushed_rows()
        self.assertEqual([], self.chem._pyparse_rows())
        self.assertFalse(self.chem.peak_inspection_data)
        self.assertFalse(self.chem.portable_trace_paths)
        self.assertEqual(plans, self.app.manual_tab.export_state())


if __name__ == '__main__':
    unittest.main()
