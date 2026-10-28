from __future__ import annotations

import math

from xinpilot_shared import *


class ManualWorkflowFrame(ttk.Frame):
    PLATE_OPTIONS = ("96-well", "48-well", "24-well")
    PLATE_DIMS = {
        "96-well": (8, 12),
        "48-well": (6, 8),
        "24-well": (4, 6),
    }

    def __init__(self, master, *, compound_provider, push_callback=None):
        super().__init__(master, style="Chem.TFrame")
        self.compound_provider = compound_provider
        self.push_callback = push_callback
        self.rows: List[Dict[str, str]] = []
        self.map_cells: Dict[str, tk.Label] = {}
        self.structure_window: tk.Toplevel | None = None
        self.structure_image_label: ttk.Label | None = None
        self.structure_title_label: ttk.Label | None = None
        self.structure_photo = None
        self._syncing_well_map = False
        self._manual_split_job = None
        self._build_ui()

    def _build_ui(self):
        self.plate_size_var = tk.StringVar(value=self.PLATE_OPTIONS[0])
        self.reaction_wells_var = tk.StringVar()
        self.chemical_var = tk.StringVar()
        self.reaction_umol_var = tk.StringVar()
        self.transfer_volume_var = tk.StringVar()
        self.temperature_var = tk.StringVar()
        self.duration_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.multi_select_wells_var = tk.BooleanVar(value=False)
        self.show_structure_var = tk.BooleanVar(value=False)
        self.is_building_block_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")

        self.manual_panes = ttk.Panedwindow(self, orient="vertical")
        self.manual_panes.pack(fill="both", expand=True, padx=8, pady=8)
        map_pane = ttk.Frame(self.manual_panes, style="Chem.TFrame", padding=(0, 0, 0, 6))
        table_pane = ttk.Frame(self.manual_panes, style="Chem.TFrame")
        self.manual_panes.add(map_pane, weight=3)
        self.manual_panes.add(table_pane, weight=4)

        self._build_well_map_ui(map_pane)

        table_box = ttk.LabelFrame(table_pane, text="Mapped additions", padding=8, style="RowRegion.TLabelframe")
        table_box.pack(fill="both", expand=True)
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        columns = ("plate_size", "reaction_well", "chemical", "is_building_block", "reaction_umol", "transfer_ul", "temperature", "duration", "notes")
        headings = ("Map", "Reaction well", "Chemical ID", "BB?", "umol/rxn", "Transfer uL", "Temp", "Length", "Notes")
        self.tree = ttk.Treeview(table_box, columns=columns, show="headings", height=18)
        widths = (90, 110, 220, 55, 85, 90, 100, 120, 330)
        for col, heading, width in zip(columns, headings, widths):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=70, anchor="w", stretch=True)
        ybar = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(table_box, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        style_region_widgets(table_box, "RowRegion")
        self._refresh_compound_choices()
        self.reaction_wells_var.trace_add("write", self._sync_map_from_wells_var)
        self.multi_select_wells_var.trace_add("write", self._on_well_selection_mode_changed)
        self.reaction_umol_var.trace_add("write", lambda *_args: self._calculate_transfer_volume_to_form())
        self.chemical_var.trace_add("write", self._on_structure_source_changed)
        self.show_structure_var.trace_add("write", self._on_show_structure_toggle)
        self._rebuild_well_map()
        self._manual_split_job = self.after(120, self._set_initial_manual_split)

    def _set_initial_manual_split(self):
        """Keep the complete 96-well map reachable at the initial window size."""
        self._manual_split_job = None
        try:
            available = self.manual_panes.winfo_height()
            if available <= 1:
                self._manual_split_job = self.after(120, self._set_initial_manual_split)
                return
            map_height = max(260, min(390, available - 170))
            self.manual_panes.sashpos(0, map_height)
        except Exception:
            pass

    def destroy(self):
        if self._manual_split_job is not None:
            try:
                self.after_cancel(self._manual_split_job)
            except tk.TclError:
                pass
            self._manual_split_job = None
        super().destroy()

    def _build_well_map_ui(self, parent):
        self.map_box = ttk.LabelFrame(parent, text="Reaction well map", padding=8, style="FileRegion.TLabelframe")
        self.map_box.pack(fill="both", expand=True)
        self.map_box.columnconfigure(0, weight=1)
        self.map_box.rowconfigure(1, weight=1)

        map_header = ttk.Frame(self.map_box, style="FileRegion.TFrame")
        map_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        map_header.columnconfigure(3, weight=1)
        ttk.Label(map_header, text="Plate map").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.plate_combo = ttk.Combobox(
            map_header,
            textvariable=self.plate_size_var,
            values=self.PLATE_OPTIONS,
            state="readonly",
            width=12,
        )
        self.plate_combo.grid(row=0, column=1, sticky="w")
        self.plate_combo.bind("<<ComboboxSelected>>", self._on_plate_size_changed)
        ttk.Label(map_header, text="Reaction well(s)").grid(row=0, column=2, sticky="w", padx=(18, 6))
        ttk.Entry(map_header, textvariable=self.reaction_wells_var, width=28).grid(row=0, column=3, sticky="ew")
        ttk.Button(map_header, text="Map Select", command=self._pick_reaction_wells).grid(
            row=0, column=4, sticky="w", padx=(8, 0)
        )

        self.map_grid = ttk.Frame(self.map_box, style="FileRegion.TFrame")
        self.map_grid.grid(row=1, column=0, sticky="nw")

        map_actions = ttk.Frame(self.map_box, style="FileRegion.TFrame")
        map_actions.grid(row=1, column=1, sticky="nsew", padx=(12, 0))
        map_actions.columnconfigure(0, weight=1)
        map_actions.rowconfigure(4, weight=1)
        ttk.Button(
            map_actions,
            text="Repeat One Reagent",
            command=self._open_add_reagents_dialog,
            style="ChemAction.TButton",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            map_actions,
            text="Assign Different Reagents",
            command=self._open_assign_different_reagents_dialog,
            style="ChemAction.TButton",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(map_actions, text="Clear Wells", command=self._clear_selected_wells).grid(
            row=2, column=0, sticky="ew"
        )
        self.delete_rows_button = ttk.Button(
            map_actions, text="Delete selected row(s)", command=self._remove_selected,
        )
        self.delete_rows_button.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        from xinpilot_tooltips import Tooltip
        Tooltip(self.delete_rows_button, "Select additions in the table below. Delete only those rows; keep other additions in the same well. Use Ctrl or Shift to select multiple rows.")
        ttk.Checkbutton(map_actions, text="Keep previous wells selected", variable=self.multi_select_wells_var).grid(
            row=4, column=0, sticky="ew", pady=(6, 0)
        )
        ttk.Button(
            map_actions,
            text="Push All to Cheminformatics",
            command=self._push_to_cheminformatics,
            style="ChemAction.TButton",
        ).grid(row=5, column=0, sticky="sew", pady=(12, 0))

        style_region_widgets(map_header, "FileRegion")
        style_region_widgets(map_actions, "FileRegion")

        self.map_menu = tk.Menu(self, tearoff=0)
        self.map_menu.add_command(label="Repeat one reagent", command=self._open_add_reagents_dialog)
        self.map_menu.add_command(label="Assign different reagents", command=self._open_assign_different_reagents_dialog)

    def _field(self, parent, row: int, col: int, label: str, var: tk.StringVar, *, width: int = 16, combo: bool = False):
        columnspan = 5 if label == "Notes" else 1
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0 if col == 0 else 12, 6), pady=3)
        if combo:
            widget = ttk.Combobox(parent, textvariable=var, values=self._compound_choices(), width=width)
            self.chemical_combo = widget
            widget.bind("<<ComboboxSelected>>", lambda _event: self._apply_selected_compound_volume_to_form())
        else:
            widget = ttk.Entry(parent, textvariable=var, width=width)
        widget.grid(row=row, column=col + 1, columnspan=columnspan, sticky="ew", pady=3)

    def _compound_choices(self) -> List[str]:
        choices = []
        for rec in list(self.compound_provider() or []):
            vals = _record_values(rec)
            cid = self._record_chemical_id(vals)
            name = str(vals.get("Name", "") or "").strip()
            label = cid if not name else f"{cid} - {name}" if cid else name
            if label and label not in choices:
                choices.append(label)
        return choices

    @staticmethod
    def _record_chemical_id(values: Dict[str, object]) -> str:
        for key in ("ID", "Chemical ID", "chemical_id", "chemical"):
            value = str(values.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _compound_lookup(self, reaction_umol: object = None) -> Dict[str, Dict[str, str]]:
        lookup: Dict[str, Dict[str, str]] = {}
        if reaction_umol is None:
            reaction_umol = self.reaction_umol_var.get() if hasattr(self, "reaction_umol_var") else ""
        for rec in list(self.compound_provider() or []):
            vals = _record_values(rec)
            cid = self._record_chemical_id(vals)
            name = str(vals.get("Name", "") or "").strip()
            label = cid if not name else f"{cid} - {name}" if cid else name
            concentration_m = self._record_concentration_m(vals)
            volume = self._volume_from_umol_and_conc(reaction_umol, concentration_m)
            payload = {
                "chemical_id": cid,
                "chemical_name": name,
                "label": label,
                "transfer_ul": volume,
                "concentration_m": str(concentration_m or ""),
            }
            for candidate in (cid, name, label):
                key = str(candidate or "").strip().casefold()
                if key:
                    lookup[key] = payload
        return lookup

    def _selected_compound_payload(self) -> Dict[str, str]:
        text = self.chemical_var.get().strip()
        return self._compound_payload_for_label(text)

    def _compound_payload_for_label(self, label: object, reaction_umol: object = None) -> Dict[str, str]:
        text = str(label or "").strip()
        payload = self._compound_lookup(reaction_umol).get(text.casefold())
        if payload:
            return dict(payload)
        cid = text.split(" - ", 1)[0].strip() if " - " in text else text
        return {"chemical_id": cid, "chemical_name": "", "label": text, "transfer_ul": "", "concentration_m": ""}

    def _compound_for_chemical_label(self, label: str):
        wanted = (label or "").strip().casefold()
        if not wanted:
            return None
        wanted_id = wanted.split(" - ", 1)[0].strip() if " - " in wanted else wanted
        for rec in list(self.compound_provider() or []):
            data = _record_values(rec)
            cid = self._record_chemical_id(data)
            name = str(data.get("Name", "") or "").strip()
            compound_label = cid if not name else f"{cid} - {name}" if cid else name
            for candidate in (cid, name, compound_label):
                text = str(candidate or "").strip().casefold()
                if text and text in {wanted, wanted_id}:
                    return data
        return None

    def _on_show_structure_toggle(self, *_args):
        if self.show_structure_var.get():
            self._refresh_structure_window()
        else:
            self._close_structure_window()

    def _on_structure_source_changed(self, *_args):
        if self.show_structure_var.get():
            self.after_idle(self._refresh_structure_window)

    def _close_structure_window(self):
        win = self.structure_window
        self.structure_window = None
        self.structure_image_label = None
        self.structure_title_label = None
        self.structure_photo = None
        if win is not None and win.winfo_exists():
            try:
                win.destroy()
            except Exception:
                pass

    def _on_structure_window_closed(self):
        self.show_structure_var.set(False)
        self._close_structure_window()

    def _ensure_structure_window(self):
        if self.structure_window is not None and self.structure_window.winfo_exists():
            return
        win = tk.Toplevel(self)
        win.title("Chemical Structure")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._on_structure_window_closed)
        try:
            win.transient(self.winfo_toplevel())
        except Exception:
            pass
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        self.structure_title_label = ttk.Label(frame, text="", anchor="center")
        self.structure_title_label.pack(fill="x", pady=(0, 6))
        self.structure_image_label = ttk.Label(frame, text="", anchor="center")
        self.structure_image_label.pack(fill="both", expand=True)
        self.structure_window = win
        try:
            _position_toplevel_near(win, self.chemical_combo)
        except Exception:
            pass

    def _refresh_structure_window(self):
        if not self.show_structure_var.get():
            return
        self._ensure_structure_window()
        if self.structure_window is None or not self.structure_window.winfo_exists():
            return
        label = self.chemical_var.get().strip()
        data = self._compound_for_chemical_label(label)
        title = label or "No Chemical ID"
        smiles = str((data or {}).get("SMILES", "") or "").strip()
        display_name = str((data or {}).get("Name", "") or "").strip()
        if display_name and display_name.casefold() not in title.casefold():
            title = f"{title} - {display_name}" if label else display_name
        if self.structure_title_label is not None:
            self.structure_title_label.configure(text=title)
        if self.structure_image_label is None:
            return
        self.structure_photo = None
        if not smiles:
            self.structure_image_label.configure(image="", text="Structure not found")
            return
        if Chem is None or Draw is None or ImageTk is None:
            self.structure_image_label.configure(image="", text="Structure renderer unavailable")
            return
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.structure_image_label.configure(image="", text="Invalid SMILES")
            return
        try:
            img = Draw.MolToImage(mol, size=(300, 220))
            self.structure_photo = ImageTk.PhotoImage(img)
            self.structure_image_label.configure(image=self.structure_photo, text="")
        except Exception as exc:
            self.structure_image_label.configure(image="", text=f"Structure render failed: {exc}")

    @staticmethod
    def _record_concentration_m(values: Dict[str, object]) -> Optional[float]:
        for key in ("Conc.", "Concentration", "concentration", "conc"):
            value = str(values.get(key, "") or "").strip()
            if not value:
                continue
            match = re.fullmatch(r"\s*([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([munµμ]?m)?\s*", value, re.IGNORECASE)
            if not match:
                continue
            concentration = float(match.group(1))
            unit = (match.group(2) or "M").lower()
            if unit == "mm":
                concentration /= 1000.0
            elif unit in {"um", "µm", "μm"}:
                concentration /= 1_000_000.0
            elif unit == "nm":
                concentration /= 1_000_000_000.0
            if math.isfinite(concentration) and concentration > 0:
                return concentration
        return None

    @staticmethod
    def _volume_from_umol_and_conc(umol: object, concentration_m: Optional[float]) -> str:
        if concentration_m is None or not math.isfinite(concentration_m) or concentration_m <= 0:
            return ""
        try:
            amount = float(str(umol or "").strip())
        except ValueError:
            return ""
        if not math.isfinite(amount) or amount <= 0:
            return ""
        volume = amount / concentration_m
        if not math.isfinite(volume) or volume <= 0:
            return ""
        text = f"{volume:.6g}"
        return text + ".0" if "." not in text and "e" not in text.lower() else text

    def _refresh_compound_choices(self):
        if hasattr(self, "chemical_combo"):
            self.chemical_combo.configure(values=self._compound_choices())

    def _plate_dims(self, plate_size: Optional[str] = None) -> Tuple[int, int]:
        return self.PLATE_DIMS.get(plate_size or self.plate_size_var.get(), self.PLATE_DIMS["96-well"])

    def _parse_reaction_wells(self, expr: str, plate_size: Optional[str] = None) -> List[str]:
        rows, cols = self._plate_dims(plate_size)
        indices = tecan_frame.parse_well_expr(expr, rows, cols, "row-major")
        return [tecan_frame.index_to_label(idx, rows, cols, "row-major") for idx in indices]

    def _sorted_wells(self, wells: List[str], plate_size: Optional[str] = None) -> List[str]:
        row_count, col_count = self._plate_dims(plate_size)

        def key(well: str):
            match = tecan_frame.WELL_LABEL_RE.match(str(well or "").strip().upper())
            if not match:
                return (999, 999)
            row = tecan_frame.row_label_to_number(match.group(1))
            col = int(match.group(2))
            if row > row_count or col > col_count:
                return (999, 999)
            return (row, col)

        return sorted({str(well or "").strip().upper() for well in wells if str(well or "").strip()}, key=key)

    def _selected_wells(self) -> List[str]:
        try:
            return self._parse_reaction_wells(self.reaction_wells_var.get())
        except Exception:
            return []

    def _set_selected_wells(self, wells: List[str]):
        if not self.multi_select_wells_var.get() and wells:
            wells = wells[-1:]
        self._syncing_well_map = True
        try:
            self.reaction_wells_var.set(",".join(self._sorted_wells(wells)))
        finally:
            self._syncing_well_map = False
        self._paint_well_map()

    def _clear_selected_wells(self):
        selected = set(self._selected_wells())
        if not selected:
            messagebox.showwarning("Manual workflow", "Select one or more reaction wells to clear.")
            return
        plate_size = self.plate_size_var.get()
        remaining = [
            row for row in self.rows
            if not (
                row.get("plate_size", self.PLATE_OPTIONS[0]) == plate_size
                and str(row.get("reaction_well", "") or "").strip().upper() in selected
            )
        ]
        removed = len(self.rows) - len(remaining)
        self.rows = remaining
        self._set_selected_wells([])
        self._refresh_table()
        self.status_var.set(f"Cleared {removed} chemical addition(s) from {len(selected)} selected well(s)")

    def _sync_map_from_wells_var(self, *_args):
        if not self._syncing_well_map:
            self._paint_well_map()

    def _on_plate_size_changed(self, _event=None):
        self._set_selected_wells([])
        self._rebuild_well_map()

    def _on_well_selection_mode_changed(self, *_args):
        if not self.multi_select_wells_var.get():
            self._set_selected_wells(self._selected_wells()[:1])
        else:
            self._paint_well_map()

    def _rebuild_well_map(self):
        for child in self.map_grid.winfo_children():
            child.destroy()
        self.map_cells.clear()
        rows, cols = self._plate_dims()

        for r in range(1, rows + 1):
            ttk.Label(self.map_grid, text=tecan_frame.row_number_to_label(r), width=3, anchor="center").grid(row=r, column=0, padx=1, pady=1)
        for c in range(1, cols + 1):
            ttk.Label(self.map_grid, text=str(c), width=5, anchor="center").grid(row=0, column=c, padx=1, pady=1)

        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                label = f"{tecan_frame.row_number_to_label(r)}{c}"
                cell = tk.Label(self.map_grid, text=label, width=6, relief="groove", bg=COLORS["file_region"], fg="black")
                cell.grid(row=r, column=c, padx=1, pady=1)
                cell.bind("<Button-1>", lambda _event, well=label: self._toggle_map_well(well))
                cell.bind("<Button-3>", lambda event, well=label: self._show_map_menu(event, well))
                self.map_cells[label] = cell
        style_region_widgets(self.map_grid, "FileRegion")
        self._paint_well_map()

    def _paint_well_map(self):
        selected = set(self._selected_wells())
        populated = {str(row.get("reaction_well", "") or "").strip().upper() for row in self.rows}
        for well, cell in self.map_cells.items():
            if well in selected:
                cell.configure(bg="#2E7D32", fg="white", relief="groove")
            elif well in populated:
                cell.configure(bg="#B9DCF4", fg="#17324D", relief="sunken")
            else:
                cell.configure(bg=COLORS["file_region"], fg="black", relief="groove")

    def _toggle_map_well(self, well: str):
        if not self.multi_select_wells_var.get():
            current = self._selected_wells()
            self._set_selected_wells([] if current == [well] else [well])
            return
        selected = set(self._selected_wells())
        if well in selected:
            selected.remove(well)
        else:
            selected.add(well)
        self._set_selected_wells(list(selected))

    def _show_map_menu(self, event, well: str):
        selected = set(self._selected_wells())
        if well not in selected:
            if self.multi_select_wells_var.get():
                selected.add(well)
                self._set_selected_wells(list(selected))
            else:
                self._set_selected_wells([well])
        try:
            self.map_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.map_menu.grab_release()

    def _apply_compound_volume_to_var(self, chemical_var: tk.StringVar, volume_var: tk.StringVar, reaction_umol: object = None):
        lookup = self._compound_lookup(reaction_umol)
        payload = lookup.get((chemical_var.get() or "").strip().casefold())
        volume_var.set(payload.get("transfer_ul", "") if payload else "")

    def _apply_selected_compound_volume_to_form(self):
        self._apply_compound_volume_to_var(self.chemical_var, self.transfer_volume_var)

    def _calculate_transfer_volume_to_form(self):
        self._apply_selected_compound_volume_to_form()

    def _open_add_reagents_dialog(self):
        wells = self._selected_wells()
        if not wells:
            messagebox.showwarning("Manual workflow", "Select one or more reaction wells on the map first.")
            return
        self._refresh_compound_choices()
        win = tk.Toplevel(self)
        win.title("Repeat One Reagent")
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Reaction well(s): {', '.join(wells)}").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        chemical_var = tk.StringVar(value=self.chemical_var.get())
        reaction_umol_var = tk.StringVar(value=self.reaction_umol_var.get())
        volume_var = tk.StringVar(value=self.transfer_volume_var.get())
        temperature_var = tk.StringVar(value=self.temperature_var.get())
        duration_var = tk.StringVar(value=self.duration_var.get())
        notes_var = tk.StringVar(value=self.notes_var.get())

        ttk.Label(body, text="Chemical ID").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        chemical_combo = ttk.Combobox(body, textvariable=chemical_var, values=self._compound_choices(), width=34)
        chemical_combo.grid(row=1, column=1, sticky="ew", pady=3)
        chemical_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_compound_volume_to_var(chemical_var, volume_var, reaction_umol_var.get()))
        chemical_var.trace_add("write", lambda *_args: self._apply_compound_volume_to_var(chemical_var, volume_var, reaction_umol_var.get()))

        ttk.Checkbutton(
            body,
            text="This is a building block",
            variable=self.is_building_block_var,
        ).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(body, text="umol/rxn").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(body, textvariable=reaction_umol_var, width=12).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(body, text="Transfer uL").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(body, textvariable=volume_var, width=12).grid(row=4, column=1, sticky="w", pady=3)
        reaction_umol_var.trace_add("write", lambda *_args: self._apply_compound_volume_to_var(chemical_var, volume_var, reaction_umol_var.get()))
        ttk.Label(body, text="Temperature").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(body, textvariable=temperature_var, width=16).grid(row=5, column=1, sticky="w", pady=3)
        ttk.Label(body, text="Reaction length").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(body, textvariable=duration_var, width=16).grid(row=6, column=1, sticky="w", pady=3)
        ttk.Label(body, text="Notes").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(body, textvariable=notes_var, width=42).grid(row=7, column=1, sticky="ew", pady=3)
        body.columnconfigure(1, weight=1)

        self._apply_compound_volume_to_var(chemical_var, volume_var)

        def add_reagents():
            self.chemical_var.set(chemical_var.get())
            self.reaction_umol_var.set(reaction_umol_var.get())
            self.transfer_volume_var.set(volume_var.get())
            self.temperature_var.set(temperature_var.get())
            self.duration_var.set(duration_var.get())
            self.notes_var.set(notes_var.get())
            base = self._base_row_from_form()
            if base is None:
                return
            selected_wells = [well for well in base.pop("wells", "").split(",") if well]
            for selected_well in selected_wells:
                self.rows.append({**base, "reaction_well": selected_well})
            self._refresh_table()
            self._set_selected_wells([])
            win.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Repeat One Reagent", command=add_reagents, style="Accent.TButton").pack(side="left")
        chemical_combo.focus_set()

    def _shared_assignment_transfer_volume(
        self,
        chemical_labels: List[object],
        reaction_umol: object,
    ) -> str:
        """Calculate one volume only when every assignment has the same known concentration."""
        labels = [str(label or "").strip() for label in chemical_labels]
        if not labels or any(not label for label in labels):
            return ""
        concentrations: List[float] = []
        for label in labels:
            payload = self._compound_payload_for_label(label, reaction_umol)
            try:
                concentration = float(str(payload.get("concentration_m", "") or "").strip())
            except ValueError:
                return ""
            if concentration <= 0:
                return ""
            concentrations.append(concentration)
        first = concentrations[0]
        if any(abs(concentration - first) > max(1e-12, abs(first) * 1e-9) for concentration in concentrations[1:]):
            return ""
        return self._volume_from_umol_and_conc(reaction_umol, first)

    def _different_reagent_rows(
        self,
        wells: List[str],
        chemical_labels: List[str],
        building_block_flags: List[bool],
        *,
        transfer_ul: object,
        reaction_umol: object = "",
        temperature: object = "",
        duration: object = "",
        notes: object = "",
        plate_size: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        """Build one positional Manual addition per selected well."""
        if not wells:
            raise ValueError("Select at least one reaction well.")
        if len(chemical_labels) != len(wells) or len(building_block_flags) != len(wells):
            raise ValueError("Each selected reaction well must have exactly one reagent assignment.")
        try:
            volume = float(str(transfer_ul or "").strip())
        except ValueError as exc:
            raise ValueError("Shared Transfer uL must be a number.") from exc
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError("Shared Transfer uL must be greater than zero.")

        common = {
            "plate_size": plate_size or self.plate_size_var.get(),
            "reaction_umol": str(reaction_umol or "").strip(),
            "transfer_ul": str(transfer_ul or "").strip(),
            "temperature": str(temperature or "").strip(),
            "duration": str(duration or "").strip(),
            "notes": str(notes or "").strip(),
        }
        additions: List[Dict[str, object]] = []
        for well, label, is_building_block in zip(wells, chemical_labels, building_block_flags):
            payload = self._compound_payload_for_label(label, reaction_umol)
            chemical_id = str(payload.get("chemical_id", "") or "").strip()
            if not chemical_id:
                raise ValueError(f"Assign a Chemical ID to reaction well {well}.")
            additions.append({
                **common,
                "reaction_well": str(well or "").strip().upper(),
                "chemical": chemical_id,
                "chemical_id": chemical_id,
                "chemical_name": payload.get("chemical_name", ""),
                "chemical_label": payload.get("label", str(label or "").strip()),
                "is_building_block": bool(is_building_block),
            })
        return additions

    def _open_assign_different_reagents_dialog(self):
        wells = self._selected_wells()
        if not wells:
            messagebox.showwarning("Manual workflow", "Select one or more reaction wells on the map first.")
            return
        wells = self._sorted_wells(wells)
        choices = self._compound_choices()

        win = tk.Toplevel(self)
        win.title("Assign Different Reagents")
        win.transient(self.winfo_toplevel())
        win.resizable(True, True)
        win.minsize(560, 520)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        ttk.Label(
            body,
            text=(
                f"{len(wells)} wells selected in plate order: {', '.join(wells)}\n"
                "Assign one reagent to each well. Every addition below uses the same Transfer uL."
            ),
            wraplength=820,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        assignment_vars = [tk.StringVar() for _well in wells]
        building_block_vars = [tk.BooleanVar(value=True) for _well in wells]

        assignment_box = ttk.LabelFrame(body, text="Well-to-reagent assignments", padding=8)
        assignment_box.grid(row=1, column=0, sticky="nsew")
        assignment_box.rowconfigure(0, weight=1)
        assignment_box.columnconfigure(0, weight=1)
        assignment_canvas = tk.Canvas(assignment_box, highlightthickness=0, width=430)
        assignment_scroll = ttk.Scrollbar(assignment_box, orient="vertical", command=assignment_canvas.yview)
        assignment_canvas.configure(yscrollcommand=assignment_scroll.set)
        assignment_canvas.grid(row=0, column=0, sticky="nsew")
        assignment_scroll.grid(row=0, column=1, sticky="ns")
        assignments = ttk.Frame(assignment_canvas)
        assignment_window = assignment_canvas.create_window((0, 0), window=assignments, anchor="nw")
        assignments.columnconfigure(2, weight=1)
        ttk.Label(assignments, text="#", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(assignments, text="Well", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(assignments, text="Chemical ID", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(assignments, text="BB?", style="Muted.TLabel").grid(row=0, column=3, sticky="w", padx=(8, 0))
        for row_index, (well, variable, building_var) in enumerate(
            zip(wells, assignment_vars, building_block_vars), start=1
        ):
            ttk.Label(assignments, text=str(row_index), width=3).grid(row=row_index, column=0, sticky="w", pady=2)
            ttk.Label(assignments, text=well, width=6).grid(row=row_index, column=1, sticky="w", pady=2)
            ttk.Combobox(assignments, textvariable=variable, values=choices, state="normal", width=34).grid(
                row=row_index, column=2, sticky="ew", pady=2
            )
            ttk.Checkbutton(assignments, variable=building_var).grid(
                row=row_index, column=3, sticky="w", padx=(8, 0), pady=2
            )

        def resize_assignments(_event=None):
            assignment_canvas.configure(scrollregion=assignment_canvas.bbox("all"))
            assignment_canvas.itemconfigure(assignment_window, width=max(1, assignment_canvas.winfo_width()))

        assignments.bind("<Configure>", resize_assignments)
        assignment_canvas.bind("<Configure>", resize_assignments)

        common_box = ttk.LabelFrame(body, text="Shared addition settings", padding=8)
        common_box.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for col in (1, 3, 5):
            common_box.columnconfigure(col, weight=1)
        # These values belong only to this positional assignment. Do not seed
        # them from Repeat One Reagent or previously mapped additions.
        volume_var = tk.StringVar()
        reaction_umol_var = tk.StringVar()
        temperature_var = tk.StringVar()
        duration_var = tk.StringVar()
        notes_var = tk.StringVar()
        ttk.Label(common_box, text="Transfer uL").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(common_box, textvariable=volume_var, width=12).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(common_box, text="umol/rxn (optional)").grid(row=0, column=2, sticky="w", padx=(12, 6), pady=3)
        ttk.Entry(common_box, textvariable=reaction_umol_var, width=12).grid(row=0, column=3, sticky="ew", pady=3)
        ttk.Label(common_box, text="Temperature").grid(row=0, column=4, sticky="w", padx=(12, 6), pady=3)
        ttk.Entry(common_box, textvariable=temperature_var, width=14).grid(row=0, column=5, sticky="ew", pady=3)
        ttk.Label(common_box, text="Reaction length").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(common_box, textvariable=duration_var, width=14).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(common_box, text="Notes").grid(row=1, column=2, sticky="w", padx=(12, 6), pady=3)
        ttk.Entry(common_box, textvariable=notes_var).grid(row=1, column=3, columnspan=3, sticky="ew", pady=3)

        def update_shared_volume(*_args):
            volume_var.set(
                self._shared_assignment_transfer_volume(
                    [variable.get() for variable in assignment_vars],
                    reaction_umol_var.get(),
                )
            )

        reaction_umol_var.trace_add("write", update_shared_volume)
        for variable in assignment_vars:
            variable.trace_add("write", update_shared_volume)

        def add_assignments():
            try:
                additions = self._different_reagent_rows(
                    wells,
                    [variable.get() for variable in assignment_vars],
                    [variable.get() for variable in building_block_vars],
                    transfer_ul=volume_var.get(),
                    reaction_umol=reaction_umol_var.get(),
                    temperature=temperature_var.get(),
                    duration=duration_var.get(),
                    notes=notes_var.get(),
                    plate_size=self.plate_size_var.get(),
                )
            except ValueError as exc:
                messagebox.showwarning("Assign Different Reagents", str(exc), parent=win)
                return
            self.rows.extend(additions)
            self._refresh_table()
            self._set_selected_wells([])
            self.status_var.set(
                f"Assigned {len(additions)} different reagent addition(s) with one shared volume"
            )
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(
            buttons,
            text=f"Add {len(wells)} Assignments",
            command=add_assignments,
            style="Accent.TButton",
        ).pack(side="left")
        try:
            _position_toplevel_near(win, self.map_box)
        except Exception:
            pass

    def _pick_reaction_wells(self):
        rows, cols = self._plate_dims()
        dlg = tecan_frame.WellMapDialog(
            self,
            rows,
            cols,
            self.reaction_wells_var.get(),
            vertical_view=False,
            anchor=self,
        )
        self.wait_window(dlg)
        if getattr(dlg, "result_labels", ""):
            self.reaction_wells_var.set(dlg.result_labels)
            self._paint_well_map()

    def _normalized_chemical(self) -> str:
        return self._selected_compound_payload().get("chemical_id", "").strip()

    def _base_row_from_form(self) -> Optional[Dict[str, str]]:
        chemical = self._normalized_chemical()
        if not chemical:
            messagebox.showwarning("Manual workflow", "Select or enter a chemical ID before adding it.")
            return None
        try:
            volume = float(self.transfer_volume_var.get().strip())
        except ValueError:
            messagebox.showwarning("Manual workflow", "Transfer uL must be a number.")
            return None
        if not math.isfinite(volume) or volume <= 0:
            messagebox.showwarning("Manual workflow", "Transfer uL must be greater than zero.")
            return None
        try:
            wells = self._parse_reaction_wells(self.reaction_wells_var.get())
        except Exception as exc:
            messagebox.showwarning("Manual workflow", str(exc))
            return None
        if not wells:
            messagebox.showwarning("Manual workflow", "Select at least one reaction well.")
            return None
        compound = self._selected_compound_payload()
        return {
            "plate_size": self.plate_size_var.get(),
            "chemical": compound.get("chemical_id", chemical),
            "chemical_id": compound.get("chemical_id", chemical),
            "chemical_name": compound.get("chemical_name", ""),
            "chemical_label": compound.get("label", self.chemical_var.get().strip()),
            "is_building_block": bool(self.is_building_block_var.get()),
            "reaction_umol": self.reaction_umol_var.get().strip(),
            "transfer_ul": self.transfer_volume_var.get().strip(),
            "temperature": self.temperature_var.get().strip(),
            "duration": self.duration_var.get().strip(),
            "notes": self.notes_var.get().strip(),
            "wells": ",".join(wells),
        }

    def _values_for_tree(self, row: Dict[str, str]) -> Tuple[str, ...]:
        return (
            row.get("plate_size", ""),
            row.get("reaction_well", ""),
            row.get("chemical_id", "") or row.get("chemical", ""),
            "Yes" if coerce_bool(row.get("is_building_block", False)) else "",
            row.get("reaction_umol", ""),
            row.get("transfer_ul", ""),
            row.get("temperature", ""),
            row.get("duration", ""),
            row.get("notes", ""),
        )

    def _refresh_table(self):
        selected_index = None
        sel = self.tree.selection()
        if sel:
            selected_index = int(sel[0]) if str(sel[0]).isdigit() else None
        self.tree.delete(*self.tree.get_children())
        for idx, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(idx), values=self._values_for_tree(row))
        if selected_index is not None and self.tree.exists(str(selected_index)):
            self.tree.selection_set(str(selected_index))
            self.tree.focus(str(selected_index))
        reaction_count = len({row.get("reaction_well", "") for row in self.rows if row.get("reaction_well", "")})
        self.status_var.set(f"{reaction_count} reaction well(s), {len(self.rows)} chemical addition(s)")
        if hasattr(self, "map_cells"):
            self._paint_well_map()

    def _add_chemical(self):
        base = self._base_row_from_form()
        if base is None:
            return
        wells = [well for well in base.pop("wells", "").split(",") if well]
        for well in wells:
            self.rows.append({**base, "reaction_well": well})
        self._refresh_table()

    def _selected_index(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Manual workflow", "Select a manual row first.")
            return None
        return int(sel[0])

    def _remove_selected(self):
        selection = self.tree.selection()
        indices = {int(item) for item in selection if str(item).isdigit() and 0 <= int(item) < len(self.rows)}
        if not indices:
            messagebox.showwarning("Manual workflow", "Select one or more additions in the table to delete.")
            return
        self.rows = [row for index, row in enumerate(self.rows) if index not in indices]
        # Do not select a different addition merely because row indices shifted.
        self.tree.selection_remove(*selection)
        self._refresh_table()
        self.status_var.set(f"Deleted {len(indices)} selected chemical addition(s). " + self.status_var.get())

    def _update_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        base = self._base_row_from_form()
        if base is None:
            return
        wells = [well for well in base.pop("wells", "").split(",") if well]
        if len(wells) != 1:
            messagebox.showwarning(
                "Manual workflow",
                "Update Selected edits one table row. Select exactly one reaction well.",
            )
            return
        self.rows[idx] = {**base, "reaction_well": wells[0]}
        self._refresh_table()
        if self.tree.exists(str(idx)):
            self.tree.selection_set(str(idx))
            self.tree.focus(str(idx))
            self.tree.see(str(idx))

    def _load_selected(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        row = self.rows[int(sel[0])]
        plate_size = row.get("plate_size", self.PLATE_OPTIONS[0])
        plate_size = plate_size if plate_size in self.PLATE_OPTIONS else self.PLATE_OPTIONS[0]
        if self.plate_size_var.get() != plate_size:
            self.plate_size_var.set(plate_size)
            self._rebuild_well_map()
        self.reaction_wells_var.set(row.get("reaction_well", ""))
        self.chemical_var.set(row.get("chemical_label", "") or row.get("chemical_id", "") or row.get("chemical", ""))
        self.is_building_block_var.set(coerce_bool(row.get("is_building_block", False)))
        self.reaction_umol_var.set(row.get("reaction_umol", ""))
        self.transfer_volume_var.set(row.get("transfer_ul", ""))
        self.temperature_var.set(row.get("temperature", ""))
        self.duration_var.set(row.get("duration", ""))
        self.notes_var.set(row.get("notes", ""))

    def _export_csv(self):
        if not self.rows:
            messagebox.showwarning("Manual workflow", "No manual reaction rows to export.")
            return
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = filedialog.asksaveasfilename(
            title="Export manual workflow CSV",
            defaultextension=".csv",
            initialdir=str(OUTPUT_DIR),
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not out:
            return
        headers = ["step", "plate_size", "reaction_well", "chemical", "reaction_umol", "transfer_ul", "temperature", "duration", "notes"]
        extra_headers = ["chemical_id", "chemical_name", "chemical_label", "is_building_block"]
        fieldnames = headers[:4] + extra_headers + headers[4:]
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for idx, row in enumerate(self.rows, start=1):
                writer.writerow({"step": idx, **row})
        self.status_var.set(f"Exported {len(self.rows)} manual row(s): {Path(out).name}")
        messagebox.showinfo("Manual workflow exported", f"Saved manual workflow CSV:\n{out}")

    def rows_for_cheminformatics(self) -> List[Dict[str, object]]:
        rows = []
        for block_index, row in enumerate(self.rows, start=1):
            well = str(row.get("reaction_well", "") or "").strip().upper()
            chemical = str(row.get("chemical_id", "") or row.get("chemical", "") or "").strip()
            if not well or not chemical:
                continue
            rows.append({
                "block": block_index,
                "well": well,
                "chemical": chemical,
                "chemical_id": chemical,
                "chemical_name": row.get("chemical_name", ""),
                "is_building_block": coerce_bool(row.get("is_building_block", False)),
                "reaction_umol": row.get("reaction_umol", ""),
                "volume": row.get("transfer_ul", ""),
                "dest_labware": f"Manual {row.get('plate_size', '96-well')} map",
                "dest_mode": f"{row.get('plate_size', '96-well')} horizontal",
                "source": "Manual workflow",
                "temperature": row.get("temperature", ""),
                "duration": row.get("duration", ""),
                "notes": row.get("notes", ""),
            })
        return rows

    def _push_to_cheminformatics(self):
        rows = self.rows_for_cheminformatics()
        if not rows:
            messagebox.showwarning("Manual workflow", "No manual reaction rows to push.")
            return
        if callable(self.push_callback):
            self.push_callback(rows)
            self.status_var.set(f"Pushed {len(rows)} manual row(s) to Cheminformatics")
        else:
            messagebox.showwarning("Manual workflow", "Cheminformatics push is not connected.")

    def transfer_blocks_for_summary(self) -> List[Dict[str, object]]:
        blocks = []
        for idx, row in enumerate(self.rows, start=1):
            try:
                volume = float(row.get("transfer_ul", 0.0) or 0.0)
            except Exception:
                continue
            plate_size = row.get("plate_size", "96-well")
            mode = f"{plate_size} horizontal"
            block = SimpleNamespace(
                source_labware="",
                source_well=1,
                source_volume=volume,
                dest_labware=f"Manual {plate_size} map",
                dest_wells_expr=row.get("reaction_well", ""),
                dest_volume=volume,
                disp_different_vol=False,
                dispense_groups=[],
                chemical_name=row.get("chemical_id", "") or row.get("chemical", ""),
                is_building_block=coerce_bool(row.get("is_building_block", False)),
                reaction_umol=str(row.get("reaction_umol", "") or ""),
                temperature=str(row.get("temperature", "") or ""),
                duration=str(row.get("duration", "") or ""),
            )
            blocks.append({
                "file_index": 0,
                "file_name": "Manual workflow",
                "mode": mode,
                "block_index": idx,
                "block": block,
                "chem_label_map": {},
                "from_snapshot": True,
            })
        return blocks

    def export_state(self) -> Dict[str, object]:
        return {
            "plate_size": self.plate_size_var.get(),
            "rows": [dict(row) for row in self.rows],
        }

    def _migrate_imported_row(self, row: Dict[str, object]) -> List[Dict[str, object]]:
        def normalized(existing: Dict[str, object]) -> Dict[str, object]:
            chemical = str(
                existing.get("chemical_id", "")
                or existing.get("Chemical ID", "")
                or existing.get("chemical", "")
                or ""
            ).strip()
            values = {key: str(value or "") for key, value in existing.items()}
            values["chemical"] = chemical
            values["chemical_id"] = chemical
            values.setdefault("chemical_name", str(existing.get("chemical_name", "") or ""))
            values.setdefault("chemical_label", str(existing.get("chemical_label", "") or chemical))
            values.setdefault("reaction_umol", str(existing.get("reaction_umol", "") or existing.get("umol", "") or ""))
            values["is_building_block"] = coerce_bool(existing.get("is_building_block", False))
            values.pop("reaction_id", None)
            return values

        if row.get("reaction_well"):
            return [normalized(row)]
        plate_size = "48-well" if "hplc" in str(row.get("dest_mode", "")).lower() else "96-well"
        raw_wells = str(row.get("dest_wells", "") or row.get("well", "") or "").strip().upper()
        wells = [part.strip() for part in raw_wells.split(",") if part.strip()] or [""]
        migrated = []
        for well in wells:
            chemical = str(row.get("chemical_id", "") or row.get("chemical", "") or "").strip()
            migrated.append({
                "plate_size": plate_size,
                "reaction_well": well,
                "chemical": chemical,
                "chemical_id": chemical,
                "chemical_name": str(row.get("chemical_name", "") or ""),
                "chemical_label": str(row.get("chemical_label", "") or chemical),
                "is_building_block": coerce_bool(row.get("is_building_block", False)),
                "reaction_umol": str(row.get("reaction_umol", "") or row.get("umol", "") or ""),
                "transfer_ul": str(row.get("transfer_ul", "") or row.get("dispense_ul", "") or row.get("aspirate_ul", "") or ""),
                "temperature": str(row.get("temperature", "") or ""),
                "duration": str(row.get("duration", "") or ""),
                "notes": str(row.get("notes", "") or ""),
            })
        return migrated

    def import_state(self, data: Dict[str, object]):
        if not isinstance(data, dict):
            return
        imported = []
        for row in data.get("rows", []) or []:
            if isinstance(row, dict):
                imported.extend(self._migrate_imported_row(row))
        self.rows = imported
        plate_size = str(data.get("plate_size", "") or "").strip()
        if plate_size not in self.PLATE_OPTIONS:
            plate_size = next(
                (
                    str(row.get("plate_size", "") or "").strip()
                    for row in imported
                    if str(row.get("plate_size", "") or "").strip() in self.PLATE_OPTIONS
                ),
                self.PLATE_OPTIONS[0],
            )
        self.plate_size_var.set(plate_size)
        self._set_selected_wells([])
        self.chemical_var.set("")
        self.reaction_umol_var.set("")
        self.transfer_volume_var.set("")
        self.temperature_var.set("")
        self.duration_var.set("")
        self.notes_var.set("")
        self.is_building_block_var.set(False)
        self._rebuild_well_map()
        self._refresh_table()
        self.status_var.set("Ready")
