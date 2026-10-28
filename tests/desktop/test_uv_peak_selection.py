"""UV selection regression, including the user's local RPT when available."""
import os,copy,importlib.util,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from peak_inspection import inspection_peak_indices,nearest_inspection_peak,eligible,peak_purity

class SelectionTests(unittest.TestCase):
    def test_spectrum_does_not_hide_integrated_peak_or_duplicate_area(self):
        well={'peaks':[dict(time=1.92,pStart=0,pEnd=0,area=0,areaAbs=0),
                       dict(time=1.93,pStart=1.90,pEnd=1.96,area=70,areaAbs=700),
                       dict(time=2.3,pStart=2.2,pEnd=2.4,area=30,areaAbs=300)],
              'exclude_ranges':[]}
        before=copy.deepcopy(well)
        self.assertEqual([1,2],inspection_peak_indices(well))
        self.assertEqual([0,1,2],inspection_peak_indices(well,True))
        self.assertEqual(1,nearest_inspection_peak(well,1.92))
        self.assertEqual(70,peak_purity(well,1))
        self.assertEqual(before,well)
        well['exclude_ranges']=[[1.9,1.96]]
        self.assertIn(1,inspection_peak_indices(well))
        self.assertFalse(eligible(well['peaks'][1],well['exclude_ranges']))

    def test_user_rpt_keeps_uv_integration(self):
        configured=os.environ.get('XINPILOT_PRIVATE_RPT')
        if not configured:self.skipTest('Set XINPILOT_PRIVATE_RPT for the optional original-data regression')
        path=Path(configured)
        if not path.exists():self.skipTest('Local user RPT unavailable')
        spec=importlib.util.spec_from_file_location('waters_selection_test',ROOT/'Modified PyParse/getWatersData.py')
        parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
        parser.init(SimpleNamespace(plate_row_no=8,plate_col_no=12,detector='UV',uv254_purity='True',points_per_trace=1000,min_uv_threshold=10,filter_by_rt=[]))
        table,*_=parser.getData(str(path))
        well={'peaks':list(table[26]),'exclude_ranges':[]}
        before=copy.deepcopy(well)
        ms=next(i for i,p in enumerate(well['peaks']) if p['time']==1.9231)
        index=nearest_inspection_peak(well,1.9231);uv=well['peaks'][index]
        self.assertNotIn(ms,inspection_peak_indices(well))
        self.assertEqual(1.9309,uv['time'])
        self.assertAlmostEqual(335.8187,uv['areaAbs'])
        self.assertTrue(eligible(uv,[]));self.assertEqual(before,well)
        report={'status':'PASS','well':'C2','spectrum_time':1.9231,'uv_peak_time':uv['time'],
                'uv_bounds':[uv['pStart'],uv['pEnd']],'areaAbs':uv['areaAbs'],'instrument_percent':uv['area'],
                'manual_purity_percent':peak_purity(well,index),'raw_data_unchanged':True}
        (ROOT/'artifacts/tests').mkdir(parents=True,exist_ok=True)
        (ROOT/'artifacts/tests/uv-selection-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':unittest.main()
