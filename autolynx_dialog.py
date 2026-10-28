"""Sample-list export dialog rendered by the existing desktop bridge."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from xinpilot.application.autolynx import load_methods, sample_csv


def open_autolynx_dialog(parent, get_samples):
    win = tk.Toplevel(parent)
    win.title('Export AutoLynx sample list')
    win.transient(parent.winfo_toplevel())
    body = ttk.Frame(win, padding=16)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Uses Reaction names and LCMS wells from LCMS Input.\nConfirm the plate configuration and methods on your Waters system.').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))
    specs = [
        ('plate', 'Waters plate position', '', None),
        ('format', 'LCMS plate format', '96-well', ['48-well', '96-well']),
        ('MS_FILE', 'MS acquisition method', '', None),
        ('MS_TUNE_FILE', 'MS tune file (optional)', '', None),
        ('INLET_FILE', 'LC / inlet method', '', None),
        ('PROCESS', 'Processing program (optional)', 'OPENLYNX', None),
        ('PROCESS_PARAMS', 'Processing method (.olp)', '', None),
        ('INJ_VOL', 'Injection volume (uL)', '', None),
        ('order', 'Injection order', 'Across rows', ['Across rows', 'Down columns']),
    ]
    values = {}
    for index, (key, label, default, choices) in enumerate(specs, 1):
        values[key] = tk.StringVar(win, value=default)
        ttk.Label(body, text=label).grid(row=index, column=0, sticky='w', padx=(0, 12), pady=4)
        widget = (ttk.Combobox(body, textvariable=values[key], values=choices, state='readonly', width=46)
                  if choices else ttk.Entry(body, textvariable=values[key], width=48))
        widget.grid(row=index, column=1, sticky='ew', pady=4)
    body.columnconfigure(1, weight=1)

    def load_example():
        path = filedialog.askopenfilename(parent=win, title='Load example MassLynx CSV', filetypes=[('CSV', '*.csv')])
        if not path:
            return
        try:
            methods = load_methods(path)
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror('Example CSV', str(exc), parent=win)
            return
        for key, value in methods.items():
            values[key].set(value)

    def save():
        try:
            content = sample_csv(get_samples(), {key: var.get() for key, var in values.items()})
        except ValueError as exc:
            messagebox.showerror('AutoLynx export', str(exc), parent=win)
            return
        path = filedialog.asksaveasfilename(parent=win, title='Save AutoLynx sample list', defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        if not path:
            return
        try:
            Path(path).write_text(content, encoding='utf-8-sig', newline='')
        except OSError as exc:
            messagebox.showerror('AutoLynx export', str(exc), parent=win)
            return
        messagebox.showinfo('AutoLynx CSV saved', f'Saved sample list:\n{path}', parent=win)
        win.destroy()

    actions = ttk.Frame(body)
    actions.grid(row=len(specs)+1, column=0, columnspan=2, sticky='e', pady=(12, 0))
    ttk.Button(actions, text='Load example CSV', command=load_example).pack(side='left', padx=4)
    ttk.Button(actions, text='Cancel', command=win.destroy).pack(side='left', padx=4)
    ttk.Button(actions, text='Export CSV', command=save).pack(side='left', padx=4)
    win.grab_set()
    return win
