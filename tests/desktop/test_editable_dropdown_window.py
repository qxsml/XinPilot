"""Exercise the real HTML renderer in WebView2 using deterministic widget data."""
import sys,time,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from desktop.live_app import html
import webview

class Fixture:
    def __init__(self):
        self.values=['Vial8Rack_1','Vial8Rack_2','Vial20','Vial1.5_Rack1','Vial1.5_Rack2','DeepPlate1','Green Plate']
        self.value=self.values[0];self.events=[];self.disabled=False
    def event(self,e):
        self.events.append(e)
        if e['action']=='value':self.value=e['value']
    def snapshot(self):
        def node(id,kind,x,y,w,h,**kw):return dict(id=id,kind=kind,x=x,y=y,width=w,height=h,style={'font':{}},children=[],text='',**kw)
        combo=node('choice','TCombobox',30,30,250,34,value=self.value,values=self.values,disabled=self.disabled,readonly=False,tooltip='48-well layout (6 x 8).')
        button=node('map','TButton',30,90,120,34,emphasized=True);button['text']='Map'
        root=node('root','Tk',0,0,800,500);root['children']=[combo,button]
        return dict(windows=[root],assets={},errors=[])

bridge=Fixture();window=webview.create_window('Dropdown regression',html=html(),js_api=bridge,width=850,height=550)
report={}
def js(s):return window.evaluate_js(s)
def wait(s):
    end=time.monotonic()+20
    while time.monotonic()<end:
        if js(s):return
        time.sleep(.1)
    raise AssertionError(s)
def run():
    try:
        wait("!!document.querySelector('.combo-arrow')")
        js("document.querySelector('.combo-arrow').click()")
        wait("document.querySelectorAll('.combo-option').length===7")
        js("document.querySelectorAll('.combo-option')[1].click()")
        wait("document.querySelector('input.editable-combo').value==='Vial8Rack_2'")
        time.sleep(.3)
        js("document.querySelector('.combo-arrow').click()")
        wait("document.querySelectorAll('.combo-option').length===7")
        js("document.querySelectorAll('.combo-option')[1].click()")
        time.sleep(.4)
        assert len([e for e in bridge.events if e['action']=='value' and e.get('selection') and e['value']=='Vial8Rack_2'])==2
        js("var i=document.querySelector('input.editable-combo');i.value='Custom rack';i.dispatchEvent(new Event('input'));i.dispatchEvent(new Event('change'))")
        time.sleep(.4)
        assert bridge.value=='Custom rack'
        assert all(not e.get('selection') for e in bridge.events if e['action']=='value' and e['value']=='Custom rack')
        bridge.values.append('New stock')
        js("document.querySelector('.combo-arrow').click()")
        wait("document.querySelectorAll('.combo-option').length===8")
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        wait("document.querySelector('.combo-choices').hidden")
        js("document.querySelector('input.editable-combo').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}))")
        wait("document.activeElement.classList.contains('combo-option')")
        js("document.activeElement.click()")
        assert js("document.querySelector('input.editable-combo').title.includes('48-well')")
        assert js("getComputedStyle(document.querySelector('.map-emphasis')).fontWeight==='700'")
        bridge.disabled=True
        wait("document.querySelector('.combo-arrow').disabled")
        assert not js("document.querySelector('#notice').textContent")
        report.update(status='PASS',all_choices=True,reselection=True,free_text=True,refresh_on_open=True,keyboard=True,tooltips=True,map_highlight=True,disabled=True)
    except Exception:report.update(status='FAIL',error=traceback.format_exc())
    finally:
        out=ROOT/'artifacts/tests';out.mkdir(parents=True,exist_ok=True)
        (out/'editable-dropdown.json').write_text(json.dumps(report,indent=2))
        window.destroy()
webview.start(run,gui='edgechromium')
print(json.dumps(report));sys.exit(report.get('status')!='PASS')
