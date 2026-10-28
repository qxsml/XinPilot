import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrated_full_software import IntegratedFullApp
from project_change_tracking import project_edit_state
from xinpilot.application.project_changes import ProjectChanges


class ProjectChangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = IntegratedFullApp()
        cls.app.withdraw()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        for token in cls.app.tk.splitlist(cls.app.tk.call('after', 'info')):
            cls.app.tk.call('after', 'cancel', token)
        cls.app.destroy()

    def setUp(self):
        self.app._mark_project_saved()

    def test_idle_and_navigation(self):
        app = self.app
        for tab in app.nb.tabs():
            if str(tab) != str(app.next_step_tab):
                app.nb.select(tab)
                app.update_idletasks()
        app.compound_tab.search_var.set('view only')
        app.reaction_summary_tab.show_reaction_schemes_var.set(True)
        self.assertFalse(app._check_project_changes(), app._change_check_error)

    def test_edits_and_revert(self):
        app = self.app
        old = app.reaction_summary_tab.temperature_var.get()
        app.reaction_summary_tab.temperature_var.set('130')
        self.assertTrue(app._check_project_changes())
        self.assertIn('Unsaved changes', app.title())
        app.reaction_summary_tab.temperature_var.set(old)
        self.assertFalse(app._check_project_changes())

    def test_manual_and_product_assignment(self):
        app = self.app
        app.manual_tab.rows.append({'reaction_well': 'A1', 'chemical_id': 'test'})
        self.assertTrue(app._check_project_changes())
        app.manual_tab.rows.pop()
        self.assertFalse(app._check_project_changes())
        app.cheminformatics_tab.product_peak_overrides['test'] = {'peak': 1}
        self.assertTrue(app._check_project_changes())
        app.cheminformatics_tab.product_peak_overrides.pop('test')
        self.assertFalse(app._check_project_changes())

    def test_module_config_and_revert(self):
        app = self.app
        var = app.opentrons_tab.temperature_module_target_var
        old = var.get(); var.set('42')
        self.assertTrue(app._check_project_changes())
        var.set(old)
        self.assertFalse(app._check_project_changes())

    def test_eight_channel_mode_is_saved_and_prompts_before_close(self):
        import tempfile

        app = self.app
        var = app.opentrons_tab.eight_channel_mode_var
        original = var.get()
        selected = 'Force single tip' if original != 'Force single tip' else 'Auto from wells'
        try:
            var.set(selected)
            self.assertTrue(app._check_project_changes())
            with patch.object(app, 'destroy') as destroy, patch(
                'integrated_full_software.messagebox.askyesnocancel', return_value=None
            ) as prompt:
                app._confirm_close()
                prompt.assert_called_once()
                destroy.assert_not_called()
            var.set(original)
            self.assertFalse(app._check_project_changes())
            var.set(selected)
            with tempfile.TemporaryDirectory() as tmp:
                saved = Path(tmp) / 'eight-channel.xinpilot.zip'
                with patch('integrated_full_software.filedialog.asksaveasfilename', return_value=str(saved)), patch(
                    'integrated_full_software.messagebox.showinfo'
                ), patch('integrated_full_software.messagebox.showerror') as error:
                    self.assertTrue(app._export_project())
                    error.assert_not_called()
                self.assertFalse(app._check_project_changes())
                var.set(original)
                app._mark_project_saved()
                with patch('integrated_full_software.filedialog.askopenfilename', return_value=str(saved)), patch(
                    'integrated_full_software.messagebox.showinfo'
                ), patch('integrated_full_software.messagebox.showerror') as error:
                    app._import_project()
                    error.assert_not_called()
                self.assertEqual(var.get(), selected)
                self.assertFalse(app._check_project_changes())
        finally:
            var.set(original)
            app._mark_project_saved()

    def test_close_clean_and_dirty_cancel(self):
        app = self.app
        with patch.object(app, 'destroy') as destroy, patch('integrated_full_software.messagebox.askyesnocancel') as prompt:
            app._confirm_close()
            destroy.assert_called_once(); prompt.assert_not_called()
        var = app.reaction_summary_tab.duration_var
        old = var.get(); var.set('4 h')
        with patch.object(app, 'destroy') as destroy, patch('integrated_full_software.messagebox.askyesnocancel', return_value=None) as prompt:
            app._confirm_close()
            prompt.assert_called_once(); destroy.assert_not_called()
        var.set(old)

    def test_failed_comparison_is_conservative(self):
        with patch('project_change_tracking.project_edit_state', side_effect=ValueError('test')):
            self.assertTrue(self.app._check_project_changes())
            self.assertIn('Changes not verified', self.app.title())
            self.app._mark_project_saved()
            self.assertTrue(self.app._project_dirty)

    def test_fingerprint_is_detached_and_key_order_independent(self):
        state = {'rows': [{'a': 1, 'b': 2}]}
        tracker = ProjectChanges(state)
        self.assertFalse(tracker.changed({'rows': [{'b': 2, 'a': 1}]}))
        state['rows'].clear()
        self.assertTrue(tracker.changed(state))
        tracker = ProjectChanges({('Tecan', 'A1'): {'chemical': 'BB1'}, 1: 'number', '1': 'text'})
        self.assertFalse(tracker.changed({'1': 'text', 1: 'number', ('Tecan', 'A1'): {'chemical': 'BB1'}}))

    def test_observer_does_not_export_or_write(self):
        app = self.app
        with patch.object(app.tecan_tab, 'export_state', side_effect=AssertionError('mutating export')), patch.object(app.cheminformatics_tab, 'export_state', side_effect=AssertionError('mutating export')):
            project_edit_state(app)

    def test_z_import_view_and_export_baselines(self):
        import tempfile
        app = self.app
        fixture = Path(__file__).parent / 'fixtures/peak-inspection-portable.zip'
        with patch('integrated_full_software.filedialog.askopenfilename', return_value=str(fixture)), patch.object(app.compound_tab, 'confirm_leave_compound_notes', return_value=True), patch('integrated_full_software.messagebox.askyesno', return_value=True), patch('integrated_full_software.messagebox.showinfo'), patch('integrated_full_software.messagebox.showerror') as error:
            app._import_project()
            error.assert_not_called()
        self.assertFalse(app._check_project_changes())
        for tab in app.nb.tabs():
            if str(tab) != str(app.next_step_tab):
                app.nb.select(tab); app.update_idletasks()
        self.assertFalse(app._check_project_changes())
        app.reaction_summary_tab.temperature_var.set('88')
        self.assertTrue(app._check_project_changes())
        with patch('integrated_full_software.filedialog.asksaveasfilename', return_value=''):
            self.assertFalse(app._export_project())
        self.assertTrue(app._check_project_changes())
        with tempfile.TemporaryDirectory() as tmp:
            with patch('integrated_full_software.filedialog.asksaveasfilename', return_value=str(Path(tmp) / 'saved.xinpilot.zip')), patch('integrated_full_software.messagebox.showinfo'), patch('integrated_full_software.messagebox.showerror') as error:
                self.assertTrue(app._export_project())
                error.assert_not_called()
            self.assertFalse(app._check_project_changes())
