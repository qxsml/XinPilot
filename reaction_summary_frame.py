from __future__ import annotations
from xinpilot.application.heatmap_layout import heatmap_layout, reaction_mode

from xinpilot_shared import *
from PIL import ImageFont


class HoverMapCanvas(tk.Canvas):
    def __init__(
        self,
        master,
        cells: List[Dict[str, object]],
        *,
        rows: int,
        cols: int,
        vial_mode: bool,
        row_headers: Optional[List[str]] = None,
        col_headers: Optional[List[str]] = None,
        **kwargs,
    ):
        width = max(280, cols * 46 + 70)
        height = max(170, rows * 42 + 62)
        super().__init__(master, width=width, height=height, highlightthickness=0, background=COLORS["panel"], **kwargs)
        self.cells = cells
        self.rows = rows
        self.cols = cols
        self.vial_mode = vial_mode
        self.row_headers = row_headers or [tecan_frame.row_number_to_label(r) for r in range(1, rows + 1)]
        self.col_headers = col_headers or [str(c) for c in range(1, cols + 1)]
        self.item_to_cell: Dict[int, Dict[str, object]] = {}
        self.hover_item: Optional[int] = None
        self.tooltip_window: Optional[tk.Toplevel] = None
        self.tooltip_label: Optional[tk.Label] = None
        self._draw()
        self.bind("<Leave>", self._clear_hover)

    def _cell_position(self, row: int, col: int) -> Tuple[float, float]:
        return 42 + (col - 1) * 46, 36 + (row - 1) * 42

    def _draw_vial(self, x: float, y: float, filled: bool) -> int:
        fill = "#3f464f" if filled else "#f8fafc"
        outline = "#1f2933" if filled else "#9aa3ad"
        self.create_oval(x - 13, y - 15, x + 13, y - 5, fill="#59616b" if filled else "#ffffff", outline=outline, width=2)
        item = self.create_rectangle(x - 13, y - 10, x + 13, y + 13, fill=fill, outline=outline, width=2)
        self.create_arc(x - 13, y + 8, x + 13, y + 18, start=180, extent=180, style="arc", outline=outline, width=2)
        return item

    def _draw_well(self, x: float, y: float, filled: bool) -> int:
        fill = "#3f464f" if filled else "#ffffff"
        outline = "#1f2933" if filled else "#9aa3ad"
        return self.create_oval(x - 13, y - 13, x + 13, y + 13, fill=fill, outline=outline, width=2)

    def _draw(self):
        for c in range(1, self.cols + 1):
            x, _ = self._cell_position(1, c)
            self.create_text(x, 16, text=self.col_headers[c - 1] if c - 1 < len(self.col_headers) else str(c), fill=COLORS["muted"], font=("Segoe UI", 8))
        for r in range(1, self.rows + 1):
            _, y = self._cell_position(r, 1)
            self.create_text(18, y, text=self.row_headers[r - 1] if r - 1 < len(self.row_headers) else str(r), fill=COLORS["muted"], font=("Segoe UI", 8))

        by_label = {str(cell.get("label", "")): cell for cell in self.cells}
        by_pos = {
            (int(cell.get("row", 0) or 0), int(cell.get("col", 0) or 0)): cell
            for cell in self.cells
            if cell.get("row") and cell.get("col")
        }
        for r in range(1, self.rows + 1):
            for c in range(1, self.cols + 1):
                label = ""
                cell = by_pos.get((r, c)) or by_label.get(label, {"label": label, "chemicals": []})
                chemicals = list(cell.get("chemicals", []) or [])
                x, y = self._cell_position(r, c)
                item = self._draw_vial(x, y, bool(chemicals)) if self.vial_mode else self._draw_well(x, y, bool(chemicals))
                self.item_to_cell[item] = cell
                self.tag_bind(item, "<Enter>", lambda event, item=item: self._show_hover(event, item))
                self.tag_bind(item, "<Motion>", self._move_tooltip)
                self.tag_bind(item, "<Leave>", self._clear_hover)

    def _show_hover(self, event, item: int):
        self.hover_item = item
        self.itemconfigure(item, outline="#0f766e", width=3)
        cell = self.item_to_cell.get(item, {})
        label = str(cell.get("label", ""))
        chemicals = [str(x) for x in cell.get("chemicals", []) or [] if str(x).strip()]
        text = f"{label}: " + (" | ".join(chemicals) if chemicals else "empty")
        if self.tooltip_window is None or not self.tooltip_window.winfo_exists():
            self.tooltip_window = tk.Toplevel(self)
            self.tooltip_window.withdraw()
            self.tooltip_window.overrideredirect(True)
            self.tooltip_window.attributes("-topmost", True)
            self.tooltip_label = tk.Label(
                self.tooltip_window,
                text=text,
                justify="left",
                bg="#fff7d6",
                fg="#111827",
                bd=1,
                relief="solid",
                padx=5,
                pady=3,
                font=("Segoe UI", 9, "bold"),
            )
            self.tooltip_label.pack()
        elif self.tooltip_label is not None:
            self.tooltip_label.configure(text=text)
        self._move_tooltip(event)

    def _move_tooltip(self, event):
        if self.tooltip_window is None or not self.tooltip_window.winfo_exists():
            return
        self.tooltip_window.update_idletasks()
        self.tooltip_window.geometry(f"+{event.x_root + 12}+{event.y_root - 18}")
        self.tooltip_window.deiconify()
        self.tooltip_window.lift()

    def _clear_hover(self, _event=None):
        if self.hover_item:
            cell = self.item_to_cell.get(self.hover_item, {})
            filled = bool(cell.get("chemicals"))
            self.itemconfigure(self.hover_item, outline="#1f2933" if filled else "#9aa3ad", width=2)
            self.hover_item = None
        if self.tooltip_window is not None and self.tooltip_window.winfo_exists():
            self.tooltip_window.destroy()
        self.tooltip_window = None
        self.tooltip_label = None


class PurityHeatMapCanvas(tk.Canvas):
    ROW_LABELS = list("ABCDEFGH")
    COL_LABELS = [str(i) for i in range(1, 13)]

    def __init__(
        self,
        master,
        title: str,
        values_by_well: Dict[str, object],
        tooltip_by_well: Optional[Dict[str, str]] = None,
        *,
        key_by_well: Optional[Dict[str, str]] = None,
        hit_summary_by_key: Optional[Dict[str, str]] = None,
        hit_callback=None,
        clear_hit_callback=None,
        mode: str = "96-well horizontal",
        width: int = 620,
        height: int = 360,
    ):
        super().__init__(master, width=width, height=height, highlightthickness=0, background=COLORS["panel"])
        self.ROW_LABELS, self.COL_LABELS, self.well_grid = heatmap_layout(mode)
        self.title = title
        self.values_by_well = {
            _normalize_well(well): value
            for well, value in (values_by_well or {}).items()
            if _normalize_well(well)
        }
        self.tooltip_by_well = {
            _normalize_well(well): str(value or "").strip()
            for well, value in (tooltip_by_well or {}).items()
            if _normalize_well(well) and str(value or "").strip()
        }
        self.key_by_well = {
            _normalize_well(well): str(value or "").strip()
            for well, value in (key_by_well or {}).items()
            if _normalize_well(well) and str(value or "").strip()
        }
        self.hit_summary_by_key = {
            str(key or "").strip(): str(value or "").strip()
            for key, value in (hit_summary_by_key or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        self.hit_callback = hit_callback
        self.clear_hit_callback = clear_hit_callback
        self.item_to_tip: Dict[int, str] = {}
        self.item_to_well: Dict[int, str] = {}
        self.tooltip_window: Optional[tk.Toplevel] = None
        self.tooltip_label: Optional[tk.Label] = None
        self._draw()
        self.bind("<Leave>", self._clear_tooltip)

    def _draw(self):
        self.delete("all")
        self.item_to_tip.clear()
        self.item_to_well.clear()
        self.create_text(310, 18, text=self.title, fill=COLORS["text"], font=("Segoe UI", 11, "bold"))
        values = [
            pct for pct in (_numeric_percent_value(value) for value in self.values_by_well.values())
            if pct is not None
        ]
        min_value = min(values) if values else 0.0
        max_value = max(values) if values else 100.0
        if max_value <= min_value:
            max_value = min_value + 1.0

        left, top = 58, 50
        cell_w, cell_h = 504 / len(self.COL_LABELS), 240 / len(self.ROW_LABELS)
        for c, label in enumerate(self.COL_LABELS, start=1):
            x = left + (c - 1) * cell_w + cell_w / 2
            self.create_text(x, top - 16, text=label, fill=COLORS["muted"], font=("Segoe UI", 8))
        for r, label in enumerate(self.ROW_LABELS, start=1):
            y = top + (r - 1) * cell_h + cell_h / 2
            self.create_text(left - 18, y, text=label, fill=COLORS["muted"], font=("Segoe UI", 8))

        for r, row_label in enumerate(self.ROW_LABELS, start=1):
            for c in range(1, len(self.COL_LABELS) + 1):
                well = self.well_grid[r - 1][c - 1]
                raw_value = self.values_by_well.get(well, "")
                pct = _numeric_percent_value(raw_value)
                fill = self._color_for_percent(pct, min_value, max_value) if pct is not None else "#f3f4f6"
                x0 = left + (c - 1) * cell_w
                y0 = top + (r - 1) * cell_h
                item = self.create_rectangle(x0, y0, x0 + cell_w - 3, y0 + cell_h - 3, fill=fill, outline="#d1d5db")
                label = str(raw_value or "").strip()
                if label:
                    self.create_text(x0 + cell_w / 2 - 1.5, y0 + cell_h / 2 - 1.5, text=label, fill="#111827", font=("Segoe UI", 7))
                key = self.key_by_well.get(well, "")
                if key and self.hit_summary_by_key.get(key):
                    ring = self.create_oval(
                        x0 + 3,
                        y0 + 2,
                        x0 + cell_w - 6,
                        y0 + cell_h - 5,
                        outline="#000000",
                        width=3,
                    )
                    self.item_to_well[ring] = well
                    self.tag_bind(ring, "<Button-3>", lambda event, well=well: self._show_context_menu(event, well))
                    self.tag_bind(ring, "<Control-Button-1>", lambda event, well=well: self._show_context_menu(event, well))
                tip = self.tooltip_by_well.get(well, "No reaction number")
                if key and self.hit_summary_by_key.get(key):
                    tip = f"{tip}\nBiology hit: {self.hit_summary_by_key[key]}"
                self.item_to_tip[item] = tip
                self.item_to_well[item] = well
                self.tag_bind(item, "<Enter>", lambda event, item=item: self._show_tooltip(event, item))
                self.tag_bind(item, "<Motion>", self._move_tooltip)
                self.tag_bind(item, "<Leave>", self._clear_tooltip)
                self.tag_bind(item, "<Button-3>", lambda event, well=well: self._show_context_menu(event, well))
                self.tag_bind(item, "<Control-Button-1>", lambda event, well=well: self._show_context_menu(event, well))

        self.create_rectangle(58, 310, 558, 326, fill="#f3f4f6", outline="#d1d5db")
        for i in range(100):
            x0 = 58 + i * 5
            color = self._color_for_percent(min_value + (max_value - min_value) * (i / 99), min_value, max_value)
            self.create_rectangle(x0, 310, x0 + 5, 326, fill=color, outline=color)
        self.create_text(58, 340, text=f"{min_value:.1f}%", anchor="w", fill=COLORS["muted"], font=("Segoe UI", 8))
        self.create_text(558, 340, text=f"{max_value:.1f}%", anchor="e", fill=COLORS["muted"], font=("Segoe UI", 8))

    def update_hit_summaries(self, hit_summary_by_key: Dict[str, str]):
        self.hit_summary_by_key = {
            str(key or "").strip(): str(value or "").strip()
            for key, value in (hit_summary_by_key or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        self._clear_tooltip()
        self._draw()

    @staticmethod
    def _color_for_percent(value: Optional[float], min_value: float, max_value: float) -> str:
        if value is None:
            return "#f3f4f6"
        ratio = max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))
        if ratio < 0.5:
            local = ratio / 0.5
            r = int(239 + (245 - 239) * local)
            g = int(68 + (158 - 68) * local)
            b = int(68 + (11 - 68) * local)
        else:
            local = (ratio - 0.5) / 0.5
            r = int(245 + (34 - 245) * local)
            g = int(158 + (197 - 158) * local)
            b = int(11 + (94 - 11) * local)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _show_tooltip(self, event, item: int):
        text = self.item_to_tip.get(item, "")
        if not text:
            return
        if self.tooltip_window is None or not self.tooltip_window.winfo_exists():
            self.tooltip_window = tk.Toplevel(self)
            self.tooltip_window.withdraw()
            self.tooltip_window.overrideredirect(True)
            self.tooltip_window.attributes("-topmost", True)
            self.tooltip_label = tk.Label(
                self.tooltip_window,
                text=text,
                bg="#fff7d6",
                fg="#111827",
                bd=1,
                relief="solid",
                padx=5,
                pady=3,
                font=("Segoe UI", 9, "bold"),
            )
            self.tooltip_label.pack()
        elif self.tooltip_label is not None:
            self.tooltip_label.configure(text=text)
        self._move_tooltip(event)

    def _move_tooltip(self, event):
        if self.tooltip_window is None or not self.tooltip_window.winfo_exists():
            return
        self.tooltip_window.update_idletasks()
        self.tooltip_window.geometry(f"+{event.x_root + 12}+{event.y_root - 18}")
        self.tooltip_window.deiconify()
        self.tooltip_window.lift()

    def _show_context_menu(self, event, well: str):
        self._clear_tooltip()
        key = self.key_by_well.get(_normalize_well(well), "")
        if not key or self.hit_callback is None:
            return "break"
        reaction_label = self.tooltip_by_well.get(_normalize_well(well), _normalize_well(well))
        menu = tk.Menu(self, tearoff=False)
        if self.hit_summary_by_key.get(key):
            menu.add_command(
                label="Edit assay hit",
                command=lambda k=key, label=reaction_label: self.hit_callback(k, f"Biology assay hit - {label}"),
            )
            if self.clear_hit_callback is not None:
                menu.add_command(label="Clear assay hit", command=lambda k=key: self.clear_hit_callback(k))
        else:
            menu.add_command(
                label="Mark assay hit",
                command=lambda k=key, label=reaction_label: self.hit_callback(k, f"Biology assay hit - {label}"),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _clear_tooltip(self, _event=None):
        if self.tooltip_window is not None and self.tooltip_window.winfo_exists():
            self.tooltip_window.destroy()
        self.tooltip_window = None
        self.tooltip_label = None


class ReactionSummaryFrame(ttk.Frame):
    VIAL_KEYWORDS = ("vial20", "vial8rack", "vial1.5", "vial1_5")

    def __init__(
        self,
        master,
        *,
        tecan_provider,
        compound_provider,
        reaction_provider,
        pushed_provider=None,
        product_provider=None,
        manual_provider=None,
        opentrons_provider=None,
    ):
        super().__init__(master, style="Chem.TFrame")
        self.tecan_provider = tecan_provider
        self.compound_provider = compound_provider
        self.reaction_provider = reaction_provider
        self.pushed_provider = pushed_provider
        self.product_provider = product_provider
        self.manual_provider = manual_provider
        self.opentrons_provider = opentrons_provider
        self.scheme_images: List[ImageTk.PhotoImage] = []
        self.scheme_image_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.show_reaction_schemes_var = tk.BooleanVar(value=False)
        self.other_chemicals_var = tk.StringVar()
        self.temperature_var = tk.StringVar()
        self.duration_var = tk.StringVar()
        self._build_ui()

    def _build_ui(self):
        top = ttk.LabelFrame(self, text="Reaction summary controls", padding=(8, 8, 8, 8), style="ChemRegion.TLabelframe")
        top.pack(fill="x")
        ttk.Checkbutton(
            top,
            text="Show reaction schemes",
            variable=self.show_reaction_schemes_var,
            command=self.refresh,
            style="ChemAction.TCheckbutton",
        ).pack(side="left", padx=(10, 0))
        self.refresh_button = ttk.Button(
            top,
            text="Refresh Summary",
            command=self.refresh,
            style="ChemAction.TButton",
        )
        self.refresh_button.pack(side="left", padx=(8, 0))
        ttk.Label(top, text="Other chemicals").pack(side="left", padx=(14, 4))
        ttk.Entry(top, textvariable=self.other_chemicals_var, width=24).pack(side="left")
        ttk.Label(top, text="Temperature").pack(side="left", padx=(14, 4))
        ttk.Entry(top, textvariable=self.temperature_var, width=14).pack(side="left")
        ttk.Label(top, text="Reaction length").pack(side="left", padx=(10, 4))
        ttk.Entry(top, textvariable=self.duration_var, width=14).pack(side="left")
        self.status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=(10, 0))
        style_region_widgets(top, "ChemRegion")

        self.canvas = tk.Canvas(self, highlightthickness=0, background=COLORS["bg"])
        y = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=y.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        y.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.content = ttk.Frame(self.canvas, style="Chem.TFrame")
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda _event=None: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))
        self._bind_reaction_mousewheel(self.canvas)
        self._bind_reaction_mousewheel(self.content)

    def _on_reaction_mousewheel(self, event):
        if event.num == 4:
            units = -3
        elif event.num == 5:
            units = 3
        else:
            delta = getattr(event, "delta", 0)
            units = int(-1 * (delta / 120)) if delta else 0
            if units == 0 and delta:
                units = -1 if delta > 0 else 1
        if units:
            self.canvas.yview_scroll(units, "units")
        return "break"

    def _bind_reaction_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_reaction_mousewheel)
        widget.bind("<Button-4>", self._on_reaction_mousewheel)
        widget.bind("<Button-5>", self._on_reaction_mousewheel)

    def _bind_reaction_mousewheel_tree(self, widget=None):
        widget = widget or self.content
        self._bind_reaction_mousewheel(widget)
        for child in widget.winfo_children():
            self._bind_reaction_mousewheel_tree(child)

    def _compound_index(self) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
        by_id: Dict[str, Dict[str, str]] = {}
        by_name: Dict[str, Dict[str, str]] = {}
        for rec in list(self.compound_provider() or []):
            vals = _record_values(rec)
            cid = str(vals.get("ID", "") or "").strip()
            name = str(vals.get("Name", "") or "").strip()
            if cid:
                by_id[cid.lower()] = vals
            if name:
                by_name[name.lower()] = vals
        return by_id, by_name

    def _resolve_compound(self, label: str) -> Dict[str, str]:
        by_id, by_name = self._compound_index()
        key = str(label or "").strip().lower()
        return by_id.get(key) or by_name.get(key) or {}

    def _reaction_role_label(self, role: str) -> str:
        role_key = str(role or "").strip().lower()
        if "electrophile" in role_key:
            return "Reactant1"
        if "nucleophile" in role_key:
            return "Reactant2"
        return str(role or "").strip()

    def _classify_chemical(self, chemical: str) -> str:
        comp = self._resolve_compound(chemical)
        for key in ("Type", "Chemical Type", "Class", "Category", "Role"):
            value = str(comp.get(key, "") or "").strip()
            if value:
                return self._reaction_role_label(value)
        try:
            reaction = self.reaction_provider() or {}
        except Exception:
            reaction = {}
        smiles = str(comp.get("SMILES", "") or "").strip()
        if smiles and reaction and Chem is not None:
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                patterns = ROLE_PATTERNS.get(reaction.get("id", ""), {})
                for role in ["Nucleophile", "Electrophile"]:
                    if any(mol.HasSubstructMatch(p) for p in _compile_patterns(patterns.get(role, []))):
                        return self._reaction_role_label(role)
                try:
                    rxn = core.AllChem.ReactionFromSmarts(reaction["smarts"])
                    templates = list(rxn.GetReactants())
                    matched = [
                        f"Reactant{index}"
                        for index, template in enumerate(templates[:3], start=1)
                        if mol.HasSubstructMatch(template)
                    ]
                    if len(matched) == 1:
                        return matched[0]
                except Exception:
                    pass
        return "Reagent / Unknown"

    def _role_from_building_block_flag(self, chemical: str, value: object, *, present: bool = True) -> str:
        if not present:
            return self._classify_chemical(chemical)
        if not coerce_bool(value):
            return "Reagent / Unknown"
        classified = self._classify_chemical(chemical)
        return classified if classified.casefold() in {"reactant1", "reactant2", "reactant3"} else "Building Block / Unknown"

    def _umol(self, chemical: str, volume: float) -> float:
        conc = core.parse_float(self._resolve_compound(chemical).get("Conc."))
        return float(conc or 0.0) * float(volume or 0.0)

    def _chemical_list(self, text: str) -> List[str]:
        pieces = re.split(r"\s*\|\s*|[,;]\s*", str(text or "").strip())
        out = []
        for piece in pieces:
            if piece and piece not in out:
                out.append(piece)
        return out

    def _exported_blocks(self) -> List[Dict[str, object]]:
        tecan = self.tecan_provider()
        rows: List[Dict[str, object]] = []
        for file_index, entry in enumerate(getattr(tecan, "exported_gwl_files", []) or [], start=1):
            path_text = str(entry.get("path", "") or "")
            path = Path(path_text) if path_text else None
            content = str(entry.get("content", "") or "")
            if path and path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                except Exception:
                    pass
            if not content.strip():
                continue
            try:
                chem_label_map: Dict[str, str] = {}
                if path:
                    csv_guess = path.with_name(path.stem + "_chemical_map.csv")
                    if csv_guess.exists():
                        chem_label_map = tecan._read_chemical_map_csv(csv_guess)
                snapshot_blocks = [
                    tecan._block_from_dict(block_data)
                    for block_data in (entry.get("blocks", []) or [])
                    if isinstance(block_data, dict)
                ]
                if snapshot_blocks:
                    blocks = snapshot_blocks
                    mode = str(entry.get("mode", "") or getattr(tecan, "mode_var").get())
                    from_snapshot = True
                else:
                    mode, blocks = tecan._blocks_from_gwl_content(content, source_path=path if path and path.exists() else None, ask_mode=False, ask_csv=False)
                    from_snapshot = False
            except Exception:
                continue
            for block_index, block in enumerate(blocks, start=1):
                rows.append({
                    "file_index": file_index,
                    "file_name": str(entry.get("name") or (path.name if path else f"GWL {file_index}")),
                    "mode": mode,
                    "block_index": block_index,
                    "block": block,
                    "chem_label_map": chem_label_map,
                    "from_snapshot": from_snapshot,
                })
        return rows

    def _manual_blocks(self) -> List[Dict[str, object]]:
        if self.manual_provider is None:
            return []
        try:
            manual = self.manual_provider()
            if manual is None:
                return []
            return list(manual.transfer_blocks_for_summary())
        except Exception:
            return []

    @staticmethod
    def _provider_transfer_rows(provider) -> List[Dict[str, object]]:
        if provider is None:
            return []
        try:
            source = provider()
            if source is None:
                return []
            rows = source.rows_for_cheminformatics()
        except Exception:
            return []
        return [dict(row) for row in (rows or []) if isinstance(row, dict)]

    def _manual_rows(self) -> List[Dict[str, object]]:
        return self._provider_transfer_rows(self.manual_provider)

    def _opentrons_rows(self) -> List[Dict[str, object]]:
        return self._provider_transfer_rows(self.opentrons_provider)

    @staticmethod
    def _transfer_source(row: Dict[str, object]) -> str:
        source = str(row.get("source", "") or "").strip().casefold()
        if source in {"manual", "manual workflow"}:
            return "manual"
        if source == "opentrons":
            return "opentrons"
        if source == "tecan" or (not source and str(row.get("gwl", "") or "").strip()):
            return "tecan"
        return source or "other"

    def _summary_transfer_rows(
        self,
        tecan_blocks: List[Dict[str, object]],
        manual_blocks: List[Dict[str, object]],
        *,
        opentrons_rows: Optional[List[Dict[str, object]]] = None,
    ) -> List[Dict[str, object]]:
        """Only explicit pushes populate the combined reaction record."""
        return self._pushed_rows()

    def _pushed_source_blocks(self, rows):
        blocks = []
        seen = set()
        for row in rows:
            payload = row.get("summary_block")
            key = (row.get("source"), row.get("gwl"), row.get("block"))
            if not isinstance(payload, dict) or key in seen:
                continue
            seen.add(key)
            blocks.append({"file_index": 1, "file_name": row.get("gwl", ""),
                           "mode": row.get("dest_mode", "96-well horizontal"),
                           "block_index": row.get("block", 1),
                           "block": tecan_frame.TransferBlock(**{**payload, "dispense_groups": [tecan_frame.DispenseGroup(**g) for g in payload.get("dispense_groups", [])]}),
                           "chem_label_map": {}, "from_snapshot": True})
        return blocks

    def _product_rows_by_well(self) -> Dict[str, Dict[str, object]]:
        if self.product_provider is None:
            return {}
        try:
            rows = self.product_provider() or []
        except Exception:
            return {}
        by_well: Dict[str, Dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            well = _normalize_well(row.get("reaction_well", "") or row.get("well", ""))
            if well:
                by_well[well] = dict(row)
        return by_well

    @staticmethod
    def _product_smiles_list(product_row: Dict[str, object]) -> List[str]:
        raw_products = product_row.get("selectivity products", [])
        if isinstance(raw_products, (list, tuple, set)):
            candidates = list(raw_products)
        else:
            candidates = str(raw_products or "").split(" | ")
        primary = str(product_row.get("desired product smiles", "") or "").strip()
        if primary:
            candidates.insert(0, primary)
        products: List[str] = []
        for value in candidates:
            smiles = str(value or "").strip()
            if smiles and smiles not in products:
                products.append(smiles)
        return products

    def _pushed_rows(self) -> List[Dict[str, object]]:
        if self.pushed_provider is None:
            return []
        try:
            rows = self.pushed_provider() or []
        except Exception:
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _add_table(self, parent, columns: Tuple[str, ...], headings: Tuple[str, ...], rows: List[Tuple[object, ...]], height: int = 6):
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="x", pady=(6, 10))
        visible_rows = max(2, min(height, len(rows) or 2))
        body = ttk.Frame(table_frame)
        body.pack(fill="x")
        table = ttk.Treeview(body, columns=columns, show="headings", height=visible_rows)
        for col, heading in zip(columns, headings):
            table.heading(col, text=heading, anchor="center")
            width = 300 if col == "chemical" else 170 if col in {"gwl", "well"} else 120
            table.column(col, width=width, minwidth=90, anchor="center", stretch=True)
        for row in rows:
            table.insert("", "end", values=row)
        xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
        ybar = ttk.Scrollbar(body, orient="vertical", command=table.yview)
        table.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        table.pack(side="left", fill="x", expand=True)
        if len(rows) > visible_rows:
            ybar.pack(side="right", fill="y")
        xbar.pack(fill="x")

    def _source_summary(self, blocks: List[Dict[str, object]]):
        ordered: Dict[str, Dict[str, object]] = {}
        known_by_source: Dict[Tuple[str, str], List[str]] = {}
        for item in blocks:
            block = item["block"]
            labware = str(block.source_labware or "").strip()
            if not labware:
                continue
            label = tecan_frame.source_index_to_label(int(block.source_well), labware) or str(block.source_well)
            chemicals = self._chemical_list(block.chemical_name)
            if chemicals:
                key = (labware, label)
                known = known_by_source.setdefault(key, [])
                for chemical in chemicals:
                    if chemical not in known:
                        known.append(chemical)
        for item in blocks:
            block = item["block"]
            labware = str(block.source_labware or "").strip()
            if not labware:
                continue
            summary = ordered.setdefault(labware, {"labware": labware, "wells": {}, "totals": {}})
            label = tecan_frame.source_index_to_label(int(block.source_well), labware) or str(block.source_well)
            chemicals = self._chemical_list(block.chemical_name)
            if not chemicals:
                chemicals = [] if known_by_source.get((labware, label)) else ["Unknown"]
            well_entry = summary["wells"].setdefault(label, [])
            for chemical in chemicals:
                if chemical not in well_entry:
                    well_entry.append(chemical)
                totals = summary["totals"].setdefault(chemical, {"volume": 0.0, "umol": 0.0})
                volume = float(block.source_volume or 0.0)
                totals["volume"] += volume
                totals["umol"] += self._umol(chemical, volume)
        return list(ordered.values())

    def _destination_summary(self, blocks: List[Dict[str, object]], pushed_rows: Optional[List[Dict[str, object]]] = None):
        wells: Dict[str, Dict[str, object]] = {}
        tables: Dict[str, List[Dict[str, object]]] = {}
        pushed_rows = pushed_rows or []

        def mode_from_style(style: object) -> str:
            text = str(style or "").lower()
            if "384" in text:
                return "384-well horizontal"
            if "48" in text:
                return "48-well horizontal"
            if "24" in text:
                return "24-well horizontal"
            return "96-well horizontal"

        destination_candidates: List[Tuple[str, str]] = []
        for item in blocks:
            block = item["block"]
            destination_candidates.append((str(item.get("mode") or "96-well horizontal"), str(block.dest_labware or "")))
        for row in pushed_rows:
            if row.get("dest_mode") or row.get("dest_map_style"):
                destination_candidates.append((str(row.get("dest_mode") or mode_from_style(row.get("dest_map_style"))), str(row.get("dest_labware", "") or "")))

        mode, dest_labware = destination_candidates[0] if destination_candidates else ("96-well horizontal", "")
        expected_dims = tecan_frame.mode_dims_order(mode)[:2]
        conflicts = sorted({
            candidate_mode
            for candidate_mode, _candidate_labware in destination_candidates
            if tecan_frame.mode_dims_order(candidate_mode)[:2] != expected_dims
        })
        if conflicts:
            raise ValueError(
                "Combined synthesis contains conflicting destination geometries. XinPilot expects one physical "
                f"destination labware, but found {mode} and {', '.join(conflicts)}."
            )
        if not dest_labware:
            dest_labware = next((label for _candidate_mode, label in destination_candidates if label), "")
        mode = reaction_mode({'dest_mode': candidate} for candidate, _ in destination_candidates)
        known_by_dest: Dict[str, List[str]] = {}
        existing_pairs: set[Tuple[str, str]] = set()
        for item in blocks:
            block = item["block"]
            item_mode = str(item.get("mode") or mode)
            chem_label_map = dict(item.get("chem_label_map", {}) or {})
            block_chemicals = self._chemical_list(block.chemical_name)

            def remember(wells_expr: str):
                for idx in tecan_frame.parse_dest_well_expr(wells_expr, item_mode, block.dest_labware):
                    label = tecan_frame.index_to_dest_label(idx, item_mode, block.dest_labware)
                    mapped_chemicals = self._chemical_list(chem_label_map.get(label, ""))
                    for chemical in block_chemicals or mapped_chemicals:
                        if chemical:
                            known = known_by_dest.setdefault(label, [])
                            if chemical not in known:
                                known.append(chemical)

            remember(block.dest_wells_expr)
            if block.disp_different_vol:
                for grp in block.dispense_groups:
                    remember(grp.wells_expr)
        for item in blocks:
            block = item["block"]
            item_mode = str(item.get("mode") or mode)
            chem_label_map = dict(item.get("chem_label_map", {}) or {})
            from_snapshot = bool(item.get("from_snapshot"))

            def add(wells_expr: str, volume: float):
                for idx in tecan_frame.parse_dest_well_expr(wells_expr, item_mode, block.dest_labware):
                    label = tecan_frame.index_to_dest_label(idx, item_mode, block.dest_labware)
                    block_chemicals = self._chemical_list(block.chemical_name)
                    mapped_chemicals = self._chemical_list(chem_label_map.get(label, ""))
                    if from_snapshot:
                        chemicals = block_chemicals or mapped_chemicals or ["Unknown"]
                    else:
                        chemicals = mapped_chemicals or block_chemicals or ["Unknown"]
                    if chemicals == ["Unknown"] and known_by_dest.get(label):
                        chemicals = []
                    cell = wells.setdefault(label, {"label": label, "chemicals": []})
                    for chemical in chemicals:
                        if chemical not in cell["chemicals"]:
                            cell["chemicals"].append(chemical)
                        group = self._role_from_building_block_flag(
                            chemical,
                            getattr(block, "is_building_block", False),
                        )
                        tables.setdefault(group, []).append({
                            "gwl": item.get("file_name", ""),
                            "well": label,
                            "chemical": chemical,
                            "volume": float(volume or 0.0),
                            "umol": self._umol(chemical, float(volume or 0.0)),
                        })
                        existing_pairs.add((_normalize_well(label), str(chemical).strip().casefold()))

            add(block.dest_wells_expr, block.dest_volume)
            if block.disp_different_vol:
                for grp in block.dispense_groups:
                    add(grp.wells_expr, grp.volume)
        for row in pushed_rows:
            source = str(row.get("source", "") or "").strip()
            source_lower = source.lower()
            well = _normalize_well(row.get("well", "") or row.get("reaction_well", ""))
            chemical = str(row.get("chemical_id", "") or row.get("chemical", "") or "").strip()
            if not well or not chemical:
                continue
            pair = (well, chemical.casefold())
            if blocks and source_lower in {"manual", "manual workflow"} and pair in existing_pairs:
                continue
            if not source_lower and pair in existing_pairs:
                continue
            volume = float(core.parse_float(row.get("dispensed_uL", row.get("volume_uL", row.get("volume", 0.0)))) or 0.0)
            raw_umol = row.get("dispensed_umol", row.get("reaction_umol", ""))
            # Older Tecan pushed rows copied the main block's amount into
            # manually sized extra groups. Volume is authoritative, including
            # when the native worklist is unavailable in a legacy project.
            if self._transfer_source(row) == "tecan":
                raw_umol = ""
            umol = float(core.parse_float(raw_umol) or 0.0) if str(raw_umol or "").strip() else self._umol(chemical, volume)
            if row.get("amount_unknown"):
                umol = None
            cell = wells.setdefault(well, {"label": well, "chemicals": []})
            if chemical not in cell["chemicals"]:
                cell["chemicals"].append(chemical)
            has_explicit_bb_flag = "is_building_block" in row
            group = self._role_from_building_block_flag(
                chemical,
                row.get("is_building_block"),
                present=has_explicit_bb_flag,
            )
            label = source or "Pushed"
            if source_lower == "opentrons":
                label = "Opentrons"
            elif source_lower in {"manual", "manual workflow"}:
                label = "Manual workflow"
            tables.setdefault(group, []).append({
                "gwl": label,
                "well": well,
                "chemical": chemical,
                "volume": volume,
                "umol": umol,
            })
            existing_pairs.add(pair)
        return mode, dest_labware, wells, tables

    def _scheme_rows(self, blocks: List[Dict[str, object]]) -> List[Dict[str, object]]:
        pushed_rows = self._pushed_rows()
        if pushed_rows:
            return self._scheme_rows_from_pushed(pushed_rows)

        by_well: Dict[str, Dict[str, object]] = {}
        product_by_well = self._product_rows_by_well()

        for item in blocks:
            block = item["block"]
            mode = str(item.get("mode") or "96-well horizontal")
            chem_label_map = dict(item.get("chem_label_map", {}) or {})
            from_snapshot = bool(item.get("from_snapshot"))

            def add(wells_expr: str, volume: float):
                for idx in tecan_frame.parse_dest_well_expr(wells_expr, mode, block.dest_labware):
                    well = _normalize_well(tecan_frame.index_to_dest_label(idx, mode, block.dest_labware))
                    if not well:
                        continue
                    block_chemicals = self._chemical_list(block.chemical_name)
                    mapped_chemicals = self._chemical_list(chem_label_map.get(well, ""))
                    chemicals = (block_chemicals or mapped_chemicals) if from_snapshot else (mapped_chemicals or block_chemicals)
                    entry = by_well.setdefault(well, {
                        "well": well,
                        "chemicals": {},
                        "temperatures": [],
                        "durations": [],
                    })
                    for chemical in chemicals or ["Unknown"]:
                        chem_entry = entry["chemicals"].setdefault(
                            chemical,
                            {
                                "chemical": chemical,
                                "volume": 0.0,
                                "is_building_block": False,
                                "building_block_flag_present": True,
                            },
                        )
                        chem_entry["volume"] += float(volume or 0.0)
                        chem_entry["is_building_block"] = (
                            coerce_bool(chem_entry.get("is_building_block"))
                            or coerce_bool(getattr(block, "is_building_block", False))
                        )
                    for attr, target in (("temperature", "temperatures"), ("duration", "durations")):
                        value = str(getattr(block, attr, "") or "").strip()
                        if value and value not in entry[target]:
                            entry[target].append(value)

            add(block.dest_wells_expr, block.dest_volume)
            if block.disp_different_vol:
                for grp in block.dispense_groups:
                    add(grp.wells_expr, grp.volume)

        scheme_rows = []
        for well, entry in sorted(by_well.items(), key=lambda kv: core.well_key(kv[0])):
            chemicals = list(entry["chemicals"].values())
            for chemical in chemicals:
                chemical_id = str(chemical.get("chemical", "") or "")
                compound = self._resolve_compound(chemical_id)
                chemical["compound"] = compound
                chemical["smiles"] = str(compound.get("SMILES", "") or "").strip()
                chemical["role"] = self._role_from_building_block_flag(
                    chemical_id,
                    chemical.get("is_building_block"),
                )
                solvent = str(compound.get("Solvent", "") or "").strip()
                if solvent:
                    chemical["solvent"] = solvent

            product_row = product_by_well.get(well, {})
            products = self._product_smiles_list(product_row)
            scheme_rows.append({
                **entry,
                "chemicals": chemicals,
                "product": products[0] if products else "",
                "products": products,
                "product_id": str(product_row.get("product_id", "") or product_row.get("reaction_name", "") or "").strip(),
            })
        return scheme_rows

    def _scheme_rows_from_pushed(self, pushed_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
        by_well: Dict[str, Dict[str, object]] = {}
        product_by_well = self._product_rows_by_well()
        for source_row in pushed_rows:
            well = _normalize_well(source_row.get("well", "") or source_row.get("reaction_well", ""))
            chemical = str(source_row.get("chemical_id", "") or source_row.get("chemical", "") or "").strip()
            if not well or not chemical:
                continue
            entry = by_well.setdefault(well, {
                "well": well,
                "chemicals": {},
                "temperatures": [],
                "durations": [],
            })
            chem_entry = entry["chemicals"].setdefault(
                chemical,
                {
                    "chemical": chemical,
                    "volume": 0.0,
                    "is_building_block": False,
                    "building_block_flag_present": False,
                },
            )
            chem_entry["volume"] += float(core.parse_float(source_row.get("volume_uL", source_row.get("volume", 0.0))) or 0.0)
            if "is_building_block" in source_row:
                chem_entry["building_block_flag_present"] = True
                chem_entry["is_building_block"] = (
                    coerce_bool(chem_entry.get("is_building_block"))
                    or coerce_bool(source_row.get("is_building_block"))
                )
            for source_key, target in (("temperature", "temperatures"), ("duration", "durations")):
                self._append_unique(entry[target], source_row.get(source_key, ""))

        scheme_rows = []
        for well, entry in sorted(by_well.items(), key=lambda kv: core.well_key(kv[0])):
            chemicals = list(entry["chemicals"].values())
            for chemical in chemicals:
                chemical_id = str(chemical.get("chemical", "") or "")
                compound = self._resolve_compound(chemical_id)
                chemical["compound"] = compound
                chemical["smiles"] = str(compound.get("SMILES", "") or "").strip()
                chemical["role"] = self._role_from_building_block_flag(
                    chemical_id,
                    chemical.get("is_building_block"),
                    present=bool(chemical.get("building_block_flag_present")),
                )
                solvent = str(compound.get("Solvent", "") or "").strip()
                if solvent:
                    chemical["solvent"] = solvent
            product_row = product_by_well.get(well, {})
            products = self._product_smiles_list(product_row)
            scheme_rows.append({
                **entry,
                "chemicals": chemicals,
                "product": products[0] if products else "",
                "products": products,
                "product_id": str(product_row.get("product_id", "") or product_row.get("reaction_name", "") or "").strip(),
            })
        return scheme_rows

    @staticmethod
    def _append_unique(values: List[str], value: object):
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)

    @staticmethod
    def _format_temperature(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        numeric = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        celsius_match = re.fullmatch(
            rf"({numeric})\s*(?:°\s*|deg(?:ree)?s?\s*)?c(?:elsius)?",
            text,
            flags=re.IGNORECASE,
        )
        if celsius_match:
            return f"{celsius_match.group(1)} °C"
        if not re.fullmatch(numeric, text):
            return text
        return f"{text} °C"

    def _scheme_cache_key(self, row: Dict[str, object]) -> str:
        payload = {
            "row": row,
            "other_chemicals": self.other_chemicals_var.get().strip(),
            "temperature": self.temperature_var.get().strip(),
            "duration": self.duration_var.get().strip(),
        }
        return json.dumps(payload, sort_keys=True, default=str)

    @staticmethod
    def _draw_centered_lines(
        draw: ImageDraw.ImageDraw,
        lines: List[str],
        *,
        center_x: float,
        y: float,
        font,
        fill: str = "#202327",
        line_height: int = 14,
    ):
        for line_idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            draw.text(
                (center_x - (bbox[2] - bbox[0]) / 2, y + line_idx * line_height),
                line,
                fill=fill,
                font=font,
            )

    @staticmethod
    def _wrapped_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 3) -> List[str]:
        words = str(text or "").split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
            lines[-1] = lines[-1].rstrip(".") + "..."
        return lines or [""]

    def _mol_image(self, smiles: str, size: Tuple[int, int]):
        if not smiles or Chem is None or Draw is None:
            return None
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            return self._trim_image_whitespace(Draw.MolToImage(mol, size=size, fitImage=True).convert("RGBA"))
        except Exception:
            return None

    @staticmethod
    def _trim_image_whitespace(img: Image.Image, *, pad: int = 8) -> Image.Image:
        rgba = img.convert("RGBA")
        pixels = rgba.load()
        width, height = rgba.size
        bounds = [width, height, 0, 0]
        found = False
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a and (r < 245 or g < 245 or b < 245):
                    bounds[0] = min(bounds[0], x)
                    bounds[1] = min(bounds[1], y)
                    bounds[2] = max(bounds[2], x)
                    bounds[3] = max(bounds[3], y)
                    found = True
        if not found:
            return rgba
        left = max(0, bounds[0] - pad)
        top = max(0, bounds[1] - pad)
        right = min(width, bounds[2] + pad + 1)
        bottom = min(height, bounds[3] + pad + 1)
        return rgba.crop((left, top, right, bottom))

    @staticmethod
    def _fit_image(img: Image.Image, max_size: Tuple[int, int]) -> Image.Image:
        fitted = img.copy()
        fitted.thumbnail(max_size, Image.LANCZOS)
        return fitted

    def _draw_centered_mol(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        smiles: str,
        label: str,
        box: Tuple[int, int, int, int],
        font,
        small_font,
    ):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle((x0, y0, x1, y1), radius=6, outline="#d7dde4", fill="#ffffff", width=1)
        mol_img = self._mol_image(smiles, (x1 - x0 - 16, y1 - y0 - 42))
        if mol_img is not None:
            mol_img = self._fit_image(mol_img, (x1 - x0 - 18, y1 - y0 - 46))
            mol_x = x0 + ((x1 - x0) - mol_img.width) // 2
            mol_y = y0 + 10 + max(0, ((y1 - y0 - 46) - mol_img.height) // 2)
            img.alpha_composite(mol_img, (mol_x, mol_y))
        else:
            placeholder = label or "Unknown"
            for line_idx, line in enumerate(self._wrapped_lines(draw, placeholder, font, x1 - x0 - 18, 3)):
                draw.text((x0 + 9, y0 + 42 + line_idx * 16), line, fill="#202327", font=font)
        label_lines = self._wrapped_lines(draw, label or "Unknown", small_font, x1 - x0 - 12, 2)
        label_y = y1 - 28
        for line_idx, line in enumerate(label_lines):
            bbox = draw.textbbox((0, 0), line, font=small_font)
            draw.text((x0 + ((x1 - x0) - (bbox[2] - bbox[0])) / 2, label_y + line_idx * 13), line, fill="#5b6470", font=small_font)

    def _scheme_image(self, row: Dict[str, object]) -> ImageTk.PhotoImage:
        products = [
            str(smiles or "").strip()
            for smiles in (row.get("products", []) or [])
            if str(smiles or "").strip()
        ]
        if not products:
            primary_product = str(row.get("product", "") or "").strip()
            products = [primary_product] if primary_product else []
        product_cards = products or [""]
        product_columns = min(3, len(product_cards))
        product_rows = (len(product_cards) + product_columns - 1) // product_columns
        width = max(940, 750 + product_columns * 178 + 12)
        height = max(220, 48 + product_rows * 150 + 30)
        img = Image.new("RGBA", (width, height), "#f8fafc")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 13)
            small_font = ImageFont.truetype("arial.ttf", 11)
            title_font = ImageFont.truetype("arial.ttf", 15)
        except Exception:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()
            title_font = ImageFont.load_default()

        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=6, outline="#d1d5db", fill="#f8fafc", width=1)
        draw.rectangle((1, 1, width - 2, 34), fill="#eef2f7", outline="#eef2f7")
        well = str(row.get("well", "") or "")
        product_id = str(row.get("product_id", "") or "").strip()
        title = f"{well}" + (f" - {product_id}" if product_id else "")
        if len(products) > 1:
            title += f" - {len(products)} possible products"
        draw.text((14, 9), title, fill="#202327", font=title_font)

        chemicals = list(row.get("chemicals", []) or [])
        reactants = [
            c for c in chemicals
            if str(c.get("role", "")).lower() in {"reactant1", "reactant2", "reactant3"}
            or str(c.get("role", "")).lower().startswith("building block")
        ]
        explicit_bb_flags = any(c.get("building_block_flag_present") for c in chemicals)
        if not reactants and not explicit_bb_flags:
            reactants = [c for c in chemicals if c.get("smiles")][:3] or chemicals[:3]
        extras = [c for c in chemicals if c not in reactants]

        x = 22
        y = 48
        mol_w, mol_h = 138, 142
        for idx, chemical in enumerate(reactants[:3]):
            if idx:
                draw.text((x - 18, y + 57), "+", fill="#202327", font=title_font)
            self._draw_centered_mol(
                img,
                draw,
                str(chemical.get("smiles", "") or ""),
                str(chemical.get("chemical", "") or ""),
                (x, y, x + mol_w, y + mol_h),
                font,
                small_font,
            )
            x += mol_w + 28

        arrow_x0 = max(350, min(x - 12, 560))
        arrow_x1 = 710
        arrow_y = 122
        draw.line((arrow_x0, arrow_y, arrow_x1, arrow_y), fill="#202327", width=3)
        draw.polygon([(arrow_x1, arrow_y), (arrow_x1 - 16, arrow_y - 9), (arrow_x1 - 16, arrow_y + 9)], fill="#202327")

        reagent_parts: List[str] = []
        condition_parts: List[str] = []
        other_names = [str(c.get("chemical", "") or "") for c in extras if str(c.get("chemical", "") or "").strip()]
        solvents: List[str] = []
        for chemical in chemicals:
            self._append_unique(solvents, chemical.get("solvent", ""))
        temperatures = list(row.get("temperatures", []) or [])
        durations = list(row.get("durations", []) or [])
        self._append_unique(temperatures, self.temperature_var.get())
        self._append_unique(durations, self.duration_var.get())
        if other_names:
            reagent_parts.append("Other: " + ", ".join(other_names))
        if self.other_chemicals_var.get().strip():
            reagent_parts.append("Other input: " + self.other_chemicals_var.get().strip())
        if solvents:
            reagent_parts.append("Solvent: " + ", ".join(solvents))
        formatted_temperatures = [self._format_temperature(temp) for temp in temperatures]
        formatted_temperatures = [temp for temp in formatted_temperatures if temp]
        if formatted_temperatures:
            condition_parts.append("Temp: " + ", ".join(formatted_temperatures))
        if durations:
            condition_parts.append("Time: " + ", ".join(durations))
        arrow_center = arrow_x0 + (arrow_x1 - arrow_x0) / 2
        label_width = arrow_x1 - arrow_x0 + 90
        reagent_text = "; ".join(reagent_parts) or "Reagents"
        reagent_lines = self._wrapped_lines(draw, reagent_text, small_font, label_width, 3)
        reagent_y = max(45, arrow_y - 18 - len(reagent_lines) * 14)
        self._draw_centered_lines(draw, reagent_lines, center_x=arrow_center, y=reagent_y, font=small_font)

        condition_text = "; ".join(condition_parts)
        if condition_text:
            condition_lines = self._wrapped_lines(draw, condition_text, small_font, label_width, 2)
            self._draw_centered_lines(
                draw,
                condition_lines,
                center_x=arrow_center,
                y=arrow_y + 14,
                font=small_font,
                fill="#5b6470",
            )

        for index, product_smiles in enumerate(product_cards):
            card_row, card_col = divmod(index, product_columns)
            x0 = 750 + card_col * 178
            y0 = 48 + card_row * 150
            if len(products) > 1:
                product_label = f"{product_id or 'Product'} ({index + 1}/{len(products)})"
            else:
                product_label = product_id or ("Product not generated" if not product_smiles else "Product")
            self._draw_centered_mol(
                img,
                draw,
                product_smiles,
                product_label,
                (x0, y0, x0 + 168, y0 + 142),
                font,
                small_font,
            )

        return ImageTk.PhotoImage(img)

    def _add_reaction_scheme_panel(self, blocks: List[Dict[str, object]], scheme_rows: Optional[List[Dict[str, object]]] = None):
        if not self.show_reaction_schemes_var.get():
            ttk.Label(
                self.content,
                text="Reaction schemes hidden.",
                style="Muted.TLabel",
            ).pack(anchor="w", padx=10, pady=(6, 4))
            self.scheme_images = []
            return
        scheme_rows = scheme_rows if scheme_rows is not None else self._scheme_rows(blocks)
        if not scheme_rows:
            return
        scheme_box = ttk.LabelFrame(
            self.content,
            text=f"Reaction Schemes ({len(scheme_rows)}) (if product structures are not showing, run Cheminformatics again)",
            padding=8,
            style="ChemRegion.TLabelframe",
        )
        scheme_box.pack(fill="x", padx=8, pady=(8, 10))
        self.scheme_images = []
        for row in scheme_rows:
            cache_key = self._scheme_cache_key(row)
            photo = self.scheme_image_cache.get(cache_key)
            if photo is None:
                photo = self._scheme_image(row)
                self.scheme_image_cache[cache_key] = photo
            self.scheme_images.append(photo)
            ttk.Label(scheme_box, image=photo, anchor="w").pack(anchor="w", fill="x", pady=(0, 8))
        style_region_widgets(scheme_box, "ChemRegion")

    def _add_pushed_transfer_details(self, pushed_rows: List[Dict[str, object]]):
        if not pushed_rows:
            return
        table_rows = []
        for row in pushed_rows:
            source = str(row.get("source", "") or "")
            if source and source.lower() not in {"tecan", "opentrons", "manual", "manual workflow", "external import"}:
                continue
            table_rows.append((
                source,
                (f"{row.get('source_labware', '')} / {row.get('source_well', '')}" if source == "External Import" else str(row.get("building_block_location", "") or row.get("source_well", "") or "")),
                str(row.get("destination_location", "") or row.get("well", "") or row.get("reaction_well", "") or ""),
                str(row.get("chemical_id", "") or row.get("chemical", "") or ""),
                f"{float(core.parse_float(row.get('dispensed_uL', row.get('volume_uL', row.get('volume', 0.0)))) or 0.0):.6g}",
                str(row.get("dispensed_umol", "") or row.get("reaction_umol", "") or ""),
            ))
        if not table_rows:
            return
        box = ttk.LabelFrame(self.content, text="Transfer Details", padding=8, style="RowRegion.TLabelframe")
        box.pack(fill="x", padx=8, pady=(8, 10))
        self._add_table(
            box,
            ("source", "building_block_location", "destination", "chemical", "volume", "umol"),
            ("Source", "Building Block Location", "Dispensed To", "Chemical ID", "Dispensed uL", "Dispensed umol"),
            table_rows,
            height=10,
        )
        style_region_widgets(box, "RowRegion")

    @staticmethod
    def _opentrons_map_dims(map_style: object, labware: object = "") -> Tuple[int, int]:
        text = str(map_style or "").lower()
        labware_text = str(labware or "").lower()
        if "12_reservoir" in labware_text or "_12_reservoir" in labware_text:
            return 1, 12
        if "8_reservoir" in labware_text or "_8_reservoir" in labware_text:
            return 1, 8
        if "6_tuberack" in labware_text or "_6_" in labware_text and "tuberack" in labware_text:
            return 2, 3
        if "10_tuberack" in labware_text or "_10_" in labware_text and "tuberack" in labware_text:
            return 2, 5
        if "15_tuberack" in labware_text or "_15_" in labware_text and "tuberack" in labware_text:
            return 3, 5
        if "24_tuberack" in labware_text or "_24_" in labware_text and "tuberack" in labware_text:
            return 4, 6
        if "1_reservoir" in labware_text or "_1_reservoir" in labware_text:
            return 1, 1
        if "384" in text:
            return 16, 24
        if "48" in text:
            return 6, 8
        if "24" in text:
            return 4, 6
        return 8, 12

    def _opentrons_cells(self, map_style: object, wells: Dict[str, List[str]], labware: object = "") -> Tuple[int, int, List[str], List[str], List[Dict[str, object]]]:
        rows, cols = self._opentrons_map_dims(map_style, labware)
        row_headers = [tecan_frame.row_number_to_label(r) for r in range(1, rows + 1)]
        col_headers = [str(c) for c in range(1, cols + 1)]
        cells = []
        for r in range(1, rows + 1):
            row_label = tecan_frame.row_number_to_label(r)
            for c in range(1, cols + 1):
                label = f"{row_label}{c}"
                cells.append({"label": label, "chemicals": wells.get(label, []), "row": r, "col": c})
        return rows, cols, row_headers, col_headers, cells

    def _add_pushed_labware_summaries(self, pushed_rows: List[Dict[str, object]]):
        opentrons_rows = [row for row in pushed_rows if str(row.get("source", "") or "").lower() == "opentrons"]
        if not opentrons_rows:
            return

        source_groups: Dict[Tuple[str, str, str], Dict[str, object]] = {}
        for row in opentrons_rows:
            chemical = str(row.get("chemical_id", "") or row.get("chemical", "") or "").strip()
            if not chemical:
                continue
            volume = float(core.parse_float(row.get("dispensed_uL", row.get("volume_uL", row.get("volume", 0.0)))) or 0.0)
            umol = float(core.parse_float(row.get("dispensed_umol", row.get("reaction_umol", 0.0))) or 0.0)
            source_alias = str(row.get("source_labware_alias", "") or "source")
            source_labware = str(row.get("source_labware", "") or source_alias)
            source_style = str(row.get("source_map_style", "") or "96 well")
            source_well = _normalize_well(row.get("source_well", ""))
            source_group = source_groups.setdefault((source_alias, source_labware, source_style), {"wells": {}, "totals": {}})
            if source_well:
                source_group["wells"].setdefault(source_well, []).append(chemical)
            total = source_group["totals"].setdefault(chemical, {"volume": 0.0, "umol": 0.0})
            total["volume"] += volume
            total["umol"] += umol

        if source_groups:
            source_box = ttk.LabelFrame(self.content, text="Opentrons Source Labware Summary", padding=8, style="FileRegion.TLabelframe")
            source_box.pack(fill="x", padx=8, pady=(8, 10))
            for (alias, labware, style), data in sorted(source_groups.items()):
                lab_box = ttk.LabelFrame(source_box, text=f"{alias} - {labware} ({style})", padding=8, style="FileRegion.TLabelframe")
                lab_box.pack(fill="x", pady=(0, 10))
                rows, cols, row_headers, col_headers, cells = self._opentrons_cells(style, data.get("wells", {}), labware)
                HoverMapCanvas(lab_box, cells, rows=rows, cols=cols, vial_mode=False, row_headers=row_headers, col_headers=col_headers).pack(anchor="w", pady=(0, 8))
                table_rows = [
                    (chemical, f"{values['volume']:.6g}", f"{values['umol']:.6g}" if values["umol"] else "")
                    for chemical, values in sorted((data.get("totals", {}) or {}).items())
                ]
                self._add_table(lab_box, ("chemical", "volume", "umol"), ("Chemical ID", "Aspirated uL", "Aspirated umol"), table_rows)
                style_region_widgets(lab_box, "FileRegion")
            style_region_widgets(source_box, "FileRegion")

    def _source_cells(self, summary: Dict[str, object]) -> Tuple[int, int, bool, List[str], List[str], List[Dict[str, object]]]:
        labware = str(summary.get("labware", ""))
        cfg = tecan_frame.SOURCE_LAYOUTS.get(labware, {"rows": 8, "cols": 12})
        rows, cols = int(cfg.get("rows", 8)), int(cfg.get("cols", 12))
        style = str(cfg.get("style", "rowcol"))
        vial_mode = any(key in labware.lower() for key in self.VIAL_KEYWORDS)
        cells = []
        used = summary.get("wells", {}) or {}
        if style == "rowcol":
            row_headers = [tecan_frame.row_number_to_label(r) for r in range(1, rows + 1)]
            col_headers = [str(c) for c in range(1, cols + 1)]
        else:
            row_headers = [str(rows - r + 1) for r in range(1, rows + 1)]
            col_headers = [tecan_frame.row_number_to_label(c) for c in range(1, cols + 1)]
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                if style == "rowcol":
                    label = f"{tecan_frame.row_number_to_label(r)}{c}"
                else:
                    label = f"{tecan_frame.row_number_to_label(c)}{rows - r + 1}"
                cells.append({"label": label, "chemicals": used.get(label, []), "row": r, "col": c})
        return rows, cols, vial_mode, row_headers, col_headers, cells

    def _destination_cells(self, mode: str, wells: Dict[str, Dict[str, object]]) -> Tuple[int, int, List[str], List[str], List[Dict[str, object]]]:
        logical_rows, logical_cols, _order = tecan_frame.mode_dims_order(mode)
        vertical = "vertical" in mode.lower()
        if vertical:
            disp_rows, disp_cols = logical_cols, logical_rows
            row_headers = [str(logical_cols - r + 1) for r in range(1, disp_rows + 1)]
            col_headers = [tecan_frame.row_number_to_label(c) for c in range(1, disp_cols + 1)]
        else:
            disp_rows, disp_cols = logical_rows, logical_cols
            row_headers = [tecan_frame.row_number_to_label(r) for r in range(1, disp_rows + 1)]
            col_headers = [str(c) for c in range(1, disp_cols + 1)]
        cells = []
        for dr in range(1, disp_rows + 1):
            for dc in range(1, disp_cols + 1):
                if vertical:
                    logical_row = dc
                    logical_col = logical_cols - dr + 1
                    label = f"{tecan_frame.row_number_to_label(logical_row)}{logical_col}"
                else:
                    label = f"{tecan_frame.row_number_to_label(dr)}{dc}"
                cell = wells.get(label, {"label": label, "chemicals": []})
                cells.append({"label": label, "chemicals": cell.get("chemicals", []), "row": dr, "col": dc})
        return disp_rows, disp_cols, row_headers, col_headers, cells

    def refresh(self):
        for child in self.content.winfo_children():
            child.destroy()
        summary_rows = self._summary_transfer_rows([], [])
        blocks = self._pushed_source_blocks(summary_rows)
        detail_rows = summary_rows
        scheme_rows = self._scheme_rows([]) if self.show_reaction_schemes_var.get() and summary_rows else []
        if not summary_rows:
            self.status_var.set("No pushed additions. Use Push All to Cheminformatics in the synthesis editor.")
            ttk.Label(self.content, text=self.status_var.get(), style="Muted.TLabel").pack(anchor="w", padx=8, pady=8)
            self._bind_reaction_mousewheel_tree()
            return

        meta = []
        if self.other_chemicals_var.get().strip():
            meta.append(f"Other chemicals: {self.other_chemicals_var.get().strip()}")
        if self.temperature_var.get().strip():
            meta.append(f"Temperature: {self._format_temperature(self.temperature_var.get())}")
        if self.duration_var.get().strip():
            meta.append(f"Length: {self.duration_var.get().strip()}")
        meta_text = " | ".join(meta)
        block_text = f"{len(summary_rows)} pushed addition(s). Re-push after editing a synthesis plan."
        plan_notice = getattr(self, "plan_status_provider", lambda: "")()
        self.status_var.set(f"{plan_notice or block_text} {meta_text}".strip())

        if meta:
            condition_box = ttk.LabelFrame(self.content, text="Reaction Conditions", padding=8, style="ChemRegion.TLabelframe")
            condition_box.pack(fill="x", padx=8, pady=(8, 10))
            ttk.Label(condition_box, text=meta_text, style="Muted.TLabel").pack(anchor="w")
            style_region_widgets(condition_box, "ChemRegion")

        self._add_reaction_scheme_panel(blocks, scheme_rows)
        self._add_pushed_labware_summaries(summary_rows)
        self._add_pushed_transfer_details(detail_rows)

        if blocks:
            source_box = ttk.LabelFrame(self.content, text="Source Labware Summary", padding=8, style="FileRegion.TLabelframe")
            source_box.pack(fill="x", padx=8, pady=(8, 10))
            for summary in self._source_summary(blocks):
                lab_box = ttk.LabelFrame(source_box, text=str(summary["labware"]), padding=8, style="FileRegion.TLabelframe")
                lab_box.pack(fill="x", pady=(0, 10))
                rows, cols, vial_mode, row_headers, col_headers, cells = self._source_cells(summary)
                HoverMapCanvas(
                    lab_box,
                    cells,
                    rows=rows,
                    cols=cols,
                    vial_mode=vial_mode,
                    row_headers=row_headers,
                    col_headers=col_headers,
                ).pack(anchor="w", pady=(0, 8))
                table_rows = [
                    (chemical, f"{data['volume']:.6g}", f"{data['umol']:.6g}" if data["umol"] else "")
                    for chemical, data in (summary.get("totals", {}) or {}).items()
                ]
                self._add_table(lab_box, ("chemical", "volume", "umol"), ("Chemical ID", "Aspirated uL", "Aspirated umol"), table_rows)
                style_region_widgets(lab_box, "FileRegion")
            style_region_widgets(source_box, "FileRegion")

        dest_box = ttk.LabelFrame(self.content, text="Reaction Destination Summary", padding=8, style="RowRegion.TLabelframe")
        dest_box.pack(fill="x", padx=8, pady=(0, 10))
        try:
            mode, dest_labware, wells, tables = self._destination_summary([], summary_rows)
        except ValueError as exc:
            self.status_var.set(str(exc))
            ttk.Label(dest_box, text=str(exc), foreground="#b00020", wraplength=900).pack(anchor="w", pady=4)
            style_region_widgets(dest_box, "RowRegion")
            self._bind_reaction_mousewheel_tree()
            return
        rows, cols, row_headers, col_headers, dest_cells = self._destination_cells(mode, wells)
        vial_mode = "hplc" in mode.lower() or any(key in dest_labware.lower() for key in self.VIAL_KEYWORDS)
        ttk.Label(dest_box, text=f"{dest_labware or 'Destination'} - {mode}", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        HoverMapCanvas(
            dest_box,
            dest_cells,
            rows=rows,
            cols=cols,
            vial_mode=vial_mode,
            row_headers=row_headers,
            col_headers=col_headers,
        ).pack(anchor="w", pady=(0, 8))

        for group in sorted(tables):
            group_box = ttk.LabelFrame(dest_box, text=group, padding=8, style="RowRegion.TLabelframe")
            group_box.pack(fill="x", pady=(0, 8))
            table_rows = [
                (
                    row.get("gwl", ""),
                    row.get("well", ""),
                    row.get("chemical", ""),
                    f"{float(row.get('volume', 0.0) or 0.0):.6g}",
                    f"{float(row.get('umol', 0.0) or 0.0):.6g}" if row.get("umol") else "",
                )
                for row in sorted(tables[group], key=lambda item: (str(item.get("gwl", "")), str(item.get("well", "")), str(item.get("chemical", ""))))
            ]
            self._add_table(
                group_box,
                ("gwl", "well", "chemical", "volume", "umol"),
                ("Source", "Well/Vial", "Chemical ID", "Dispensed uL", "Dispensed umol"),
                table_rows,
                height=10,
            )
            style_region_widgets(group_box, "RowRegion")
        style_region_widgets(dest_box, "RowRegion")
        self._bind_reaction_mousewheel_tree()

    def export_state(self) -> Dict[str, object]:
        return {
            "show_reaction_schemes": self.show_reaction_schemes_var.get(),
            "other_chemicals": self.other_chemicals_var.get(),
            "temperature": self.temperature_var.get(),
            "duration": self.duration_var.get(),
        }

    def import_state(self, data: Dict[str, object]):
        if not isinstance(data, dict):
            return
        self.show_reaction_schemes_var.set(bool(data.get("show_reaction_schemes", False)))
        self.other_chemicals_var.set(str(data.get("other_chemicals", "") or ""))
        self.temperature_var.set(str(data.get("temperature", "") or ""))
        self.duration_var.set(str(data.get("duration", "") or ""))
