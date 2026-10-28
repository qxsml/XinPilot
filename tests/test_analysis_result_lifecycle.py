"""Regression checks for job ownership and product-specific result invalidation."""
import copy
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
import tkinter as tk

from cheminformatics_frame import CheminformaticsFrame
from pyparse_runner_frame import PyParseRunnerFrame, _AnalysisJob, _pyparse_platemap_signature, _analysis_input_signature
from integrated_full_software import IntegratedFullApp


class AnalysisJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.map = self.root / 'map.csv'
        self.map.write_text('well,smiles\nA1,CCO\n')
        self.frame = object.__new__(PyParseRunnerFrame)
        self.frame._project_generation = 1
        self.frame.proc = None
        self.frame._set_run_controls = Mock()
        self.frame.status_label = SimpleNamespace(config=Mock())
        self.frame.log = SimpleNamespace(insert=Mock(), see=Mock())
        self.frame.result_context_callback = lambda: 'project-A-targets'
        self.frame.result_callback = Mock()
        self.frame.platemap_var = SimpleNamespace(get=lambda: str(self.map))
        self.frame.output_dir_var = SimpleNamespace(get=lambda: str(self.root / 'WRONG-new-folder'))
        self.job = _AnalysisJob(3, 1, self.root / 'actual-run-folder', 'product',
                               'project-A-targets', _pyparse_platemap_signature(str(self.map)), 0)
        self.frame._active_job = self.job

    def test_success_uses_original_folder_and_kind_despite_changed_display(self):
        self.frame.current_analysis_kind = 'impurity'
        self.frame._complete_job(self.job, 0, 1)
        self.frame.result_callback.assert_called_once_with(self.job.output_dir, 'product')

    def test_import_or_next_step_invalidates_running_job(self):
        self.frame.invalidate_pending_results()
        self.frame._complete_job(self.job, 0, 1)
        self.frame.result_callback.assert_not_called()
        self.frame._set_run_controls.assert_called_once_with(False)

    def test_changed_targets_or_modified_platemap_do_not_attach_results(self):
        for change in ('target', 'map'):
            with self.subTest(change=change):
                self.frame._active_job = self.job
                self.frame.result_context_callback = lambda: ('new-targets' if change == 'target' else 'project-A-targets')
                if change == 'map':
                    self.map.write_text('well,smiles\nA1,CCN\n')
                self.frame._complete_job(self.job, 0, 1)
                self.frame.result_callback.assert_not_called()

    def test_old_completion_cannot_clear_another_job(self):
        active = _AnalysisJob(4, 1, self.root / 'new', 'product', None, (), 0)
        self.frame._active_job = active
        self.frame._complete_job(self.job, 0, 1)
        self.assertIs(active, self.frame._active_job)
        self.frame._set_run_controls.assert_not_called()

    def test_rpt_changed_by_another_analysis_page_does_not_attach(self):
        original = self.root / 'original.rpt'
        original.write_text('original report')
        job = replace(self.job, input_signature=_analysis_input_signature(original))
        self.frame._active_job = job
        self.frame.input_data_var = SimpleNamespace(get=lambda: str(self.root / 'different.rpt'))
        self.frame._complete_job(job, 0, 1)
        self.frame.result_callback.assert_not_called()


class ProductInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.row = {'reaction_well': 'A1', 'pyparse_well': 'C1', 'desired product smiles': 'CCO'}
        self.other = {'reaction_well': 'A2', 'pyparse_well': 'C2', 'desired product smiles': 'CCO'}
        self.f = object.__new__(CheminformaticsFrame)
        f = self.f
        f._product_structure_manual_key = lambda row: row['reaction_well']
        f._lcms_target_for_row = lambda row: row['desired product smiles']
        f._pyparse_rows = lambda: [self.row, self.other]
        f.pushed_rows = {('manual', 'A1', 'reagent'): {'chemical': 'reagent', 'well': 'A1'}}
        f.impurity_exclusions = {}
        f.carried_impurity_sources = {}
        f.invalidated_product_analysis = {}
        f.pyparse_purity_by_well = {'C1': '70%', 'C2': '80%'}
        f.modified_pyparse_purity_by_well = {'C1': '70%', 'C2': '80%'}
        f.modified_pyparse_purity_by_product = {'CCO': {'C1': '70%', 'C2': '80%'}}
        f.modified_pyparse_conflicts_by_product = {'CCO': {'C1': 'conflict'}}
        f.product_peak_overrides = {'CCO': {'C1': {'peak_index': 0}, 'C2': {'peak_index': 1}}}
        f.peak_inspection_data = {'wells': {'C1': {'raw': 'retained'}, 'C2': {}},
                                  'targets': {'CCO': {'C1': {'automatic': {}}, 'C2': {'automatic': {}}}}}
        f.portable_trace_paths = {'C1': {'modified_uv': 'old.png', 'impurity_modified': 'impurity.png'},
                                  'C2': {'modified_uv': 'other.png'}}
        f.product_structure_manual_notes = {'A1': {'manual_purity': '70', 'comments': 'sample note'}}
        f.product_structure_uv_source_by_key = {'A1': 'pyparse'}
        f.lcms_target_smiles_by_well = {'A1': 'CCO', 'A2': 'CCO'}
        f.lcms_target_summaries_by_well = {'A1': 'target'}

    def test_changed_structure_detaches_old_assignments_preserves_other_wells_and_comments(self):
        self.assertTrue(self.f._on_product_structure_changed(self.row, 'CCN'))
        self.assertEqual('', self.f._product_structure_purity_for_row(self.row))
        self.assertNotIn('C1', self.f.pyparse_purity_by_well)
        self.assertEqual('80%', self.f.pyparse_purity_by_well['C2'])
        self.assertNotIn('C1', self.f.product_peak_overrides['CCO'])
        self.assertIn('C2', self.f.product_peak_overrides['CCO'])
        self.assertEqual({'comments': 'sample note'}, self.f.product_structure_manual_notes['A1'])
        self.assertEqual({'impurity_modified': 'impurity.png'}, self.f.portable_trace_paths['C1'])
        self.assertEqual({'modified_uv': 'other.png'}, self.f.portable_trace_paths['C2'])
        self.assertEqual({'raw': 'retained'}, self.f.peak_inspection_data['wells']['C1'])
        self.assertIsNone(self.f._peak_context(self.row)[2])

    def test_equivalent_smiles_do_not_clear_valid_results(self):
        before = copy.deepcopy(self.f.product_peak_overrides)
        self.assertFalse(self.f._on_product_structure_changed(self.row, 'OCC'))
        self.assertEqual(before, self.f.product_peak_overrides)
        self.assertEqual('CCO', self.f.lcms_target_smiles_by_well['A1'])

    def test_tuple_pushed_keys_and_target_mapping_are_supported_in_run_context(self):
        original = self.f.analysis_context_signature()
        self.row['pyparse_well'] = 'C3'
        self.assertNotEqual(original, self.f.analysis_context_signature())

    def test_fresh_analysis_unblocks_only_matching_source(self):
        self.f._on_product_structure_changed(self.row, 'CCN')
        self.row['desired product smiles'] = 'CCN'
        self.f._accept_fresh_analysis('modified', {'C1': '50%'})
        self.assertTrue(self.f._analysis_is_invalidated(self.row, 'modified'))
        self.f.modified_pyparse_purity_by_product['CCN'] = {'C1': '50%'}
        self.f._accept_fresh_analysis('modified', {'C1': '50%'})
        self.assertFalse(self.f._analysis_is_invalidated(self.row, 'modified'))
        self.assertTrue(self.f._analysis_is_invalidated(self.row, 'pyparse'))


class ProductInvalidationRoundTripTests(unittest.TestCase):
    def test_corrected_imported_product_does_not_regain_old_result_on_import(self):
        app = IntegratedFullApp()
        app.withdraw()
        try:
            fixture = Path(__file__).parent / 'fixtures' / 'peak-inspection-portable.zip'
            with tempfile.TemporaryDirectory() as directory, patch('integrated_full_software.OUTPUT_DIR', Path(directory)):
                data, _ = app._load_project_package(fixture)
                app._apply_project_data(data)
                f = app.cheminformatics_tab
                old = dict(f._pyparse_rows()[0])
                well = old['reaction_well']
                self.assertTrue(f._product_structure_purity_for_row(old))
                f.imported_product_details[well] = dict(f.imported_product_details.get(well, {}), **{'desired product smiles': 'CCN'})
                self.assertTrue(f._on_product_structure_changed(old, 'CCN'))
                saved = f.export_state()
                f.import_state(saved)
                corrected = next(row for row in f._pyparse_rows() if row['reaction_well'] == well)
                self.assertEqual('', f._product_structure_purity_for_row(corrected))
                self.assertTrue(f._analysis_is_invalidated(corrected, 'modified'))
                self.assertTrue(all(path is None for path in f._product_trace_paths(corrected).values()))
                self.assertIsNone(f._peak_context(corrected)[2])
        finally:
            for timer in app.tk.call('after', 'info'):
                app.tk.call('after', 'cancel', timer)
            app.destroy()


if __name__ == '__main__':
    unittest.main()
