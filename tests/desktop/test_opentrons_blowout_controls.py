"""Check blowout controls through the same controller transport as TypeScript."""
import sys
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from desktop.live_engine import Controller


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


c = Controller()
try:
    frame = c.app.opentrons_tab
    frame._create_single_row()
    c.app.update()
    frame._open_motion_dialog()
    c.app.update()
    combo = next(w for w in descendants(c.app) if isinstance(w, ttk.Combobox)
                 and str(w.cget('textvariable')) == str(frame.blowout_location_var))
    snapshot = c.serialize(combo)
    assert set(snapshot['values']) == {'No blowout', 'Source', 'Destination', 'Liquid waste'}
    c.event({'action': 'value', 'id': str(combo), 'value': 'Liquid waste', 'selection': True})
    assert frame.blowout_location_var.get() == 'Liquid waste'
    dialog = combo.winfo_toplevel()
    done = next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == 'Done')
    c.app.update()
    assert done.winfo_rooty() + done.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
    c.event({'action': 'invoke', 'id': str(done)})
    print('PASS: blowout choices serialize/select through desktop bridge; dialog action visible.')
finally:
    c.app.destroy()
