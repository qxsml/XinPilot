import unittest
from tkinter import ttk
from unittest.mock import patch

from integrated_full_software import IntegratedFullApp
from xinpilot_theme import configure_controls, COLORS
from xinpilot_shared import PRODUCT_SUMMARY_ROW_COLORS


def contrast(a, b):
    def luminance(color):
        values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    low, high = sorted((luminance(a), luminance(b)))
    return (high + 0.05) / (low + 0.05)


class InterfaceThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = IntegratedFullApp()
        cls.errors = []
        cls.app.report_callback_exception = lambda *_args: cls.errors.append(_args)
        cls.app.update()
        cls.app.state('normal')
        cls.app.geometry('1200x760+0+0')
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        for timer in cls.app.tk.call('after', 'info'):
            cls.app.tk.call('after', 'cancel', timer)
        cls.app.destroy()

    def test_action_and_navigation_text_meets_normal_text_contrast(self):
        style = ttk.Style(self.app)
        for name in ('FileAction.TButton', 'ChemAction.TButton', 'Danger.TButton', 'Toolkit.TMenubutton',
                     'Main.TNotebook.Tab', 'Chem.TNotebook.Tab', 'Treeview'):
            for state in ((), ('active',), ('pressed',), ('selected',)):
                fg = style.lookup(name, 'foreground', state)
                bg = style.lookup(name, 'background', state)
                with self.subTest(name=name, state=state):
                    self.assertGreaterEqual(contrast(fg, bg), 4.5)

    def test_keyboard_focus_is_visible_and_disabled_labels_keep_their_surface(self):
        style = ttk.Style(self.app)
        for name in ('FileAction.TButton', 'TEntry', 'TCombobox'):
            self.assertNotEqual(style.lookup(name, 'bordercolor'), style.lookup(name, 'bordercolor', ('focus',)))
        for name in ('ChemRegion.TLabel', 'ChemRegion.LiveEdit.TLabel', 'FileRegion.TLabel'):
            self.assertEqual(style.lookup(name, 'background'), style.lookup(name, 'background', ('disabled',)))

    def test_child_theme_setup_does_not_reset_the_root_theme(self):
        style = ttk.Style(self.app)
        with patch.object(ttk.Style, 'theme_use', side_effect=AssertionError('Theme reset')):
            configure_controls(self.app)
            self.app.compound_tab._configure_styles()
        self.assertEqual(style.layout('TNotebook.Tab'), style.layout('Main.TNotebook.Tab'))

    def test_tables_align_numbers_and_keep_scrollbars(self):
        self.assertEqual('e', str(self.app.compound_tab.tree.column('MW', 'anchor')))
        self.assertEqual('e', str(self.app.opentrons_tab.tree.column('volume', 'anchor')))
        self.app.nb.select(self.app.product_summary_tab)
        self.app.update()
        self.assertTrue(self.app.cheminformatics_tab.product_table_x_scrollbar.winfo_ismapped())

    def test_product_markings_are_not_replaced_by_zebra_stripes(self):
        chem = self.app.cheminformatics_tab
        rows = [{'reaction_name': 'Test A', 'reaction_well': 'A1', 'pyparse_well': 'A1'},
                {'reaction_name': 'Test B', 'reaction_well': 'A2', 'pyparse_well': 'A2'}]
        original = dict(chem.product_structure_row_colors)
        try:
            chem.product_structure_row_colors['lcms:A1'] = 'green'
            with patch.object(chem, '_pyparse_rows', return_value=rows):
                chem._refresh_product_structure_preview()
                self.assertIn('rowcolor_green', chem.product_structure_table.item('0', 'tags'))
                self.assertNotIn('even', chem.product_structure_table.item('0', 'tags'))
                self.assertIn('odd', chem.product_structure_table.item('1', 'tags'))
                self.assertEqual(PRODUCT_SUMMARY_ROW_COLORS['green'], str(chem.product_structure_table.tag_configure('rowcolor_green', 'background')))
        finally:
            chem.product_structure_row_colors = original
            chem._refresh_product_structure_preview()

    def test_opentrons_draft_highlight_tracks_the_actual_draft_flag(self):
        frame = self.app.opentrons_tab
        self.assertEqual(('incomplete',), frame._transfer_row_tags({'_draft': True}, 0))
        self.assertNotIn('incomplete', frame._transfer_row_tags({'_draft': 'false'}, 0))
        before = list(frame.rows)
        try:
            frame.rows = [frame._new_transfer_draft(batch=False)]
            frame._refresh_table()
            self.assertEqual(('incomplete',), frame.tree.item('0', 'tags'))
            self.assertIn('Incomplete', frame.tree.item('0', 'values')[0])
        finally:
            frame.rows = before
            frame._refresh_table()
        self.assertFalse(self.errors)

    def test_editing_message_and_structure_preview_fit_minimum_window(self):
        app = self.app
        app.nb.select(app.synthesis_tab)
        app._show_synthesis_editor('Opentrons')
        robot = app.opentrons_tab
        robot.transfer_mode_status_var.set('Editing single row 1. Edits stay in the project; Export Project saves a file.')
        app.update()
        label = robot.transfer_mode_status_label
        edge = robot.transfer_row_canvas.winfo_rootx() + robot.transfer_row_canvas.winfo_width()
        self.assertLessEqual(label.winfo_rootx() + label.winfo_width(), edge)
        self.assertLessEqual(int(label.cget('wraplength')), label.winfo_width())
        for control in (robot.show_structure_check, robot.building_block_check):
            self.assertLessEqual(control.winfo_rootx() + control.winfo_reqwidth(), edge)
        app.nb.select(app.product_summary_tab)
        app.update()
        self.assertGreaterEqual(app.cheminformatics_tab.product_structure_label.winfo_height(), 170)
