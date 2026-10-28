import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from toolkit.clogp_calculator.clogp_calculator import calculate, load_payload, SCHEMA, CLogPCalculator
from integrated_full_software import IntegratedFullApp
import tools_launcher

class CLogPTests(unittest.TestCase):
    def test_known_values_and_invalid_structures(self):
        self.assertAlmostEqual(float(calculate('CCO')[0]), -0.001, places=3)
        self.assertAlmostEqual(float(calculate('c1ccccc1')[0]), 1.687, places=3)
        for smiles in ('', 'invalid', '[Na+].[Cl-]', 'C[NH3+]', 'CCO.O'):
            self.assertEqual(calculate(smiles)[0], '')

    def test_transfer_and_cleanup(self):
        fake = SimpleNamespace(current_project_name='Example', current_synthesis_step=1)
        payload = IntegratedFullApp._clogp_calculator_payload(fake, [{'product_id':'P1', 'product_smiles':'CCO'}])
        self.assertEqual(payload['schema'], SCHEMA)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'payload.json'
            p.write_text(json.dumps(payload), encoding='utf-8')
            self.assertEqual(load_payload(p)[0]['product_smiles'], 'CCO')
            self.assertFalse(p.exists())

    def test_send_all_manual_auto_and_failed_launch_cleanup(self):
        from test_solution_calculator_integration import _SendProbe
        class Probe(_SendProbe):
            _send_products_to_clogp_calculator = IntegratedFullApp._send_products_to_clogp_calculator
            _clogp_calculator_payload = IntegratedFullApp._clogp_calculator_payload
            _write_clogp_calculator_payload = IntegratedFullApp._write_clogp_calculator_payload
        for mode, expected in (("all", 2), ("manual", 1), ("auto", 1)):
            probe = Probe(mode)
            probe.manual_selection = [1]
            probe.threshold = 50
            with patch('integrated_full_software.launch_clogp_calculator', return_value=True) as launch:
                self.assertTrue(probe._send_products_to_clogp_calculator())
                products = load_payload(launch.call_args.args[0])
            self.assertEqual(len(products), expected)
            self.assertEqual(probe.compound_records, ["unchanged"])
            self.assertEqual(probe.current_synthesis_step, 3)
            self.assertFalse(probe._solution_calculator_dialog_active)
        probe = Probe()
        with patch('integrated_full_software.launch_clogp_calculator', return_value=False) as launch:
            self.assertFalse(probe._send_products_to_clogp_calculator())
            self.assertFalse(Path(launch.call_args.args[0]).exists())

    def test_source_and_frozen_launch(self):
        with patch.object(tools_launcher.subprocess,'Popen') as popen:
            self.assertTrue(tools_launcher.launch_clogp_calculator('example.json'))
            self.assertTrue(Path(popen.call_args.args[0][1]).is_file())
            self.assertEqual(popen.call_args.args[0][-2:], ['--input','example.json'])
        with patch.object(tools_launcher.sys,'frozen',True,create=True), patch.object(tools_launcher.subprocess,'Popen') as popen:
            self.assertTrue(tools_launcher.launch_clogp_calculator())
            self.assertEqual(popen.call_args.args[0][1:],['--xinpilot-run-tool','clogp-calculator'])

    def test_gui_selection_edit_import_export(self):
        app=CLogPCalculator([{'product_id':'P1','product_smiles':'CCO'},{'product_id':'P2','product_smiles':'c1ccccc1'}])
        app.withdraw()
        try:
            ids=app.tree.get_children()
            app.tree.selection_set(ids[0]); app.update()
            app.calculate_selected()
            self.assertEqual(app.tree.item(ids[0],'values')[4],'-0.001')
            self.assertEqual(app.tree.item(ids[1],'values')[4],'')
            app.calculate_all()
            self.assertEqual(app.tree.item(ids[1],'values')[4],'1.687')
            app.fields[3].set('CC'); app.update_row()
            self.assertEqual(app.tree.item(ids[0],'values')[4],'')
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'results.csv'
                with patch('tkinter.filedialog.asksaveasfilename',return_value=str(p)):
                    app.export_csv()
                with p.open(encoding='utf-8-sig',newline='') as f:
                    rows=list(csv.DictReader(f))
                self.assertEqual(rows[1]['SMILES'],'c1ccccc1')
                self.assertIn('Wildman-Crippen',rows[1]['Method'])
                with patch('tkinter.filedialog.askopenfilename',return_value=str(p)):
                    app.import_csv()
                self.assertEqual(len(app.tree.get_children()),4)
        finally:
            app.destroy()

if __name__=='__main__': unittest.main()
