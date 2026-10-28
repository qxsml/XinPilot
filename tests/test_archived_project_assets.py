import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from archived_project_assets import package_archived_steps, resolve_archived_steps
from integrated_full_software import IntegratedFullApp


class ArchivedAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def state(self, name, portable=False):
        source = self.root / name
        (source / 'graphs').mkdir(parents=True)
        (source / 'graphs' / 'chroma-Product1-A1-uv254.png').write_bytes(b'example trace')
        (source / 'compoundtable.csv').write_text('name,g_smiles,best_well\nProduct1,CCO,A1\n')
        (source / 'original.rpt').write_text('must not be packaged')
        gwl = source / 'same.gwl'
        gwl.write_text('W;\n')
        (source / 'same_chemical_map.csv').write_text('A1,example\n')
        chem = {'modified_pyparse_result_dir': str(source), 'peak_inspection_data': {'wells': {'A1': {}}}}
        if portable:
            chem['portable_trace_paths'] = {'A1': {'modified_uv': str(source / 'graphs' / 'chroma-Product1-A1-uv254.png')}}
        return {'tecan': {'exported_gwl_files': [{'name': 'same.gwl', 'path': str(gwl), 'content': 'A;saved_snapshot\nW;\n'}]}, 'cheminformatics': chem}

    def test_two_steps_round_trip_without_sender_paths_and_reexport(self):
        payload = {'multistep_workflow': {'completed_steps': [
            {'step_number': 1, 'state': self.state('one', portable=True)},
            {'step_number': 2, 'state': self.state('two')},
        ]}}
        original = copy.deepcopy(payload)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            self.assertEqual([], package_archived_steps(zf, payload))
            zf.writestr('project.json', json.dumps(payload))
        self.assertNotIn('portable_assets', original['multistep_workflow']['completed_steps'][0]['state'])
        # Make all original paths unavailable without deleting any input files.
        (self.root / 'one').rename(self.root / 'one_moved')
        (self.root / 'two').rename(self.root / 'two_moved')
        receiver = self.root / 'receiver'
        with zipfile.ZipFile(buffer) as zf:
            self.assertFalse(any(name.endswith('.rpt') for name in zf.namelist()))
            self.assertEqual(2, sum(name.endswith('.gwl') for name in zf.namelist()))
            zf.extractall(receiver)
        imported = json.loads((receiver / 'project.json').read_text())
        resolve_archived_steps(imported, receiver, IntegratedFullApp._prepare_imported_gwl_entries)
        for step in imported['multistep_workflow']['completed_steps']:
            state = step['state']
            result = Path(state['cheminformatics']['modified_pyparse_result_dir'])
            self.assertTrue((result / 'graphs' / 'chroma-Product1-A1-uv254.png').is_file())
            self.assertTrue((result / 'compoundtable.csv').is_file())
            entry = state['tecan']['exported_gwl_files'][0]
            self.assertIn('saved_snapshot', Path(entry['portable_source_path']).read_text())
            self.assertTrue(Path(entry['portable_chemical_map_source_path']).is_file())
            self.assertEqual('', entry['path'])
            self.assertTrue(entry['requires_save_as'])
        second = io.BytesIO()
        with zipfile.ZipFile(second, 'w') as zf:
            self.assertEqual([], package_archived_steps(zf, imported))
            self.assertEqual(2, sum(name.endswith('.gwl') for name in zf.namelist()))

    def test_export_does_not_mutate_shared_history(self):
        history = [{'state': self.state('shared')}]
        payload = {'multistep_workflow': {'completed_steps': history}}
        original = copy.deepcopy(history)
        with zipfile.ZipFile(io.BytesIO(), 'w') as zf:
            package_archived_steps(zf, payload)
        self.assertEqual(original, history)
        self.assertIsNot(history, payload['multistep_workflow']['completed_steps'])

    def test_active_export_includes_archived_files(self):
        payload = {'tecan': {}, 'cheminformatics': {}, 'multistep_workflow': {'completed_steps': [{'state': self.state('archived')}]}}
        chem = SimpleNamespace(_cheminformatics_result_export_rows=lambda: [], _impurity_reaction_rows=lambda: [])
        with zipfile.ZipFile(io.BytesIO(), 'w') as zf:
            IntegratedFullApp._add_portable_project_assets(SimpleNamespace(cheminformatics_tab=chem), zf, payload)
            self.assertTrue(any(p.startswith('assets/steps/001/') and p.endswith('.gwl') for p in zf.namelist()))

    def test_resolver_rejects_paths_outside_extraction(self):
        outside = self.root / 'outside.png'
        outside.write_bytes(b'outside')
        receiver = self.root / 'receiver'
        receiver.mkdir()
        state = {'cheminformatics': {}, 'portable_assets': {'trace_manifest': {'A1': {'modified_uv': '../outside.png'}}, 'modified_pyparse_result_dir': '..'}}
        data = {'multistep_workflow': {'completed_steps': [{'state': state}]}}
        resolve_archived_steps(data, receiver, IntegratedFullApp._prepare_imported_gwl_entries)
        self.assertEqual({}, state['cheminformatics']['portable_trace_paths'])
        self.assertEqual('', state['cheminformatics']['modified_pyparse_result_dir'])

    def test_missing_legacy_files_are_reported(self):
        state = {'cheminformatics': {'modified_pyparse_result_dir': str(self.root / 'missing')}}
        payload = {'multistep_workflow': {'completed_steps': [{'state': state}]}}
        with zipfile.ZipFile(io.BytesIO(), 'w') as zf:
            warnings = package_archived_steps(zf, payload)
        self.assertEqual(1, len(warnings))
        self.assertIn('no available images', warnings[0])


if __name__ == '__main__':
    unittest.main()
