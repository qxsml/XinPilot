import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manual_workflow_frame import ManualWorkflowFrame


class ManualDeleteRowsTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.frame = ManualWorkflowFrame(self.root, compound_provider=lambda: [])
        self.frame.rows = [
            dict(plate_size='96-well', reaction_well=well, chemical_id=chemical, transfer_ul='5')
            for well, chemical in [('A1', 'BB'), ('A1', 'CAT'), ('B1', 'BB'), ('C1', 'BASE')]]
        self.frame._refresh_table()

    def tearDown(self):
        self.frame.destroy()
        self.root.destroy()

    def test_nonadjacent_selected_additions_only_are_deleted(self):
        self.frame.tree.selection_set('0', '2')
        self.frame.delete_rows_button.invoke()
        self.assertEqual([('A1', 'CAT'), ('C1', 'BASE')],
                         [(r['reaction_well'], r['chemical_id']) for r in self.frame.rows])
        self.assertFalse(self.frame.tree.selection())
        self.assertEqual(2, len(self.frame.rows_for_cheminformatics()))

    def test_single_and_all_rows(self):
        self.frame.tree.selection_set('1')
        self.frame._remove_selected()
        self.assertEqual(['BB', 'BB', 'BASE'], [r['chemical_id'] for r in self.frame.rows])
        self.frame.tree.selection_set(*self.frame.tree.get_children())
        self.frame._remove_selected()
        self.assertEqual([], self.frame.rows)
        self.assertEqual((), self.frame.tree.get_children())

    @patch('manual_workflow_frame.messagebox.showwarning')
    def test_no_selection_does_not_delete(self, warning):
        before = list(self.frame.rows)
        self.frame._remove_selected()
        self.assertEqual(before, self.frame.rows)
        warning.assert_called_once()

    def test_below_clear_wells_in_same_column(self):
        button = self.frame.delete_rows_button
        clear = next(w for w in button.master.winfo_children()
                     if isinstance(w, ttk.Button) and w.cget('text') == 'Clear Wells')
        self.assertEqual(clear.grid_info()['column'], button.grid_info()['column'])
        self.assertEqual(int(clear.grid_info()['row']) + 1, int(button.grid_info()['row']))
        self.assertEqual('ew', button.grid_info()['sticky'])


if __name__ == '__main__':
    unittest.main()
