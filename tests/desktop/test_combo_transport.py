"""Check real controller tooltip, selection and persistent batch-map semantics."""
import sys
from pathlib import Path
from tkinter import ttk
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from desktop.live_engine import Controller
from xinpilot_tooltips import Tooltip
import tecan_frame

c=Controller()
try:
    host=c.app.tecan_tab
    host.mode_var.set('HPLC vials horizontal')
    host._on_mode_changed()
    assert '48-well' in host._format_tooltip.text
    assert c.serialize(host.mode_combo)['tooltip']==host._format_tooltip.text
    probe=ttk.Combobox(c.app,values=tecan_frame.SOURCE_LABWARE_OPTIONS)
    probe.place(x=10,y=10,width=180,height=30)
    Tooltip(probe,'Directly constructed tooltip')
    c.app.update()
    assert c.serialize(probe)['tooltip']=='Directly constructed tooltip'
    assert len(c.serialize(probe)['values'])==7
    selected=[]
    probe.bind('<<ComboboxSelected>>',lambda e:selected.append(probe.get()))
    c.event(dict(action='value',id=str(probe),value='Vial',selection=False))
    assert not selected
    for _ in range(2):
        c.event(dict(action='value',id=str(probe),value='Vial8Rack_2',selection=True))
    assert selected==['Vial8Rack_2','Vial8Rack_2']
    probe.configure(state='disabled')
    c.event(dict(action='value',id=str(probe),value='Vial20',selection=True))
    assert probe.get()=='Vial8Rack_2'
    from opentrons_frame import OpentronsFrame
    frame=OpentronsFrame(c.app)
    frame._create_batch_row()
    for button in (frame.source_map_button,frame.dest_map_button):
        assert c.serialize(button)['emphasized']
    frame.destroy()
    frame=OpentronsFrame(c.app)
    frame._set_transfer_type(True)
    frame.volume_var.set('25')
    batch=frame._build_logical_batch_row('individual',['A1'],{'A1':'CHEM-1'},'dest1',[['A2']],exclude_row_index=None)
    frame.rows=[batch];frame._refresh_table()
    frame.tree.selection_set('0');frame.tree.focus('0');frame._on_transfer_row_select()
    frame._edit_selected_transfer()
    for button in (frame.source_map_button,frame.dest_map_button):
        assert c.serialize(button)['emphasized'], 'Completed batch must retain Map highlight'
    frame.destroy()
    print('PASS: tooltip registration, all source choices, typing vs selection, reselection, disabled controls and map emphasis')
finally:
    c.app.destroy()
