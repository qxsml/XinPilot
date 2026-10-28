import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rdkit import Chem
from toolkit.clogp_calculator.molecular_properties import assess, rule_values
from toolkit.clogp_calculator.clogp_calculator import CLogPCalculator


class PropertyTests(unittest.TestCase):
    def test_reference_descriptors(self):
        result = assess(Chem.MolFromSmiles('CCO'), True)
        self.assertAlmostEqual(float(result['MW (g/mol)']), 46.069, places=3)
        self.assertAlmostEqual(float(result['TPSA (A^2)']), 20.23, places=2)
        self.assertEqual((result['HBD'], result['HBA'], result['Rotatable bonds']), (1, 1, 0))
        self.assertEqual(result['Lipinski violations'], 0)
        self.assertEqual(result['Veber'], 'Within limits')
        self.assertTrue(0 < float(result['QED']) < 1)
        self.assertEqual(result['PAINS count'], 0)
        self.assertEqual(result['Brenk count'], 0)

    def test_threshold_boundaries_use_unrounded_values(self):
        self.assertEqual(rule_values(500, 5, 5, 10, 10, 140)['Lipinski violations'], 0)
        result = rule_values(500.0001, 5.0001, 6, 11, 11, 140.0001)
        self.assertEqual(result['Lipinski violations'], 4)
        self.assertEqual(result['Veber'], 'Outside limits')
        self.assertIn('TPSA > 140', result['Veber criteria exceeded'])

    def test_alert_identity_and_highlight_atoms(self):
        mol = Chem.MolFromSmiles('Oc1ccccc1O')
        result = assess(mol, True)
        self.assertGreaterEqual(result['PAINS count'], 1)
        self.assertGreaterEqual(result['Brenk count'], 1)
        for family in ('PAINS', 'Brenk'):
            alert = next(a for a in result['alerts'] if a['catalog'] == family and 'catechol' in a['name'])
            self.assertTrue(alert['atoms'])
            self.assertTrue(all(0 <= i < mol.GetNumAtoms() for i in alert['atoms']))
            self.assertEqual(sum(mol.GetAtomWithIdx(i).GetAtomicNum() == 8 for i in alert['atoms']), 2)

    def test_charged_rules_are_not_inferred(self):
        result = assess(Chem.MolFromSmiles('C[NH3+]'), False)
        self.assertEqual(result['QED'], '')
        self.assertEqual(result['Lipinski violations'], '')
        self.assertEqual(result['Veber'], '')
        self.assertTrue(result['MW (g/mol)'])


class PropertyGuiTests(unittest.TestCase):
    def setUp(self):
        self.app = CLogPCalculator([
            {'product_id': 'catechol', 'product_smiles': 'Oc1ccccc1O'},
            {'product_id': 'ethanol', 'product_smiles': 'CCO'},
            {'product_id': 'charged', 'product_smiles': 'C[NH3+]'},
            {'product_id': 'salt', 'product_smiles': 'CCO.[Na+]'},
            {'product_id': 'invalid', 'product_smiles': 'bad smiles'}])
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()

    def test_all_tabs_selection_alert_drawing_and_invalidation(self):
        app = self.app
        ids = app.tree.get_children()
        app.calculate_all()
        self.assertEqual(len(app.results), 3)
        self.assertEqual(app.results[ids[2]]['QED'], '')
        self.assertEqual(app.tree.item(ids[3], 'values')[4], '')
        self.assertEqual(len(app.notebook.tabs()), 4)
        app.alert_tree.selection_set(ids[0])
        app.update()
        self.assertEqual(app.tree.selection(), (ids[0],))
        self.assertTrue(app._alert_items)
        self.assertIsNotNone(app._preview_image)
        app.notebook.select(0)
        app.fields[3].set('CCO')
        app.update_row()
        self.assertNotIn(ids[0], app.results)
        self.assertEqual(app.rule_tree.set(ids[0], 'QED'), '')
        self.assertEqual(app.alert_tree.set(ids[0], 'PAINS count'), '')
        self.assertFalse(app._alert_items)
        app.delete_selected()
        for table in app.tables:
            self.assertFalse(table.exists(ids[0]))

    def test_export_counts_rules_and_missing_results(self):
        app = self.app
        ids = app.tree.get_children()
        app.property_tree.selection_set(ids[:2])
        app.update()
        app.calculate_selected()
        self.assertEqual(set(app.results), set(ids[:2]))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'properties.csv'
            with patch('tkinter.filedialog.asksaveasfilename', return_value=str(p)):
                app.export_csv()
            with p.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
        self.assertIn('catechol', rows[0]['PAINS alerts'])
        self.assertEqual(rows[1]['PAINS count'], '0')
        self.assertEqual(rows[2]['PAINS count'], '')
        self.assertEqual(rows[2]['QED'], '')
        self.assertIn('MW<=500', rows[0]['Rule definitions'])
        self.assertTrue(rows[0]['RDKit version'])


if __name__ == '__main__':
    unittest.main()
