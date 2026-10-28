import unittest
import tkinter as tk
from xinpilot.application.heatmap_layout import heatmap_layout, reaction_mode
from reaction_summary_frame import PurityHeatMapCanvas


class HeatmapLayoutTests(unittest.TestCase):
    def test_recorded_formats(self):
        for mode, count in [('HPLC vials horizontal', 48), ('48-well horizontal', 48), ('24-well horizontal', 24), ('384-well horizontal', 384)]:
            resolved = reaction_mode([{'dest_mode': mode}])
            self.assertEqual(sum(map(len, heatmap_layout(resolved)[2])), count)
        self.assertEqual(reaction_mode([{'dest_map_style': '48 well'}]), '48-well horizontal')

    def test_compatible_aliases_and_conflicts(self):
        reaction_mode([{'dest_mode': 'HPLC vials horizontal'}, {'dest_mode': '48-well horizontal'}])
        with self.assertRaises(ValueError):
            reaction_mode([{'dest_mode': '48-well horizontal'}, {'dest_mode': '96-well horizontal'}])
        self.assertEqual(reaction_mode([{'dest_mode': 'HPLC vials vertical'}, {'dest_mode': 'HPLC vials horizontal'}]), 'HPLC vials horizontal')

    def test_vertical_positions(self):
        rows, cols, grid = heatmap_layout('HPLC vials vertical')
        self.assertEqual((rows[0], cols[0], grid[0][0], grid[-1][-1]), ('8', 'A', 'A8', 'F1'))

    def test_canvas_well_identity_and_default_lcms(self):
        root = tk.Tk()
        root.withdraw()
        try:
            for mode, count, first in [('HPLC vials horizontal', 48, 'A1'), ('HPLC vials vertical', 48, 'A8'), ('96-well horizontal', 96, 'A1'), ('384-well horizontal', 384, 'A1')]:
                canvas = PurityHeatMapCanvas(root, 'test', {'A1': 37}, mode=mode)
                self.assertEqual(len(canvas.item_to_well), count)
                self.assertEqual(next(iter(canvas.item_to_well.values())), first)
                self.assertEqual(canvas.values_by_well['A1'], 37)
                canvas.destroy()
            canvas = PurityHeatMapCanvas(root, 'LCMS', {})
            self.assertEqual(len(canvas.item_to_well), 96)
        finally:
            root.destroy()
