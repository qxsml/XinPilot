"""Smoke test actual TypeScript controls in Windows WebView2."""
import json, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
(ROOT/'artifacts/tests').mkdir(parents=True,exist_ok=True)
from desktop.live_app import LiveBridge, html
import webview
bridge=LiveBridge()
window=webview.create_window('XinPilot live renderer verification',html=html(),js_api=bridge,width=1280,height=850)
bridge._window=window
report={}
def wait_js(expression, timeout=45):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=window.evaluate_js(expression)
        if value:return value
        time.sleep(.2)
    raise AssertionError('Timed out: '+expression)
def check():
    try:
        wait_js("document.querySelectorAll('.tabs button').length>0")
        titles=window.evaluate_js("[...document.querySelector('.tabs').children].map(b=>b.textContent)")
        report['tabs']=[]
        for title in titles:
            window.evaluate_js("[...document.querySelector('.tabs').children].find(b=>b.textContent==="+json.dumps(title)+").click()")
            wait_js("document.querySelector('.tabs .active').textContent==="+json.dumps(title))
            time.sleep(.5)
            info=window.evaluate_js("({controls:document.querySelectorAll('.widget').length,unsupported:[...document.querySelectorAll('.unsupported')].map(n=>n.textContent),error:document.querySelector('#notice').textContent})")
            assert not info['unsupported'],info
            assert not info['error'],info
            report['tabs'].append({'title':title,**info})
        # Exercise the original synthesis selector in the actual DOM.
        def click_text(label):
            wait_js("[...document.querySelectorAll('button')].some(b=>(b.getAttribute('aria-label')||b.textContent)==="+json.dumps(label)+")")
            window.evaluate_js("[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||b.textContent)==="+json.dumps(label)+").click()")
            time.sleep(.6)
        click_text('Synthesis Plan')
        report['editors']=[]
        for editor in ['Tecan','Opentrons','Manual','External Import']:
            click_text(editor)
            required = {'Tecan':'New GWL','Opentrons':'Generate Protocol...',
                        'Manual':'Clear Wells','External Import':'Import transfer file'}[editor]
            wait_js("[...document.querySelectorAll('button.widget')].some(b=>b.textContent==="+json.dumps(required)+")")
            info=window.evaluate_js("({controls:document.querySelectorAll('.widget').length,unsupported:[...document.querySelectorAll('.unsupported')].map(n=>n.textContent),error:document.querySelector('#notice').textContent,buttons:[...document.querySelectorAll('button.widget')].map(b=>b.textContent)})")
            assert not info['unsupported'] and not info['error'],info
            assert info['controls']>30,info
            report['editors'].append({'editor':editor,**info})
            click_text('Change synthesis editor')
        click_text('Compound Notes')
        click_text('Add Rows')
        wait_js("document.querySelector('.toplevel .window-title').textContent.includes('Add Rows')")
        window.evaluate_js("(()=>{const i=document.querySelector('.toplevel input');i.value='2';i.dispatchEvent(new Event('input'));})()")
        click_text('Add')
        wait_js("document.querySelectorAll('.tree tbody tr').length===2")
        report['add_rows_dialog']=True
        report['status']='PASS' 
    except Exception:report.update(status='FAIL',error=traceback.format_exc())
    finally:
        (ROOT/'artifacts/tests/live-window-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        window.evaluate_js("ready=false")
        window.destroy()
        bridge._shutdown()
webview.start(check,gui='edgechromium')
print(json.dumps(report))
sys.exit(report.get('status')!='PASS')
