"""Check imported stock/structures/traces and peak popup in real WebView2."""
import json,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
(ROOT/'artifacts/tests').mkdir(parents=True,exist_ok=True)
from desktop.live_app import LiveBridge,html
import webview
class FixtureBridge(LiveBridge):
    def file_dialog(self,token):
        path=ROOT/'tests/fixtures/peak-inspection-portable.zip'
        return self.event({'action':'answer','id':token,'value':str(path)})
if len(sys.argv)>1:
    from unittest.mock import patch
    with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(Path(sys.argv[1]).resolve())):
        bridge=FixtureBridge()
else:
    bridge=FixtureBridge()
window=webview.create_window('XinPilot scientific display verification',html=html(),js_api=bridge,width=1280,height=850)
bridge._window=window;report={}
def js(code):return window.evaluate_js(code)
def wait(code,timeout=50):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if js(code):return
        time.sleep(.2)
    raise AssertionError('Timeout: '+code+'; '+str(js("document.querySelector('#notice').textContent")))
def click(label):
    selector="[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||b.textContent)==="+json.dumps(label)+" && b.getAttribute('aria-busy')!=='true')"
    wait('!!('+selector+')')
    js(selector+'.click()')

def check():
    try:
        wait("document.querySelectorAll('.tabs button').length>0")
        click('Import Project')
        for _ in range(100):
            js("[...document.querySelectorAll('#prompt button')].find(b=>['OK','Yes'].includes(b.textContent))?.click()")
            if js("document.querySelector('#prompt')?.textContent.includes('Loaded project')"):
                click('OK');break
            time.sleep(.2)
        time.sleep(.5)
        click('Cheminformatics')
        wait("[...document.querySelectorAll('button')].some(b=>b.textContent==='Clear Pushed Chemicals')")
        click('Clear Pushed Chemicals')
        wait("[...document.querySelectorAll('.toplevel button')].some(b=>b.textContent==='Clear inputs only')")
        labels=js("[...document.querySelectorAll('.toplevel button')].map(b=>b.textContent)")
        assert 'Clear inputs, products and results' in labels and 'Cancel' in labels
        click('Cancel')
        wait("document.querySelectorAll('.toplevel').length===0")
        time.sleep(.4)
        click('Clear Pushed Chemicals')
        wait("[...document.querySelectorAll('.toplevel button')].some(b=>b.textContent==='Clear inputs only')")
        click('Clear inputs only')
        wait("document.querySelectorAll('.toplevel').length===0")
        click('Product Summary')
        wait("document.body.textContent.includes('previous inputs')")
        wait("document.querySelectorAll('.tree tbody tr').length>0")
        report['retained_rows']=js("document.querySelectorAll('.tree tbody tr').length")
        click('Reaction Summary')
        wait("document.body.textContent.includes('No pushed additions')")
        click('Cheminformatics')
        click('Clear Pushed Chemicals')
        wait("[...document.querySelectorAll('.toplevel button')].some(b=>b.textContent==='Clear inputs, products and results')")
        click('Clear inputs, products and results')
        wait("document.querySelectorAll('.toplevel').length===0")
        click('Product Summary')
        wait("document.querySelectorAll('.tree tbody tr').length===0")
        report.update(status='PASS', popup_choices=labels, retained_notice=True, summary_cleared=True, downstream_cleared=True)
    except Exception:
        report.update(status='FAIL', error=traceback.format_exc())
    finally:
        js('ready=false');bridge._shutdown();window.destroy()
webview.start(check,gui='edgechromium')
(ROOT/'artifacts/tests/clear-pushed-window.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report));sys.exit(report.get('status')!='PASS')
