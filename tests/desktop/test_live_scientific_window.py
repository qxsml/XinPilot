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
layout_file=ROOT/'outputs/peak_inspection_layout.json'
saved_layout=layout_file.read_bytes() if layout_file.exists() else None
layout_file.parent.mkdir(parents=True,exist_ok=True)
layout_file.write_text('{}',encoding='utf-8')
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
def click(label):js("[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||b.textContent)==="+json.dumps(label)+").click()")
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
        wait("data.get('.')?.title?.includes('peak-inspection-portable')")
        report['project_title']=bridge._title
        assert bridge._title.startswith('XinPilot') and 'peak-inspection-portable' in bridge._title,bridge._title
        click('Product Summary')
        wait("document.querySelector('.tabs .active').textContent==='Product Summary'")
        wait("document.querySelectorAll('.tree tbody tr').length>0")
        js("document.querySelector('.tree tbody tr').click()")
        wait("document.querySelectorAll('.label img').length>=2")
        report['traces_loaded']=js("[...document.querySelectorAll('.label img')].every(i=>i.complete&&i.naturalWidth>0)")
        assert report['traces_loaded']
        js("(()=>{const n=[...document.querySelectorAll('.label')].find(n=>n.textContent.startsWith('UV trace from Modified')).nextElementSibling;const r=n.getBoundingClientRect();n.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,clientX:r.left+r.width/2,clientY:r.top+r.height/2}));})()")
        wait("[...document.querySelectorAll('.toplevel button')].some(b=>b.textContent==='Assign as product')")
        report['peak_popup']=True
        time.sleep(2)
        assert 'Unsaved changes' not in bridge._title, bridge._title
        assert 'Changes not verified' not in bridge._title, bridge._title
        report['view_only_stays_clean'] = True
        wait("document.querySelectorAll('.toplevel .canvas svg image').length>=2")
        time.sleep(.8)
        report['plot_geometry']=js("(()=>{const results=[];for(const [id,d] of data){if(d.kind!=='Canvas'||!nodes.get(id)?.closest('.toplevel'))continue;const svg=nodes.get(id).querySelector(':scope > svg');if(!svg)continue;const images=[...svg.querySelectorAll(':scope > image')];let i=0;for(const item of d.items){if(item.type!=='image'||!assets[item.props.image])continue;const image=images[i++],p=item.props;if(p.anchor==='center')results.push({x:Number(image.getAttribute('x')),y:Number(image.getAttribute('y')),expectedX:item.coords[0]-p.image_width/2,expectedY:item.coords[1]-p.image_height/2,viewBox:svg.getAttribute('viewBox'),width:d.width,height:d.height});}}return results})()")
        assert len(report['plot_geometry'])==2, 'Both UV and MS plots must be rendered'
        report['visible_plot_heights']=js("[...document.querySelectorAll('.toplevel .canvas svg image')].map(i=>i.closest('.canvas').parentElement.getBoundingClientRect().height)")
        assert min(report['visible_plot_heights'])>100,report
        for plot in report['plot_geometry']:
            assert abs(plot['x']-plot['expectedX'])<.01 and abs(plot['y']-plot['expectedY'])<.01,plot
            assert plot['x']==0 and plot['y']==0,plot
            assert list(map(float,plot['viewBox'].split()))[2:]==[plot['width'],plot['height']],plot
        js("document.querySelectorAll('.toplevel .tree tbody tr')[0].click()")
        time.sleep(.4);click('Assign as product')
        wait("document.querySelector('.toplevel').textContent.includes('UV254 purity: 70%')")
        js("document.querySelectorAll('.toplevel .tree tbody tr')[1].click()")
        time.sleep(.4);click('Assign as product')
        wait("document.querySelector('.toplevel').textContent.includes('UV254 purity: 30%')")
        wait("data.get('.')?.title?.includes('Unsaved changes')")
        report['manual_assignment_marks_changed'] = True
        click('Restore automatic assignment')
        wait("document.querySelector('.toplevel').textContent.includes('UV254 purity: 70%')")
        report['manual_assignment_and_restore']=[70,30,70]
        js("window.savedPeakRow=document.querySelector('.toplevel .tree tbody tr');document.querySelectorAll('.toplevel .tree tbody tr')[1].click()")
        time.sleep(.6)
        assert js("window.savedPeakRow===document.querySelector('.toplevel .tree tbody tr')"),'Selection rebuilt the table'
        assert js("document.querySelector('.toplevel .tree')===document.activeElement"),'Table lost keyboard focus'
        report['stable_table_selection']=True
        old_width=js("document.querySelector('.toplevel').getBoundingClientRect().width")
        click('Expand window')
        wait("document.querySelector('.toplevel').getBoundingClientRect().width>"+str(old_width+40))
        assert js("(()=>{const r=document.querySelector('.peak-actions').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()"),'Peak footer outside viewport'
        click('Restore window size')
        wait("Math.abs(document.querySelector('.toplevel').getBoundingClientRect().width-"+str(old_width)+")<4")
        report['expand_restore_and_visible_actions']=True
        js("(()=>{const tree=[...data.values()].find(d=>d.kind==='Treeview'&&nodes.get(d.id)?.closest('.toplevel'));window.columnTest={id:tree.id,column:tree.columns[0].id,width:tree.columns[0].width+35};void send({action:'column_size',...window.columnTest})})()")
        wait("data.get(window.columnTest.id).columns[0].width===window.columnTest.width")
        report['column_resize']=True
        report['trace_layout'] = js("(()=>{const panes=[...data.values()].filter(d=>d.kind.toLowerCase().includes('panedwindow')&&nodes.get(d.id)?.closest('.toplevel')).sort((a,b)=>b.height-a.height);window.peakPanes=panes.map(d=>d.id);return {panes:panes.length,handles:document.querySelectorAll('.toplevel .sash').length,plotFraction:panes[0].children[0].height/panes[0].height}})()")
        assert report['trace_layout']['panes']==2 and report['trace_layout']['handles']==2,report
        assert report['trace_layout']['plotFraction']>.65,report
        js("(()=>{const d=data.get(window.peakPanes[1]);window.oldUVHeight=d.children[0].height;void send({action:'sash',id:d.id,index:0,position:Math.round(d.height*.65)})})()")
        wait("Math.abs(data.get(window.peakPanes[1]).children[0].height-window.oldUVHeight)>20")
        js("(()=>{const d=data.get(window.peakPanes[0]);window.oldPlotHeight=d.children[0].height;void send({action:'sash',id:d.id,index:0,position:Math.round(d.height*.70)})})()")
        wait("Math.abs(data.get(window.peakPanes[0]).children[0].height-window.oldPlotHeight)>20")
        click('Hide peak table')
        wait("document.querySelectorAll('.toplevel .tree').length===0")
        assert js("(()=>{const r=document.querySelector('.peak-actions').getBoundingClientRect();return r.bottom<=innerHeight})()")
        time.sleep(.8)
        stored=json.loads((ROOT/'outputs/peak_inspection_layout.json').read_text(encoding='utf-8'))
        assert stored['table_visible'] is False,stored
        click('Close')
        wait("document.querySelectorAll('.toplevel').length===0")
        js("(()=>{const n=[...document.querySelectorAll('.label')].find(n=>n.textContent.startsWith('UV trace from Modified')).nextElementSibling;const r=n.getBoundingClientRect();n.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,clientX:r.left+r.width/2,clientY:r.top+r.height/2}));})()")
        wait("[...document.querySelectorAll('.toplevel button')].some(b=>b.textContent==='Show peak table')")
        assert js("document.querySelectorAll('.toplevel .tree').length===0")
        click('Show peak table')
        wait("document.querySelectorAll('.toplevel .tree tbody tr').length===2")
        report['resize_hide_reopen_restore']=True
        report['unsupported']=js("[...document.querySelectorAll('.unsupported')].map(n=>n.textContent)")
        report['errors']=js("document.querySelector('#notice').textContent")
        assert not report['unsupported'] and not report['errors'],report
        report['status']='PASS'
    except Exception:
        report.update(status='FAIL',error=traceback.format_exc())
        report['canvas_debug']=js("[...data.values()].filter(d=>d.kind==='Canvas'&&nodes.get(d.id)?.closest('.toplevel')).map(d=>({id:d.id,width:d.width,height:d.height,items:d.items,html:nodes.get(d.id).outerHTML.slice(0,1200)}))")
    finally:
        (ROOT/'artifacts/tests/live-scientific-window-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        js('ready=false');window.destroy();bridge._shutdown()
        if saved_layout is not None:layout_file.write_bytes(saved_layout)
        elif layout_file.exists():layout_file.unlink()
webview.start(check,gui='edgechromium')
print(json.dumps(report));sys.exit(report.get('status')!='PASS')
