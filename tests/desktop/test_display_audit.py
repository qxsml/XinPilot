"""Audit WebView2 controls for unintended clipping and unsupported widgets.

Intentional one-line ellipsis is allowed only when a tooltip retains the exact
full text. Local already uses this for long status labels; comparison evidence
is retained in refactor-records/baseline-display-audit.json.
"""
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
        report['viewport']=window.evaluate_js('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})')
        report['tabs']=[]
        for title in titles:
            window.evaluate_js("[...document.querySelector('.tabs').children].find(b=>b.textContent==="+json.dumps(title)+").click()")
            wait_js("document.querySelector('.tabs .active').textContent==="+json.dumps(title))
            time.sleep(.5)
            info=window.evaluate_js("({controls:document.querySelectorAll('.widget').length,unsupported:[...document.querySelectorAll('.unsupported')].map(n=>n.textContent),error:document.querySelector('#notice').textContent})")
            info['invalid_text']=window.evaluate_js("document.body.textContent.includes(String.fromCharCode(65533))")
            info['truncated']=window.evaluate_js("[...document.querySelectorAll('.check span,.label span,button.widget span')].filter(n=>n.scrollWidth>n.clientWidth+2).filter(n=>!(getComputedStyle(n).textOverflow==='ellipsis'&&n.closest('[title]')?.title===n.textContent)).map(n=>({text:n.textContent,width:n.clientWidth,needed:n.scrollWidth}))")
            info['clipped']=window.evaluate_js("[...document.querySelectorAll('.label,button.widget,.check,.tabs button')].filter(n=>n.textContent.trim()&&(n.scrollWidth>n.clientWidth+2||n.scrollHeight>n.clientHeight+2)).map(n=>({text:n.textContent,width:n.clientWidth,scrollWidth:n.scrollWidth,height:n.clientHeight,scrollHeight:n.scrollHeight,font:getComputedStyle(n).fontSize,kind:n.dataset.kind}))")
            assert not info['clipped'] and not info['truncated'] and not info['invalid_text'],info
            assert not info['unsupported'],info
            assert not info['error'],info
            report['tabs'].append({'title':title,**info})
        # Exercise the original synthesis selector in the actual DOM.
        def click_text(label):
            window.evaluate_js("[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||b.textContent)==="+json.dumps(label)+").click()")
            time.sleep(.6)
        click_text('Synthesis Plan')
        report['editors']=[]
        for editor in ['Tecan','Opentrons','Manual']:
            click_text(editor)
            marker={'Tecan':'Add Batch','Opentrons':'Create Single','Manual':'Repeat One Reagent'}[editor]
            wait_js("[...document.querySelectorAll('button.widget')].some(b=>b.textContent==="+json.dumps(marker)+")")
            info=window.evaluate_js("({controls:document.querySelectorAll('.widget').length,unsupported:[...document.querySelectorAll('.unsupported')].map(n=>n.textContent),error:document.querySelector('#notice').textContent,buttons:[...document.querySelectorAll('button.widget')].map(b=>b.textContent)})")
            info['invalid_text']=window.evaluate_js("document.body.textContent.includes(String.fromCharCode(65533))")
            info['truncated']=window.evaluate_js("[...document.querySelectorAll('.check span,.label span,button.widget span')].filter(n=>n.scrollWidth>n.clientWidth+2).filter(n=>!(getComputedStyle(n).textOverflow==='ellipsis'&&n.closest('[title]')?.title===n.textContent)).map(n=>({text:n.textContent,width:n.clientWidth,needed:n.scrollWidth}))")
            info['clipped']=window.evaluate_js("[...document.querySelectorAll('.label,button.widget,.check,.tabs button')].filter(n=>n.textContent.trim()&&(n.scrollWidth>n.clientWidth+2||n.scrollHeight>n.clientHeight+2)).map(n=>({text:n.textContent,width:n.clientWidth,scrollWidth:n.scrollWidth,height:n.clientHeight,scrollHeight:n.scrollHeight,font:getComputedStyle(n).fontSize,kind:n.dataset.kind}))")
            assert not info['clipped'] and not info['truncated'] and not info['invalid_text'],info
            assert not info['unsupported'] and not info['error'],info
            assert info['controls']>30,info
            if editor=='Tecan':
                info['custom_edit_heading']=window.evaluate_js("(()=>{const group=[...data.values()].find(d=>d.kind==='TLabelframe'&&d.text==='Edit'&&d.labelwidget);if(!group)return false;return !nodes.get(group.id).querySelector(':scope > .group-title')&&nodes.get(group.labelwidget)?.textContent==='Edit';})()")
                assert info['custom_edit_heading'],info
            info['duplicate_group_titles']=window.evaluate_js("[...data.values()].filter(d=>d.labelwidget&&nodes.get(d.id)?.querySelector(':scope > .group-title')).map(d=>d.id)")
            assert not info['duplicate_group_titles'],info
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
        (ROOT/'artifacts/tests/display-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        window.evaluate_js("ready=false")
        # Match the normal host's close handshake: let bridge replies settle
        # before disposing WebView2, including a snapshot already in flight.
        wait_js("!polling && inFlight === 0", timeout=10)
        window.destroy()
        bridge._shutdown()
webview.start(check,gui='edgechromium')
print(report.get('status'),[(r.get('title',r.get('editor')),len(r.get('clipped',[]))) for r in report.get('tabs',[])+report.get('editors',[])])
sys.exit(report.get('status')!='PASS')
