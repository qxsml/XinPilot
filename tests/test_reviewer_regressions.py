"""Independent reproductions of the November 2026 review's priority findings."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ReviewerRegressions(unittest.TestCase):
    def test_mitsunobu_acid_has_one_inverted_product(self):
        import integrated_tecan_compound_cheminformatics as core
        smarts = next(r['smarts'] for r in core.load_reactions() if r['id'] == 'mitsunobu')
        for alcohol in ('C[C@H](O)CC', 'C[C@@H](O)CC'):
            a, acid = (core.Chem.MolFromSmiles(s) for s in (alcohol, 'O=C(O)c1ccccc1'))
            products = core.run_reaction(smarts, a, acid)
            self.assertEqual(1, len(products))
            before = core.Chem.FindMolChiralCenters(a)[0][1]
            after = core.Chem.FindMolChiralCenters(core.Chem.MolFromSmiles(products[0]))[0][1]
            self.assertNotEqual(before, after)

    def test_every_pipette_has_tip_capacity_validation(self):
        from xinpilot.application.opentrons_domain import PIPETTE_MAX_UL, PIPETTE_TIPRACK_CAPACITIES
        from xinpilot.application.opentrons_validation import validate_used_pipette_tipracks
        self.assertEqual(set(PIPETTE_MAX_UL), set(PIPETTE_TIPRACK_CAPACITIES))
        for name, allowed in PIPETTE_TIPRACK_CAPACITIES.items():
            for capacity in (20, 50, 200, 300, 1000):
                with self.subTest(pipette=name, tips=capacity):
                    flex = name.startswith('flex')
                    cfg = dict(name=name, tiprack=f'opentrons_96_tiprack_{capacity}ul',
                               tiprack_slots=['A1' if flex else '1'], tip_start_column='1', tip_start_well='A1')
                    args = ([], 'D3', 'Flex' if flex else 'OT-2', {'left':cfg}, [{'pipette_key':'left'}], [])
                    if '96channel' in name or capacity not in allowed:
                        with self.assertRaises(ValueError): validate_used_pipette_tipracks(*args)
                    else:
                        self.assertEqual({'left'}, validate_used_pipette_tipracks(*args))

    def test_legacy_zero_exit_failure_report_is_detected(self):
        from xinpilot.application.analysis_jobs import analysis_failure
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.assertEqual('', analysis_failure(path))
            (path/'html_output.html').write_text('<h1>Unspecified error occurred</h1>')
            self.assertIn('failure', analysis_failure(path))
            (path/'html_output.html').write_text('<h1>Analysis complete</h1>')
            self.assertEqual('', analysis_failure(path))

    def test_gwl_external_change_and_unsaved_cancel_block_push(self):
        from tecan_frame import TecanFrame
        from xinpilot.application.tecan_domain import TransferBlock
        from xinpilot.application.tecan_worklist import build_gwl_lines
        from xinpilot.application.tecan_domain import PLATE_MODES
        mode=PLATE_MODES[0]
        block=TransferBlock(dest_wells_expr='A1',chemical_name='BB1')
        content='\n'.join(build_gwl_lines([block],mode))+'\n'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'plan.gwl';path.write_text(content)
            entry=dict(path=str(path),name=path.name,content=content)
            obj=SimpleNamespace(exported_gwl_files=[entry], labware_aliases={}, _active_gwl_index=0,
                _read_text_file=lambda p:p.read_text(), _current_gwl_has_unsaved_changes=lambda:False,
                _blocks_for_exported_gwl_entry=lambda i,e:(mode,[block],{}))
            with patch('tecan_frame.messagebox.showerror') as error, patch('tecan_frame.messagebox.askyesno',return_value=False):
                self.assertTrue(TecanFrame._prepare_gwls_for_push(obj))
                obj._current_gwl_has_unsaved_changes=lambda:True
                self.assertFalse(TecanFrame._prepare_gwls_for_push(obj))
                obj._current_gwl_has_unsaved_changes=lambda:False
                path.write_text(content.replace(';20.0;', ';19.0;'))
                self.assertFalse(TecanFrame._prepare_gwls_for_push(obj))
                self.assertIn('outside XinPilot',error.call_args.args[1])
                path.write_text(content)
                block.dest_wells_expr='B1'
                self.assertFalse(TecanFrame._prepare_gwls_for_push(obj))
                self.assertIn('disagree',error.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
