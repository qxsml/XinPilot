"""Drive project import and scientific display through renderer events."""
import concurrent.futures,json,time,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
(ROOT/'artifacts/tests').mkdir(parents=True,exist_ok=True)
from desktop.live_app import LiveBridge
b=LiveBridge();pool=concurrent.futures.ThreadPoolExecutor(max_workers=3)
def flat(n):
    yield n
    for c in n['children']:yield from flat(c)
def snapshot():
    s=b.snapshot()
    assert not s['errors'],s['errors']
    return s
def nodes():return [n for w in snapshot()['windows'] for n in flat(w)]
def wait_for(probe, description, timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=probe()
        if value:return value
        time.sleep(.1)
    raise AssertionError('Timed out waiting for '+description)
def button(label):return next(n for n in nodes() if n['kind'] in ('Button','TButton') and n['text']==label)
def click(label):return pool.submit(b.event,{'action':'invoke','id':button(label)['id']})
def tab(label):
    ns=nodes();nb=next(n for n in ns if n['kind']=='TNotebook')
    t=next(t for t in nb['tabs'] if t.get('label')==label or t['text']==label)
    b.event({'action':'tab','id':nb['id'],'tab':t['id']});time.sleep(.5)
report={}
try:
    fixture=ROOT/'tests/fixtures/peak-inspection-portable.zip'
    job=click('Import Project');deadline=time.monotonic()+60;prompts=[]
    while time.monotonic()<deadline:
        s=snapshot();d=s.get('dialog')
        if d:
            prompts.append({'kind':d['kind'],'message':d.get('message','')})
            value=str(fixture) if d['kind']=='askopenfilename' else True if d['kind'] in ('askyesno','askokcancel') else 'ok'
            b.event({'action':'answer','id':d['id'],'value':value})
        if job.done():job.result();break
        time.sleep(.15)
    else:raise AssertionError('Import did not finish')
    report['import_prompts']=prompts
    tab('Product Summary')
    # Projection/layout can finish after the tab event returns. Wait for the
    # imported rows rather than assuming a fixed half-second is sufficient.
    tables=wait_for(lambda:[n for n in nodes() if n['kind']=='Treeview' and n['rows']], 'imported product rows')
    report['product_tables']=[{'columns':n['columns'],'rows':n['rows']} for n in tables]
    assert tables
    b.event({'action':'selection','id':tables[0]['id'],'items':[tables[0]['rows'][0]['id']]});time.sleep(.8)
    report['product_image_widgets']=[{'id':n['id'],'width':n['width'],'height':n['height']} for n in nodes() if n.get('image')]
    report['product_canvas_images']=sum(1 for n in nodes() for item in n.get('items',[]) if item['type']=='image' and item['props'].get('image'))
    report['product_labels']=[{'text':n['text'],'id':n['id'],'image':n.get('image')} for n in nodes() if n['kind'] in ('Label','TLabel')]
    assert len(report['product_image_widgets'])>=2
    labels=report['product_labels'];title=next(n for n in labels if n['text'].startswith('UV trace from Modified'));trace=next(n for n in nodes() if n['id']==labels[labels.index(title)+1]['id'])
    future=pool.submit(b.event,{'action':'pointer','id':trace['id'],'sequence':'<Button-1>','x':trace['width']//2,'y':trace['height']//2})
    wait_for(lambda:any(n['kind']=='TButton' and n['text']=='Assign as product' for n in nodes()), 'peak inspection assignment controls')
    report['peak_dialogs']=[w.get('title') for w in snapshot()['windows'][1:]]
    report['peak_buttons']=[n['text'] for n in nodes() if n['kind']=='TButton' and 'assign' in n['text'].lower()]
    assert 'Assign as product' in report['peak_buttons']
    time.sleep(2)
    report['peak_layout']=[{'kind':n['kind'],'id':n['id'],'width':n['width'],'height':n['height'],'items':n.get('items',[])} for w in snapshot()['windows'][1:] for n in flat(w) if n['kind'] in ('Canvas','TPanedwindow','TFrame')]
    report['status']='PASS'
except Exception:report.update(status='FAIL',error=traceback.format_exc())
finally:
    (ROOT/'artifacts/tests/live-project-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    b._shutdown();pool.shutdown(wait=False)
print(report.get('status'),report.get('error',''))
sys.exit(report.get('status')!='PASS')
