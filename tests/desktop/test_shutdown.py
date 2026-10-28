"""Actual WebView2 save/cancel/close regression. Run each case in a fresh process."""
import json,sys,time,traceback,zipfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from desktop.live_app import LiveBridge,html
import webview
case=sys.argv[1]
out=ROOT/'artifacts/tests'/('shutdown-'+case+'-'+uuid.uuid4().hex)
out.mkdir(parents=True)
class Bridge(LiveBridge):
    def file_dialog(self,token):
        return self.event({'action':'answer','id':token,'value':str(out/'project.xinpilot.zip') if case=='save' else ''})
bridge=Bridge();log_path=Path(bridge._log.name)
window=webview.create_window('Shutdown regression',html=html(),js_api=bridge,width=1280,height=850)
bridge._window=window;window.events.closing+=bridge._request_close
report={'case':case};closed=[]
window.events.closed+=lambda:closed.append(True)
def js(code):return window.evaluate_js(code)
def wait(code):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if js(code):return
        time.sleep(.15)
    raise AssertionError(code)
def choose(label):
    js("[...document.querySelectorAll('#prompt button')].find(b=>b.textContent==="+json.dumps(label)+").click()")
def request():
    window.destroy()
    wait("document.querySelector('#prompt').textContent.includes('Save progress before closing?')")
def check():
    try:
        wait("document.querySelectorAll('.tabs button').length>0")
        if case == 'clean':
            window.destroy()
            assert bridge._controller_closed.wait(30), 'Unchanged project did not close directly'
            report['status'] = 'PASS'
            return
        # Close prompts now apply only after a meaningful project edit.
        js("[...document.querySelectorAll('button')].find(b=>b.textContent==='Add Rows').click()")
        wait("document.querySelector('.toplevel .window-title')?.textContent.includes('Add Rows')")
        wait("[...document.querySelectorAll('.toplevel button')].some(b=>b.textContent==='Add')")
        js("[...document.querySelectorAll('.toplevel button')].find(b=>b.textContent==='Add').click()")
        wait("document.querySelectorAll('.tree tbody tr').length>0")
        request()
        if case=='cancel':
            choose('Cancel')
            wait("document.querySelector('#prompt').textContent===''")
            time.sleep(.6)
            assert not bridge._closing and bridge._process.poll() is None
            assert js("document.querySelectorAll('.tabs button').length>0")
            request();choose('No')
        elif case=='save_cancel':
            choose('Yes')
            wait("document.querySelector('#prompt').textContent===''")
            time.sleep(.8)
            assert not bridge._closing and bridge._process.poll() is None
            request();choose('No')
        else:choose('Yes' if case=='save' else 'No')
        deadline=time.monotonic()+40
        while not bridge._controller_closed.is_set() and time.monotonic()<deadline:
            if case=='save':
                js("[...document.querySelectorAll('#prompt button')].find(b=>b.textContent==='OK')?.click()")
            time.sleep(.1)
        assert bridge._controller_closed.wait(1),'Controller did not exit'
        report['status']='PASS'
    except Exception:
        report.update(status='FAIL',error=traceback.format_exc())
        bridge._shutdown();window.destroy()
webview.start(check,gui='edgechromium')
bridge._shutdown()
report['native_close_count']=len(closed)
report['controller_exit_code']=bridge._process.returncode
report['controller_log']=log_path.read_text(encoding='utf-8')
if case=='save':
    try:
        with zipfile.ZipFile(out/'project.xinpilot.zip') as z:
            json.loads(z.read('project.json'))
        report['export_valid']=True
    except Exception:report.update(status='FAIL',export_error=traceback.format_exc())
if len(closed)!=1 or bridge._process.returncode!=0 or report['controller_log'].strip():report['status']='FAIL'
(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report));sys.exit(report.get('status')!='PASS')
