import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from integrated_full_software import IntegratedFullApp
from peak_inspection import PeakInspectionMixin
from toolkit.clogp_calculator.clogp_calculator import load_payload


class BrandingCompatibilityTests(unittest.TestCase):
    def test_new_and_legacy_project_titles(self):
        for extension in ('.xinpilot.zip', '.rxnpilot.zip', '.syntrack.zip', '.oneclick.zip', '.oneclick.json'):
            self.assertEqual(IntegratedFullApp._project_name_from_path('Example' + extension), 'Example')

    def test_legacy_calculator_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'legacy.json'
            for brand in ('xinpilot', 'rxnpilot', 'syntrack'):
                p.write_text(json.dumps({'schema': brand + '_clogp_calculator.v1',
                                        'products': [{'product_smiles': 'CCO'}]}), encoding='utf-8')
                self.assertEqual(load_payload(p)[0]['product_smiles'], 'CCO')

    def test_legacy_analysis_bundle_and_new_precedence(self):
        probe = SimpleNamespace(_peak_reset=lambda: None, logw=lambda _: None)
        with tempfile.TemporaryDirectory() as folder, patch('peak_inspection.validate_data', side_effect=lambda d: d):
            p = Path(folder)
            (p / 'syntrack_peaks.json').write_text('{"legacy": true}', encoding='utf-8')
            PeakInspectionMixin._peak_load(probe, folder)
            self.assertTrue(probe.peak_inspection_data['legacy'])
            (p / 'rxnpilot_peaks.json').write_text('{"rxnpilot": true}', encoding='utf-8')
            PeakInspectionMixin._peak_load(probe, folder)
            self.assertTrue(probe.peak_inspection_data['rxnpilot'])
            (p / 'xinpilot_peaks.json').write_text('{"new": true}', encoding='utf-8')
            PeakInspectionMixin._peak_load(probe, folder)
            self.assertTrue(probe.peak_inspection_data['new'])

    def test_default_export_extension(self):
        source = Path(__file__).resolve().parents[1] / 'integrated_full_software.py'
        text = source.read_text(encoding='utf-8')
        self.assertIn('defaultextension=".xinpilot.zip"', text)
        self.assertIn('*.syntrack.zip', text)
        self.assertIn('*.rxnpilot.zip', text)

    def test_rxnpilot_tecan_settings_fallback_and_new_precedence(self):
        import tecan_frame as tecan
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            old_labware, new_labware = p/'old_labware.json', p/'new_labware.json'
            old_liquid, new_liquid = p/'old_liquid.json', p/'new_liquid.json'
            old_labware.write_text(json.dumps({'labware_aliases': {'Vial8Rack_1': 'Saved rack'}}))
            old_liquid.write_text(json.dumps({'liquid_classes': ['Saved class']}))
            with patch.multiple(tecan, LABWARE_NAME_SETTINGS_PATH=new_labware,
                                RXNPILOT_LABWARE_NAME_SETTINGS_PATH=old_labware,
                                LEGACY_LABWARE_NAME_SETTINGS_PATH=p/'missing.json',
                                LIQUID_CLASS_SETTINGS_PATH=new_liquid,
                                RXNPILOT_LIQUID_CLASS_SETTINGS_PATH=old_liquid):
                self.assertEqual(tecan.TecanFrame._load_labware_aliases(None)['Vial8Rack_1'], 'Saved rack')
                self.assertEqual(tecan.TecanFrame._load_liquid_classes(None), ['Saved class'])
                new_labware.write_text(json.dumps({'labware_aliases': {'Vial8Rack_1': 'New rack'}}))
                new_liquid.write_text(json.dumps({'liquid_classes': ['New class']}))
                self.assertEqual(tecan.TecanFrame._load_labware_aliases(None)['Vial8Rack_1'], 'New rack')
                self.assertEqual(tecan.TecanFrame._load_liquid_classes(None), ['New class'])


if __name__ == '__main__':
    unittest.main()
