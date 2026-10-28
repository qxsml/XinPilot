"""Guided batch entry; committed batches use ordinary Tecan transfer blocks."""
import math
import tkinter as tk
from tkinter import ttk

import tecan_frame as tecan


def source_availability(host, rows, index):
    row = rows[index]
    labware = host._canonical_labware_name(row['source_labware'])
    blocked, reusable = host._source_label_availability(labware, row['chemical'])
    usages = []
    for other_index, other in enumerate(rows):
        if other_index == index or host._canonical_labware_name(other['source_labware']) != labware:
            continue
        try:
            label = tecan.source_index_to_label(int(other['source_well']), labware)
        except (ValueError, TypeError):
            continue
        if label:
            usages.append((label, other['chemical']))
    pending_blocked, pending_reusable = tecan.classify_source_well_usage(usages, row['chemical'])
    blocked = blocked | pending_blocked
    return blocked, (reusable | pending_reusable) - blocked


def validate_sources(host, rows):
    if not 1 <= len(rows) <= 8:
        raise ValueError('Choose between 1 and 8 blocks.')
    for index, row in enumerate(rows):
        prefix = f'Block {index + 1}: '
        if not host._compound_for_chemical_label(row['chemical']):
            raise ValueError(prefix + 'select a Chemical ID from Compound Notes.')
        labware = host._canonical_labware_name(row['source_labware'])
        if labware not in tecan.SOURCE_LAYOUTS:
            raise ValueError(prefix + 'select source labware with a supported map.')
        try:
            well = int(row['source_well'])
        except (ValueError, TypeError):
            raise ValueError(prefix + 'select a source well.') from None
        cfg = tecan.SOURCE_LAYOUTS[labware]
        if not 1 <= well <= cfg['rows'] * cfg['cols']:
            raise ValueError(prefix + 'source well is outside the labware.')
        blocked, _reusable = source_availability(host, rows, index)
        if tecan.source_index_to_label(well, labware) in blocked:
            raise ValueError(prefix + 'the source well is assigned to another chemical in a loaded GWL or this batch.')


def prepare_blocks(host, rows, destination, liquid_class, extra_percent='', wash=True, amount_unit='umol/rxn'):
    """Validate without changing the editor or writing a GWL."""
    if amount_unit not in ('umol/rxn', 'uL/well'):
        raise ValueError('Select umol/rxn or uL/well.')
    validate_sources(host, rows)
    if host.mode_var.get() not in tecan.PLATE_MODES:
        raise ValueError('Select a destination format before adding blocks.')
    destination = host._canonical_labware_name(destination.strip())
    if not destination:
        raise ValueError('Select destination labware.')
    if liquid_class not in host.liquid_classes:
        raise ValueError('Select a liquid class.')
    try:
        percent = float(str(extra_percent).strip().rstrip('%') or 0)
    except ValueError:
        raise ValueError('Extra aspirate must be a valid percentage.') from None
    if not math.isfinite(percent) or percent < 0:
        raise ValueError('Extra aspirate must be a finite, non-negative percentage.')
    blocks = []
    for index, row in enumerate(rows):
        prefix = f'Block {index + 1}: '
        try:
            amount = float(row['umol'])
        except (ValueError, TypeError):
            raise ValueError(prefix + f'enter a positive amount in {amount_unit}.') from None
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError(prefix + f'enter a finite, positive amount in {amount_unit}.')
        record = host._compound_for_chemical_label(row['chemical'])
        if amount_unit == 'uL/well':
            volume = float(f'{amount:.1f}')
        else:
            concentration = host._record_concentration_m(record)
            if not concentration or not math.isfinite(concentration):
                raise ValueError(prefix + 'add a valid stock concentration in Compound Notes first.')
            volume = float(host._volume_from_umol_and_conc(amount, concentration))
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError(prefix + 'calculated volume is below the supported 0.1 uL precision.')
        try:
            wells = tecan.parse_dest_well_expr(row['wells'], host.mode_var.get(), destination)
        except Exception as exc:
            raise ValueError(prefix + f'invalid destination wells: {exc}') from exc
        if not wells:
            raise ValueError(prefix + 'select at least one destination well.')
        aspirate = volume * len(wells) * (1 + percent / 100)
        if not math.isfinite(aspirate):
            raise ValueError(prefix + 'calculated aspiration volume is too large.')
        blocks.append(tecan.TransferBlock(
            source_labware=host._canonical_labware_name(row['source_labware']),
            source_well=int(row['source_well']), source_volume=tecan.rounded_gwl_volume(aspirate),
            dest_labware=destination, dest_wells_expr=row['wells'].strip(),
            dest_volume=volume, liquid_class=liquid_class,
            chemical_name=str(record.get('ID') or row['chemical']).strip(),
            reaction_umol=str(row['umol']).strip() if amount_unit == 'umol/rxn' else '',
            is_building_block=bool(row['building_block']), add_wash=wash,
            extra_aspirate_percent=str(extra_percent).strip(),
        ))
    return blocks


class TecanBatchDialog(tk.Toplevel):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.entry_index = host._active_gwl_index
        self.entry = host.exported_gwl_files[self.entry_index]
        self.title('Add Batch')
        self.configure(background=ttk.Style(self).lookup('TFrame', 'background') or '#f5f6f7')
        self.transient(host.winfo_toplevel())
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.count = tk.StringVar(self, '1')
        self.amount_unit = tk.StringVar(self, 'umol/rxn')
        self._previous_amount_unit = self.amount_unit.get()
        self.all_umol = tk.StringVar(self)
        self.destination = tk.StringVar(self, '')
        self.liquid = tk.StringVar(self, host._default_liquid_class())
        self.extra = tk.StringVar(self, '')
        self.wash = tk.BooleanVar(self, True)
        self.rows = []
        for _ in range(8):
            self.rows.append({
                name: (tk.BooleanVar(self, False) if name == 'building_block' else tk.StringVar(self, value))
                for name, value in dict(chemical='', source_labware=tecan.SOURCE_LABWARE_OPTIONS[0],
                                       source_well='', building_block=False, umol='', wells='').items()
            })
        self.status = tk.StringVar(self)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.heading = ttk.Label(self, padding=(14, 10), font=('Segoe UI', 11, 'bold'))
        self.heading.grid(row=0, column=0, sticky='w')
        self.body = ttk.Frame(self, padding=(14, 0))
        self.body.grid(row=1, column=0, sticky='nsew')
        ttk.Label(self, textvariable=self.status, foreground='#a12727', wraplength=820,
                  padding=(14, 8)).grid(row=2, column=0, sticky='ew')
        self.footer = ttk.Frame(self, padding=(14, 8))
        self.footer.grid(row=3, column=0, sticky='ew')
        self.footer.columnconfigure(0, weight=1)
        self.geometry('960x580')
        self.minsize(860, 540)
        self.show_sources()
        tecan._position_toplevel_near(self, host.batch_addition_button)
        self.grab_set()

    def active_rows(self):
        count = int(self.count.get())
        return [{key: var.get() for key, var in row.items()} for row in self.rows[:count]]

    def clear_page(self):
        for parent in (self.body, self.footer):
            for child in parent.winfo_children():
                child.destroy()
        self.status.set('')
        ttk.Button(self.footer, text='Cancel', command=self.destroy).grid(row=0, column=3, padx=(8, 0))

    def fit_page(self):
        # Tk's requested size reflects Windows text/DPI scaling and all eight
        # rows. Do not keep the fixed initial geometry when it clips controls.
        self.update_idletasks()
        width = min(self.winfo_screenwidth() - 40, max(860, self.winfo_reqwidth() + 24))
        height = min(self.winfo_screenheight() - 80, max(540, self.winfo_reqheight() + 24))
        self.minsize(width, height)
        width = min(self.winfo_screenwidth() - 40, max(width, self.winfo_width()))
        height = min(self.winfo_screenheight() - 80, max(height, self.winfo_height()))
        x = max(0, min(self.winfo_x(), self.winfo_screenwidth() - width - 20))
        y = max(0, min(self.winfo_y(), self.winfo_screenheight() - height - 60))
        self.geometry(f'{width}x{height}+{x}+{y}')

    def destroy(self):
        for var, trace in getattr(self, '_preview_traces', []):
            var.trace_remove('write', trace)
        self._preview_traces = []
        super().destroy()

    @staticmethod
    def block_badge(parent, index):
        badge = tk.Label(parent, text=str(index + 1), width=3, height=1,
                         background='#dce8f2', foreground='#18384f', relief='solid', borderwidth=1)
        badge.grid(row=index + 1, column=0, padx=(0, 12), pady=5)

    def show_sources(self):
        self.clear_page()
        self.heading.configure(text='1 of 2 — Chemicals and source wells')
        top = ttk.Frame(self.body)
        top.pack(fill='x', pady=(0, 10))
        ttk.Label(top, text='Number of blocks').pack(side='left')
        count = ttk.Combobox(top, textvariable=self.count, values=list(range(1, 9)), state='readonly', width=4)
        count.pack(side='left', padx=8)
        count.bind('<<ComboboxSelected>>', lambda _event: self.show_sources())
        self.host._refresh_compound_options()
        chemicals = self.host.chemical_combo.cget('values')
        table = ttk.Frame(self.body)
        table.pack(fill='x')
        for col, text in enumerate(['Block', 'Chemical ID', 'Source labware', 'Well index', '', 'Building block']):
            ttk.Label(table, text=text).grid(row=0, column=col, sticky='w', padx=(0, 10))
        table.columnconfigure(1, weight=1)
        for index, row in enumerate(self.rows[:int(self.count.get())]):
            self.block_badge(table, index)
            ttk.Combobox(table, textvariable=row['chemical'], values=chemicals, width=22,
                         state='readonly').grid(row=index + 1, column=1, sticky='ew', padx=(0, 10))
            ttk.Combobox(table, textvariable=row['source_labware'], values=tecan.SOURCE_LABWARE_OPTIONS,
                         width=18, state='readonly').grid(row=index + 1, column=2, padx=(0, 10))
            ttk.Entry(table, textvariable=row['source_well'], width=8).grid(row=index + 1, column=3, sticky='w')
            button = ttk.Button(table, text='Map Select')
            button.configure(command=lambda i=index, b=button: self.pick_source(i, b))
            button.grid(row=index + 1, column=4, padx=10)
            ttk.Checkbutton(table, variable=row['building_block']).grid(row=index + 1, column=5)
        ttk.Button(self.footer, text='Next', command=self.next_page,
                   style='ChemAction.TButton').grid(row=0, column=2)
        self.fit_page()

    def pick_source(self, index, anchor):
        rows = self.active_rows()
        row = rows[index]
        if not row['chemical']:
            self.status.set(f'Block {index + 1}: select a Chemical ID first.')
            return
        labware = self.host._canonical_labware_name(row['source_labware'])
        blocked, reusable = source_availability(self.host, rows, index)
        try:
            initial = tecan.source_index_to_label(int(row['source_well']), labware)
        except (ValueError, TypeError):
            initial = ''
        dialog = tecan.SourceWellDialog(self, labware, initial, anchor=anchor,
                                       occupied_labels=blocked, reusable_labels=reusable)
        self.wait_window(dialog)
        self.grab_set()
        if getattr(dialog, 'result_label', ''):
            self.rows[index]['source_well'].set(str(tecan.source_label_to_index(dialog.result_label, labware)))
        self.status.set('')

    def next_page(self):
        try:
            validate_sources(self.host, self.active_rows())
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.show_destinations()

    def show_destinations(self):
        self.clear_page()
        self.heading.configure(text='2 of 2 — Amounts and destination wells')
        common = ttk.Frame(self.body)
        common.pack(fill='x', pady=(0, 12))
        for col, text in enumerate(['Destination labware', 'Liquid class (all blocks)', 'Extra aspirate (%)']):
            ttk.Label(common, text=text).grid(row=0, column=col, sticky='w', padx=(0, 15))
        ttk.Combobox(common, textvariable=self.destination, values=self.host._get_dest_labware_options_for_mode(),
                     width=22).grid(row=1, column=0, padx=(0, 15))
        ttk.Combobox(common, textvariable=self.liquid, values=self.host.liquid_classes, state='readonly',
                     width=30).grid(row=1, column=1, padx=(0, 15))
        ttk.Entry(common, textvariable=self.extra, width=10).grid(row=1, column=2, sticky='w')
        ttk.Checkbutton(common, text='Wash after each block', variable=self.wash).grid(row=1, column=3, padx=10)
        shared = ttk.Frame(self.body)
        shared.pack(fill='x', pady=(0, 10))
        ttk.Label(shared, text='Amount unit').pack(side='left')
        unit = ttk.Combobox(shared, textvariable=self.amount_unit,
                            values=('umol/rxn', 'uL/well'), state='readonly', width=12)
        unit.pack(side='left', padx=8)
        unit.bind('<<ComboboxSelected>>', self.change_amount_unit)
        ttk.Label(shared, text=f'{self.amount_unit.get()} for all').pack(side='left')
        ttk.Entry(shared, textvariable=self.all_umol, width=10).pack(side='left', padx=8)
        ttk.Button(shared, text='Apply to all', command=self.apply_all).pack(side='left')
        table = ttk.Frame(self.body)
        table.pack(fill='x')
        for col, text in enumerate(['Block', 'Chemical ID', self.amount_unit.get(), 'Destination wells', '', 'Dispense / aspirate (uL)']):
            ttk.Label(table, text=text).grid(row=0, column=col, sticky='w', padx=(0, 10))
        self.previews = []
        for index, row in enumerate(self.rows[:int(self.count.get())]):
            self.block_badge(table, index)
            ttk.Label(table, textvariable=row['chemical'], width=18).grid(row=index + 1, column=1, sticky='w')
            amount = ttk.Entry(table, textvariable=row['umol'], width=10)
            amount.grid(row=index + 1, column=2, padx=(0, 10))
            wells = ttk.Entry(table, textvariable=row['wells'], width=20)
            wells.grid(row=index + 1, column=3, padx=(0, 10))
            button = ttk.Button(table, text='Map Select')
            button.configure(command=lambda i=index, b=button: self.pick_destination(i, b))
            button.grid(row=index + 1, column=4, padx=(0, 10))
            preview = ttk.Label(table, text='—')
            preview.grid(row=index + 1, column=5, sticky='w')
            self.previews.append(preview)
        # One shared binding handles typed, pasted and programmatic value changes.
        if not hasattr(self, '_preview_traces'):
            self._preview_traces = []
            for var in [self.destination, self.extra] + [r[k] for r in self.rows for k in ('umol', 'wells')]:
                self._preview_traces.append((var, var.trace_add('write', lambda *_: self.refresh_previews())))
        self.refresh_previews()
        ttk.Button(self.footer, text='Back', command=self.show_sources).grid(row=0, column=1, padx=8)
        ttk.Button(self.footer, text='Apply', command=self.apply,
                   style='ChemAction.TButton').grid(row=0, column=2)
        self.fit_page()

    def change_amount_unit(self, _event=None):
        if self.amount_unit.get() == self._previous_amount_unit:
            return
        self._previous_amount_unit = self.amount_unit.get()
        self.all_umol.set('')
        for row in self.rows:
            row['umol'].set('')
        self.show_destinations()
        self.status.set('Amounts cleared after changing units. Enter amounts in ' + self.amount_unit.get() + '.')

    def apply_all(self):
        for row in self.rows[:int(self.count.get())]:
            row['umol'].set(self.all_umol.get())
        self.refresh_previews()

    def refresh_previews(self):
        for index, preview in enumerate(getattr(self, 'previews', [])):
            if not preview.winfo_exists():
                continue
            try:
                block = prepare_blocks(self.host, [self.active_rows()[index]], self.destination.get(),
                                       self.liquid.get(), self.extra.get(), self.wash.get(), self.amount_unit.get())[0]
                preview.configure(text=f'{block.dest_volume:g} each / {block.source_volume:g} total')
            except (ValueError, IndexError):
                preview.configure(text='—')

    def pick_destination(self, index, anchor):
        if not self.destination.get().strip():
            self.status.set('Select destination labware before choosing wells.')
            return
        rows, cols, _order = tecan.mode_dims_order(self.host.mode_var.get())
        highlighted = self.host._dispensed_destination_labels(self.destination.get())
        for i, row in enumerate(self.active_rows()):
            if i == index:
                continue
            try:
                for well in tecan.parse_dest_well_expr(row['wells'], self.host.mode_var.get(), self.destination.get()):
                    highlighted.add(tecan.index_to_dest_label(well, self.host.mode_var.get(), self.destination.get()))
            except ValueError:
                pass
        dialog = tecan.WellMapDialog(self, rows, cols, self.rows[index]['wells'].get(),
                                    vertical_view='vertical' in self.host.mode_var.get().lower(),
                                    anchor=anchor, highlight_labels=highlighted)
        self.wait_window(dialog)
        self.grab_set()
        if getattr(dialog, 'result_labels', ''):
            self.rows[index]['wells'].set(dialog.result_labels)
        self.refresh_previews()

    def apply(self):
        idx, entry = self.host._selected_gwl_entry()
        if idx != self.entry_index or entry is not self.entry or idx != self.host._active_gwl_index:
            self.status.set('The active GWL changed. Close this popup and reopen it for the intended GWL.')
            return
        try:
            blocks = prepare_blocks(self.host, self.active_rows(), self.destination.get(),
                                    self.liquid.get(), self.extra.get(), self.wash.get(), self.amount_unit.get())
        except ValueError as exc:
            self.status.set(str(exc))
            return
        first = len(self.host.blocks)
        self.host.blocks.extend(blocks)
        self.host._refresh_list()
        self.host.listbox.selection_set(first)
        self.host.listbox.see(first)
        self.host._on_select(None)
        self.destroy()
