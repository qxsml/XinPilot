"""Exercise the normal modified analysis pipeline for optional product adducts."""
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_modified_pyparse_annotations import modified_pyparse as mp


class ProductAdductTests(unittest.TestCase):
    def test_switches_and_competing_integrations(self):
        expected = {(): [True,False,False,True], ('na',): [True,True,False,True],
                    ('nh4',): [True,False,True,True], ('na','nh4'): [True]*4}
        old = getattr(mp,'options',None)
        self.addCleanup(setattr,mp,'options',old)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rpt = root/'input.rpt'
            rpt.touch()
            plate = root/'map.csv'
            plate.write_text('well,desired product smiles\n' + ''.join(f'A{i},CCO\n' for i in range(1,5)))
            for keys, accepted in expected.items():
                with self.subTest(keys=keys):
                    peaks = {}
                    traces = {}
                    for well, masses in enumerate(([47.05], [69.03], [64.08], [47.05,69.03,64.08]),1):
                        peaks[well] = [dict(well=well,time=1,area=80,areaAbs=800,pStart=.9,pEnd=1.1,
                                            **{'MS+':[(mass,100) for mass in masses],'MS-':[],'UV':[],'peakID':1}),
                                       dict(well=well,time=2,area=20,areaAbs=200,pStart=1.9,pEnd=2.1,
                                            **{'MS+':[(69.03,100)],'MS-':[],'UV':[],'peakID':2})]
                        traces[well] = {'uv':[[0,.9,1,1.1,1.9,2,2.1,3],[0,0,80,0,0,20,0,0]],'ms_plus':[],'ms_minus':[]}
                    out=root/('run' + ''.join(keys))
                    args=['PyParse.py',str(rpt),str(plate),'-o',str(out),'-r','1','-c','4','-V','False','-u254','True','-spa','True','-ffi','False']
                    if keys: args += ['--product-adducts',*keys]
                    with patch.object(sys,'argv',args), patch.object(mp.getWatersData,'getData',return_value=[peaks,traces,{i:str(i) for i in peaks},{i:1000 for i in peaks}]):
                        mp.main()
                    for handler in list(logging.root.handlers):
                        if getattr(handler,'baseFilename','').startswith(str(root)):
                            handler.close()
                            logging.root.removeHandler(handler)
                    records=json.loads((out/'xinpilot_peaks.json').read_text())['targets']['CCO']
                    for i, expect in enumerate(accepted,1):
                        record=records[f'A{i}']
                        self.assertEqual(bool(record['peak_adducts'][0]),expect)
                        self.assertEqual(bool(record['assigned_peak_indices']),expect or 'na' in keys)
                        if record['assigned_peak_indices']:
                            self.assertGreater(record['automatic_purity'],0)
                    common=records['A4']['peak_adducts'][0]
                    self.assertEqual(set(common),{'[M+H]+'} | ({'[M+Na]+'} if 'na' in keys else set()) | ({'[M+NH4]+'} if 'nh4' in keys else set()))


    def test_one_centroid_in_two_windows_scores_once(self):
        from types import SimpleNamespace
        opts = SimpleNamespace(product_adducts=['na','nh4'],calc_higherions='False',
                               mass_abs_tol=.5,min_peak_area=0,min_rel_intensity_well=0,
                               min_rel_area_well=0,time_abs_tol=.01,min_massconf_threshold=1)
        compound=dict(type='Product',locations=[3],mass1=100,mass2=104.96,mass3=0,rt=0)
        peak=dict(time=1,area=100,areaAbs=200,pStart=.9,pEnd=1.1,UV=[],
                  **{'MS+':[(122.99,60),(300,40)],'MS-':[]})
        with patch.object(mp,'options',opts,create=True):
            hits=mp.findHits(compound,{3:[peak]})
        self.assertEqual([(h['well'],h['mass_conf']) for h in hits],[(3,60)])

    def test_options_and_evidence_survive_project_export(self):
        from desktop.live_engine import Controller
        import zipfile
        from xinpilot.application.project_archive import save_project_package
        engine=Controller()
        try:
            app=engine.app
            fixture=Path(__file__).parent/'fixtures/peak-inspection-portable.zip'
            with zipfile.ZipFile(fixture) as archive:
                state=json.loads(archive.read('project.json'))
            chem=state['cheminformatics']
            chem['peak_inspection_data']['missing_uv254'] = {'C7': {'sample': 'example'}}
            record=next(iter(chem['peak_inspection_data']['targets'].values()))['A1']
            record.update(assigned_peak_indices=[0],peak_adducts=[['[M+H]+','[M+Na]+'],[]])
            app._apply_project_data(state)
            runner=app.modified_pyparse_tab
            self.assertFalse(any(v.get() for v in runner.product_adduct_vars.values()))
            for var in runner.product_adduct_vars.values():
                var.set(True)
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'roundtrip.xinpilot.zip'
                save_project_package(path,app._project_payload(),package_assets=app._add_portable_project_assets)
                with zipfile.ZipFile(path) as archive:
                    restored=json.loads(archive.read('project.json'))
                app._apply_project_data(restored)
            self.assertTrue(all(v.get() for v in runner.product_adduct_vars.values()))
            returned=next(iter(app.cheminformatics_tab.peak_inspection_data['targets'].values()))['A1']
            self.assertEqual(returned['peak_adducts'],record['peak_adducts'])
            missing_row = {'pyparse_well': 'C7'}
            self.assertEqual(app.cheminformatics_tab._modified_pyparse_purity_for_row(missing_row), 'N/A')
            self.assertEqual(app.cheminformatics_tab._modified_pyparse_purity_display_for_row(missing_row),
                             'Unavailable (no UV254 chromatogram)')
        finally:
            engine.stop()
