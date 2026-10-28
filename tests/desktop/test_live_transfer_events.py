"""Verify batch and map event transport against original Tecan calculations."""
import json,sys,traceback
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
(ROOT/'artifacts/tests').mkdir(parents=True,exist_ok=True)
from desktop.live_engine import Controller
from tecan_batch_dialog import TecanBatchDialog
import tecan_frame as tecan
from tkinter import ttk
c=Controller();report={}
def widgets(w):
    yield w
    for child in w.winfo_children():yield from widgets(child)
def value(var,text,root):
    control=next(w for w in widgets(root) if isinstance(w,ttk.Entry) and str(w.cget('textvariable'))==str(var))
    c.event({'action':'value','id':control._w,'value':text});c.app.update()
def click(text,root):
    control=next(w for w in widgets(root) if isinstance(w,ttk.Button) and w.cget('text')==text)
    c.event({'action':'invoke','id':control._w});c.app.update()
try:
    host=c.app.tecan_tab
    host.compound_provider=lambda:[SimpleNamespace(values={'ID':'BB1','Conc.':'0.2'}),SimpleNamespace(values={'ID':'BB2','Conc.':'0.2'})]
    host.exported_gwl_files=[dict(name='Current',path='',content='',blocks=[]),dict(name='Other',path='',content='',blocks=[host._block_to_dict(tecan.TransferBlock(source_well=3,chemical_name='BB2'))])]
    host._active_gwl_index=0;host._refresh_gwl_list();host.gwl_listbox.selection_set(0)
    host.mode_var.set('96-well horizontal')
    popup=TecanBatchDialog(host);c.app.update()
    value(popup.count,'2',popup)
    for index,row in enumerate(popup.rows[:2]):
        value(row['chemical'],f'BB{index+1}',popup)
        value(row['source_labware'],'Vial8Rack_1',popup)
        value(row['source_well'],str(index+1),popup)
    value(popup.rows[0]['source_well'],'',popup)
    map_errors=[]
    def choose_source():
        try:
            dialog=next(w for w in widgets(popup) if isinstance(w,tecan.SourceWellDialog))
            assert tecan.source_index_to_label(3,'Vial8Rack_1') in dialog.occupied
            cell=dialog.cells[tecan.source_index_to_label(1,'Vial8Rack_1')]
            c.event({'action':'pointer','id':cell._w,'sequence':'<Button-1>','x':8,'y':8})
            assert dialog.selected==tecan.source_index_to_label(1,'Vial8Rack_1')
            click('Use Selected',dialog)
            report['source_occupancy_map']=True
        except Exception:
            map_errors.append(traceback.format_exc())
            for w in list(widgets(popup)):
                if isinstance(w,tecan.SourceWellDialog):w.destroy()
    c.app.after(120,choose_source);click('Map Select',popup)
    assert not map_errors,map_errors
    click('Next',popup)
    value(popup.destination,'DeepPlate1',popup);value(popup.extra,'10',popup)
    for i,row in enumerate(popup.rows[:2]):
        value(row['umol'],'10' if i==0 else '1',popup)
        value(row['wells'],f'A{i+1},B{i+1}',popup)
    value(popup.rows[0]['wells'],'',popup)
    def choose_destination():
        try:
            dialog=next(w for w in widgets(popup) if isinstance(w,tecan.WellMapDialog))
            c.event({'action':'pointer','id':dialog.cells['A1']._w,'sequence':'<Button-1>','x':8,'y':8})
            c.event({'action':'pointer','id':dialog.cells['B1']._w,'sequence':'<Enter>','x':8,'y':8,'state':256})
            c.event({'action':'pointer','id':dialog.cells['B1']._w,'sequence':'<ButtonRelease-1>','x':8,'y':8})
            assert dialog.selected=={'A1','B1'},dialog.selected
            assert dialog.drag_state is None
            click('Use Selection',dialog)
            report['destination_drag_selection']=True
        except Exception:
            map_errors.append(traceback.format_exc())
            for w in list(widgets(popup)):
                if isinstance(w,tecan.WellMapDialog):w.destroy()
    c.app.after(120,choose_destination);click('Map Select',popup)
    assert not map_errors,map_errors
    click('Apply',popup)
    assert [b.dest_volume for b in host.blocks]==[50,5]
    assert [round(b.source_volume,6) for b in host.blocks]==[110,11]
    lines=host._build_lines();assert sum(line.startswith('D;') for line in lines)==4
    popup=TecanBatchDialog(host);c.app.update()
    for key,text in [('chemical','BB1'),('source_labware','Vial8Rack_1'),('source_well','1')]:
        value(popup.rows[0][key],text,popup)
    click('Next',popup)
    value(popup.amount_unit,'uL/well',popup)
    assert popup._previous_amount_unit=='uL/well'
    value(popup.destination,'DeepPlate1',popup);value(popup.extra,'10',popup)
    value(popup.all_umol,'12.5',popup);click('Apply to all',popup)
    value(popup.rows[0]['wells'],'A3,B3',popup)
    click('Apply',popup)
    assert host.blocks[-1].dest_volume==12.5
    assert abs(host.blocks[-1].source_volume-27.5)<1e-8
    assert host.blocks[-1].reaction_umol==''
    report.update(status='PASS',dispense_ul=[50,5],aspirate_ul=[110,11],gwl_dispense_lines=4,direct_volume_transport=True)
except Exception:report.update(status='FAIL',error=traceback.format_exc())
finally:
    c.app.destroy();(ROOT/'artifacts/tests/live-transfer-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report));sys.exit(report.get('status')!='PASS')
