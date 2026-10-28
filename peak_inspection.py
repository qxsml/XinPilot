"""Portable inspection of instrument-integrated Modified PyParse peaks.

Overrides are separate from the automatic analysis; no RPT or analysis output
is rewritten. Areas are taken from the instrument, never integrated on screen.
"""
from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from xinpilot_shared import _canonical_smiles_key, _normalize_well


def peak_unavailable_reason(peak, exclusions):
    start, end = float(peak['pStart']), float(peak['pEnd'])
    if start == 0 or end <= start:
        return 'No UV integration boundaries available for this spectrum.'
    if any(end > float(lo) and start < float(hi) for lo, hi in exclusions):
        return 'This peak overlaps an explicit UV254 exclusion range.'
    if max(float(peak['areaAbs']), float(peak['area'])) <= 0:
        return 'No positive UV integrated area available for this peak.'
    return ''


def eligible(peak, exclusions):
    return not peak_unavailable_reason(peak, exclusions)


def inspection_peak_indices(well, include_spectra=False):
    """Keep original indices: spectrum-only records are not UV integrations."""
    integrated = [i for i, peak in enumerate(well['peaks']) if eligible(peak, [])]
    return list(range(len(well['peaks']))) if include_spectra or not integrated else integrated


def nearest_inspection_peak(well, rt, indices=None):
    indices = inspection_peak_indices(well) if indices is None else indices
    containing = [i for i in indices if eligible(well['peaks'][i], [])
                  and float(well['peaks'][i]['pStart']) <= rt <= float(well['peaks'][i]['pEnd'])]
    return min(containing or indices, key=lambda i: abs(float(well['peaks'][i]['time']) - rt))


def peak_purity(well, index):
    peaks = well['peaks']
    if type(index) is not int or not 0 <= index < len(peaks):
        raise ValueError('Select an existing integrated peak.')
    exclusions = well.get('exclude_ranges', [])
    reason = peak_unavailable_reason(peaks[index], exclusions)
    if reason:
        raise ValueError(reason)
    def area(peak):
        absolute = float(peak['areaAbs'])
        return max(0.0, absolute if absolute > 0 else float(peak['area']))
    total = sum(area(p) for p in peaks if eligible(p, exclusions))
    if total <= 0:
        raise ValueError('No positive integrated area is available for this well.')
    return round(100 * area(peaks[index]) / total, 2)


def validate_data(data):
    """Reject unsupported/corrupt numerical data before exposing editing controls."""
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Unsupported peak data version.')
    for well in data['wells'].values():
        for peak in well['peaks']:
            for key in ('time', 'pStart', 'pEnd', 'area', 'areaAbs'):
                if not math.isfinite(float(peak[key])):
                    raise ValueError('Non-finite peak value.')
            for key in ('MS+', 'MS-'):
                for mass, intensity in peak[key]:
                    if not all(math.isfinite(float(v)) for v in (mass, intensity)):
                        raise ValueError('Invalid spectrum.')
        for lo, hi in well.get('exclude_ranges', []):
            if not math.isfinite(float(lo)) or not math.isfinite(float(hi)) or hi < lo:
                raise ValueError('Invalid exclusion range.')
        trace = well['trace']
        for values in (trace.values() if isinstance(trace, dict) else [trace]):
            if not values:
                continue
            if len(values) != 2 or len(values[0]) != len(values[1]):
                raise ValueError('Invalid chromatogram.')
            if any(not math.isfinite(float(v)) for axis in values for v in axis):
                raise ValueError('Invalid chromatogram value.')
    for records in data['targets'].values():
        for label, record in records.items():
            if label not in data['wells'] or not math.isfinite(float(record['automatic_purity'])):
                raise ValueError('Missing well or automatic result.')
    return data


class PeakInspectionMixin:
    def _peak_reset(self):
        self.peak_inspection_data = {}
        self.product_peak_overrides = {}
        self._peak_preview_cache = {}

    def _peak_load(self, output_dir):
        self._peak_reset()
        path = Path(output_dir) / 'xinpilot_peaks.json'
        if not path.is_file():
            path = Path(output_dir) / 'rxnpilot_peaks.json'
        if not path.is_file():
            path = Path(output_dir) / 'syntrack_peaks.json'  # Legacy analysis bundles
        if path.is_file():
            try:
                self.peak_inspection_data = validate_data(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.logw(f'Peak inspection data could not be loaded: {exc}')

    def _peak_import(self, state):
        self._peak_reset()
        data = state.get('peak_inspection_data')
        if not data:
            return
        try:
            self.peak_inspection_data = validate_data(copy.deepcopy(data))
            for target, wells in state.get('product_peak_overrides', {}).items():
                for label, override in wells.items():
                    if label not in data['targets'].get(target, {}):
                        continue
                    try:
                        peak_purity(data['wells'][label], override['peak_index'])
                    except (ValueError, KeyError, TypeError):
                        continue
                    self.product_peak_overrides.setdefault(target, {})[label] = copy.deepcopy(override)
        except (ValueError, KeyError, TypeError) as exc:
            self._peak_reset()
            self.logw(f'Peak inspection data could not be restored: {exc}')

    def _peak_context(self, row):
        target = _canonical_smiles_key(self._lcms_target_for_row(row))
        label = _normalize_well(row.get('pyparse_well', ''))
        data = getattr(self, 'peak_inspection_data', {})
        record = data.get('targets', {}).get(target, {}).get(label)
        well = data.get('wells', {}).get(label)
        override = getattr(self, 'product_peak_overrides', {}).get(target, {}).get(label)
        return target, label, record, well, override

    def _peak_override_purity(self, row):
        _, _, record, well, override = self._peak_context(row)
        if record and well and override:
            return f"{peak_purity(well, override['peak_index']):g}%"
        return None

    def _peak_assignment_description(self, row):
        _, _, record, well, override = self._peak_context(row)
        if record and well and override:
            rt = well['peaks'][override['peak_index']]['time']
            return f'Manually assigned ({float(rt):g} min)'
        return 'Automatic'

    def _peak_assign(self, row, index):
        target, label, record, well, _ = self._peak_context(row)
        if not record or not well:
            raise ValueError('Numerical peak data is unavailable; rerun Modified PyParse.')
        peak_purity(well, index)
        self.product_peak_overrides.setdefault(target, {})[label] = {
            'peak_index': index, 'assigned_at': datetime.now(timezone.utc).isoformat(),
            'method': 'existing instrument-integrated peak',
        }
        self._peak_preview_cache = {}

    def _peak_restore(self, row):
        target, label, _, _, _ = self._peak_context(row)
        overrides = getattr(self, 'product_peak_overrides', {})
        overrides.get(target, {}).pop(label, None)
        if target in overrides and not overrides[target]:
            del overrides[target]
        self._peak_preview_cache = {}

    def _peak_refresh(self):
        self._refresh_product_structure_preview(reset_selection=False)
        self._refresh_product_structure_purity_display()
        self._refresh_product_structure_trace_display()

    def _peak_unbind(self):
        for label, binding in getattr(self, '_peak_trace_bindings', []):
            label.unbind('<Button-1>', binding)
            label.configure(cursor='')
        self._peak_trace_bindings = []

    def _peak_bind_trace(self, row, photos):
        self._peak_unbind()
        _, label, record, well, override = self._peak_context(row)
        widget = self.product_structure_trace_widgets[1]
        if not record or not well:
            if photos[1] is not None:
                widget.configure(cursor='hand2')
                binding = widget.bind('<Button-1>', lambda event: messagebox.showinfo(
                    'Peak inspection', 'This analysis contains images only. Rerun Modified PyParse '
                    'to inspect spectra and assign existing peaks.', parent=self))
                self._peak_trace_bindings = [(widget, binding)]
            return
        geometry = record.get('geometry', {})
        if override:
            photos[1], geometry = self._peak_manual_photo(row, self._product_structure_trace_width(), False)
            photos[2], _ = self._peak_manual_photo(row, self._product_structure_trace_width(), True)
            for slot in (1, 2):
                self.product_structure_trace_widgets[slot].configure(image=photos[slot], text='')
        self._peak_current_photos = photos  # keep Tk images alive
        self.product_structure_trace_title_widgets[1].configure(
            text='UV trace from Modified PyParse — click a peak to inspect' +
            (' — Manually assigned' if override else ''))
        widget.configure(cursor='hand2')
        def clicked(event):
            rt = None
            photo = photos[1]
            if photo is not None and geometry.get('axes'):
                left, bottom, width, height = geometry['axes']
                x = (event.x - (widget.winfo_width() - photo.width()) / 2) / photo.width()
                y = (event.y - (widget.winfo_height() - photo.height()) / 2) / photo.height()
                if left <= x <= left + width and 1-bottom-height <= y <= 1-bottom:
                    lo, hi = geometry['xlim']
                    rt = lo + (x-left) / width * (hi-lo)
            self._open_peak_inspector(dict(row), rt)
        binding = widget.bind('<Button-1>', clicked)
        self._peak_trace_bindings = [(widget, binding)]

    def _peak_manual_photo(self, row, width, es):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from PIL import Image, ImageTk
        target, label, record, well, override = self._peak_context(row)
        key = (target, label, override['peak_index'], width, es)
        cache = getattr(self, '_peak_preview_cache', {})
        if key in cache:
            return cache[key]
        fig = Figure(figsize=(max(3, width/100), 2.8 if es else 3), dpi=100, layout='constrained')
        axes = fig.subplots(2 if es else 1, 1, squeeze=False).ravel()
        peak = well['peaks'][override['peak_index']]
        trace = well['trace']
        if not isinstance(trace, dict):
            trace = {'uv': trace}
        for ax, name in zip(axes, ('ms_minus', 'ms_plus') if es else ('uv',)):
            values = trace.get(name, [])
            if values and values[0]:
                ax.plot(values[0], values[1], color='#263f50', lw=1)
                ax.axvspan(peak['pStart'], peak['pEnd'], color='#cc5252', alpha=.23)
            else:
                ax.text(.5, .5, 'No ES trace available', transform=ax.transAxes, ha='center')
            ax.set_ylabel({'uv':'UV254 (AUs)', 'ms_minus':'ES−', 'ms_plus':'ES+'}[name])
        axes[-1].set_xlabel('Retention time (min)')
        axes[0].set_title(f"Manually assigned: {float(peak['time']):g} min; UV254 purity {peak_purity(well, override['peak_index']):g}%", fontsize=10)
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        geometry = {'axes': list(axes[0].get_position().bounds), 'xlim': list(axes[0].get_xlim())}
        photo = ImageTk.PhotoImage(Image.frombuffer('RGBA', canvas.get_width_height(), canvas.buffer_rgba(), 'raw', 'RGBA', 0, 1).copy())
        cache[key] = (photo, geometry)
        self._peak_preview_cache = cache
        return cache[key]

    def _open_peak_inspector(self, row, rt=None):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        target, label, record, well, override = self._peak_context(row)
        if not record or not well or not well['peaks']:
            messagebox.showinfo('Peak inspection', 'No integrated peaks available for this target and well.', parent=self)
            return
        # Layout preferences are local UI state, never part of analysis/project data.
        from xinpilot_shared import APP_DIR
        layout_path = APP_DIR / 'outputs' / 'peak_inspection_layout.json'
        try:
            preferences = json.loads(layout_path.read_text(encoding='utf-8'))
            if not isinstance(preferences, dict):
                preferences = {}
        except (OSError, ValueError):
            preferences = {}
        def preference(name, default, low, high):
            try:
                value = float(preferences.get(name, default))
                return max(low, min(high, value)) if math.isfinite(value) else default
            except (TypeError, ValueError):
                return default
        win = tk.Toplevel(self)
        win.title(f'Peak inspection \u2014 {record["name"]} \u2014 {label}')
        width = int(preference('width', 1100, 750, max(750, win.winfo_screenwidth()-60)))
        height = int(preference('height', 740, 560, max(560, win.winfo_screenheight()-120)))
        win.geometry(f'{width}x{height}')
        win.minsize(750, 560)
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.columnconfigure(0, weight=1)
        win.rowconfigure(2, weight=1)
        status = tk.StringVar()
        status_label = ttk.Label(win, textvariable=status, padding=8, wraplength=1000)
        status_label.grid(row=0, column=0, sticky='ew')
        hint_label = ttk.Label(win, text='Select a peak on the UV trace to inspect or assign it. Drag the dividers to resize the traces and table.', wraplength=1000)
        hint_label.grid(row=1, column=0, sticky='ew', padx=8)
        content = ttk.Panedwindow(win, orient='vertical')
        content.grid(row=2, column=0, sticky='nsew', padx=4)
        plots = ttk.Panedwindow(content, orient='vertical')
        content.add(plots, weight=5)
        def plot_panel(parent, figure):
            host = ttk.Frame(parent)
            parent.add(host, weight=1)
            host.columnconfigure(0, weight=1)
            host.rowconfigure(0, weight=1)
            view = tk.Canvas(host, height=210, highlightthickness=0, background='white')
            view.grid(row=0, column=0, sticky='nsew')
            scroll = ttk.Scrollbar(host, orient='vertical', command=view.yview)
            scroll.grid(row=0, column=1, sticky='ns')
            view.configure(yscrollcommand=scroll.set)
            canvas = FigureCanvasTkAgg(figure, master=view)
            item = view.create_window(0, 0, window=canvas.get_tk_widget(), anchor='nw')
            def resize(event):
                height = max(170, event.height)
                view.itemconfigure(item, width=event.width, height=height)
                view.configure(scrollregion=(0, 0, event.width, height))
            view.bind('<Configure>', resize)
            toolbar = NavigationToolbar2Tk(canvas, host, pack_toolbar=False)
            toolbar.grid(row=1, column=0, columnspan=2, sticky='ew')
            return canvas, toolbar
        fig = Figure(figsize=(10, 2.4), dpi=100, layout='constrained')
        uv = fig.add_subplot(111)
        canvas, toolbar = plot_panel(plots, fig)
        mass_fig = Figure(figsize=(10, 2.4), dpi=100, layout='constrained')
        plus, minus = mass_fig.subplots(1, 2)
        mass_canvas, mass_toolbar = plot_panel(plots, mass_fig)
        box = ttk.Frame(content, padding=4)
        table_visible = [preferences.get('table_visible', True) is not False]
        if table_visible[0]:
            content.add(box, weight=1)
        show_spectra = tk.BooleanVar(value=False)
        spectra_toggle = ttk.Checkbutton(box, text='Show spectra without UV integration', variable=show_spectra)
        spectra_toggle.pack(anchor='w', pady=(0, 4))
        table = ttk.Treeview(box, columns=('rt','area','percent','state'), show='headings', height=2, selectmode='browse')
        for key, heading in [('rt','Retention time (min)'), ('area','Integrated area'), ('percent','Instrument area (%)'), ('state','Assignment / exclusion')]:
            table.heading(key, text=heading)
            table.column(key, width=160)
        scroll = ttk.Scrollbar(box, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        table.pack(fill='both', expand=True)
        detail = tk.StringVar()
        detail_label = ttk.Label(win, textvariable=detail, padding=8, wraplength=950)
        detail_label.grid(row=4, column=0, sticky='ew')
        actions = ttk.Frame(win, padding=8)
        actions.grid(row=5, column=0, sticky='ew')
        def resize_text(event):
            if event.widget is win:
                for text_label in (status_label, hint_label, detail_label):
                    text_label.configure(wraplength=max(200, event.width-32))
        win.bind('<Configure>', resize_text)
        layout_ready = [False]
        save_job = [None]
        ratios = [preference('plots_fraction', .80, .50, .95), preference('uv_fraction', .50, .20, .80)]
        def save_layout():
            save_job[0] = None
            if not layout_ready[0] or not win.winfo_exists():
                return
            try:
                layout_path.parent.mkdir(parents=True, exist_ok=True)
                layout_path.write_text(json.dumps({'width': win.winfo_width(), 'height': win.winfo_height(),
                    'plots_fraction': ratios[0], 'uv_fraction': ratios[1], 'table_visible': table_visible[0]}), encoding='utf-8')
            except OSError:
                pass  # A read-only preferences directory must not block inspection.
        def schedule_save(*_):
            if not layout_ready[0]:
                return
            if save_job[0] is not None:
                win.after_cancel(save_job[0])
            save_job[0] = win.after(500, save_layout)
        def apply_layout():
            if not win.winfo_exists():
                return
            win.update_idletasks()
            if table_visible[0]:
                content.sashpos(0, int(content.winfo_height()*ratios[0]))
            win.update_idletasks()
            plots.sashpos(0, int(plots.winfo_height()*ratios[1]))
            layout_ready[0] = True
        def toggle_table():
            save_layout()
            if table_visible[0]:
                content.forget(box)
            else:
                content.add(box, weight=1)
            table_visible[0] = not table_visible[0]
            table_button.configure(text='Hide peak table' if table_visible[0] else 'Show peak table')
            apply_layout()
            schedule_save()
        def capture_layout(event):
            if not layout_ready[0]:
                return
            pane = event.widget
            if pane is content and table_visible[0] and pane.winfo_height() > 1:
                ratios[0] = max(.50, min(.95, pane.sashpos(0)/pane.winfo_height()))
            elif pane is plots and pane.winfo_height() > 1:
                ratios[1] = max(.20, min(.80, pane.sashpos(0)/pane.winfo_height()))
            schedule_save()
        for pane in (content, plots):
            pane.bind('<ButtonRelease-1>', capture_layout, add='+')
            pane.bind('<<PaneResized>>', capture_layout, add='+')
        def resized_window(event):
            if event.widget is win:
                win.after_idle(apply_layout)
                schedule_save()
        win.bind('<Configure>', resized_window, add='+')
        def closing(event):
            if event.widget is win and save_job[0] is not None:
                win.after_cancel(save_job[0])
                save_job[0] = None
        win.bind('<Destroy>', closing, add='+')
        win.after(120, apply_layout)
        selection = [0]
        peaks = well['peaks']

        def redraw(*_):
            if table.selection():
                selection[0] = int(table.selection()[0])
            idx = selection[0]
            peak = peaks[idx]
            current = self._peak_context(row)[4]
            for ax in (uv, plus, minus):
                ax.clear()
            trace = well['trace']
            values = trace.get('uv', []) if isinstance(trace, dict) else trace
            if values and values[0]:
                uv.plot(values[0], values[1], color='#263f50', linewidth=1)
            ranges = [(peaks[current['peak_index']]['pStart'], peaks[current['peak_index']]['pEnd'])] if current else record['ranges']
            for lo, hi in ranges:
                uv.axvspan(lo, hi, color='#cc5252', alpha=.22)
            for lo, hi in well.get('exclude_ranges', []):
                uv.axvspan(lo, hi, color='grey', alpha=.18)
            uv.axvline(peak['time'], color='#2379ad', linestyle='--')
            uv.set_xlabel('Retention time (min)')
            uv.set_ylabel('UV254 (AUs)')
            uv.set_title('Red: assigned product; dashed blue: inspected peak; grey: excluded region', fontsize=9)
            for ax, signal in ((plus, 'MS+'), (minus, 'MS-')):
                spectrum = peak[signal]
                if spectrum:
                    ax.vlines([v[0] for v in spectrum], 0, [v[1] for v in spectrum], color='#326f96')
                    for mass, intensity in sorted(spectrum, key=lambda v: v[1], reverse=True)[:5]:
                        ax.annotate(f'{mass:.4f}', (mass, intensity), xytext=(0,3), textcoords='offset points', fontsize=8, ha='center')
                    ax.margins(y=.25)
                else:
                    ax.text(.5,.5,'No spectrum available',transform=ax.transAxes,ha='center')
                ax.set_title(f'{signal} at {float(peak["time"]):g} min', fontsize=10)
                ax.set_xlabel('m/z')
                ax.set_ylabel('Relative intensity')
            purity = self._peak_override_purity(row) or f'{record["automatic_purity"]:g}%'
            status.set(f'{self._peak_assignment_description(row)} — UV254 purity: {purity}; automatic result: {record["automatic_purity"]:g}%')
            conflict = record.get('assignment_conflict') or self._modified_pyparse_conflict_for_row(row)
            if conflict:
                status.set(status.get() + ' — Starting-material mass conflict; manual override allowed.')
            try:
                proposed = peak_purity(well, idx)
                detail.set(f'Inspected peak: {float(peak["time"]):g} min; bounds {float(peak["pStart"]):g}–{float(peak["pEnd"]):g} min. Assigning this peak gives {proposed:g}% UV254 purity using the existing exclusions.')
                assign.configure(state='normal')
            except ValueError as exc:
                detail.set(str(exc))
                assign.configure(state='disabled')
            restore.configure(state='normal' if current else 'disabled')
            for i, p in enumerate(peaks):
                if not table.exists(str(i)):
                    continue
                unavailable = peak_unavailable_reason(p, well.get('exclude_ranges', []))
                assigned = i == current['peak_index'] if current else any(float(p['pEnd']) > lo and float(p['pStart']) < hi for lo, hi in record['ranges'])
                state = unavailable if unavailable else ('Manually assigned' if current else 'Automatic product') if assigned else ''
                has_uv = eligible(p, [])
                table.item(str(i), values=(f'{float(p["time"]):g}', f'{float(p["areaAbs"]):g}' if has_uv else '—', f'{float(p["area"]):g}' if has_uv else '—', state))
            canvas.draw_idle()
            mass_canvas.draw_idle()

        def change(restore_auto=False):
            # Guard against an analysis/project replaced while a dialog is open.
            if self._peak_context(row)[2] is not record:
                messagebox.showwarning('Analysis changed', 'Reopen peak inspection for the current analysis.', parent=win)
                win.destroy()
                return
            if restore_auto:
                self._peak_restore(row)
            else:
                self._peak_assign(row, selection[0])
            self._peak_refresh()
            redraw()

        assign = ttk.Button(actions, text='Assign as product', command=change)
        assign.pack(side='left')
        restore = ttk.Button(actions, text='Restore automatic assignment', command=lambda: change(True))
        restore.pack(side='left', padx=8)
        table_button = ttk.Button(actions, text='Hide peak table' if table_visible[0] else 'Show peak table', command=toggle_table)
        table_button.pack(side='left', padx=8)
        def close_inspector():
            save_layout()
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', close_inspector)
        ttk.Button(actions, text='Close', command=close_inspector).pack(side='right')
        visible_indices = inspection_peak_indices(well)
        for i in visible_indices:
            table.insert('', 'end', iid=str(i))
        initial = nearest_inspection_peak(well, rt, visible_indices) if rt is not None else override['peak_index'] if override and override['peak_index'] in visible_indices else visible_indices[0]
        table.selection_set(str(initial))
        table.see(str(initial))
        table.bind('<<TreeviewSelect>>', redraw)
        def rebuild_table():
            selected = selection[0]
            indices = inspection_peak_indices(well, show_spectra.get())
            table.delete(*table.get_children())
            for i in indices:
                table.insert('', 'end', iid=str(i))
            if selected not in indices:
                selected = nearest_inspection_peak(well, float(peaks[selected]['time']), indices)
            table.selection_set(str(selected))
            table.see(str(selected))
            redraw()
        spectra_toggle.configure(command=rebuild_table)
        def select_on_plot(event):
            if event.inaxes is uv and event.xdata is not None and not toolbar.mode:
                idx = nearest_inspection_peak(well, event.xdata)
                if not table.exists(str(idx)):
                    return
                table.selection_set(str(idx))
                table.see(str(idx))
        canvas.mpl_connect('button_press_event', select_on_plot)
        redraw()
        return win
