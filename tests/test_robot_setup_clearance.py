"""Rack selection and conservative single-nozzle deck-clearance regressions."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opentrons_frame import OpentronsFrame
from xinpilot.application.opentrons_validation import validate_partial_nozzle_clearance
from xinpilot.application.opentrons_protocol import compile_protocol
from test_robot_review_fixes import request, transfer


class Value:
    def __init__(self, value): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class RobotSetupClearanceTests(unittest.TestCase):
    def test_changing_right_or_reselecting_left_keeps_left_rack(self):
        f = SimpleNamespace(robot_var=Value('OT-2'), left_pipette_var=Value('p300_single_gen2'),
            left_tiprack_var=Value('opentrons_96_tiprack_300ul'), right_pipette_var=Value('None'),
            right_tiprack_var=Value('opentrons_96_filtertiprack_20ul'))
        for mount in ('right', 'left'):
            OpentronsFrame._on_pipette_changed(f, mount)
            self.assertEqual('opentrons_96_tiprack_300ul', f.left_tiprack_var.get())
        f.left_pipette_var.set('p20_single_gen2')
        OpentronsFrame._on_pipette_changed(f, 'left')
        self.assertEqual('opentrons_96_filtertiprack_20ul', f.left_tiprack_var.get())
        f.left_pipette_var.set('p300_single_gen2')
        OpentronsFrame._on_pipette_changed(f, 'left')
        self.assertEqual('opentrons_96_filtertiprack_200ul', f.left_tiprack_var.get())

    def test_flex_compatible_custom_rack_choice_survives(self):
        f = SimpleNamespace(robot_var=Value('Flex'), left_pipette_var=Value('flex_8channel_1000'),
            left_tiprack_var=Value('opentrons_flex_96_tiprack_200ul'), right_pipette_var=Value('None'),
            right_tiprack_var=Value(''))
        OpentronsFrame._on_pipette_changed(f, 'left')
        self.assertEqual('opentrons_flex_96_tiprack_200ul', f.left_tiprack_var.get())

    def test_clearance_both_directions_and_empty_neighbor(self):
        for nozzle, target, blocker in [('H1', 'C1', 'B1'), ('A1', 'B2', 'C2')]:
            with self.subTest(nozzle=nozzle):
                args = dict(row_number=3, nozzle=nozzle, accessed_slots={'source':target})
                with self.assertRaisesRegex(ValueError, blocker):
                    validate_partial_nozzle_clearance(**args, occupied_slots={blocker:'tip rack'})
                validate_partial_nozzle_clearance(**args, occupied_slots={target:'source'})

    def test_compiler_rejects_partial_nozzle_with_overhanging_labware(self):
        req = request([transfer(dest_wells='A1')])
        req.pipettes['left']['name'] = 'flex_8channel_1000'
        # Source C1 overhangs B1; destination D1 overhangs occupied source C1.
        with self.assertRaisesRegex(ValueError, 'clearance'):
            compile_protocol(req)
        # Move destination into a separate column, leave the overhang lanes empty.
        req.labware_configs[1]['slot'] = 'C3'
        req.pipettes['left']['tiprack_slots'] = ['C2']
        self.assertIn("'nozzle_start': 'H1'", compile_protocol(req))

    def test_full_eight_channels_do_not_require_partial_nozzle_clearance(self):
        req = request([transfer(dest_wells=','.join(f'{r}1' for r in 'ABCDEFGH'))])
        req.pipettes['left']['name'] = 'flex_8channel_1000'
        self.assertIn("'nozzle_layout': 'all'", compile_protocol(req))

    def test_unused_rack_is_excluded_but_plate_moves_update_clearance(self):
        req = request([transfer(dest_wells='A1')])
        req.labware_configs[1]['slot'] = 'C3'
        req.pipettes['left'].update(name='flex_8channel_1000', tiprack_slots=['C2'])
        req.pipettes['right'] = dict(req.pipettes['left'], name='flex_1channel_1000', tiprack_slots=['B1'])
        # Right mount is not loaded by this protocol, so its rack is not an obstacle.
        compile_protocol(req)
        req.pipettes['right']['tiprack_slots'] = ['D1']
        req.rows.insert(0, transfer(pipette_key='right', dest_wells='A1',
            move_plate=True, move_labware_alias='dest1', move_to_slot='B1'))
        with self.assertRaisesRegex(ValueError, 'Row 2.*B1'):
            compile_protocol(req)


if __name__ == '__main__':
    unittest.main()
