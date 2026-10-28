"""Regression cases for incorrect values, stale results, and imported assets."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'toolkit' / 'solution_calculator'))
from solution_calculations import prepare_stock, required_amount
from solution_calculator import SolutionCalculatorApp, MODE_PREPARE, MODE_CHECK, MODE_REQUIRED, product_to_batch_row
from compound_notes_frame import CompoundNotesFrame
from integrated_full_software import IntegratedFullApp
from manual_workflow_frame import ManualWorkflowFrame
from opentrons_frame import OpentronsFrame
from tecan_frame import gwl_a_line, gwl_d_line
from multistep_workflow import parse_percent, build_product_candidate, select_candidates_by_threshold


class NumericAccuracyTests(unittest.TestCase):
    def test_robot_numeric_validators_reject_nonfinite_values(self):
        for validator in (OpentronsFrame._required_positive_float, OpentronsFrame._optional_positive_float,
                          OpentronsFrame._optional_nonnegative_float, OpentronsFrame._optional_nonnegative_float_or_none):
            for value in ('nan', 'inf', '-inf'):
                with self.subTest(validator=validator.__name__, value=value), self.assertRaises(ValueError):
                    validator(value, 'Transfer setting')
        self.assertEqual(0, OpentronsFrame._optional_nonnegative_float_or_none(0, 'Delay'))
        self.assertIsNone(OpentronsFrame._optional_nonnegative_float_or_none('', 'Delay'))

    def test_gwl_never_emits_nonfinite_or_zero_rounded_volume(self):
        for emitter in (gwl_a_line, gwl_d_line):
            for value in (float('nan'), float('inf'), -1, 0, 0.01):
                with self.subTest(emitter=emitter.__name__, value=value), self.assertRaises(ValueError):
                    emitter('Plate1', 1, value, 'Water')
        self.assertEqual('A;Plate1;;;1;;10.0;Water;;;', gwl_a_line('Plate1', 1, 10, 'Water'))

    def test_numeric_zero_purity_is_a_valid_measurement(self):
        self.assertEqual(0.0, parse_percent(0))
        candidate = build_product_candidate({'reaction_well': 'A1'}, 0, 'Manual')
        self.assertEqual('0', candidate['purity'])
        self.assertEqual([candidate], select_candidates_by_threshold([candidate], 0))
        invalid = [{'purity_percent': value} for value in (None, 'bad', -1, 101, float('inf'), float('nan'))]
        self.assertEqual([], select_candidates_by_threshold(invalid, 0))

    def test_stock_calculator_rejects_nonfinite_inputs(self):
        defaults = dict(amount=10, amount_unit='mg', molecular_weight=500,
                        target_concentration=10, concentration_unit='mM',
                        mass_purity_percent=100, rounding_increment_ul=0)
        for field in ('amount', 'molecular_weight', 'target_concentration', 'mass_purity_percent', 'rounding_increment_ul'):
            for value in ('nan', 'inf', '-inf', '1e999'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    prepare_stock(**{**defaults, field: value})

    def test_finite_inputs_cannot_produce_infinite_or_zero_results(self):
        with self.assertRaises(ValueError):
            prepare_stock(amount='1e308', amount_unit='umol', target_concentration='1e-308', concentration_unit='mM')
        with self.assertRaises(ValueError):
            required_amount(target_concentration='1e-300', concentration_unit='uM',
                            final_volume='1e-300', volume_unit='uL', molecular_weight=100)

    def test_compound_notes_rejects_negative_mw_in_umol_mode_atomically(self):
        frame = object.__new__(CompoundNotesFrame)
        for mw in ('-10', '0', 'nan', 'inf'):
            values = {'Quantity input unit': 'umol', 'Quantity(umol)': '10', 'Conc.': '0.1', 'MW': mw}
            before = dict(values)
            with self.subTest(mw=mw), self.assertRaises(ValueError):
                frame._calculate_record_values(values)
            self.assertEqual(before, values)

    def test_manual_concentration_accepts_scientific_and_micro_units(self):
        for text, expected in [('1e-3', 0.001), ('2.5e1 mM', 0.025), ('25 µM', 0.000025), ('25 μM', 0.000025)]:
            with self.subTest(text=text):
                self.assertAlmostEqual(expected, ManualWorkflowFrame._record_concentration_m({'Conc.': text}))
        self.assertEqual('0.04', ManualWorkflowFrame._volume_from_umol_and_conc('0.02', 0.5))
        self.assertEqual('', ManualWorkflowFrame._volume_from_umol_and_conc('nan', 0.5))

    def test_manual_assignments_reject_nonfinite_volume_before_writing_rows(self):
        frame = object.__new__(ManualWorkflowFrame)
        for value in ('nan', 'inf', '-inf'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                frame._different_reagent_rows(['A1'], ['BB1'], [True], transfer_ul=value)


class CalculatorUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.app = SolutionCalculatorApp()
        self.app.withdraw()
        self.app.update()

    def tearDown(self):
        self.app.update_idletasks()
        self.app.destroy()

    def test_changed_input_disables_copy_and_removes_old_result(self):
        app = self.app
        app.single_amount_unit_var.set('umol')
        app.single_amount_var.set('10')
        app._calculate_single()
        self.assertTrue(app._single_result_valid)
        app.single_concentration_var.set('20')
        self.assertFalse(app._single_result_valid)
        self.assertIn('disabled', app.single_copy_button.state())
        self.assertNotIn('1000', app.single_result.get('1.0', 'end'))
        with patch.object(app, 'clipboard_clear') as clear:
            app._copy_single_result()
            clear.assert_not_called()

    def test_failed_calculation_does_not_leave_previous_result(self):
        app = self.app
        app.single_amount_unit_var.set('umol')
        app.single_amount_var.set('10')
        app._calculate_single()
        app.single_amount_var.set('nan')
        with patch('solution_calculator.messagebox.showerror'):
            app._calculate_single()
        self.assertFalse(app._single_result_valid)
        self.assertIn('Cannot calculate', app.single_result.get('1.0', 'end'))

    def test_modes_disable_only_unused_inputs_without_erasing_values(self):
        app = self.app
        app.single_volume_var.set('2.5')
        for mode, disabled in [(MODE_PREPARE, (False, False, True)),
                               (MODE_CHECK, (False, True, False)),
                               (MODE_REQUIRED, (True, False, False))]:
            app.mode_var.set(mode)
            for widgets, expected in zip((app.single_amount_widgets, app.single_concentration_widgets, app.single_volume_widgets), disabled):
                self.assertEqual(expected, 'disabled' in widgets[0].state())
            self.assertEqual('2.5', app.single_volume_var.get())

    def test_common_settings_recalculate_both_batches_and_clear_invalid_results(self):
        app = self.app
        row = product_to_batch_row({'product_id': 'P1', 'product_mw': '500'})
        row.update(amount='10', amount_unit='umol', target_mm='10', mass_purity='100', rounding_ul='0')
        app._calculate_row(row)
        self.assertEqual('1000', row['final_volume_ul'])
        app.batch_rows = [row]
        app.batch_common_target_var.set('20')
        app._apply_common_settings()
        self.assertEqual('500', row['final_volume_ul'])
        app.import_batch_rows = [copy.deepcopy(row)]
        app.import_common_target_var.set('40')
        app.import_common_amount_unit_var.set('umol')
        app._apply_import_common_settings()
        self.assertEqual('250', app.import_batch_rows[0]['final_volume_ul'])
        app.batch_common_target_var.set('nan')
        app._apply_common_settings()
        self.assertEqual('', row['final_volume_ul'])
        self.assertNotEqual('Ready', row['status'])


class ProjectAccuracyTests(unittest.TestCase):
    def test_invalid_project_is_rejected_before_extraction(self):
        app = object.__new__(IntegratedFullApp)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'bad.zip'
            with zipfile.ZipFile(path, 'w') as zf:
                zf.writestr('project.json', '[]')
            with patch('integrated_full_software.OUTPUT_DIR', root / 'outputs'), self.assertRaisesRegex(ValueError, 'JSON object'):
                app._load_project_package(path)
            self.assertFalse((root / 'outputs').exists())

    def test_bundled_result_directory_must_stay_inside_package(self):
        app = object.__new__(IntegratedFullApp)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outside = root / 'unrelated_results'
            outside.mkdir()
            for reference, expected in [(str(outside), False), ('../../unrelated_results', False), ('assets/results', True)]:
                path = root / 'project.zip'
                with zipfile.ZipFile(path, 'w') as zf:
                    zf.writestr('project.json', json.dumps({'version': 1, 'portable_assets': {'pyparse_result_dir': reference}, 'cheminformatics': {}}))
                    zf.writestr('assets/results/result.csv', 'sample\nA1\n')
                with patch('integrated_full_software.OUTPUT_DIR', root / 'outputs'):
                    data, extracted = app._load_project_package(path)
                resolved = data['cheminformatics'].get('pyparse_result_dir')
                self.assertEqual(expected, bool(resolved))
                if resolved:
                    self.assertTrue(Path(resolved).is_relative_to(extracted))
