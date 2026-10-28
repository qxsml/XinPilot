"""One reaction plate, orientation-specific Tecan addressing."""
import json
import unittest
from unittest.mock import patch

from integrated_full_software import IntegratedFullApp
from tecan_frame import TransferBlock
from xinpilot.application.heatmap_layout import reaction_mode, heatmap_layout
from xinpilot.application.tecan_domain import parse_dest_well_expr, index_to_dest_label
from xinpilot.application.tecan_worklist import build_gwl_lines


class UnifiedPlateTests(unittest.TestCase):
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

    def transfers(self, size):
        prefix = 'HPLC vials' if size == 48 else '96-well'
        rows, worklists = [], []
        for orientation, volume in [('vertical', 10), ('horizontal', 20)]:
            mode = f'{prefix} {orientation}'
            block = TransferBlock(chemical_name='TEST', source_labware='Vial8Rack_1',
                                  source_well=1, source_volume=volume,
                                  dest_labware='ReactionPlate', dest_wells_expr='B2',
                                  dest_volume=volume, liquid_class='Water')
            worklists.append((mode, block, build_gwl_lines([block], mode)))
            rows.extend(self.app.tecan_tab._building_block_rows_from_blocks(
                [block], mode, include_all_chemicals=True, gwl_name=orientation+'.gwl'))
        return rows, worklists

    def test_all_wells_keep_identity_and_different_numeric_addresses(self):
        for prefix in ('HPLC vials', '96-well'):
            horizontal, vertical = prefix+' horizontal', prefix+' vertical'
            for row in heatmap_layout(horizontal)[2]:
                for well in row:
                    for mode in (horizontal, vertical):
                        index = parse_dest_well_expr(well, mode, 'ReactionPlate')[0]
                        self.assertEqual(index_to_dest_label(index, mode, 'ReactionPlate'), well)
            self.assertNotEqual(parse_dest_well_expr('B2', horizontal, 'ReactionPlate'),
                                parse_dest_well_expr('B2', vertical, 'ReactionPlate'))

    def test_mixed_orientation_push_repeat_roundtrip_clear_and_gwl_unchanged(self):
        for size in (48, 96):
            with self.subTest(size=size):
                self.chem.clear_for_next_synthesis_step()
                rows, worklists = self.transfers(size)
                original = json.loads(json.dumps(rows))
                self.chem.push_from_tecan(rows)
                self.chem.push_from_tecan(rows)
                self.assertEqual(len(self.chem.pushed_rows), 2)
                self.chem.import_state(json.loads(json.dumps(self.chem.export_state())))
                pushed = list(self.chem.pushed_rows.values())
                self.assertEqual({r['well'] for r in pushed}, {'B2'})
                self.assertEqual({r['dest_mode'] for r in pushed}, {r['dest_mode'] for r in original})
                mode, _, wells, tables = self.app.reaction_summary_tab._destination_summary([], pushed)
                self.assertIn('horizontal', mode)
                self.assertEqual(set(wells), {'B2'})
                self.assertEqual(sum(r['volume'] for group in tables.values() for r in group), 30)
                self.assertIn('horizontal', reaction_mode(pushed))
                for source_mode, block, before in worklists:
                    self.assertEqual(build_gwl_lines([block], source_mode), before)
                with patch.object(self.chem, '_ask_clear_pushed', return_value='all'):
                    self.chem._clear_pushed_rows()
                self.assertFalse(self.chem.pushed_rows)

    def test_all_routes_combine_in_either_push_order_and_reject_wrong_size(self):
        for size in (48, 96):
            for tecan_first in (True, False):
                with self.subTest(size=size, tecan_first=tecan_first):
                    self.chem.clear_for_next_synthesis_step()
                    rows, _ = self.transfers(size)
                    common = dict(well='B2', chemical='TEST', volume_uL=5,
                                  dest_mode=f'{size}-well horizontal', is_building_block=False)
                    if tecan_first:
                        self.chem.push_from_tecan(rows)
                    self.chem.push_from_manual([dict(common, source='Manual workflow')])
                    self.chem.push_from_opentrons([dict(common, source='Opentrons')])
                    self.chem.push_from_external([dict(common, source='External Import')])
                    if not tecan_first:
                        self.chem.push_from_tecan(rows)
                    pushed = list(self.chem.pushed_rows.values())
                    self.assertEqual(len(pushed), 5)
                    _, _, _, tables = self.app.reaction_summary_tab._destination_summary([], pushed)
                    self.assertEqual(sum(r['volume'] for group in tables.values() for r in group), 45)
                    before = json.dumps(list(self.chem.pushed_rows.values()), sort_keys=True)
                    with self.assertRaises(ValueError):
                        self.chem.push_from_manual([dict(common, dest_mode=f'{96 if size == 48 else 48}-well horizontal')])
                    self.assertEqual(json.dumps(list(self.chem.pushed_rows.values()), sort_keys=True), before)


if __name__ == '__main__':
    unittest.main()
