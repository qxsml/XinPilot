import csv
import io
import tempfile
import unittest
from pathlib import Path
from xinpilot.application.autolynx import HEADERS, load_methods, sample_csv


class AutoLynxTests(unittest.TestCase):
    def setUp(self):
        self.settings = dict(plate='2', format='96-well', MS_FILE='100-1200 3 min', INLET_FILE='LC method', PROCESS='OPENLYNX', PROCESS_PARAMS='method.olp', INJ_VOL='2')
        self.samples = [dict(reaction_name='RXN_B', pyparse_well='B1', reaction_well='A1'), dict(reaction_name='RXN_A', pyparse_well='A2', reaction_well='B2')]

    def test_fields_and_lcms_locations(self):
        text = sample_csv(self.samples, self.settings)
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(list(rows[0]), HEADERS)
        self.assertEqual(rows[0]['FILE_NAME'], 'RXN_A')
        self.assertEqual(rows[0]['SAMPLE_LOCATION'], '2:A,2')
        self.assertIn('"2:A,2"', text)
        self.assertEqual(rows[0]['INJ_VOL'], '2')
        self.assertEqual(rows[0]['ID'], '')
        self.settings['order'] = 'Down columns'
        self.assertEqual(list(csv.DictReader(io.StringIO(sample_csv(self.samples, self.settings))))[0]['FILE_NAME'], 'RXN_B')

    def test_reject_invalid_samples(self):
        for samples in ([], [dict(reaction_name='', pyparse_well='A1')], [dict(reaction_name='bad/name', pyparse_well='A1')], [dict(reaction_name='x', pyparse_well='')], [dict(reaction_name='x', pyparse_well='I1')], [self.samples[0], self.samples[0]]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                sample_csv(samples, self.settings)

    def test_volume_required_and_plate_size(self):
        for volume in ('', 'nan', 'inf', '-2', '0', 'abc'):
            with self.subTest(volume=volume), self.assertRaises(ValueError):
                sample_csv(self.samples, dict(self.settings, INJ_VOL=volume))
        with self.assertRaises(ValueError):
            sample_csv([dict(reaction_name='x', pyparse_well='H12')], dict(self.settings, format='48-well'))

    def test_template_imports_only_methods(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'example.csv'
            path.write_text(sample_csv(self.samples, self.settings), encoding='utf-8-sig')
            settings = load_methods(path)
            self.assertEqual(settings['PROCESS_PARAMS'], 'method.olp')
            for key in ('INJ_VOL', 'FILE_NAME', 'SAMPLE_LOCATION', 'plate'):
                self.assertNotIn(key, settings)
            path.write_text('MS_FILE,INLET_FILE\na,b\nx,b\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_methods(path)


if __name__ == '__main__':
    unittest.main()
