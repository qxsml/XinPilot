from __future__ import annotations

import itertools
from typing import Iterable

from xinpilot_shared import *
from reaction_summary_frame import PurityHeatMapCanvas
from xinpilot.application.heatmap_layout import heatmap_layout, reaction_mode
import impurity_analysis
import ion_handling
from peak_inspection import PeakInspectionMixin


def _trace_crop_box(crop: str, width: int, height: int) -> Optional[Tuple[int, int, int, int]]:
    """Return the source-image crop while retaining complete plot axes."""
    crop_fractions = {
        "mass_trace_panel": (0.0, 0.76, 1.0, 1.0),
        "pyparse_uv_panel": (0.035, 0.39, 0.99, 0.985),
        "uv_panel": (0.035, 0.535, 0.99, 0.80),
        "es_plus_panel": (0.0, 0.35, 1.0, 0.55),
        # The ES+ numerical x-axis labels extend below the former 0.525
        # boundary.  Stop just before the following UV panel title instead.
        "es_trace_panels": (0.0, 0.264, 1.0, 0.540),
    }
    fractions = crop_fractions.get(crop)
    if fractions is None:
        return None
    left, top, right, bottom = fractions
    return (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )


class CheminformaticsFrame(PeakInspectionMixin, ttk.Frame):
    def __init__(
        self,
        master,
        compound_provider,
        tecan_provider,
        pyparse_input_callback=None,
        modified_pyparse_input_callback=None,
        pyparse_stock_update_callback=None,
        product_structure_parent=None,
        synthesis_step_provider=None,
    ):
        super().__init__(master)
        self._peak_reset()
        self.compound_provider = compound_provider
        self.tecan_provider = tecan_provider
        self.pyparse_input_callback = pyparse_input_callback
        self.modified_pyparse_input_callback = modified_pyparse_input_callback
        self.pyparse_stock_update_callback = pyparse_stock_update_callback
        self.product_structure_parent = product_structure_parent
        self.synthesis_step_provider = synthesis_step_provider
        self.reactions = core.load_reactions()
        self.reaction_var = tk.StringVar(value="")
        self.retained_product_rows = []
        self.retained_detail_rows = []
        self.retained_results_var = tk.StringVar(value="")
        self.pushed_change_callback = None
        self.pushed_plan_fingerprints = {}
        self.product_details_generated = False
        self.output_var = tk.StringVar(value="")
        self.name_start_var = tk.StringVar(value="")
        self.reaction_name_edit_well = ""
        self.pyparse_output_var = tk.StringVar(value="")
        self.pyparse_well_var = tk.StringVar(value="")
        self.pyparse_wells: Dict[str, str] = {}
        self.impurity_exclusions: Dict[str, bool] = {}
        self.carried_impurity_sources: Dict[str, Dict[str, object]] = {}
        self._impurity_cache_signature = ""
        self._impurity_cache_rows: List[Dict[str, str]] = []
        self.impurity_pyparse_output_var = tk.StringVar(value="")
        self.impurity_advanced_review_visible = False
        self.product_summary_mode = "product"
        self.impurity_structure_img = None
        self.impurity_structure_cache: Dict[Tuple[str, int, int], ImageTk.PhotoImage] = {}
        self.pyparse_experiment_count_var = tk.StringVar(value="1")
        self.pyparse_update_current_stock_var = tk.BooleanVar(value=False)
        self.pyparse_update_master_stock_var = tk.BooleanVar(value=False)
        self.custom_reactant_order_var = tk.StringVar(value="Automatic (try all orders)")
        self.custom_output_dir_var = tk.StringVar(value="")
        self.custom_products: Dict[str, Dict[str, str]] = {}
        self.custom_failures: Dict[str, str] = {}
        self.reaction_site_selections: Dict[str, Dict[str, object]] = {}
        self._reaction_site_options_cache: Dict[str, List[Dict[str, object]]] = {}
        self.reaction_names: Dict[str, str] = {}
        self.imported_product_details: Dict[str, Dict[str, str]] = {}
        self.building_block_identity_by_well = {}
        self.product_review_wells: Dict[str, str] = {}
        self._last_product_identity_rows = {}
        self.pending_product_identity_rows = {}
        self.building_block_ion_rules: Dict[str, Dict[str, object]] = {}
        self.lcms_target_smiles_by_well: Dict[str, str] = {}
        self.lcms_target_summaries_by_well: Dict[str, str] = {}
        self.lcms_handling_mode = "automatic"
        self.pushed_rows: Dict[Tuple[str, str, str], Dict[str, object]] = {}
        self.product_structure_img = None
        self.product_structure_float_img = None
        self.product_structure_float_window = None
        self.product_structure_float_pin_var = tk.BooleanVar(value=False)
        self.product_structure_float_pin_button = None
        self.product_structure_heatmap_pin_var = tk.BooleanVar(value=False)
        self.product_structure_biology_hit_pin_var = tk.BooleanVar(value=False)
        self.product_structure_biology_hit_window = None
        self.product_structure_biology_hit_key = ""
        self.product_structure_biology_hit_title = "Biology assay hit"
        self.product_structure_biology_hit_detail_var = tk.StringVar(value="")
        self.product_structure_biology_hit_vars: Dict[str, tk.BooleanVar] = {}
        self.product_structure_biology_hit_other_var = tk.StringVar(value="")
        self.product_structure_current_smiles = ""
        self.product_structure_current_lcms_smiles = ""
        self.product_structure_drag_start: Optional[Tuple[int, int]] = None
        self.product_structure_cache: Dict[Tuple[str, int, int], ImageTk.PhotoImage] = {}
        self.product_structure_lcms_cache: Dict[Tuple[str, int, int], ImageTk.PhotoImage] = {}
        self.product_structure_float_cache: Dict[Tuple[str, int, int], ImageTk.PhotoImage] = {}
        self.product_selectivity_structure_cache: Dict[Tuple[str, int, int], ImageTk.PhotoImage] = {}
        self.product_structure_preview_width = 520
        self.product_structure_preview_height = 240
        self.pyparse_purity_by_well: Dict[str, str] = {}
        self.modified_pyparse_purity_by_well: Dict[str, str] = {}
        self.modified_pyparse_purity_by_product: Dict[str, Dict[str, str]] = {}
        self.modified_pyparse_conflicts_by_product: Dict[str, Dict[str, str]] = {}
        self.pyparse_result_dir: Optional[Path] = None
        self.modified_pyparse_result_dir: Optional[Path] = None
        self.modified_pyparse_impurity_result_dir: Optional[Path] = None
        self.portable_trace_paths: Dict[str, Dict[str, str]] = {}
        self.invalidated_product_analysis: Dict[str, List[str]] = {}
        self.product_structure_trace_images: Dict[str, ImageTk.PhotoImage] = {}
        self.product_structure_pyparse_purity_var = tk.StringVar(value="UV254 purity from PyParse: ")
        self.product_structure_modified_purity_var = tk.StringVar(value="UV254 purity from Modified PyParse: ")
        self.product_structure_manual_purity_var = tk.StringVar(value="")
        self.product_structure_uv_source_var = tk.StringVar(value="modified")
        self.product_structure_uv_source_by_key: Dict[str, str] = {}
        self.product_structure_manual_notes: Dict[str, Dict[str, str]] = {}
        self.product_structure_row_colors: Dict[str, str] = {}
        self.product_structure_biology_hits: Dict[str, List[str]] = {}
        self.product_structure_heatmap_canvases: List["PurityHeatMapCanvas"] = []
        self.product_structure_current_manual_key = ""
        self._ketcher_server = None
        self._ketcher_thread = None
        self._ketcher_port: Optional[int] = None
        self._ketcher_template_queue: "queue.Queue[str]" = queue.Queue()
        self._build_ui()
        self.after(250, self._poll_ketcher_templates)

    def _build_ui(self):
        self.tab_icons = make_tab_icons(self)
        self.inner_nb = ttk.Notebook(self, style="CompactChem.TNotebook", takefocus=0)
        self.inner_nb.pack(fill="both", expand=True, padx=8, pady=8)

        products_tab = ttk.Frame(self.inner_nb, style="Chem.TFrame")
        impurity_tab = ttk.Frame(self.inner_nb, style="Chem.TFrame")
        custom_tab = ttk.Frame(self.inner_nb, style="Chem.TFrame")
        stock_tab = ttk.Frame(self.inner_nb, style="Chem.TFrame")
        pyparse_tab = ttk.Frame(self.inner_nb, style="Chem.TFrame")
        product_structure_tab = self.product_structure_parent
        if product_structure_tab is None:
            product_structure_tab = ttk.Frame(self.inner_nb, style="Chem.TFrame")
        self.inner_nb.add(products_tab, text="Product Details", image=self.tab_icons["chem"], compound="top")
        self.inner_nb.add(custom_tab, text="Custom Template", image=self.tab_icons["template"], compound="top")
        self.inner_nb.add(stock_tab, text="Update Stock", image=self.tab_icons["map"], compound="top")
        self.inner_nb.add(pyparse_tab, text="LCMS Input", image=self.tab_icons["map"], compound="top")
        self.inner_nb.add(impurity_tab, text="Impurity Input & Analysis", image=self.tab_icons["chem"], compound="top")
        if self.product_structure_parent is None:
            self.inner_nb.add(product_structure_tab, text="Product Summary", image=self.tab_icons["chem"], compound="top")

        for pane in (products_tab, product_structure_tab):
            ttk.Label(pane, textvariable=self.retained_results_var, foreground="#8a4b12", wraplength=1000).pack(fill="x", padx=8)
        top = ttk.LabelFrame(products_tab, text="Cheminformatics from current pushed synthesis plan", padding=8, style="ChemRegion.TLabelframe")
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="Reaction type").grid(row=0, column=0, sticky="w")
        self.reaction_combo = ttk.Combobox(top, textvariable=self.reaction_var, values=[r["label"] for r in self.reactions], state="readonly", width=48)
        self.reaction_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.reaction_combo.bind("<<ComboboxSelected>>", self._on_reaction_type_selected)
        ttk.Button(top, text="Copy Selected SMILES", command=self._copy_selected_product_detail_smiles).grid(row=0, column=2, padx=6)
        ttk.Button(top, text="Edit Product…", command=self._edit_selected_product_detail, style="RowAction.TButton").grid(row=0, column=3, padx=6)

        out = ttk.Frame(top)
        out.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(out, text="Output CSV (optional)").pack(side="left")
        ttk.Entry(out, textvariable=self.output_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Browse", command=self._pick_output).pack(side="left")
        ttk.Button(out, text="Clear", command=lambda: self.output_var.set("")).pack(side="left", padx=(6, 0))
        top.columnconfigure(1, weight=1)

        names = ttk.Frame(top)
        names.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(names, text="Reaction name").pack(side="left")
        self.product_reaction_name_entry = ttk.Entry(names, textvariable=self.name_start_var, width=24)
        self.product_reaction_name_entry.pack(side="left", padx=6)
        self.product_reaction_name_entry.bind("<KeyRelease>", self._save_reaction_name_edit)
        self.product_reaction_name_entry.bind("<FocusOut>", self._save_reaction_name_edit)
        ttk.Button(names, text="Fill Down", command=self._fill_reaction_names, style="ChemAction.TButton").pack(side="left")
        ttk.Button(names, text="Clear Pushed Chemicals", command=self._clear_pushed_rows, style="Danger.TButton").pack(side="left", padx=(12, 0))
        ttk.Button(names, text="Input Product Details", command=self._input_product_details, style="FileAction.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(names, text="Generate Product Details", command=self._generate, style="ChemAction.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(names, text="Charge Rules…", command=self._review_charge_rules_action).pack(side="left", padx=(6, 0))
        style_region_widgets(top, "ChemRegion")

        body = ttk.Frame(products_tab, padding=8)
        body.pack(fill="both", expand=True)
        self.preview = ttk.Treeview(body, columns=("reaction_name", "well", "reactant1", "reactant2", "reactant3", "product_smiles"), show="headings", height=18)
        for col, text, width in [
            ("reaction_name", "Reaction name", 180),
            ("well", "Well", 80),
            ("reactant1", "Reactant 1 / BB", 220),
            ("reactant2", "Reactant 2 / BB", 220),
            ("reactant3", "Reactant 3 / BB", 220),
            ("product_smiles", "Product SMILES", 360),
        ]:
            self.preview.heading(col, text=text)
            self.preview.column(col, width=width, anchor="w")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<<TreeviewSelect>>", self._on_product_details_row_select)
        self.preview.bind("<Control-c>", self._copy_selected_product_detail_smiles)
        self.preview.bind("<Double-Button-1>", self._edit_selected_product_detail)

        log_box = ttk.LabelFrame(products_tab, text="Log", padding=8, style="RowRegion.TLabelframe")
        log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log = tk.Text(log_box, height=8, wrap="word")
        self.log.pack(fill="both", expand=True)
        style_region_widgets(log_box, "RowRegion")

        stock_box = ttk.LabelFrame(stock_tab, text="Update stock lists from exported GWL files", padding=12, style="FileRegion.TLabelframe")
        stock_box.pack(fill="x", padx=8, pady=8)
        ttk.Label(stock_box, text="How many times was this experiment conducted?").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(stock_box, text="Experiment count").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(stock_box, textvariable=self.pyparse_experiment_count_var, width=10).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Checkbutton(stock_box, text="Update current Compound Notes stock list?", variable=self.pyparse_update_current_stock_var).grid(row=2, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(stock_box, text="Update master stock list?", variable=self.pyparse_update_master_stock_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Button(stock_box, text="Update Stock", command=self._run_stock_update, style="ChemAction.TButton").grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Label(
            stock_box,
            text="Uses every GWL file listed in Tecan's 'Exported GWL files from this edition' panel.",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        style_region_widgets(stock_box, "FileRegion")

        py_top = ttk.LabelFrame(pyparse_tab, text="PyParse platemap from Cheminformatics", padding=8, style="ChemRegion.TLabelframe")
        py_top.pack(fill="x", padx=8, pady=8)
        ttk.Button(py_top, text="Use Reaction Wells", command=self._use_reaction_wells_for_pyparse).grid(row=0, column=0, padx=4, sticky="w")
        ttk.Label(py_top, text="Selected LCMS well").grid(row=0, column=1, padx=(18, 4), sticky="e")
        ttk.Entry(py_top, textvariable=self.pyparse_well_var, width=10).grid(row=0, column=2, sticky="w")
        ttk.Button(py_top, text="Apply to Selected", command=self._apply_selected_pyparse_well, style="RowAction.TButton").grid(row=0, column=3, padx=4, sticky="w")
        ttk.Button(
            py_top,
            text="Map Selection",
            command=self._pick_pyparse_wells_on_map,
            style="ChemAction.TButton",
        ).grid(row=0, column=4, padx=4, sticky="w")
        ttk.Button(py_top, text="Copy Selected SMILES", command=self._copy_selected_pyparse_product_smiles).grid(row=0, column=5, padx=4, sticky="w")

        py_out = ttk.Frame(py_top)
        py_out.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        ttk.Label(py_out, text="Save platemap CSV (optional)").pack(side="left")
        ttk.Entry(py_out, textvariable=self.pyparse_output_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(py_out, text="Browse", command=self._pick_pyparse_output).pack(side="left")
        ttk.Button(py_out, text="Clear", command=lambda: self.pyparse_output_var.set("")).pack(side="left", padx=(6, 0))
        ttk.Button(py_out, text="Generate Input for LCMS Analysis", command=self._generate_pyparse_input, style="ChemAction.TButton").pack(side="left", padx=(6, 0))
        py_top.columnconfigure(5, weight=1)
        from autolynx_dialog import open_autolynx_dialog
        ttk.Button(py_top, text="Export AutoLynx sample list", command=lambda: open_autolynx_dialog(self, self._pyparse_rows), style="ChemAction.TButton").grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))
        style_region_widgets(py_top, "ChemRegion")

        py_body = ttk.Frame(pyparse_tab, padding=8)
        py_body.pack(fill="both", expand=True)
        columns = ("reaction_name", "reaction_well", "pyparse_well", "product_id", "product_smiles")
        self.pyparse_preview = ttk.Treeview(py_body, columns=columns, show="headings", height=18)
        for col, text, width in [
            ("reaction_name", "Reaction name", 170),
            ("reaction_well", "Reaction well", 100),
            ("pyparse_well", "LCMS well", 100),
            ("product_id", "Product ID", 170),
            ("product_smiles", "LCMS target SMILES", 610),
        ]:
            self.pyparse_preview.heading(col, text=text)
            self.pyparse_preview.column(col, width=width, anchor="w")
        self.pyparse_preview.pack(fill="both", expand=True)
        self.pyparse_preview.bind("<<TreeviewSelect>>", self._on_pyparse_row_select)
        self.pyparse_preview.bind("<Control-c>", self._copy_selected_pyparse_product_smiles)

        self._build_impurity_analysis_ui(impurity_tab)

        structure_body = ttk.Frame(product_structure_tab, padding=8)
        structure_body.pack(fill="both", expand=True)
        self.product_structure_split = ttk.Panedwindow(structure_body, orient="horizontal")
        self.product_structure_split.pack(fill="both", expand=True)

        preview_scroll = ttk.Frame(self.product_structure_split)
        product_table_host = ttk.Frame(self.product_structure_split, style="RowRegion.TFrame")
        self.product_structure_split.add(preview_scroll, weight=3)
        self.product_structure_split.add(product_table_host, weight=1)
        preview_canvas = tk.Canvas(
            preview_scroll,
            width=max(1, self.product_structure_preview_width + 28),
            highlightthickness=0,
            background=COLORS["bg"],
        )
        self.product_structure_preview_canvas = preview_canvas
        preview_y = ttk.Scrollbar(preview_scroll, orient="vertical", command=preview_canvas.yview)
        preview_canvas.configure(yscrollcommand=preview_y.set)
        preview_canvas.grid(row=0, column=0, sticky="nsew")
        preview_y.grid(row=0, column=1, sticky="ns")
        preview_scroll.grid_rowconfigure(0, weight=1)
        preview_scroll.grid_columnconfigure(0, weight=1)

        preview_box = ttk.LabelFrame(preview_canvas, text="Structure Preview", padding=8, style="ChemRegion.TLabelframe")
        preview_window = preview_canvas.create_window((0, 0), window=preview_box, anchor="nw")

        def _sync_preview_scroll_region(_event=None):
            content_width = max(1, preview_canvas.winfo_width())
            preview_canvas.itemconfigure(preview_window, width=content_width)
            preview_canvas.configure(scrollregion=preview_canvas.bbox("all"))

        def _sync_preview_width(event):
            content_width = max(1, event.width)
            preview_canvas.itemconfigure(preview_window, width=content_width)
            self._sync_product_structure_detail_wraps(content_width)
            _sync_preview_scroll_region()

        def _preview_mousewheel(event):
            if preview_y.get() == (0.0, 1.0):
                return
            preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        preview_box.bind("<Configure>", _sync_preview_scroll_region)
        preview_canvas.bind("<Configure>", _sync_preview_width)
        preview_canvas.bind("<Enter>", lambda _event: preview_canvas.bind_all("<MouseWheel>", _preview_mousewheel))
        preview_canvas.bind("<Leave>", lambda _event: preview_canvas.unbind_all("<MouseWheel>"))
        self.product_structure_info_box = ttk.Frame(preview_box)
        self.product_structure_info_box.pack(fill="x")
        structure_tools = ttk.Frame(self.product_structure_info_box)
        structure_tools.pack(fill="x", pady=(0, 4))
        ttk.Button(
            structure_tools,
            text="Copy SMILES",
            command=self._copy_current_product_structure_smiles,
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            structure_tools,
            text="Detach",
            command=self._detach_product_structure_preview,
        ).pack(side="right")
        structure_compare = ttk.Frame(self.product_structure_info_box)
        structure_compare.pack(fill="x")
        structure_compare.grid_columnconfigure(0, weight=1, uniform="structure")
        structure_compare.grid_columnconfigure(1, weight=1, uniform="structure")
        structure_compare.grid_rowconfigure(1, minsize=170)
        self.product_structure_heading = ttk.Label(structure_compare, text="Product Details structure", style="Section.TLabel")
        self.product_structure_heading.grid(row=0, column=0, sticky="w", pady=(0, 3))
        self.product_structure_lcms_heading = ttk.Label(structure_compare, text="LCMS target structure", style="Section.TLabel")
        self.product_structure_lcms_heading.grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(0, 3))
        self.product_structure_label = ttk.Label(
            structure_compare,
            text="Select a product row",
            anchor="center",
            width=max(1, self.product_structure_preview_width // 16),
            background="#ffffff",
            relief="solid",
        )
        self.product_structure_label.grid(row=1, column=0, sticky="nsew")
        self.product_structure_label.configure(
            width=max(1, self.product_structure_preview_width // 16),
        )
        self.product_structure_lcms_label = ttk.Label(
            structure_compare,
            text="Generate LCMS Input to create target",
            anchor="center",
            width=max(1, self.product_structure_preview_width // 16),
            background="#ffffff",
            relief="solid",
        )
        self.product_structure_lcms_label.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        info_detail = ttk.Frame(self.product_structure_info_box)
        info_detail.pack(fill="x", pady=(8, 0))
        info_detail.grid_columnconfigure(0, weight=3, minsize=300)
        info_detail.grid_columnconfigure(1, weight=2, minsize=220)
        left_info = ttk.Frame(info_detail)
        left_info.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        manual_box = ttk.Frame(info_detail)
        manual_box.grid(row=0, column=1, sticky="nsew")
        manual_box.grid_columnconfigure(2, weight=1)

        self.product_structure_meta_var = tk.StringVar(value="")
        self.product_structure_meta_label = ttk.Label(
            left_info,
            textvariable=self.product_structure_meta_var,
            wraplength=self.product_structure_preview_width,
            justify="left",
        )
        self.product_structure_meta_label.pack(fill="x")
        purity_box = ttk.Frame(left_info)
        purity_box.pack(fill="x", pady=(8, 0))
        ttk.Radiobutton(
            purity_box,
            variable=self.product_structure_uv_source_var,
            value="pyparse",
            command=self._set_current_product_structure_uv_source,
        ).grid(row=0, column=0, sticky="nw", padx=(0, 4))
        self.product_structure_pyparse_purity_label = ttk.Label(
            purity_box,
            textvariable=self.product_structure_pyparse_purity_var,
            wraplength=self.product_structure_preview_width,
            justify="left",
        )
        self.product_structure_pyparse_purity_label.grid(row=0, column=1, sticky="ew")
        ttk.Radiobutton(
            purity_box,
            variable=self.product_structure_uv_source_var,
            value="modified",
            command=self._set_current_product_structure_uv_source,
        ).grid(row=1, column=0, sticky="nw", padx=(0, 4))
        self.product_structure_modified_purity_label = ttk.Label(
            purity_box,
            textvariable=self.product_structure_modified_purity_var,
            wraplength=self.product_structure_preview_width,
            justify="left",
        )
        self.product_structure_modified_purity_label.grid(row=1, column=1, sticky="ew")
        purity_box.grid_columnconfigure(1, weight=1)
        purity_actions = ttk.Frame(purity_box)
        purity_actions.grid(
            row=2,
            column=1,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Button(
            purity_actions,
            text="Generate Heat Map",
            command=self._generate_product_structure_heat_maps,
            style="ChemAction.TButton",
        ).pack(side="left")
        self.product_results_export_button = ttk.Button(
            purity_actions,
            text="Export CSV",
            command=self._export_product_results_csv,
            style="FileAction.TButton",
        )
        self.product_results_export_button.pack(side="left", padx=(6, 0))
        ttk.Radiobutton(
            manual_box,
            variable=self.product_structure_uv_source_var,
            value="manual",
            command=self._set_current_product_structure_uv_source,
        ).grid(row=0, column=0, sticky="w", padx=(0, 4), pady=(0, 4))
        ttk.Label(manual_box, text="Purity by manual:").grid(row=0, column=1, sticky="w", padx=(0, 6), pady=(0, 4))
        manual_entry = ttk.Entry(manual_box, textvariable=self.product_structure_manual_purity_var, width=14)
        manual_entry.grid(row=0, column=2, sticky="ew", pady=(0, 4))
        ttk.Label(manual_box, text="Comments:").grid(row=1, column=1, sticky="nw", padx=(0, 6))
        self.product_structure_manual_comment_text = tk.Text(manual_box, height=3, width=24, wrap="word")
        self.product_structure_manual_comment_text.grid(row=1, column=2, sticky="ew")
        for widget in (manual_entry, self.product_structure_manual_comment_text):
            widget.bind("<FocusOut>", self._save_current_product_structure_manual_fields, add="+")
            widget.bind("<KeyRelease>", self._save_current_product_structure_manual_fields, add="+")
        self._bind_product_structure_detach_events(self.product_structure_info_box)
        trace_box = ttk.Frame(preview_box)
        self.product_structure_trace_box = trace_box
        trace_box.pack(fill="x", pady=(8, 0))
        self.product_structure_trace_widgets = []
        self.product_structure_trace_title_widgets = []
        for title in ("UV trace from PyParse", "UV trace from Modified PyParse", "ES+/ES- traces from Modified PyParse"):
            title_label = ttk.Label(trace_box, text=title)
            title_label.pack(fill="x", anchor="w", pady=(5, 0))
            self.product_structure_trace_title_widgets.append(title_label)
            lbl = ttk.Label(trace_box, text="", anchor="center", background="#ffffff", relief="solid")
            lbl.pack(fill="x", anchor="w", pady=(2, 0))
            self.product_structure_trace_widgets.append(lbl)
        style_region_widgets(preview_box, "ChemRegion")

        ttk.Label(
            product_table_host,
            text="Right-click a product row for color and biology-hit actions.",
            style="RowRegion.Muted.TLabel",
            wraplength=300,
            justify="left",
        ).pack(fill="x", padx=4, pady=(0, 4))
        self.product_summary_tables = ttk.Notebook(product_table_host, style="Chem.TNotebook", takefocus=0)
        self.product_summary_tables.pack(fill="both", expand=True)
        table_box = ttk.Frame(self.product_summary_tables, padding=8, style="RowRegion.TFrame")
        impurity_table_box = ttk.Frame(self.product_summary_tables, padding=8, style="RowRegion.TFrame")
        self.product_summary_tables.add(table_box, text="Products")
        self.product_summary_tables.add(impurity_table_box, text="Impurities")
        self.product_summary_tables.bind("<<NotebookTabChanged>>", self._on_product_summary_table_changed)
        table_box.grid_rowconfigure(0, weight=1)
        table_box.grid_columnconfigure(0, weight=1)
        product_columns = (
            "reaction_name",
            "reaction_well",
            "pyparse_well",
        )
        self.product_structure_table = ttk.Treeview(table_box, columns=product_columns, show="headings", height=18)
        configure_table_tags(self.product_structure_table)
        for col, text, width in [
            ("reaction_name", "RXN number", 130),
            ("reaction_well", "RXN well", 85),
            ("pyparse_well", "LCMS Well", 85),
        ]:
            self.product_structure_table.heading(col, text=text)
            self.product_structure_table.column(col, width=width, anchor="w")
        product_y = ttk.Scrollbar(table_box, orient="vertical", command=self.product_structure_table.yview)
        self.product_structure_table.configure(yscrollcommand=product_y.set)
        self.product_structure_table.grid(row=0, column=0, sticky="nsew")
        product_y.grid(row=0, column=1, sticky="ns")
        self.product_table_x_scrollbar = ttk.Scrollbar(table_box, orient="horizontal", command=self.product_structure_table.xview)
        self.product_structure_table.configure(xscrollcommand=self.product_table_x_scrollbar.set)
        self.product_table_x_scrollbar.grid(row=1, column=0, sticky="ew")
        for color_name, color_hex in PRODUCT_SUMMARY_ROW_COLORS.items():
            self.product_structure_table.tag_configure(f"rowcolor_{color_name}", background=color_hex)
        self.product_structure_table.tag_configure("biology_hit", foreground="#000000", font=("Segoe UI", 10, "bold"))
        self.product_structure_table.bind("<<TreeviewSelect>>", self._on_product_structure_select)
        self.product_structure_table.bind("<Button-3>", self._show_product_structure_color_menu)
        self.product_structure_table.bind("<Control-Button-1>", self._show_product_structure_color_menu)
        style_region_widgets(table_box, "RowRegion")

        impurity_table_box.grid_rowconfigure(0, weight=1)
        impurity_table_box.grid_columnconfigure(0, weight=1)
        self.product_impurity_table = ttk.Treeview(
            impurity_table_box,
            columns=product_columns,
            show="headings",
            height=18,
        )
        for col, text, width in [
            ("reaction_name", "RXN number", 130),
            ("reaction_well", "RXN well", 85),
            ("pyparse_well", "LCMS Well", 85),
        ]:
            self.product_impurity_table.heading(col, text=text)
            self.product_impurity_table.column(col, width=width, anchor="w")
        impurity_y = ttk.Scrollbar(impurity_table_box, orient="vertical", command=self.product_impurity_table.yview)
        self.product_impurity_table.configure(yscrollcommand=impurity_y.set)
        self.product_impurity_table.grid(row=0, column=0, sticky="nsew")
        impurity_y.grid(row=0, column=1, sticky="ns")
        self.product_impurity_table.bind("<<TreeviewSelect>>", self._on_product_impurity_select)
        style_region_widgets(impurity_table_box, "RowRegion")
        self._initial_product_split_ready = False
        self.product_structure_split.bind("<Configure>", lambda _event: self._set_initial_product_summary_split(), add="+")
        self.after_idle(self._set_initial_product_summary_split)

        custom_top = ttk.LabelFrame(custom_tab, text="Mapped reaction template", padding=8, style="ChemRegion.TLabelframe")
        custom_top.pack(fill="x", padx=8, pady=8)
        ttk.Button(custom_top, text="Draw Reaction", command=self._open_sketcher_helper, style="DrawReaction.TButton").grid(row=0, column=0, padx=(0, 8), sticky="w")
        ttk.Button(custom_top, text="Load Template...", command=self._load_custom_template, style="FileAction.TButton").grid(row=0, column=1, padx=(0, 6), sticky="w")
        ttk.Button(custom_top, text="Save Template...", command=self._save_custom_template, style="FileAction.TButton").grid(row=0, column=2, padx=(0, 12), sticky="w")
        ttk.Label(custom_top, text="Reactant order").grid(row=0, column=3, sticky="w", padx=(0, 6), pady=3)
        ttk.Combobox(
            custom_top,
            textvariable=self.custom_reactant_order_var,
            values=["Automatic (try all orders)", "As listed"],
            state="readonly",
            width=24,
        ).grid(row=0, column=4, sticky="w", pady=3)
        ttk.Label(custom_top, text="Reaction name").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 3))
        self.custom_reaction_name_entry = ttk.Entry(custom_top, textvariable=self.name_start_var, width=18)
        self.custom_reaction_name_entry.grid(row=1, column=1, sticky="w", pady=(6, 3))
        self.custom_reaction_name_entry.bind("<KeyRelease>", self._save_reaction_name_edit)
        self.custom_reaction_name_entry.bind("<FocusOut>", self._save_reaction_name_edit)
        ttk.Button(custom_top, text="Fill Down", command=self._fill_reaction_names, style="ChemAction.TButton").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(6, 3))
        ttk.Button(custom_top, text="Clear Pushed Chemicals", command=self._clear_pushed_rows, style="Danger.TButton").grid(row=1, column=3, sticky="w", padx=(0, 6), pady=(6, 3))
        ttk.Button(custom_top, text="Input Product Details", command=self._input_product_details, style="FileAction.TButton").grid(row=1, column=4, sticky="w", pady=(6, 3))

        self.custom_template_text = tk.Text(custom_top, height=7, wrap="word")
        self.custom_template_text.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        custom_top.columnconfigure(4, weight=1)
        style_region_widgets(custom_top, "ChemRegion")

        custom_actions = ttk.Frame(custom_tab, padding=(8, 0, 8, 6))
        custom_actions.pack(fill="x")
        custom_actions.columnconfigure(1, weight=1)
        ttk.Button(custom_actions, text="Generate Custom Products for All", command=lambda: self._generate_custom_products(selected_only=False), style="ChemAction.TButton").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Button(custom_actions, text="Copy Selected SMILES", command=self._copy_selected_custom_product_smiles).grid(row=0, column=1, sticky="w")
        self.clear_custom_input_reaction_button = ttk.Button(
            custom_actions,
            text="Clear Input Reaction",
            command=self._clear_custom_input_reaction,
            style="Danger.TButton",
        )
        self.clear_custom_input_reaction_button.grid(row=0, column=2, columnspan=2, sticky="e")
        ttk.Label(custom_actions, text="Output CSV folder (optional)").grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 6))
        custom_output_entry = ttk.Entry(custom_actions, textvariable=self.custom_output_dir_var, width=46)
        custom_output_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        ttk.Button(custom_actions, text="Browse", command=self._pick_custom_output_dir).grid(row=1, column=2, padx=(6, 3), pady=(6, 0))
        ttk.Button(custom_actions, text="Clear", command=lambda: self.custom_output_dir_var.set("")).grid(row=1, column=3, padx=(3, 0), pady=(6, 0))

        detail_box = ttk.LabelFrame(custom_tab, text="Selected custom row detail", padding=8, style="RowRegion.TLabelframe")
        detail_box.pack(fill="x", padx=8, pady=(0, 8))
        self.custom_detail = tk.Text(detail_box, height=4, wrap="word")
        self.custom_detail.pack(fill="x", expand=True)
        self.custom_detail.configure(state="disabled")
        style_region_widgets(detail_box, "RowRegion")

        custom_body = ttk.Frame(custom_tab, padding=8)
        custom_body.pack(fill="both", expand=True)
        custom_cols = ("well", "reaction_name", "reactant1", "reactant2", "reactant3", "custom_product", "status")
        self.custom_preview = ttk.Treeview(custom_body, columns=custom_cols, show="headings", height=12)
        for col, text, width in [
            ("well", "Well", 80),
            ("reaction_name", "Reaction name", 170),
            ("reactant1", "Reactant 1 / BB", 190),
            ("reactant2", "Reactant 2 / BB", 190),
            ("reactant3", "Reactant 3 / BB", 190),
            ("custom_product", "Custom product SMILES", 300),
            ("status", "Status", 250),
        ]:
            self.custom_preview.heading(col, text=text)
            self.custom_preview.column(col, width=width, anchor="w")
        custom_x = ttk.Scrollbar(custom_body, orient="horizontal", command=self.custom_preview.xview)
        custom_y = ttk.Scrollbar(custom_body, orient="vertical", command=self.custom_preview.yview)
        self.custom_preview.configure(xscrollcommand=custom_x.set, yscrollcommand=custom_y.set)
        custom_body.grid_rowconfigure(0, weight=1)
        custom_body.grid_columnconfigure(0, weight=1)
        self.custom_preview.grid(row=0, column=0, sticky="nsew")
        custom_y.grid(row=0, column=1, sticky="ns")
        custom_x.grid(row=1, column=0, sticky="ew")
        self.custom_preview.bind("<<TreeviewSelect>>", self._on_custom_row_select)
        self.custom_preview.bind("<Control-c>", self._copy_selected_custom_product_smiles)

    def _set_initial_product_summary_split(self):
        if self._initial_product_split_ready:
            return
        try:
            total_width = self.product_structure_split.winfo_width()
            if total_width <= 1:
                return
            preview_width = max(560, min(total_width - 310, int(total_width * 0.72)))
            self.product_structure_split.sashpos(0, preview_width)
            self._initial_product_split_ready = True
        except Exception:
            pass

    def _build_impurity_analysis_ui(self, analysis_tab):
        top = ttk.LabelFrame(
            analysis_tab,
            text="Automatic impurity guidance for Modified PyParse",
            padding=8,
            style="ChemRegion.TLabelframe",
        )
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(
            top,
            text=(
                "All valid predicted impurities are included automatically. Candidates come from unreacted starting "
                "materials and conservative RDKit SMARTS side-reaction rules. Modified PyParse checks them as LCMS "
                "guidance; a match is not definitive impurity identification."
            ),
            wraplength=1040,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        ttk.Label(top, text="Save platemap CSV (optional)").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.impurity_pyparse_output_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Browse", command=self._pick_impurity_pyparse_output, style="FileAction.TButton").grid(row=1, column=2)
        ttk.Button(
            top,
            text="Generate Modified PyParse Impurity Targets",
            command=self._generate_impurity_pyparse_input,
            style="ChemAction.TButton",
        ).grid(row=1, column=3, padx=(8, 0))
        ttk.Button(
            top,
            text="Refresh Analysis",
            command=self._refresh_impurity_previews,
            style="RowAction.TButton",
        ).grid(row=2, column=3, sticky="e", pady=(8, 0))
        top.grid_columnconfigure(1, weight=1)
        style_region_widgets(top, "ChemRegion")

        advanced_header = ttk.Frame(analysis_tab, padding=(8, 0, 8, 6))
        advanced_header.pack(fill="x")
        self.impurity_advanced_review_button = ttk.Button(
            advanced_header,
            text="Show Advanced Review",
            command=self._toggle_impurity_advanced_review,
        )
        self.impurity_advanced_review_button.pack(side="left")
        ttk.Label(
            advanced_header,
            text="Optional: exclude unusual targets; normal use requires no manual selection.",
        ).pack(side="left", padx=(8, 0))

        self.impurity_advanced_review_frame = ttk.Frame(analysis_tab, padding=(8, 0, 8, 8))
        ttk.Button(
            self.impurity_advanced_review_frame,
            text="Include Selected",
            command=lambda: self._set_selected_impurity_targets(True),
            style="ChemAction.TButton",
        ).pack(side="left")
        ttk.Button(
            self.impurity_advanced_review_frame,
            text="Exclude Selected",
            command=lambda: self._set_selected_impurity_targets(False),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            self.impurity_advanced_review_frame,
            text="Restore All Targets",
            command=lambda: self._set_all_impurity_targets(True),
        ).pack(side="left", padx=(14, 0))
        ttk.Button(
            self.impurity_advanced_review_frame,
            text="Copy Selected SMILES",
            command=self._copy_selected_impurity_smiles,
        ).pack(side="left", padx=(14, 0))

        body = ttk.Frame(analysis_tab, padding=(8, 0, 8, 8))
        self.impurity_analysis_body = body
        body.pack(fill="both", expand=True)
        columns = (
            "reaction_name", "reaction_well", "pyparse_well", "label", "category",
            "name", "formula", "exact_mass", "origin", "lineage", "basis", "included",
        )
        self.impurity_analysis_table = ttk.Treeview(body, columns=columns, show="headings", height=18, selectmode="extended")
        for col, text, width in [
            ("reaction_name", "RXN number", 130),
            ("reaction_well", "RXN well", 75),
            ("pyparse_well", "LCMS well", 80),
            ("label", "Impurity", 82),
            ("category", "Category", 160),
            ("name", "Candidate", 190),
            ("formula", "Formula", 110),
            ("exact_mass", "Exact mass", 90),
            ("origin", "Origin", 190),
            ("lineage", "Step/well lineage", 330),
            ("basis", "Prediction basis", 300),
            ("included", "Analyze", 65),
        ]:
            self.impurity_analysis_table.heading(col, text=text)
            self.impurity_analysis_table.column(col, width=width, anchor="w")
        iy = ttk.Scrollbar(body, orient="vertical", command=self.impurity_analysis_table.yview)
        ix = ttk.Scrollbar(body, orient="horizontal", command=self.impurity_analysis_table.xview)
        self.impurity_analysis_table.configure(yscrollcommand=iy.set, xscrollcommand=ix.set)
        self.impurity_analysis_table.grid(row=0, column=0, sticky="nsew")
        iy.grid(row=0, column=1, sticky="ns")
        ix.grid(row=1, column=0, sticky="ew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.impurity_analysis_table.bind("<Double-Button-1>", self._toggle_selected_impurity_targets)
        self.impurity_analysis_table.bind("<Control-c>", self._copy_selected_impurity_smiles)

    def _toggle_impurity_advanced_review(self):
        self.impurity_advanced_review_visible = not self.impurity_advanced_review_visible
        if self.impurity_advanced_review_visible:
            self.impurity_advanced_review_frame.pack(
                fill="x",
                before=self.impurity_analysis_body,
            )
            self.impurity_advanced_review_button.configure(text="Hide Advanced Review")
        else:
            self.impurity_advanced_review_frame.pack_forget()
            self.impurity_advanced_review_button.configure(text="Show Advanced Review")

    @staticmethod
    def _impurity_target_key(row: Dict[str, object]) -> str:
        return f"{_normalize_well(row.get('reaction_well', ''))}|{str(row.get('smiles', '') or '').strip()}"

    def _reaction_by_id(self, reaction_id: str) -> Optional[Dict[str, str]]:
        reaction_id = str(reaction_id or "").strip()
        return next((reaction for reaction in self.reactions if str(reaction.get("id", "")) == reaction_id), None)

    def _impurity_rows(self) -> List[Dict[str, str]]:
        try:
            reaction_rows = self._pyparse_rows()
            current_step = 1
            synthesis_step_provider = getattr(self, "synthesis_step_provider", None)
            if synthesis_step_provider:
                try:
                    current_step = max(1, int(synthesis_step_provider() or 1))
                except (TypeError, ValueError):
                    current_step = 1
            carried_impurity_sources = getattr(self, "carried_impurity_sources", {}) or {}
            signature = json.dumps({
                "step": current_step,
                "carried_impurity_sources": carried_impurity_sources,
                "reaction_rows": [
                    {
                        key: row.get(key, "")
                        for key in (
                            "reaction_name", "reaction", "reaction_well", "pyparse_well",
                            "desired product smiles", "selectivity products", "limiting reactant smiles", "limiting reactant name",
                            "limiting reactant id", "excess reactant smiles", "excess reactant name", "excess reactant id",
                            "reactant 1 smiles", "reactant 1 name", "reactant 1 id",
                            "reactant 2 smiles", "reactant 2 name", "reactant 2 id",
                            "reactant 3 smiles", "reactant 3 name", "reactant 3 id",
                        )
                    }
                    for row in reaction_rows
                ],
            }, sort_keys=True, default=str)
            if signature != self._impurity_cache_signature:
                self._impurity_cache_rows = impurity_analysis.flatten_impurity_rows(
                    reaction_rows,
                    self._reaction_by_id,
                    carried_sources=carried_impurity_sources,
                    current_step=current_step,
                )
                self._impurity_cache_signature = signature
            rows = [dict(row) for row in self._impurity_cache_rows]
        except Exception as exc:
            self.logw(f"Impurity analysis warning: {exc}")
            return []
        for row in rows:
            row["included"] = "Yes" if not self.impurity_exclusions.get(self._impurity_target_key(row), False) else "No"
        return rows

    def _included_impurity_rows(self) -> List[Dict[str, str]]:
        included = [dict(row) for row in self._impurity_rows() if row.get("included") == "Yes"]
        counts: Dict[str, int] = {}
        for row in included:
            reaction_well = _normalize_well(row.get("reaction_well", ""))
            counts[reaction_well] = counts.get(reaction_well, 0) + 1
            row["label"] = f"Impurity {counts[reaction_well]}"
            # PyParse uses the compound name in graph filenames.  A well suffix
            # prevents Impurity1 from another reaction overwriting this graph.
            safe_reaction = _safe_pyparse_graph_token(reaction_well) or "reaction"
            safe_lcms = _safe_pyparse_graph_token(row.get("pyparse_well", "")) or "well"
            row["pyparse_name"] = f"Impurity{counts[reaction_well]}__{safe_reaction}_{safe_lcms}"
        return included

    def _refresh_impurity_previews(self):
        rows = self._impurity_rows()
        if hasattr(self, "impurity_analysis_table"):
            self.impurity_analysis_table.delete(*self.impurity_analysis_table.get_children())
            for index, row in enumerate(rows):
                self.impurity_analysis_table.insert("", "end", iid=str(index), values=(
                    row.get("reaction_name", ""), row.get("reaction_well", ""), row.get("pyparse_well", ""),
                    row.get("label", ""), row.get("category", ""), row.get("name", ""),
                    row.get("formula", ""), row.get("exact_mass", ""), row.get("origin", ""),
                    row.get("lineage", ""), row.get("basis", ""), row.get("included", ""),
                ))
        if hasattr(self, "product_impurity_table"):
            self._refresh_product_impurity_preview()

    def _set_selected_impurity_targets(self, include: bool):
        rows = self._impurity_rows()
        for iid in self.impurity_analysis_table.selection():
            try:
                row = rows[int(iid)]
            except (ValueError, IndexError):
                continue
            key = self._impurity_target_key(row)
            if include:
                self.impurity_exclusions.pop(key, None)
            else:
                self.impurity_exclusions[key] = True
        self._refresh_impurity_previews()

    def _toggle_selected_impurity_targets(self, _event=None):
        rows = self._impurity_rows()
        selected = list(self.impurity_analysis_table.selection())
        if not selected:
            return
        try:
            include = rows[int(selected[0])].get("included") != "Yes"
        except (ValueError, IndexError):
            return
        self._set_selected_impurity_targets(include)

    def _set_all_impurity_targets(self, include: bool):
        if include:
            self.impurity_exclusions.clear()
        else:
            self.impurity_exclusions = {
                self._impurity_target_key(row): True for row in self._impurity_rows()
            }
        self._refresh_impurity_previews()

    def _copy_selected_impurity_smiles(self, _event=None):
        rows = self._impurity_rows()
        values = []
        for iid in self.impurity_analysis_table.selection():
            try:
                values.append(rows[int(iid)].get("smiles", ""))
            except (ValueError, IndexError):
                continue
        return self._copy_text_to_clipboard("\n".join(value for value in values if value), "Impurity SMILES")

    def logw(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def _copy_text_to_clipboard(self, text: object, label: str = "SMILES"):
        value = str(text or "").strip()
        if not value:
            messagebox.showwarning("Nothing to copy", f"No {label} is available for the selected row.")
            return "break"
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()
        self.logw(f"Copied {label} to clipboard: {value}")
        return "break"

    def _selected_tree_value(self, tree: ttk.Treeview, column_index: int) -> str:
        selection = tree.selection()
        if not selection:
            return ""
        values = tree.item(selection[0], "values") or ()
        if column_index >= len(values):
            return ""
        return str(values[column_index] or "")

    def _copy_selected_product_detail_smiles(self, _event=None):
        return self._copy_text_to_clipboard(self._selected_tree_value(self.preview, 5), "Product SMILES")

    @staticmethod
    def _reaction_name_tree_well(tree: ttk.Treeview, well_column: int) -> str:
        selection = tree.selection()
        if not selection:
            return ""
        values = tree.item(selection[0], "values") or ()
        if well_column >= len(values):
            return ""
        return _normalize_well(values[well_column])

    def _load_reaction_name_from_tree(
        self,
        tree: ttk.Treeview,
        *,
        well_column: int,
        name_column: int,
    ) -> None:
        selection = tree.selection()
        if not selection:
            return
        values = tree.item(selection[0], "values") or ()
        if well_column >= len(values):
            return
        well = _normalize_well(values[well_column])
        if not well:
            return
        self.reaction_name_edit_well = well
        name = str(values[name_column] or "") if name_column < len(values) else ""
        self.name_start_var.set(name)

    def _on_product_details_row_select(self, _event=None):
        self._load_reaction_name_from_tree(
            self.preview,
            well_column=1,
            name_column=0,
        )

    @staticmethod
    def _set_tree_reaction_name(
        tree: ttk.Treeview,
        well: str,
        reaction_name: str,
        *,
        well_column: int,
        name_column: int,
    ) -> None:
        target_well = _normalize_well(well)
        for iid in tree.get_children():
            values = list(tree.item(iid, "values") or ())
            if well_column >= len(values) or _normalize_well(values[well_column]) != target_well:
                continue
            while len(values) <= name_column:
                values.append("")
            values[name_column] = reaction_name
            tree.item(iid, values=tuple(values))
            return

    def _store_reaction_name(self, well: str, reaction_name: str) -> None:
        well = _normalize_well(well)
        if not well:
            return
        reaction_name = str(reaction_name or "").strip()
        self.reaction_names[well] = reaction_name
        if well in self.imported_product_details:
            imported = dict(self.imported_product_details.get(well, {}) or {})
            imported["reaction_name"] = reaction_name
            self.imported_product_details[well] = imported
        if hasattr(self, "preview"):
            self._set_tree_reaction_name(
                self.preview,
                well,
                reaction_name,
                well_column=1,
                name_column=0,
            )
        if hasattr(self, "custom_preview"):
            self._set_tree_reaction_name(
                self.custom_preview,
                well,
                reaction_name,
                well_column=0,
                name_column=1,
            )

    def _save_reaction_name_edit(self, _event=None):
        tree, well_column = self._reaction_name_fill_context()
        if tree is None:
            return
        selected_well = self._reaction_name_tree_well(tree, well_column)
        edit_well = _normalize_well(getattr(self, "reaction_name_edit_well", ""))
        if not selected_well or selected_well != edit_well:
            return
        self._store_reaction_name(selected_well, self.name_start_var.get())

    def _reaction_name_fill_context(self):
        active_tab = ""
        if hasattr(self, "inner_nb"):
            try:
                active_tab = str(self.inner_nb.tab("current", "text") or "")
            except tk.TclError:
                active_tab = ""
        if active_tab == "Custom Template" and hasattr(self, "custom_preview"):
            return self.custom_preview, 0
        if hasattr(self, "preview"):
            return self.preview, 1
        return None, 0

    def _edit_selected_product_detail(self, _event=None):
        selection = self.preview.selection()
        if not selection:
            messagebox.showwarning("No product selected", "Select a Product Details row first.")
            return "break"
        values = self.preview.item(selection[0], "values") or ()
        well = _normalize_well(values[1] if len(values) > 1 else "")
        row = next((
            candidate for candidate in self._pyparse_rows()
            if _normalize_well(candidate.get("reaction_well", "")) == well
        ), None)
        if not row:
            messagebox.showwarning(
                "Product unavailable",
                "The selected Product Details row could not be loaded.",
            )
            return "break"
        win = tk.Toplevel(self)
        win.title(f"Edit Product Details - {well}")
        win.transient(self.winfo_toplevel())
        win.geometry("760x430")
        win.resizable(True, False)
        win.grab_set()
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Edit the final generated product. This does not change the building-block charge rules.",
            wraplength=720,
            justify="left",
        ).pack(fill="x", anchor="w")
        smiles_var = tk.StringVar(value=str(row.get("desired product smiles", "") or ""))
        ttk.Label(body, text="Product SMILES").pack(fill="x", anchor="w", pady=(10, 3))
        entry = ttk.Entry(body, textvariable=smiles_var)
        entry.pack(fill="x")
        preview = ttk.Label(body, anchor="center", background="#ffffff", relief="solid")
        preview.pack(fill="both", expand=True, pady=(10, 6))
        detail_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=detail_var, justify="left").pack(fill="x", anchor="w")
        image_ref: Dict[str, ImageTk.PhotoImage] = {}

        def refresh_preview(*_args):
            smiles = smiles_var.get().strip()
            if not smiles:
                preview.configure(image="", text="Paste product SMILES")
                detail_var.set("")
                return
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                preview.configure(image="", text="Invalid product SMILES")
                detail_var.set("")
                return
            canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
            photo = ImageTk.PhotoImage(Draw.MolToImage(mol, size=(700, 220), fitImage=True).convert("RGBA"))
            image_ref["preview"] = photo
            preview.configure(image=photo, text="")
            exact, mw, formula, _mh, _mna, _neg = core.mass_fields(canonical)
            detail_var.set(f"Formula: {formula}   Molecular weight: {mw}   Exact mass: {exact}")

        smiles_var.trace_add("write", refresh_preview)
        refresh_preview()
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 0))

        def save():
            mol = Chem.MolFromSmiles(smiles_var.get().strip())
            if mol is None:
                messagebox.showerror("Invalid product SMILES", "Enter a valid product SMILES.", parent=win)
                return
            canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
            exact, mw, formula, mh, mna, neg = core.mass_fields(canonical)
            imported = dict(self.imported_product_details.get(well, {}) or {})
            imported.update({
                "reaction_well": well,
                "pyparse_well": str(row.get("pyparse_well", "") or ""),
                "reaction_name": str(row.get("reaction_name", "") or f"RXN_{well}"),
                "product_id": str(row.get("product_id", "") or row.get("reaction_name", "") or f"RXN_{well}"),
                "desired product name": str(row.get("desired product name", "") or row.get("reaction_name", "") or f"RXN_{well}"),
                "desired product smiles": canonical,
                "desired product exact mass": exact,
                "desired product mw": mw,
                "desired product formula": formula,
                "desired product mh": mh,
                "desired product mna": mna,
                "desired product negative mass": neg,
                "selectivity products": [canonical],
            })
            for index in range(1, 4):
                for field in ("id", "name", "smiles"):
                    key = f"reactant {index} {field}"
                    imported[key] = str(row.get(key, imported.get(key, "")) or "")
            self.imported_product_details[well] = imported
            self.__dict__.get("product_review_wells", {}).pop(well, None)
            self.product_details_generated = True
            previous = self.__dict__.get("pending_product_identity_rows", {}).pop(well, row)
            changed = self._on_product_structure_changed(previous, canonical)
            self._refresh_product_details_preview(show_products=True)
            self._refresh_pyparse_preview()
            if changed:
                self.logw(f"Edited Product Details for {well}; previous product analytical assignments were cleared. Regenerate LCMS input and rerun analysis for this product. Sample comments were retained.")
            else:
                self.logw(f"Saved Product Details for {well}; the structure and analytical associations are unchanged.")
            win.destroy()

        ttk.Button(actions, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(actions, text="Save Product", command=save, style="ChemAction.TButton").pack(side="right", padx=(0, 8))
        entry.focus_set()
        self.wait_window(win)
        return "break"

    def analysis_context_signature(self):
        """Immutable target/mapping identity for accepting background results."""
        rows = [dict(row, _lcms_target=self._lcms_target_for_row(row)) for row in self._pyparse_rows()]
        payload = {
            "rows": rows,
            "pushed_rows": list(self.pushed_rows.values()),
            "impurity_exclusions": self.impurity_exclusions,
            "carried_impurity_sources": self.carried_impurity_sources,
        }
        return json.dumps(payload, sort_keys=True, default=str)

    def _analysis_is_invalidated(self, row, source):
        self._sync_building_block_identity()
        if self._product_regeneration_waiting(row):
            return True
        well = _normalize_well(row.get("reaction_well", ""))
        return source in self.__dict__.get("invalidated_product_analysis", {}).get(well, [])

    def _stage_product_regeneration(self):
        """Remember resolved products before controls hide or change them."""
        pending = self.__dict__.setdefault("pending_product_identity_rows", {})
        for well, row in self.__dict__.get("_last_product_identity_rows", {}).items():
            if row.get("desired product smiles"):
                pending.setdefault(well, dict(row))

    def _product_regeneration_waiting(self, row):
        previous = self.__dict__.get("pending_product_identity_rows", {}).get(
            _normalize_well(row.get("reaction_well", "")))
        return previous is not None and (
            _canonical_smiles_key(previous.get("desired product smiles", ""))
            != _canonical_smiles_key(row.get("desired product smiles", "")))

    def _complete_product_regeneration(self, rows):
        current = {_normalize_well(row.get("reaction_well", "")): row for row in rows}
        previous = self.__dict__.get("pending_product_identity_rows", {})
        self.pending_product_identity_rows = {}
        for well, row in previous.items():
            self._on_product_structure_changed(row, current.get(well, {}).get("desired product smiles", ""))

    def _clear_product_manual_assignment(self, row):
        well = _normalize_well(row.get("pyparse_well", ""))
        overrides = self.__dict__.get("product_peak_overrides", {})
        for target, values in list(overrides.items()):
            values.pop(well, None)
            if not values:
                overrides.pop(target, None)
        key = self._product_structure_manual_key(row)
        if self.__dict__.get("product_structure_current_manual_key") == key:
            self._save_current_product_structure_manual_fields()
            self.product_structure_manual_purity_var.set("")
        self.__dict__.get("product_structure_manual_notes", {}).get(key, {}).pop("manual_purity", None)
        self.__dict__.get("product_structure_uv_source_by_key", {}).pop(key, None)
        self._peak_preview_cache = {}
        self.__dict__.get("product_structure_trace_images", {}).clear()

    def _invalidate_product_analysis(self, row, *, preserve_automatic_evidence=False):
        """Detach product-specific results, retaining sample data and comments."""
        reaction_well = _normalize_well(row.get("reaction_well", ""))
        well = _normalize_well(row.get("pyparse_well", ""))
        if not any(self.__dict__.get(name) for name in (
            "pyparse_result_dir", "modified_pyparse_result_dir", "pyparse_purity_by_well",
            "modified_pyparse_purity_by_product", "portable_trace_paths", "peak_inspection_data",
            "product_structure_manual_notes",
        )):
            return
        self.__dict__.setdefault("invalidated_product_analysis", {})[reaction_well] = ["pyparse", "modified"]
        self._clear_product_manual_assignment(row)
        if preserve_automatic_evidence:
            return
        for name in ("pyparse_purity_by_well", "modified_pyparse_purity_by_well"):
            self.__dict__.get(name, {}).pop(well, None)
        for name in ("modified_pyparse_purity_by_product", "modified_pyparse_conflicts_by_product", "product_peak_overrides"):
            table = self.__dict__.get(name, {})
            for target, wells in list(table.items()):
                wells.pop(well, None)
                if not wells:
                    table.pop(target, None)
        # Numerical chromatograms remain available as sample evidence, but old
        # product assignments must not reactivate if a structure is edited back.
        targets = self.__dict__.get("peak_inspection_data", {}).get("targets", {})
        for target, wells in list(targets.items()):
            wells.pop(well, None)
            if not wells:
                targets.pop(target, None)
        traces = self.__dict__.get("portable_trace_paths", {}).get(well, {})
        for name in ("pyparse_uv", "modified_uv", "modified_es"):
            traces.pop(name, None)

    def _on_product_structure_changed(self, row, smiles):
        if _canonical_smiles_key(row.get("desired product smiles", "")) == _canonical_smiles_key(smiles):
            return False
        self._invalidate_product_analysis(row)
        well = _normalize_well(row.get("reaction_well", ""))
        self.lcms_target_smiles_by_well.pop(well, None)
        self.lcms_target_summaries_by_well.pop(well, None)
        return True

    def _peak_context(self, row):
        target, label, record, well, override = super()._peak_context(row)
        if self._analysis_is_invalidated(row, "modified"):
            return target, label, None, well, None
        return target, label, record, well, override

    def _accept_fresh_analysis(self, source, values):
        invalid = self.__dict__.get("invalidated_product_analysis", {})
        if not invalid:
            return
        for row in self._pyparse_rows():
            well = _normalize_well(row.get("pyparse_well", ""))
            reaction_well = _normalize_well(row.get("reaction_well", ""))
            if well not in values:
                continue
            if source == "modified":
                target = _canonical_smiles_key(self._lcms_target_for_row(row))
                if well not in self.modified_pyparse_purity_by_product.get(target, {}):
                    continue
            sources = invalid.get(reaction_well, [])
            if source in sources:
                sources.remove(source)
            if not sources:
                invalid.pop(reaction_well, None)

    def _copy_selected_pyparse_product_smiles(self, _event=None):
        return self._copy_text_to_clipboard(self._selected_tree_value(self.pyparse_preview, 4), "Desired product SMILES")

    def _copy_selected_custom_product_smiles(self, _event=None):
        return self._copy_text_to_clipboard(self._selected_tree_value(self.custom_preview, 5), "Custom product SMILES")

    def _copy_current_product_structure_smiles(self, _event=None):
        return self._copy_text_to_clipboard(self.product_structure_current_smiles, "Product SMILES")

    def _ensure_product_structure_uv_source(self):
        if self.product_structure_uv_source_var.get() not in {"pyparse", "modified", "manual"}:
            self.product_structure_uv_source_var.set("modified")

    def _set_current_product_structure_uv_source(self):
        self._ensure_product_structure_uv_source()
        row = self._selected_product_structure_row()
        if not row:
            return
        key = self._product_structure_manual_key(row)
        if not key:
            return
        source = self.product_structure_uv_source_var.get()
        if source == "modified":
            self.product_structure_uv_source_by_key.pop(key, None)
        else:
            self.product_structure_uv_source_by_key[key] = source

    def _product_structure_uv_source_for_row(self, row: Optional[Dict[str, object]]) -> str:
        key = self._product_structure_manual_key(row)
        source = self.product_structure_uv_source_by_key.get(key, "") if key else ""
        return source if source in {"pyparse", "modified", "manual"} else "modified"

    def _sync_product_structure_uv_source_for_row(self, row: Optional[Dict[str, object]] = None):
        self.product_structure_uv_source_var.set(self._product_structure_uv_source_for_row(row))

    def _product_structure_uv_source_label(self, source: Optional[str] = None) -> str:
        source = source or self.product_structure_uv_source_var.get()
        if source == "pyparse":
            return "UV254 purity from PyParse"
        if source == "manual":
            return "Purity by manual"
        return "UV254 purity from Modified PyParse"

    def _product_structure_purity_for_row(self, row: Dict[str, object], source: Optional[str] = None) -> str:
        self._sync_building_block_identity()
        if self._product_regeneration_waiting(row):
            return ""
        source = source or self._product_structure_uv_source_for_row(row)
        lcms_well = _normalize_well(row.get("pyparse_well", ""))
        if source == "pyparse":
            if self._analysis_is_invalidated(row, "pyparse"):
                return ""
            return self.pyparse_purity_by_well.get(lcms_well, "") if lcms_well else ""
        if source == "manual":
            manual_values = self.product_structure_manual_notes.get(self._product_structure_manual_key(row), {})
            return str(manual_values.get("manual_purity", "") or "").strip()
        return self._modified_pyparse_purity_for_row(row)

    def _product_results_export_rows(self) -> List[Dict[str, str]]:
        source_names = {
            "pyparse": "PyParse",
            "modified": "Modified PyParse",
            "manual": "Manual",
        }
        export_rows = []
        for row in self._pyparse_rows():
            product_smiles = str(row.get("desired product smiles", "") or "").strip()
            if not product_smiles:
                continue
            source = self._product_structure_uv_source_for_row(row)
            export_rows.append({
                "Reaction Number": str(row.get("reaction_name", "") or ""),
                "Reaction Well": str(row.get("reaction_well", "") or ""),
                "LCMS Well": str(row.get("pyparse_well", "") or ""),
                "Exact Mass": str(row.get("desired product exact mass", "") or ""),
                "Molecular Weight": str(row.get("desired product mw", "") or ""),
                "Molecular Formula": str(row.get("desired product formula", "") or ""),
                "Product SMILES": product_smiles,
                "UV254 Purity": self._product_structure_purity_for_row(row, source),
                "UV254 Purity Source": source_names[source] + (
                    f" — {self._peak_assignment_description(row)}"
                    if source == "modified" and self._peak_override_purity(row) is not None else ""
                ),
            })
        return export_rows

    def _export_product_results_csv(self):
        self._save_current_product_structure_manual_fields()
        rows = self._product_results_export_rows()
        if not rows:
            messagebox.showwarning(
                "No product results",
                "No product results are available. Generate or input Product Details first.",
            )
            return
        output = filedialog.asksaveasfilename(
            title="Export Product Results CSV",
            defaultextension=".csv",
            initialdir=str(OUTPUT_DIR),
            initialfile="product_results.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not output:
            return
        path = Path(output)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        except Exception as exc:
            messagebox.showerror("Export CSV failed", str(exc))
            return
        self.logw(f"Exported {len(rows)} product result(s): {path}")
        messagebox.showinfo(
            "Product Results Exported",
            f"Exported {len(rows)} product result(s):\n{path}",
        )

    def _modified_pyparse_purity_for_row(self, row: Dict[str, object]) -> str:
        if self._analysis_is_invalidated(row, "modified"):
            return ""
        if getattr(self, "product_peak_overrides", {}):
            override = self._peak_override_purity(row)
            if override is not None:
                return override
        well = _normalize_well(row.get("pyparse_well", ""))
        smiles_key = _canonical_smiles_key(self._lcms_target_for_row(row))
        if not well or not smiles_key:
            return ""
        return self.modified_pyparse_purity_by_product.get(smiles_key, {}).get(well, "")

    def _modified_pyparse_conflict_for_row(self, row: Dict[str, object]) -> str:
        if self._analysis_is_invalidated(row, "modified"):
            return ""
        well = _normalize_well(row.get("pyparse_well", ""))
        smiles_key = _canonical_smiles_key(self._lcms_target_for_row(row))
        if not well or not smiles_key:
            return ""
        conflicts = getattr(self, "modified_pyparse_conflicts_by_product", {}) or {}
        return conflicts.get(smiles_key, {}).get(well, "")

    def _modified_pyparse_purity_display_for_row(self, row: Dict[str, object]) -> str:
        if self._analysis_is_invalidated(row, "modified"):
            return "Reanalysis required (product/target edited)"
        purity = self._modified_pyparse_purity_for_row(row)
        if getattr(self, "product_peak_overrides", {}) and self._peak_override_purity(row) is not None:
            return f"{purity} — {self._peak_assignment_description(row)}"
        if (
            _blank_or_zero(purity)
            and self._modified_pyparse_conflict_for_row(row) == PRODUCT_REACTANT_MASS_CONFLICT
        ):
            return "0% ⚠ Product/reactant mass conflict"
        return purity

    def _generate_product_structure_heat_maps(self):
        try:
            mode = reaction_mode(self.pushed_rows.values())
        except ValueError as exc:
            messagebox.showwarning("Reaction layout", str(exc), parent=self)
            return
        valid_reaction_wells = {well for row in heatmap_layout(mode)[2] for well in row}
        self._save_current_product_structure_manual_fields()
        self._ensure_product_structure_uv_source()
        source_label = "selected per-well purity source"
        reaction_values: Dict[str, str] = {}
        lcms_values: Dict[str, str] = {}
        reaction_tooltips: Dict[str, str] = {}
        lcms_tooltips: Dict[str, str] = {}
        reaction_keys: Dict[str, str] = {}
        lcms_keys: Dict[str, str] = {}
        for row in self._pyparse_rows():
            purity = self._product_structure_purity_for_row(row)
            if _numeric_percent_value(purity) is None:
                continue
            reaction_name = str(row.get("reaction_name", "") or "").strip() or "No reaction number"
            reaction_well = _normalize_well(row.get("reaction_well", ""))
            lcms_well = _normalize_well(row.get("pyparse_well", ""))
            key = self._product_structure_manual_key(row)
            if reaction_well in valid_reaction_wells:
                reaction_values[reaction_well] = purity
                reaction_tooltips[reaction_well] = reaction_name
                if key:
                    reaction_keys[reaction_well] = key
            if re.match(r"^[A-H](?:[1-9]|1[0-2])$", lcms_well):
                lcms_values[lcms_well] = purity
                lcms_tooltips[lcms_well] = reaction_name
                if key:
                    lcms_keys[lcms_well] = key

        if not reaction_values and not lcms_values:
            messagebox.showwarning("No purity values", f"No numeric {source_label} values are available for heat maps.")
            return

        win = tk.Toplevel(self)
        heatmap_title = f"Product Summary Heat Maps - {source_label}"
        win.title(heatmap_title)
        win.geometry("1280x470")
        win.minsize(720, 420)
        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        tools = ttk.Frame(body)
        tools.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        tools.grid_columnconfigure(0, weight=1)

        def sync_heatmap_pin():
            pinned = bool(self.product_structure_heatmap_pin_var.get())
            try:
                win.attributes("-topmost", pinned)
                win.title(f"{heatmap_title} - Pinned" if pinned else heatmap_title)
                if pinned:
                    win.lift()
            except tk.TclError:
                pass

        ttk.Button(tools, text="Apply to List", command=self._apply_product_structure_heatmap_colors_to_list).grid(
            row=0,
            column=1,
            sticky="e",
        )
        ttk.Checkbutton(
            tools,
            text="Pin",
            variable=self.product_structure_heatmap_pin_var,
            command=sync_heatmap_pin,
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        reaction_box = ttk.LabelFrame(body, text="Reaction well heat map", padding=8)
        reaction_box.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        lcms_box = ttk.LabelFrame(body, text="LCMS well heat map", padding=8)
        lcms_box.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

        hit_summaries = {
            key: self._biology_hit_summary_for_key(key)
            for key in set(reaction_keys.values()) | set(lcms_keys.values())
            if self._biology_hits_for_key(key)
        }
        self.product_structure_heatmap_canvases = [
            canvas
            for canvas in self.product_structure_heatmap_canvases
            if canvas.winfo_exists()
        ]
        reaction_canvas = PurityHeatMapCanvas(
            reaction_box,
            f"Reaction well ({mode}) - {source_label}",
            reaction_values,
            reaction_tooltips,
            mode=mode,
            key_by_well=reaction_keys,
            hit_summary_by_key=hit_summaries,
            hit_callback=self._open_biology_hit_dialog,
            clear_hit_callback=lambda key: self._set_biology_hits_for_key(key, []),
        )
        reaction_canvas.pack(fill="both", expand=True)
        lcms_canvas = PurityHeatMapCanvas(
            lcms_box,
            f"LCMS well - {source_label}",
            lcms_values,
            lcms_tooltips,
            key_by_well=lcms_keys,
            hit_summary_by_key=hit_summaries,
            hit_callback=self._open_biology_hit_dialog,
            clear_hit_callback=lambda key: self._set_biology_hits_for_key(key, []),
        )
        lcms_canvas.pack(fill="both", expand=True)
        self.product_structure_heatmap_canvases.extend([reaction_canvas, lcms_canvas])
        sync_heatmap_pin()
        self.logw(f"Generated Product Summary heat maps using {source_label}.")

    def _apply_product_structure_heatmap_colors_to_list(self):
        self._save_current_product_structure_manual_fields()
        values: List[Tuple[str, float]] = []
        for row in self._pyparse_rows():
            key = self._product_structure_manual_key(row)
            if not key:
                continue
            pct = _numeric_percent_value(self._product_structure_purity_for_row(row))
            if pct is not None:
                values.append((key, pct))
        if not values:
            messagebox.showwarning("No purity values", "No numeric purity values are available to apply to the Products list.")
            return

        numeric_values = [pct for _, pct in values]
        min_value = min(numeric_values)
        max_value = max(numeric_values)
        if max_value <= min_value:
            max_value = min_value + 1.0
        for key, pct in values:
            self.product_structure_row_colors[key] = PurityHeatMapCanvas._color_for_percent(pct, min_value, max_value)
        self._refresh_product_structure_preview(reset_selection=False)
        self.logw(f"Applied heat map colors to {len(values)} Product Summary row(s).")

    def _product_structure_manual_key(self, row: Optional[Dict[str, object]]) -> str:
        if not row:
            return ""
        lcms_well = _normalize_well(row.get("pyparse_well", ""))
        if lcms_well:
            return f"lcms:{lcms_well}"
        rxn_well = _normalize_well(row.get("reaction_well", ""))
        if rxn_well:
            return f"rxn:{rxn_well}"
        reaction_name = str(row.get("reaction_name", "") or "").strip()
        return f"name:{reaction_name}" if reaction_name else ""

    def _product_structure_row_color(self, row: Optional[Dict[str, object]]) -> str:
        key = self._product_structure_manual_key(row)
        if not key:
            return ""
        color = str(self.product_structure_row_colors.get(key, "") or "").strip().lower()
        if color in PRODUCT_SUMMARY_ROW_COLORS or _is_hex_color(color):
            return color
        return ""

    def _product_structure_row_color_tag(self, color: str) -> str:
        color = str(color or "").strip().lower()
        if not color:
            return ""
        if color in PRODUCT_SUMMARY_ROW_COLORS:
            tag = f"rowcolor_{color}"
            self.product_structure_table.tag_configure(tag, background=PRODUCT_SUMMARY_ROW_COLORS[color])
            return tag
        if _is_hex_color(color):
            tag = f"rowcolor_hex_{color.lstrip('#')}"
            self.product_structure_table.tag_configure(tag, background=color)
            return tag
        return ""

    def _set_product_structure_row_color(self, iid: str, color: str):
        rows = self._pyparse_rows()
        try:
            idx = int(iid)
        except Exception:
            return
        if not (0 <= idx < len(rows)):
            return
        key = self._product_structure_manual_key(rows[idx])
        if not key:
            return
        color = str(color or "").strip().lower()
        if color in PRODUCT_SUMMARY_ROW_COLORS:
            self.product_structure_row_colors[key] = color
        else:
            self.product_structure_row_colors.pop(key, None)
        self._refresh_product_structure_preview(reset_selection=False)

    def _biology_hits_for_key(self, key: str) -> List[str]:
        return [
            str(value).strip()
            for value in self.product_structure_biology_hits.get(str(key or ""), []) or []
            if str(value).strip()
        ]

    def _biology_hit_summary_for_key(self, key: str) -> str:
        hits = self._biology_hits_for_key(key)
        return ", ".join(hits)

    def _biology_hit_summary_for_row(self, row: Optional[Dict[str, object]]) -> str:
        return self._biology_hit_summary_for_key(self._product_structure_manual_key(row))

    def _set_biology_hits_for_key(self, key: str, assays: List[str]):
        key = str(key or "")
        if not key:
            return
        cleaned: List[str] = []
        seen = set()
        for assay in assays:
            value = str(assay or "").strip()
            if not value:
                continue
            dedupe_key = value.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cleaned.append(value)
        if cleaned:
            self.product_structure_biology_hits[key] = cleaned
        else:
            self.product_structure_biology_hits.pop(key, None)
        self._refresh_product_structure_preview(reset_selection=False)
        self._refresh_product_structure_heatmap_hit_marks()
        row = self._selected_product_structure_row()
        if row:
            self._on_product_structure_select()

    def _refresh_product_structure_heatmap_hit_marks(self):
        canvases = []
        for canvas in getattr(self, "product_structure_heatmap_canvases", []):
            try:
                if not canvas.winfo_exists():
                    continue
                keys = set(canvas.key_by_well.values())
                canvas.update_hit_summaries({
                    key: self._biology_hit_summary_for_key(key)
                    for key in keys
                    if self._biology_hits_for_key(key)
                })
                canvases.append(canvas)
            except tk.TclError:
                continue
        self.product_structure_heatmap_canvases = canvases

    def _biology_hit_dialog_presets(self) -> List[str]:
        return ["SPR", "ASMS", "Cell", "Protein thermal shift", "Biochemical", "NanoDSF"]

    def _biology_hit_detail_for_row(self, row: Optional[Dict[str, object]]) -> str:
        if not row:
            return "No product selected"
        hits = self._biology_hit_summary_for_row(row) or "None marked"
        return (
            f"RXN number: {row.get('reaction_name', '') or 'N/A'}\n"
            f"RXN well: {row.get('reaction_well', '') or 'N/A'}   "
            f"LCMS well: {row.get('pyparse_well', '') or 'N/A'}\n"
            f"Active assays: {hits}"
        )

    def _sync_biology_hit_dialog_pin(self):
        window = self.product_structure_biology_hit_window
        if window is None:
            return
        pinned = bool(self.product_structure_biology_hit_pin_var.get())
        try:
            window.attributes("-topmost", pinned)
            window.title(f"{self.product_structure_biology_hit_title} - Pinned" if pinned else self.product_structure_biology_hit_title)
            if pinned:
                window.lift()
        except tk.TclError:
            pass

    def _load_biology_hit_dialog(self, key: str, title: str, row: Optional[Dict[str, object]] = None):
        key = str(key or "")
        if not key:
            return
        self.product_structure_biology_hit_key = key
        self.product_structure_biology_hit_title = title or "Biology assay hit"
        existing = set(value.lower() for value in self._biology_hits_for_key(key))
        presets = self._biology_hit_dialog_presets()
        preset_lookup = {assay.lower() for assay in presets}
        for assay, var in self.product_structure_biology_hit_vars.items():
            var.set(assay.lower() in existing)
        other_existing = ", ".join(value for value in self._biology_hits_for_key(key) if value.lower() not in preset_lookup)
        self.product_structure_biology_hit_other_var.set(other_existing)
        if row is None:
            row = self._selected_product_structure_row()
        self.product_structure_biology_hit_detail_var.set(self._biology_hit_detail_for_row(row))
        self._sync_biology_hit_dialog_pin()

    def _sync_biology_hit_dialog_to_row(self, row: Optional[Dict[str, object]]):
        window = self.product_structure_biology_hit_window
        if window is None:
            return
        try:
            if not window.winfo_exists():
                self.product_structure_biology_hit_window = None
                return
        except tk.TclError:
            self.product_structure_biology_hit_window = None
            return
        key = self._product_structure_manual_key(row)
        if not key:
            self.product_structure_biology_hit_key = ""
            self.product_structure_biology_hit_title = "Biology assay hit"
            for var in self.product_structure_biology_hit_vars.values():
                var.set(False)
            self.product_structure_biology_hit_other_var.set("")
            self.product_structure_biology_hit_detail_var.set(self._biology_hit_detail_for_row(row))
            self._sync_biology_hit_dialog_pin()
            return
        label = str((row or {}).get("reaction_name", "") or (row or {}).get("reaction_well", "") or (row or {}).get("pyparse_well", "") or "selected product")
        self._load_biology_hit_dialog(key, f"Biology assay hit - {label}", row)

    def _open_biology_hit_dialog(self, key: str, title: str = "Biology assay hit"):
        key = str(key or "")
        if not key:
            return
        row = self._selected_product_structure_row()
        window = self.product_structure_biology_hit_window
        if window is not None:
            try:
                if window.winfo_exists():
                    self._load_biology_hit_dialog(key, title, row)
                    window.lift()
                    window.focus_force()
                    return
            except tk.TclError:
                pass

        presets = self._biology_hit_dialog_presets()
        win = tk.Toplevel(self)
        self.product_structure_biology_hit_window = win
        win.title(title)
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)

        def close_window():
            self.product_structure_biology_hit_window = None
            try:
                win.attributes("-topmost", False)
                win.destroy()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", close_window)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Select biology assay for this hit:").grid(row=0, column=0, sticky="w")

        ttk.Checkbutton(
            header,
            text="Pin",
            variable=self.product_structure_biology_hit_pin_var,
            command=self._sync_biology_hit_dialog_pin,
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            body,
            textvariable=self.product_structure_biology_hit_detail_var,
            style="Muted.TLabel",
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 6))
        vars_by_assay: Dict[str, tk.BooleanVar] = {}
        for i, assay in enumerate(presets, start=2):
            var = tk.BooleanVar(value=False)
            vars_by_assay[assay] = var
            ttk.Checkbutton(body, text=assay, variable=var).grid(row=i, column=0, columnspan=2, sticky="w", pady=1)
        self.product_structure_biology_hit_vars = vars_by_assay
        ttk.Label(body, text="Other:").grid(row=len(presets) + 2, column=0, sticky="w", pady=(6, 0))
        other_entry = ttk.Entry(body, textvariable=self.product_structure_biology_hit_other_var, width=28)
        other_entry.grid(row=len(presets) + 2, column=1, sticky="ew", pady=(6, 0))
        body.grid_columnconfigure(1, weight=1)

        def save():
            current_key = self.product_structure_biology_hit_key
            if not current_key:
                return
            assays = [assay for assay, var in self.product_structure_biology_hit_vars.items() if var.get()]
            other = self.product_structure_biology_hit_other_var.get().strip()
            if other:
                assays.append(other)
            if not assays:
                messagebox.showwarning("No assay selected", "Select at least one biology assay, or use Remove hit.")
                return
            self._set_biology_hits_for_key(current_key, assays)
            self._sync_biology_hit_dialog_to_row(self._selected_product_structure_row())

        def remove():
            current_key = self.product_structure_biology_hit_key
            if current_key:
                self._set_biology_hits_for_key(current_key, [])
                self._sync_biology_hit_dialog_to_row(self._selected_product_structure_row())

        btns = ttk.Frame(body)
        btns.grid(row=len(presets) + 3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Remove hit", command=remove).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Close", command=close_window).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Save hit", command=save, style="Accent.TButton").pack(side="left")
        self._load_biology_hit_dialog(key, title, row)
        other_entry.focus_set()
        win.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + max(40, (parent.winfo_width() - win.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(40, (parent.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{x}+{y}")
        self._sync_biology_hit_dialog_pin()

    def _mark_product_structure_iid_as_biology_hit(self, iid: str):
        rows = self._pyparse_rows()
        try:
            idx = int(iid)
        except Exception:
            return
        if not (0 <= idx < len(rows)):
            return
        row = rows[idx]
        key = self._product_structure_manual_key(row)
        if not key:
            return
        label = str(row.get("reaction_name", "") or row.get("reaction_well", "") or row.get("pyparse_well", "") or "selected product")
        self._open_biology_hit_dialog(key, f"Biology assay hit - {label}")

    def _show_product_structure_color_menu(self, event):
        if not hasattr(self, "product_structure_table"):
            return "break"
        iid = self.product_structure_table.identify_row(event.y)
        if not iid:
            return "break"
        self.product_structure_table.selection_set(iid)
        self.product_structure_table.focus(iid)
        self._on_product_structure_select()
        menu = tk.Menu(self.product_structure_table, tearoff=False)
        key = self._product_structure_manual_key(self._selected_product_structure_row())
        if self._biology_hits_for_key(key):
            menu.add_command(label="Edit assay hit", command=lambda item=iid: self._mark_product_structure_iid_as_biology_hit(item))
            menu.add_command(label="Clear assay hit", command=lambda k=key: self._set_biology_hits_for_key(k, []))
        else:
            menu.add_command(label="Mark assay hit", command=lambda item=iid: self._mark_product_structure_iid_as_biology_hit(item))
        menu.add_separator()
        for label, color in [("Green", "green"), ("Yellow", "yellow"), ("Red", "red"), ("Blue", "blue")]:
            menu.add_command(label=label, command=lambda c=color, item=iid: self._set_product_structure_row_color(item, c))
        menu.add_separator()
        menu.add_command(label="Clear color", command=lambda item=iid: self._set_product_structure_row_color(item, ""))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _product_structure_comment_widget(self) -> Optional[tk.Text]:
        float_widget = getattr(self, "product_structure_float_manual_comment_text", None)
        if float_widget is not None:
            try:
                if float_widget.winfo_exists():
                    return float_widget
            except tk.TclError:
                pass
        widget = getattr(self, "product_structure_manual_comment_text", None)
        if widget is not None:
            try:
                if widget.winfo_exists():
                    return widget
            except tk.TclError:
                pass
        return None

    def _set_product_structure_comment_text(self, text: str):
        for attr in ("product_structure_manual_comment_text", "product_structure_float_manual_comment_text"):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                if not widget.winfo_exists():
                    continue
                widget.delete("1.0", "end")
                if text:
                    widget.insert("1.0", text)
            except tk.TclError:
                continue

    def _save_current_product_structure_manual_fields(self, _event=None):
        key = self.product_structure_current_manual_key
        if not key:
            return
        comment_widget = self._product_structure_comment_widget()
        comment = ""
        if comment_widget is not None:
            try:
                comment = comment_widget.get("1.0", "end-1c").strip()
            except tk.TclError:
                comment = ""
        purity = self.product_structure_manual_purity_var.get().strip()
        if purity or comment:
            self.product_structure_manual_notes[key] = {
                "manual_purity": purity,
                "comments": comment,
            }
        else:
            self.product_structure_manual_notes.pop(key, None)

    def _load_product_structure_manual_fields(self, row: Optional[Dict[str, object]]):
        key = self._product_structure_manual_key(row)
        self.product_structure_current_manual_key = key
        values = self.product_structure_manual_notes.get(key, {}) if key else {}
        self.product_structure_manual_purity_var.set(str(values.get("manual_purity", "") or ""))
        self._set_product_structure_comment_text(str(values.get("comments", "") or ""))

    def _pick_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=str(OUTPUT_DIR), filetypes=[("CSV", "*.csv")])
        if p:
            self.output_var.set(p)

    def _pick_custom_output_dir(self):
        p = filedialog.askdirectory(title="Select custom product CSV output folder", initialdir=str(OUTPUT_DIR))
        if p:
            self.custom_output_dir_var.set(p)

    def _reaction(self) -> Dict[str, str]:
        label = self.reaction_var.get()
        reaction = next((r for r in self.reactions if r["label"] == label), None)
        if reaction is None:
            raise ValueError("Select a reaction type before generating Product Details.")
        return reaction

    def _on_reaction_type_selected(self, _event=None):
        self._stage_product_regeneration()
        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        if hasattr(self, "pyparse_preview"):
            self._refresh_pyparse_preview()

    def _compound_index(self):
        by_id = {}
        by_name = {}
        for rec in self.compound_provider():
            vals = _record_values(rec)
            cid = (vals.get("ID") or "").strip()
            name = (vals.get("Name") or "").strip()
            if cid:
                by_id[cid.lower()] = vals
            if name:
                by_name[name.lower()] = vals
        return by_id, by_name

    def _building_block_identities(self):
        """Resolve identities from Compound Notes, including edits under the same ID."""
        identities = {}
        by_id, by_name = self._compound_index()
        canonical_smiles = {}
        for row in self.__dict__.get("pushed_rows", {}).values():
            if not coerce_bool(row.get("is_building_block", False)):
                continue
            well = _normalize_well(row.get("well", ""))
            chemical = str(row.get("chemical", "") or "")
            key = chemical.strip().lower()
            compound = by_id.get(key) or by_name.get(key) or {}
            smiles = str(compound.get("SMILES", "") or "")
            if smiles not in canonical_smiles:
                canonical_smiles[smiles] = _canonical_smiles_key(smiles)
            identity = (
                str(compound.get("ID") or row.get("chemical_id") or chemical).strip().casefold(),
                canonical_smiles[smiles],
            )
            identities.setdefault(well, set()).add(identity)
        return {well: sorted(values) for well, values in identities.items()}

    def _sync_building_block_identity(self):
        """Detach old assignments before readers expose a changed reaction identity."""
        if self.__dict__.get("_syncing_building_block_identity"):
            return
        retained = self.__dict__.get("retained_results_var")
        if retained is not None and retained.get():
            return  # These are an intentional snapshot of the previous inputs.
        if "compound_provider" not in self.__dict__:
            return
        current = self._building_block_identities()
        previous = self.__dict__.get("building_block_identity_by_well")
        self.building_block_identity_by_well = current
        if previous is None:
            return
        previous = {well: [tuple(item) for item in values] for well, values in previous.items()}
        changed = {well for well in previous.keys() | current.keys()
                   if previous.get(well) != current.get(well)}
        if not changed:
            return
        self._syncing_building_block_identity = True
        try:
            prior_rows = self.__dict__.get("_last_product_identity_rows", {})
            review = self.__dict__.setdefault("product_review_wells", {})
            for well in changed:
                row = prior_rows.get(well)
                if row is not None:
                    self._invalidate_product_analysis(row)
                self.custom_products.pop(well, None)
                self.custom_failures.pop(well, None)
                self.lcms_target_smiles_by_well.pop(well, None)
                self.lcms_target_summaries_by_well.pop(well, None)
                if well in self.imported_product_details:
                    review[well] = "Review Product Details: building blocks changed"
            if prior_rows:
                self.logw("Building-block structures changed; review/regenerate affected products and reanalyze: "
                          + ", ".join(sorted(changed)))
        finally:
            self._syncing_building_block_identity = False

    @staticmethod
    def _building_block_ion_key(compound: Dict[str, object]) -> str:
        compound_id = str(compound.get("ID", "") or "").strip()
        smiles = str(compound.get("SMILES", "") or "").strip()
        try:
            canonical = ion_handling.analyze_smiles(smiles)["canonical_smiles"]
        except Exception:
            canonical = smiles
        return f"{compound_id.casefold()}|{canonical}"

    def _charged_building_blocks(self) -> List[Dict[str, object]]:
        unique: Dict[str, Dict[str, object]] = {}
        for pushed in self.pushed_rows.values():
            if not coerce_bool(pushed.get("is_building_block", False)):
                continue
            compound = self._resolve_compound(str(pushed.get("chemical", "") or ""))
            if not compound or not str(compound.get("SMILES", "") or "").strip():
                continue
            try:
                analysis = ion_handling.analyze_smiles(compound.get("SMILES", ""))
            except Exception:
                continue
            if not analysis.get("charged"):
                continue
            key = self._building_block_ion_key(compound)
            unique.setdefault(key, {
                "key": key,
                "compound": dict(compound),
                "analysis": analysis,
            })
        return sorted(
            unique.values(),
            key=lambda item: str((item.get("compound", {}) or {}).get("ID", "") or "").casefold(),
        )

    @staticmethod
    def _charge_site_preview_photo(parent, analysis: Dict[str, object], size=(520, 220)):
        mol = Chem.Mol(parent)
        for number, site in enumerate(analysis.get("sites", []) or [], start=1):
            atom = mol.GetAtomWithIdx(int(site["atom_index"]))
            atom.SetProp("atomNote", str(number))
        image = Draw.MolToImage(mol, size=size, fitImage=True).convert("RGBA")
        return ImageTk.PhotoImage(image)

    @staticmethod
    def _ion_rule_is_complete(analysis: Dict[str, object], rule: Optional[Dict[str, object]]) -> bool:
        if not isinstance(rule, dict):
            return False
        if str(rule.get("counterion_action", "")) not in {"keep", "remove"}:
            return False
        actions = dict(rule.get("site_actions", {}) or {})
        for site in analysis.get("sites", []) or []:
            action = str(actions.get(str(site["atom_index"]), ""))
            if action not in {"keep", "neutralize"}:
                return False
            if site.get("permanent") and action != "keep":
                return False
        return True

    def _ask_building_block_ion_rule(
        self,
        item: Dict[str, object],
        initial_rule: Optional[Dict[str, object]] = None,
    ) -> Optional[Tuple[Dict[str, object], bool]]:
        analysis = dict(item.get("analysis", {}) or {})
        compound = dict(item.get("compound", {}) or {})
        rule = dict(initial_rule or ion_handling.default_rule(analysis))
        rule["site_actions"] = dict(rule.get("site_actions", {}) or {})
        win = tk.Toplevel(self)
        win.title("Charged Building Block Review")
        win.transient(self.winfo_toplevel())
        win.geometry("760x650")
        win.minsize(700, 560)
        win.grab_set()
        result: Dict[str, object] = {"value": None}
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                f"Building block: {compound.get('ID', '') or compound.get('Name', '') or 'Unnamed'}\n"
                "Assign every charged site before XinPilot generates products. Charge removal means proton-only "
                "neutralization; atoms and connectivity are retained."
            ),
            justify="left",
            wraplength=720,
        ).pack(fill="x", anchor="w")
        parent = Chem.MolFromSmiles(str(analysis.get("parent_smiles", "") or ""))
        preview = ttk.Label(body, anchor="center", background="#ffffff", relief="solid")
        preview.pack(fill="x", pady=(10, 8))
        preview_photo = self._charge_site_preview_photo(parent, analysis)
        preview.configure(image=preview_photo)
        preview.image = preview_photo
        ttk.Label(
            body,
            text=f"As entered: {analysis.get('canonical_smiles', '')}",
            wraplength=720,
            justify="left",
        ).pack(fill="x", anchor="w")

        counterion_box = ttk.LabelFrame(body, text="Counterion", padding=8)
        counterion_box.pack(fill="x", pady=(10, 6))
        counterion_var = tk.StringVar(
            value=str(rule.get("counterion", "") or analysis.get("counterion_text", "") or "Unknown")
        )
        counterion_action_var = tk.StringVar(value=str(rule.get("counterion_action", "remove") or "remove"))
        ttk.Label(counterion_box, text="Counterion SMILES or Unknown").grid(row=0, column=0, sticky="w")
        ttk.Entry(counterion_box, textvariable=counterion_var, width=42).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        ttk.Radiobutton(counterion_box, text="Remove spectator counterion", variable=counterion_action_var, value="remove").grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Radiobutton(counterion_box, text="Keep counterion in generated product", variable=counterion_action_var, value="keep").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(6, 0))
        counterion_box.grid_columnconfigure(1, weight=1)

        sites_box = ttk.LabelFrame(body, text="Charged sites", padding=8)
        sites_box.pack(fill="both", expand=True, pady=(6, 6))
        site_vars: Dict[str, tk.StringVar] = {}
        for number, site in enumerate(analysis.get("sites", []) or [], start=1):
            atom_key = str(site["atom_index"])
            default_action = "keep" if site.get("permanent") else "neutralize"
            action = str((rule.get("site_actions", {}) or {}).get(atom_key, default_action))
            var = tk.StringVar(value=action)
            site_vars[atom_key] = var
            charge = int(site.get("formal_charge", 0) or 0)
            sign = "+" if charge > 0 else ""
            ttk.Label(
                sites_box,
                text=f"Site {number}: {site.get('label', '')} ({site.get('symbol', '')}{sign}{charge})",
            ).grid(row=number - 1, column=0, sticky="w", pady=3)
            ttk.Radiobutton(sites_box, text="Keep charge", variable=var, value="keep").grid(row=number - 1, column=1, sticky="w", padx=(14, 0))
            neutral = ttk.Radiobutton(sites_box, text="Neutralize", variable=var, value="neutralize")
            neutral.grid(row=number - 1, column=2, sticky="w", padx=(12, 0))
            if site.get("permanent"):
                var.set("keep")
                neutral.configure(state="disabled")

        apply_matching_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body,
            text="Apply these site principles to all remaining building blocks with matching charged chemotypes",
            variable=apply_matching_var,
        ).pack(fill="x", anchor="w", pady=(4, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(12, 0))

        def cancel():
            result["value"] = None
            win.destroy()

        def save():
            counterion = counterion_var.get().strip() or "Unknown"
            if (
                counterion_action_var.get() == "keep"
                and counterion.casefold() != "unknown"
                and Chem.MolFromSmiles(counterion.replace(" . ", ".")) is None
            ):
                messagebox.showerror(
                    "Invalid counterion",
                    "Enter the counterion as valid SMILES (for example [Cl-]) or enter Unknown.",
                    parent=win,
                )
                return
            chemotype_values: Dict[str, set] = {}
            for site in analysis.get("sites", []) or []:
                chemotype = str(site.get("chemotype", ""))
                chemotype_values.setdefault(chemotype, set()).add(
                    site_vars[str(site["atom_index"])].get()
                )
            conflicts = [name for name, values in chemotype_values.items() if len(values) > 1]
            if apply_matching_var.get() and conflicts:
                messagebox.showwarning(
                    "Cannot apply conflicting chemotype rules",
                    "Two sites with the same charged chemotype have different principles. "
                    "Uncheck the matching-chemotype option, or assign the same principle to those sites.",
                    parent=win,
                )
                return
            result["value"] = ({
                "counterion_action": counterion_action_var.get(),
                "counterion": counterion,
                "site_actions": {key: var.get() for key, var in site_vars.items()},
                "chemotype_actions": {
                    chemotype: next(iter(values))
                    for chemotype, values in chemotype_values.items()
                    if len(values) == 1
                },
            }, bool(apply_matching_var.get()))
            win.destroy()

        ttk.Button(actions, text="Cancel", command=cancel).pack(side="right")
        ttk.Button(actions, text="Save and Continue", command=save, style="ChemAction.TButton").pack(side="right", padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", cancel)
        self.wait_window(win)
        return result.get("value")

    def _review_charged_building_blocks(self, force: bool = False) -> bool:
        items = self._charged_building_blocks()
        if not items:
            if force:
                messagebox.showinfo("Charged Building Block Review", "No charged building blocks are currently assigned to the synthesis plan.")
            return True
        prefills: Dict[str, Dict[str, object]] = {}
        handled_this_run = set()
        for item in items:
            key = str(item["key"])
            if key in handled_this_run:
                continue
            if (
                not force
                and self._ion_rule_is_complete(
                    dict(item.get("analysis", {}) or {}),
                    self.building_block_ion_rules.get(key),
                )
            ):
                continue
            initial = self.building_block_ion_rules.get(key) or prefills.get(key)
            response = self._ask_building_block_ion_rule(item, initial)
            if response is None:
                return False
            rule, apply_matching = response
            self.building_block_ion_rules[key] = rule
            handled_this_run.add(key)
            if not apply_matching:
                continue
            chemotype_actions = dict(rule.get("chemotype_actions", {}) or {})
            for other in items:
                other_key = str(other["key"])
                if other_key == key or (not force and other_key in self.building_block_ion_rules):
                    continue
                other_analysis = dict(other.get("analysis", {}) or {})
                matched_actions = {
                    str(site["atom_index"]): chemotype_actions[str(site.get("chemotype", ""))]
                    for site in other_analysis.get("sites", []) or []
                    if str(site.get("chemotype", "")) in chemotype_actions
                }
                if not matched_actions:
                    continue
                proposed = ion_handling.default_rule(other_analysis)
                proposed["counterion_action"] = rule.get("counterion_action", "remove")
                proposed["site_actions"].update(matched_actions)
                proposed["chemotype_actions"] = dict(chemotype_actions)
                all_matched = len(matched_actions) == len(other_analysis.get("sites", []) or [])
                if all_matched:
                    self.building_block_ion_rules[other_key] = proposed
                    handled_this_run.add(other_key)
                else:
                    prefills[other_key] = proposed
        return True

    def _review_charge_rules_action(self):
        if not self._review_charged_building_blocks(force=True):
            return
        self._stage_product_regeneration()
        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        self.logw("Charge rules updated. Generate Product Details again to apply them.")

    def _apply_building_block_ion_rule(self, compound: Dict[str, object], smiles: str) -> Dict[str, object]:
        try:
            analysis = ion_handling.analyze_smiles(smiles)
        except Exception:
            return {"reaction_smiles": smiles, "kept_counterions": [], "summary": ""}
        if not analysis.get("charged"):
            return {"reaction_smiles": analysis.get("canonical_smiles", smiles), "kept_counterions": [], "summary": ""}
        rule = self.building_block_ion_rules.get(self._building_block_ion_key(compound))
        if not rule:
            return {"reaction_smiles": smiles, "kept_counterions": [], "summary": "Charge rule unassigned"}
        return ion_handling.apply_rule(smiles, rule)

    def _resolve_compound(self, label: str) -> Optional[Dict[str, str]]:
        by_id, by_name = self._compound_index()
        key = (label or "").strip().lower()
        return by_id.get(key) or by_name.get(key)

    def _classify(self, smiles: str, reaction: Dict[str, str]) -> str:
        mol = Chem.MolFromSmiles(smiles or "")
        if mol is None:
            return "Unknown"
        patterns = ROLE_PATTERNS.get(reaction["id"], {})
        matched_roles = [
            role
            for role in ["Nucleophile", "Electrophile"]
            if any(mol.HasSubstructMatch(p) for p in _compile_patterns(patterns.get(role, [])))
        ]
        if len(matched_roles) > 1:
            return "Ambiguous"
        if matched_roles:
            return matched_roles[0]
        try:
            rxn = core.AllChem.ReactionFromSmarts(reaction["smarts"])
            templates = list(rxn.GetReactants())
            # Existing Cheminformatic engine runs reactants as (electrophile, nucleophile).
            template_roles = []
            if len(templates) >= 1 and mol.HasSubstructMatch(templates[0]):
                template_roles.append("Electrophile")
            if len(templates) >= 2 and mol.HasSubstructMatch(templates[1]):
                template_roles.append("Nucleophile")
            if len(template_roles) > 1:
                return "Ambiguous"
            if template_roles:
                return template_roles[0]
        except Exception:
            pass
        return "Unknown"

    def _pushed_key(self, row):
        # Retain independent additions across sources, worklists and blocks.
        return (str(row.get("source", "Tecan" if row.get("gwl") else "")).casefold(),
                str(row.get("gwl", "")), str(row.get("block", "")),
                str(row.get("well", "")).strip().upper(),
                str(row.get("chemical", "")).strip().casefold(),
                str(row.get("dest_labware", "")).strip().casefold(),
                str(row.get("_push_occurrence", "")))

    def _ask_clear_pushed(self):
        dialog = tk.Toplevel(self)
        dialog.title("Clear pushed inputs")
        dialog.transient(self.winfo_toplevel())
        result = [None]
        def choose(value):
            result[0] = value
            dialog.destroy()
        ttk.Label(dialog, text="Clear pushed additions from Cheminformatics and Reaction Summary?\n"
                  "Choose whether to retain generated products and LCMS results.\n"
                  "Original synthesis plans and external files are kept.",
                  padding=16, wraplength=620).pack(fill="x")
        buttons = ttk.Frame(dialog, padding=12)
        buttons.pack(fill="x")
        for label, value in (("Clear inputs only", "inputs"),
                             ("Clear inputs, products and results", "all"), ("Cancel", None)):
            ttk.Button(buttons, text=label, command=lambda v=value: choose(v)).pack(side="left", padx=4)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        dialog.bind("<Escape>", lambda _event: choose(None))
        dialog.grab_set()
        self.wait_window(dialog)
        return result[0]

    def _clear_pushed_rows(self):
        if not self.pushed_rows and not self.retained_product_rows and not self._pyparse_rows():
            return
        choice = self._ask_clear_pushed()
        if choice not in ("inputs", "all"):
            return
        if choice == "inputs":
            self.retained_product_rows = [dict(row) for row in self._pyparse_rows()]
            self.retained_detail_rows = [list(self.preview.item(i, "values")) for i in self.preview.get_children()]
            self.pushed_rows.clear()
            self.pushed_plan_fingerprints.clear()
            self.retained_results_var.set("Retained products / LCMS results belong to previous inputs. Generate new products to replace them.")
        else:
            reaction = self.reaction_var.get()
            self.clear_for_next_synthesis_step()
            self.reaction_var.set(reaction)
        self._refresh_product_details_preview(show_products=self.product_details_generated)
        self._refresh_pyparse_preview()
        if callable(self.pushed_change_callback):
            self.pushed_change_callback(choice)
        self.logw("Cleared pushed inputs; " + ("previous results retained." if choice == "inputs" else "products and LCMS records cleared."))

    @staticmethod
    def _lookup_product_detail(row: Dict[str, str], names: List[str]) -> str:
        for name in names:
            value = row.get(name, "")
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _read_product_detail_rows(path: Path) -> List[Dict[str, str]]:
        suffix = path.suffix.lower()
        rows: List[Dict[str, str]] = []
        if suffix in {".xlsx", ".xlsm"}:
            workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
            try:
                sheet = workbook.active
                raw_rows = sheet.iter_rows(values_only=True)
                headers = next(raw_rows, None)
                if not headers:
                    return []
                normalized_headers = [str(value or "").strip().lower() for value in headers]
                for raw in raw_rows:
                    row = {
                        header: "" if value is None else str(value).strip()
                        for header, value in zip(normalized_headers, raw)
                        if header
                    }
                    if any(str(value).strip() for value in row.values()):
                        rows.append(row)
            finally:
                workbook.close()
            return rows

        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row = {
                    str(key or "").strip().lower(): str(value or "").strip()
                    for key, value in raw.items()
                    if key is not None
                }
                if any(row.values()):
                    rows.append(row)
        return rows

    def _input_product_details(self):
        filename = filedialog.askopenfilename(
            title="Input product details",
            filetypes=[
                ("Product detail files", "*.csv *.xlsx *.xlsm"),
                ("CSV", "*.csv"),
                ("Excel", "*.xlsx *.xlsm"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return

        path = Path(filename)
        try:
            source_rows = self._read_product_detail_rows(path)
        except Exception as exc:
            messagebox.showerror("Input product details", f"Could not read product details:\n{exc}")
            return

        imported: Dict[str, Dict[str, str]] = {}
        explicit_mapping_wells = set()
        skipped = 0
        invalid = 0
        for index, row in enumerate(source_rows, start=1):
            reaction_well = _normalize_well(self._lookup_product_detail(row, [
                "reaction well",
                "rxn well",
                "well",
                "plate well",
                "source well",
            ]))
            pyparse_well = _normalize_well(self._lookup_product_detail(row, [
                "lcms well",
                "pyparse well",
                "analysis well",
                "sample well",
            ]))
            if not reaction_well:
                reaction_well = pyparse_well or f"INPUT_{index}"
            explicit_mapping = bool(pyparse_well)
            if not pyparse_well:
                pyparse_well = reaction_well

            smiles = self._lookup_product_detail(row, [
                "desired product smiles",
                "product smiles",
                "smiles",
                "product smi",
            ])
            if not smiles:
                skipped += 1
                continue
            try:
                mol, canonical = core.canonical_smiles(smiles)
                exact, mw, formula, mh, mna, neg = core.mass_fields(canonical)
            except Exception:
                invalid += 1
                continue

            product_id = self._lookup_product_detail(row, [
                "desired product id",
                "product id",
                "compound id",
                "reaction number",
                "rxn number",
                "id",
            ])
            product_name = self._lookup_product_detail(row, [
                "desired product name",
                "product name",
                "compound name",
                "name",
            ])
            reaction_name = product_id or product_name or f"Product_{reaction_well}"

            imported_row = {
                "reaction_well": reaction_well,
                "pyparse_well": pyparse_well,
                "reaction_name": reaction_name,
                "product_id": product_id or reaction_name,
                "desired product name": product_name or reaction_name,
                "desired product smiles": canonical,
                "desired product exact mass": exact,
                "desired product mw": mw,
                "desired product formula": formula,
                "desired product mh": mh,
                "desired product mna": mna,
                "desired product negative mass": neg,
            }
            selectivity_text = self._lookup_product_detail(row, [
                "possible selectivity product smiles",
                "selectivity products",
                "possible products",
            ])
            selectivity_products = [canonical]
            for candidate in re.split(r"\s*\|\s*|[\r\n]+", selectivity_text or ""):
                candidate = candidate.strip()
                if not candidate:
                    continue
                try:
                    candidate = core.canonical_smiles(candidate)[1]
                except Exception:
                    continue
                if candidate not in selectivity_products:
                    selectivity_products.append(candidate)
            imported_row["selectivity products"] = (
                selectivity_products
                if self._are_same_mass_selectivity_products(selectivity_products)
                else [canonical]
            )
            for reactant_index in range(1, 4):
                for field in ("id", "name", "smiles"):
                    value = self._lookup_product_detail(row, [
                        f"reactant {reactant_index} {field}",
                        f"reactant{reactant_index} {field}",
                        f"bb{reactant_index} {field}",
                    ])
                    imported_row[f"reactant {reactant_index} {field}"] = value
            imported[reaction_well] = imported_row
            if explicit_mapping:
                explicit_mapping_wells.add(reaction_well)

        if not imported:
            messagebox.showwarning(
                "Input product details",
                "No product details were imported. Include product SMILES and a well/reaction well column where possible.",
            )
            self.logw(f"No product details imported from {path.name}; skipped {skipped}, invalid {invalid}.")
            return

        previous_rows = {_normalize_well(row.get("reaction_well", "")): dict(row)
                         for row in self._pyparse_rows()}
        previous_rows.update(self.__dict__.get("pending_product_identity_rows", {}))
        previous_trace_targets = {}
        for row in previous_rows.values():
            sample = _normalize_well(row.get("pyparse_well", ""))
            previous_trace_targets.setdefault(sample, set()).add(_canonical_smiles_key(self._lcms_target_for_row(row)))
        conflicts = [f"{well}: {previous_rows[well].get('pyparse_well', '')} -> {imported[well]['pyparse_well']}"
                     for well in sorted(explicit_mapping_wells)
                     if well in previous_rows and previous_rows[well].get("pyparse_well")
                     and _normalize_well(previous_rows[well]["pyparse_well"]) != imported[well]["pyparse_well"]]
        if conflicts and not messagebox.askyesno(
            "Replace LCMS well mappings",
            "The imported Product Details specify different LCMS wells:\n" + "\n".join(conflicts)
            + "\n\nUse these incoming mappings? Old sample assignments will not be transferred.", parent=self,
        ):
            return
        if self.retained_results_var.get():
            if not messagebox.askyesno("Replace retained results", "Replace the retained products and LCMS results with these imported product details?", parent=self):
                return
            self._replace_retained_results()
            previous_rows = {}
        self.imported_product_details = imported
        for well in explicit_mapping_wells:
            self.pyparse_wells[well] = imported[well]["pyparse_well"]
        for well in imported:
            self.__dict__.get("product_review_wells", {}).pop(well, None)
        self.product_details_generated = True
        current_rows = {_normalize_well(row.get("reaction_well", "")): row for row in self._pyparse_rows()}
        changes = []
        for well, previous in previous_rows.items():
            current = current_rows.get(well, {})
            changed_product = (_canonical_smiles_key(previous.get("desired product smiles", ""))
                               != _canonical_smiles_key(current.get("desired product smiles", "")))
            changed_mapping = (_normalize_well(previous.get("pyparse_well", ""))
                               != _normalize_well(current.get("pyparse_well", "")))
            if changed_product or changed_mapping:
                changes.append((well, previous, current, changed_product, changed_mapping))
        remapping = any(change[4] for change in changes)
        # Install all associations before resolving any destination. Automatic
        # product+sample evidence is independent of reaction-row ownership: a
        # mapping permutation must not delete the next row's destination data.
        for well, previous, current, changed_product, changed_mapping in changes:
            self._invalidate_product_analysis(previous, preserve_automatic_evidence=remapping)
            if changed_mapping and current:
                self._clear_product_manual_assignment(current)
            self.lcms_target_smiles_by_well.pop(well, None)
            self.lcms_target_summaries_by_well.pop(well, None)
        self.pending_product_identity_rows = {}
        for well, previous, current, changed_product, changed_mapping in changes:
            if changed_mapping and not changed_product:
                new_well = _normalize_well(current.get("pyparse_well", ""))
                target = _canonical_smiles_key(self._lcms_target_for_row(current))
                if new_well in self.modified_pyparse_purity_by_product.get(target, {}):
                    sources = self.invalidated_product_analysis.get(well, [])
                    if "modified" in sources:
                        sources.remove("modified")
        if remapping:
            current_trace_targets = {}
            for row in current_rows.values():
                sample = _normalize_well(row.get("pyparse_well", ""))
                current_trace_targets.setdefault(sample, set()).add(_canonical_smiles_key(self._lcms_target_for_row(row)))
            for sample, targets in previous_trace_targets.items():
                if targets != current_trace_targets.get(sample, set()):
                    traces = self.portable_trace_paths.get(sample, {})
                    for name in ("pyparse_uv", "modified_uv", "modified_es"):
                        traces.pop(name, None)
        self._refresh_product_details_preview(show_products=True)
        self._refresh_pyparse_preview()
        self.logw(
            f"Imported {len(imported)} product detail row(s) from {path.name}; "
            f"skipped {skipped} without SMILES, {invalid} invalid SMILES."
        )

    def _replace_pushed_source(self, source_name: str, source_rows: List[Dict[str, object]]):
        from xinpilot.application.heatmap_layout import reaction_mode

        source_key = source_name.strip().casefold()
        aliases = {
            "tecan": {"tecan"},
            "manual workflow": {"manual", "manual workflow"},
            "opentrons": {"opentrons"},
        }.get(source_key, {source_key})
        replacement = dict(self.pushed_rows)
        for key, row in list(replacement.items()):
            existing_source = str(row.get("source", "") or "").strip().casefold()
            legacy_tecan = source_key == "tecan" and not existing_source and bool(row.get("gwl"))
            if existing_source in aliases or legacy_tecan:
                del replacement[key]
        occurrences = {}
        for source_row in source_rows:
            item = dict(source_row)
            item.setdefault("source", source_name)
            item["is_building_block"] = coerce_bool(item.get("is_building_block", False))
            key = self._pushed_key(item)
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            item["_push_occurrence"] = occurrence
            replacement[self._pushed_key(item)] = item
        # Validate the complete proposed composition before changing live state.
        # Every synthesis route uses this same boundary, regardless of push order.
        reaction_mode(replacement.values())
        self._pyparse_rows()  # Snapshot the previous resolved products before replacing inputs.
        self.pushed_rows = replacement
        self._sync_building_block_identity()
        if callable(self.pushed_change_callback):
            self.pushed_change_callback("push:" + source_name)

    def push_from_tecan(self, source_rows: Optional[List[Dict[str, object]]] = None):
        source_rows = list(source_rows if source_rows is not None else (self.tecan_provider() or []))
        self._replace_pushed_source("Tecan", source_rows)
        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        msg = (
            f"Pushed {len(source_rows)} Tecan chemical well row(s); "
            f"{len(self.pushed_rows)} total recorded. Select a reaction type and click Generate Product Details."
        )
        self.logw(msg)

    def push_from_manual(self, source_rows: List[Dict[str, object]]):
        rows = [dict(item) for item in (source_rows or []) if isinstance(item, dict)]
        self._replace_pushed_source("Manual workflow", rows)
        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        msg = (
            f"Pushed {len(rows)} manual chemical row(s); "
            f"{len(self.pushed_rows)} total recorded. Select a reaction type and click Generate Product Details."
        )
        self.logw(msg)

    def push_from_opentrons(self, source_rows: List[Dict[str, object]]):
        rows = [dict(item) for item in (source_rows or []) if isinstance(item, dict)]
        self._replace_pushed_source("Opentrons", rows)
        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        msg = (
            f"Pushed {len(rows)} Opentrons chemical row(s); "
            f"{len(self.pushed_rows)} total recorded. Select a reaction type and click Generate Product Details."
        )
        self.logw(msg)

    def push_from_external(self, source_rows):
        self._replace_pushed_source("External Import", source_rows)
        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        self.logw(f"Pushed {len(source_rows)} external transfer rows. Select a reaction type and Generate Product Details.")

    def export_state(self) -> Dict[str, object]:
        self._sync_building_block_identity()
        self._save_current_product_structure_manual_fields()
        return {
            "reaction": self.reaction_var.get(),
            "product_details_generated": bool(self.product_details_generated),
            "pushed_plan_fingerprints": self.pushed_plan_fingerprints,
            "retained_product_rows": self.retained_product_rows,
            "retained_detail_rows": self.retained_detail_rows,
            "retained_results_notice": self.retained_results_var.get(),
            "output_csv": self.output_var.get(),
            "reaction_name_start": self.name_start_var.get(),
            "pyparse_output_csv": self.pyparse_output_var.get(),
            "impurity_pyparse_output_csv": self.impurity_pyparse_output_var.get(),
            "impurity_exclusions": dict(self.impurity_exclusions),
            "carried_impurity_sources": dict(self.carried_impurity_sources),
            "pyparse_result_dir": str(self.pyparse_result_dir) if self.pyparse_result_dir else "",
            "modified_pyparse_result_dir": str(self.modified_pyparse_result_dir) if self.modified_pyparse_result_dir else "",
            "modified_pyparse_impurity_result_dir": (
                str(self.modified_pyparse_impurity_result_dir)
                if self.modified_pyparse_impurity_result_dir else ""
            ),
            "pyparse_wells": dict(self.pyparse_wells),
            "custom_reactant_order": self.custom_reactant_order_var.get(),
            "custom_output_dir": self.custom_output_dir_var.get(),
            "custom_template": self.custom_template_text.get("1.0", "end-1c"),
            "custom_products": dict(self.custom_products),
            "custom_failures": dict(self.custom_failures),
            "reaction_site_selections": dict(self.reaction_site_selections),
            "reaction_names": dict(self.reaction_names),
            "imported_product_details": dict(self.imported_product_details),
            "building_block_identity_by_well": self.__dict__.get("building_block_identity_by_well"),
            "product_review_wells": dict(self.__dict__.get("product_review_wells", {})),
            "pending_product_identity_rows": dict(self.__dict__.get("pending_product_identity_rows", {})),
            "building_block_ion_rules": dict(self.building_block_ion_rules),
            "lcms_target_smiles_by_well": dict(self.lcms_target_smiles_by_well),
            "lcms_target_summaries_by_well": dict(self.lcms_target_summaries_by_well),
            "lcms_handling_mode": self.lcms_handling_mode,
            "pushed_rows": list(self.pushed_rows.values()),
            "cheminformatics_result_rows": self._cheminformatics_result_export_rows(),
            "pyparse_purity_by_well": dict(self.pyparse_purity_by_well),
            "modified_pyparse_purity_by_well": dict(self.modified_pyparse_purity_by_well),
            "modified_pyparse_purity_by_product": {
                smiles: dict(values)
                for smiles, values in self.modified_pyparse_purity_by_product.items()
            },
            "modified_pyparse_conflicts_by_product": {
                smiles: dict(values)
                for smiles, values in self.modified_pyparse_conflicts_by_product.items()
            },
            "product_structure_uv_source": self.product_structure_uv_source_var.get(),
            "product_structure_uv_source_by_key": dict(self.product_structure_uv_source_by_key),
            "portable_trace_paths": dict(self.portable_trace_paths),
            "invalidated_product_analysis": dict(self.__dict__.get("invalidated_product_analysis", {})),
            "product_structure_manual_notes": dict(self.product_structure_manual_notes),
            "peak_inspection_data": getattr(self, "peak_inspection_data", {}),
            "product_peak_overrides": getattr(self, "product_peak_overrides", {}),
            "product_structure_row_colors": dict(self.product_structure_row_colors),
            "product_structure_biology_hits": dict(self.product_structure_biology_hits),
            "product_structure_preview_rows": self._product_structure_export_rows(),
        }

    def _cheminformatics_result_export_rows(self) -> List[Dict[str, object]]:
        try:
            return [dict(row) for row in self._pyparse_rows()]
        except Exception:
            return []

    def _product_structure_export_rows(self) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for row in self._cheminformatics_result_export_rows():
            lcms_well = _normalize_well(row.get("pyparse_well", ""))
            manual_values = self.product_structure_manual_notes.get(self._product_structure_manual_key(row), {})
            rows.append({
                "rxn_number": str(row.get("reaction_name", "") or ""),
                "rxn_well": str(row.get("reaction_well", "") or ""),
                "lcms_well": str(row.get("pyparse_well", "") or ""),
                "product_smiles": str(row.get("desired product smiles", "") or ""),
                "lcms_target_smiles": self._lcms_target_for_row(row),
                "lcms_preparation": self._lcms_summary_for_row(row),
                "exact_mass": str(row.get("desired product exact mass", "") or ""),
                "uv254_purity_from_pyparse": self._product_structure_purity_for_row(row, "pyparse"),
                "uv254_purity_from_modified_pyparse": self._modified_pyparse_purity_for_row(row),
                "purity_by_manual": str(manual_values.get("manual_purity", "") or ""),
                "purity_source": self._product_structure_uv_source_for_row(row),
                "comments": str(manual_values.get("comments", "") or ""),
                "row_color": self._product_structure_row_color(row),
                "biology_assay_hits": self._biology_hit_summary_for_row(row),
            })
        return rows

    def import_state(self, data: Dict[str, object]):
        self.building_block_identity_by_well = None
        self._last_product_identity_rows = {}
        self.product_review_wells = dict(data.get("product_review_wells", {}) or {})
        self.pending_product_identity_rows = {
            _normalize_well(well): dict(row)
            for well, row in (data.get("pending_product_identity_rows", {}) or {}).items()
            if isinstance(row, dict)
        }
        self.invalidated_product_analysis = {
            _normalize_well(well): [source for source in sources if source in {"pyparse", "modified"}]
            for well, sources in (data.get("invalidated_product_analysis", {}) or {}).items()
            if _normalize_well(well) and isinstance(sources, (list, tuple))
        }
        self.pushed_plan_fingerprints = dict(data.get("pushed_plan_fingerprints", {}))
        self.retained_product_rows = [dict(row) for row in data.get("retained_product_rows", []) if isinstance(row, dict)]
        self.retained_detail_rows = list(data.get("retained_detail_rows", []))
        self.retained_results_var.set(str(data.get("retained_results_notice", "")))
        self._peak_import(data)
        reaction = str(data.get("reaction", "") or "")
        labels = [r["label"] for r in self.reactions]
        if reaction in labels:
            self.reaction_var.set(reaction)
        self.output_var.set(str(data.get("output_csv", self.output_var.get()) or ""))
        self.name_start_var.set(str(data.get("reaction_name_start", self.name_start_var.get()) or ""))
        self.pyparse_output_var.set(str(data.get("pyparse_output_csv", "") or ""))
        self.impurity_pyparse_output_var.set(str(data.get("impurity_pyparse_output_csv", "") or ""))
        self.impurity_exclusions = {
            str(key): bool(value)
            for key, value in (data.get("impurity_exclusions", {}) or {}).items()
            if bool(value)
        }
        self.carried_impurity_sources = {
            str(key): dict(value)
            for key, value in (data.get("carried_impurity_sources", {}) or {}).items()
            if str(key).strip() and isinstance(value, dict)
        }
        pyparse_result_dir = str(data.get("pyparse_result_dir", "") or "").strip()
        modified_result_dir = str(data.get("modified_pyparse_result_dir", "") or "").strip()
        modified_impurity_result_dir = str(data.get("modified_pyparse_impurity_result_dir", "") or "").strip()
        self.pyparse_result_dir = Path(pyparse_result_dir) if pyparse_result_dir else None
        self.modified_pyparse_result_dir = Path(modified_result_dir) if modified_result_dir else None
        self.modified_pyparse_impurity_result_dir = (
            Path(modified_impurity_result_dir) if modified_impurity_result_dir else None
        )
        # Legacy projects stored only one Modified PyParse folder.  If that
        # folder is clearly an impurity run, do not let it replace product
        # traces after import.
        if self.modified_pyparse_result_dir and not modified_impurity_result_dir:
            try:
                has_impurity_summaries = any(
                    any(graph_dir.glob("chroma-ImpuritySummary__*"))
                    for graph_dir in self._graph_image_dirs(self.modified_pyparse_result_dir)
                )
            except Exception:
                has_impurity_summaries = False
            if has_impurity_summaries:
                self.modified_pyparse_impurity_result_dir = self.modified_pyparse_result_dir
                self.modified_pyparse_result_dir = None
        self.pyparse_wells = {
            str(k).strip().upper(): str(v).strip().upper()
            for k, v in (data.get("pyparse_wells", {}) or {}).items()
        }
        order = str(data.get("custom_reactant_order", self.custom_reactant_order_var.get()) or "")
        if order in {"Automatic (try all orders)", "As listed"}:
            self.custom_reactant_order_var.set(order)
        elif order in {"Reactant 1, Reactant 2", "Reactant 2, Reactant 1"}:
            # Backward-compatible migration from the former two-reactant UI.
            self.custom_reactant_order_var.set("Automatic (try all orders)" if order.startswith("Reactant 2") else "As listed")
        self.custom_output_dir_var.set(str(data.get("custom_output_dir", self.custom_output_dir_var.get()) or ""))
        self.custom_template_text.delete("1.0", "end")
        self.custom_template_text.insert("1.0", str(data.get("custom_template", "") or ""))
        self.custom_products = {
            str(k).strip().upper(): dict(v)
            for k, v in (data.get("custom_products", {}) or {}).items()
            if isinstance(v, dict)
        }
        self.custom_failures = {
            str(k).strip().upper(): str(v)
            for k, v in (data.get("custom_failures", {}) or {}).items()
        }
        self.reaction_names = {
            str(k).strip().upper(): str(v)
            for k, v in (data.get("reaction_names", {}) or {}).items()
        }
        self.imported_product_details = {
            _normalize_well(k): dict(v)
            for k, v in (data.get("imported_product_details", {}) or {}).items()
            if isinstance(v, dict)
        }
        self.building_block_ion_rules = {
            str(key): dict(value)
            for key, value in (data.get("building_block_ion_rules", {}) or {}).items()
            if str(key).strip() and isinstance(value, dict)
        }
        self.lcms_target_smiles_by_well = {
            _normalize_well(key): str(value or "").strip()
            for key, value in (data.get("lcms_target_smiles_by_well", {}) or {}).items()
            if _normalize_well(key) and str(value or "").strip()
        }
        self.lcms_target_summaries_by_well = {
            _normalize_well(key): str(value or "").strip()
            for key, value in (data.get("lcms_target_summaries_by_well", {}) or {}).items()
            if _normalize_well(key)
        }
        lcms_mode = str(data.get("lcms_handling_mode", "automatic") or "automatic")
        self.lcms_handling_mode = lcms_mode if lcms_mode in {"automatic", "exact", "review"} else "automatic"
        self.reaction_site_selections = {
            str(key): dict(value)
            for key, value in (data.get("reaction_site_selections", {}) or {}).items()
            if isinstance(value, dict)
        }
        self._reaction_site_options_cache.clear()
        self.pushed_rows.clear()
        for item in data.get("pushed_rows", []) or []:
            if isinstance(item, dict):
                row = dict(item)
                # Projects saved before explicit BB flags contained only structural
                # reactants, so preserve that historical meaning during migration.
                row["is_building_block"] = (
                    True if "is_building_block" not in row
                    else coerce_bool(row.get("is_building_block"))
                )
                self.pushed_rows[self._pushed_key(row)] = row
        self.product_details_generated = bool(data.get("product_details_generated", False))
        self.pyparse_purity_by_well = {
            _normalize_well(k): str(v)
            for k, v in (data.get("pyparse_purity_by_well", {}) or {}).items()
            if str(v).strip()
        }
        self.modified_pyparse_purity_by_well = {
            _normalize_well(k): str(v)
            for k, v in (data.get("modified_pyparse_purity_by_well", {}) or {}).items()
            if str(v).strip()
        }
        self.modified_pyparse_purity_by_product = {
            _canonical_smiles_key(smiles): {
                _normalize_well(well): str(value)
                for well, value in values.items()
                if _normalize_well(well) and str(value).strip()
            }
            for smiles, values in (data.get("modified_pyparse_purity_by_product", {}) or {}).items()
            if _canonical_smiles_key(smiles) and isinstance(values, dict)
        }
        self.modified_pyparse_conflicts_by_product = {
            _canonical_smiles_key(smiles): {
                _normalize_well(well): str(value)
                for well, value in values.items()
                if (
                    _normalize_well(well)
                    and str(value).strip() == PRODUCT_REACTANT_MASS_CONFLICT
                )
            }
            for smiles, values in (data.get("modified_pyparse_conflicts_by_product", {}) or {}).items()
            if _canonical_smiles_key(smiles) and isinstance(values, dict)
        }
        if self.modified_pyparse_result_dir and self.modified_pyparse_result_dir.exists():
            parsed_product_purity = _read_modified_pyparse_uv254_purity_by_product(
                self.modified_pyparse_result_dir
            )
            if parsed_product_purity:
                self.modified_pyparse_purity_by_product = parsed_product_purity
            self.modified_pyparse_conflicts_by_product = (
                _read_modified_pyparse_conflicts_by_product(self.modified_pyparse_result_dir)
            )
        uv_source = str(data.get("product_structure_uv_source", self.product_structure_uv_source_var.get()) or "").strip()
        if uv_source in {"pyparse", "modified", "manual"}:
            self.product_structure_uv_source_var.set(uv_source)
        else:
            self.product_structure_uv_source_var.set("modified")
        self.product_structure_uv_source_by_key = {
            str(key): str(value).strip()
            for key, value in (data.get("product_structure_uv_source_by_key", {}) or {}).items()
            if str(value).strip() in {"pyparse", "modified", "manual"}
        }
        self.portable_trace_paths = {}
        for well, traces in (data.get("portable_trace_paths", {}) or {}).items():
            if not isinstance(traces, dict):
                continue
            normalized_well = _normalize_well(well)
            if not normalized_well:
                continue
            self.portable_trace_paths[normalized_well] = {
                str(trace_key): str(trace_path)
                for trace_key, trace_path in traces.items()
                if str(trace_path).strip()
            }
        self.product_structure_manual_notes = {}
        for key, values in (data.get("product_structure_manual_notes", {}) or {}).items():
            if not isinstance(values, dict):
                continue
            manual_purity = str(values.get("manual_purity", "") or "").strip()
            comments = str(values.get("comments", "") or "").strip()
            if manual_purity or comments:
                self.product_structure_manual_notes[str(key)] = {
                    "manual_purity": manual_purity,
                    "comments": comments,
                }
        self.product_structure_row_colors = {
            str(key): str(value).strip().lower()
            for key, value in (data.get("product_structure_row_colors", {}) or {}).items()
            if str(value).strip().lower() in PRODUCT_SUMMARY_ROW_COLORS or _is_hex_color(value)
        }
        self.product_structure_biology_hits = {}
        for key, values in (data.get("product_structure_biology_hits", {}) or {}).items():
            if isinstance(values, (list, tuple)):
                self._set_biology_hits_for_key(str(key), [str(value) for value in values])
            elif str(values or "").strip():
                self._set_biology_hits_for_key(str(key), [part.strip() for part in str(values).split(",")])
        for item in data.get("product_structure_preview_rows", []) or []:
            if not isinstance(item, dict):
                continue
            lcms_well = _normalize_well(item.get("lcms_well", ""))
            if not lcms_well:
                continue
            pyparse_value = str(item.get("uv254_purity_from_pyparse", "") or "").strip()
            modified_value = str(item.get("uv254_purity_from_modified_pyparse", "") or "").strip()
            if pyparse_value and lcms_well not in self.pyparse_purity_by_well:
                self.pyparse_purity_by_well[lcms_well] = pyparse_value
            if modified_value and lcms_well not in self.modified_pyparse_purity_by_well:
                self.modified_pyparse_purity_by_well[lcms_well] = modified_value
            manual_purity = str(item.get("purity_by_manual", "") or "").strip()
            comments = str(item.get("comments", "") or "").strip()
            if manual_purity or comments:
                key = self._product_structure_manual_key({
                    "pyparse_well": item.get("lcms_well", ""),
                    "reaction_well": item.get("rxn_well", ""),
                    "reaction_name": item.get("rxn_number", ""),
                })
                if key:
                    self.product_structure_manual_notes[key] = {
                        "manual_purity": manual_purity,
                        "comments": comments,
                    }
            row_color = str(item.get("row_color", "") or "").strip().lower()
            if row_color in PRODUCT_SUMMARY_ROW_COLORS or _is_hex_color(row_color):
                key = self._product_structure_manual_key({
                    "pyparse_well": item.get("lcms_well", ""),
                    "reaction_well": item.get("rxn_well", ""),
                    "reaction_name": item.get("rxn_number", ""),
                })
                if key:
                    self.product_structure_row_colors[key] = row_color
            biology_assays = str(item.get("biology_assay_hits", "") or "").strip()
            if biology_assays:
                key = self._product_structure_manual_key({
                    "pyparse_well": item.get("lcms_well", ""),
                    "reaction_well": item.get("rxn_well", ""),
                    "reaction_name": item.get("rxn_number", ""),
                })
                if key:
                    self._set_biology_hits_for_key(key, [part.strip() for part in biology_assays.split(",")])
            purity_source = str(item.get("purity_source", "") or "").strip()
            if purity_source in {"pyparse", "manual"}:
                key = self._product_structure_manual_key({
                    "pyparse_well": item.get("lcms_well", ""),
                    "reaction_well": item.get("rxn_well", ""),
                    "reaction_name": item.get("rxn_number", ""),
                })
                if key:
                    self.product_structure_uv_source_by_key[key] = purity_source
        self.building_block_identity_by_well = data.get("building_block_identity_by_well")
        self._last_product_identity_rows = {
            _normalize_well(row.get("reaction_well", "")): dict(row)
            for row in data.get("cheminformatics_result_rows", []) or [] if isinstance(row, dict)
        }
        self._classify_preview()
        self._load_product_structure_manual_fields(self._selected_product_structure_row())
        self._refresh_product_structure_purity_display()
        self._refresh_product_structure_trace_display()
        self._refresh_impurity_previews()
        self.logw("Imported Cheminformatics project state.")

    def clear_for_next_synthesis_step(self, carried_impurity_sources: Optional[Dict[str, Dict[str, object]]] = None):
        """Clear experiment-specific state while keeping the configured reaction registry."""
        self.building_block_identity_by_well = None
        self._last_product_identity_rows = {}
        self.product_review_wells = {}
        self.pending_product_identity_rows = {}
        self.pushed_plan_fingerprints = {}
        self.retained_product_rows = []
        self.retained_detail_rows = []
        self.retained_results_var.set("")
        self.reaction_var.set("")
        self.product_details_generated = False
        self.output_var.set("")
        self.name_start_var.set("")
        self.reaction_name_edit_well = ""
        self.pyparse_output_var.set("")
        self.pyparse_well_var.set("")
        self.impurity_pyparse_output_var.set("")
        self.pyparse_experiment_count_var.set("1")
        self.pyparse_update_current_stock_var.set(False)
        self.pyparse_update_master_stock_var.set(False)
        self.custom_reactant_order_var.set("Automatic (try all orders)")
        self.custom_output_dir_var.set("")
        self.custom_template_text.delete("1.0", "end")

        self.pyparse_wells.clear()
        self.impurity_exclusions.clear()
        self.carried_impurity_sources = {
            str(key): dict(value)
            for key, value in (carried_impurity_sources or {}).items()
            if str(key).strip() and isinstance(value, dict)
        }
        self._impurity_cache_signature = ""
        self._impurity_cache_rows = []
        self.custom_products.clear()
        self.custom_failures.clear()
        self.reaction_site_selections.clear()
        self._reaction_site_options_cache.clear()
        self.reaction_names.clear()
        self.imported_product_details.clear()
        self.pushed_rows.clear()
        self.lcms_target_smiles_by_well.clear()
        self.lcms_target_summaries_by_well.clear()
        self.pyparse_purity_by_well.clear()
        self.modified_pyparse_purity_by_well.clear()
        self.modified_pyparse_purity_by_product.clear()
        self._peak_reset()
        self.modified_pyparse_conflicts_by_product.clear()
        self.pyparse_result_dir = None
        self.modified_pyparse_result_dir = None
        self.modified_pyparse_impurity_result_dir = None
        self.portable_trace_paths.clear()
        self.invalidated_product_analysis = {}
        self.product_structure_uv_source_var.set("modified")
        self.product_structure_uv_source_by_key.clear()
        self.product_structure_manual_notes.clear()
        self.product_structure_row_colors.clear()
        self.product_structure_biology_hits.clear()
        self.product_structure_current_manual_key = ""
        self.product_structure_current_smiles = ""
        self.product_structure_current_lcms_smiles = ""
        self.product_structure_manual_purity_var.set("")
        self.product_structure_meta_var.set("Select a product row")
        self._set_product_structure_comment_text("")
        self._clear_product_structure_trace_display()
        self._render_product_structure("")
        self._render_lcms_target_structure("")
        self._classify_preview()
        self._refresh_product_structure_purity_display({})
        self.log.delete("1.0", "end")
        self.logw("Ready for the next synthesis step.")

    def _discard_portable_trace_keys(self, keys: Iterable[str]) -> None:
        """Invalidate only portable traces replaced by one analysis source."""
        discarded = {str(key) for key in keys}
        if not discarded:
            return
        for well, traces in list(self.portable_trace_paths.items()):
            remaining = {
                str(key): str(path)
                for key, path in traces.items()
                if str(key) not in discarded and str(path).strip()
            }
            if remaining:
                self.portable_trace_paths[well] = remaining
            else:
                self.portable_trace_paths.pop(well, None)

    def set_pyparse_result_dir(self, source: str, output_dir: Path):
        if source == "modified_impurity":
            self.modified_pyparse_impurity_result_dir = output_dir
            self._discard_portable_trace_keys(("impurity_modified",))
            values = {}
        elif source == "modified":
            self._peak_load(output_dir)
            self.modified_pyparse_result_dir = output_dir
            self._discard_portable_trace_keys(("modified_uv", "modified_es"))
            values = _read_pyparse_uv254_purity_by_well(output_dir, modified=True)
            self.modified_pyparse_purity_by_well = values
            self.modified_pyparse_purity_by_product = _read_modified_pyparse_uv254_purity_by_product(output_dir)
            self.modified_pyparse_conflicts_by_product = (
                _read_modified_pyparse_conflicts_by_product(output_dir)
            )
        else:
            self.pyparse_result_dir = output_dir
            self._discard_portable_trace_keys(("pyparse_uv", "impurity_pyparse"))
            values = _read_pyparse_uv254_purity_by_well(output_dir, modified=False)
            self.pyparse_purity_by_well = values
        if source in {"modified", "standard", "pyparse"}:
            self._accept_fresh_analysis("modified" if source == "modified" else "pyparse", values)
        if hasattr(self, "product_structure_table"):
            self._refresh_product_structure_preview(reset_selection=False)
        self._refresh_product_structure_purity_display()
        self._refresh_product_structure_trace_display()
        self.logw(f"Loaded {len(values)} UV254 purity value(s) from {source} PyParse output.")

    def _current_rows(self, reaction: Optional[Dict[str, str]] = None):
        self._sync_building_block_identity()
        rows = []
        for item in self.pushed_rows.values():
            chemical = str(item.get("chemical", ""))
            comp = self._resolve_compound(chemical)
            original_smiles = (comp or {}).get("SMILES", "")
            is_building_block = coerce_bool(item.get("is_building_block", False))
            ion_treatment = (
                self._apply_building_block_ion_rule(comp or {}, original_smiles)
                if is_building_block and comp and original_smiles
                else {"reaction_smiles": original_smiles, "kept_counterions": [], "summary": ""}
            )
            smiles = str(ion_treatment.get("reaction_smiles", original_smiles) or "")
            role = self._classify(smiles, reaction) if smiles and reaction else "Unknown"
            status_note = ""
            if not comp:
                status_note = "not found in Compound Notes"
            elif not smiles:
                status_note = "no SMILES in Compound Notes"
            elif reaction and role == "Unknown":
                status_note = f"SMILES not recognized for {reaction['label']}: {smiles}"
            elif not reaction:
                status_note = "select reaction type and generate product details"
            rows.append({
                **item,
                "compound": comp,
                "smiles": smiles,
                "original_smiles": original_smiles,
                "kept_counterions": list(ion_treatment.get("kept_counterions", []) or []),
                "ion_handling_summary": str(ion_treatment.get("summary", "") or ""),
                "is_building_block": is_building_block,
                "role": role if is_building_block else "Reagent",
                "status_note": status_note,
            })
        return rows

    def _custom_current_rows(self):
        self._sync_building_block_identity()
        rows = []
        for item in self.pushed_rows.values():
            chemical = str(item.get("chemical", ""))
            comp = self._resolve_compound(chemical)
            original_smiles = (comp or {}).get("SMILES", "")
            is_building_block = coerce_bool(item.get("is_building_block", False))
            ion_treatment = (
                self._apply_building_block_ion_rule(comp or {}, original_smiles)
                if is_building_block and comp and original_smiles
                else {"reaction_smiles": original_smiles, "kept_counterions": [], "summary": ""}
            )
            smiles = str(ion_treatment.get("reaction_smiles", original_smiles) or "")
            status_note = ""
            if not comp:
                status_note = "not found in Compound Notes"
            elif not smiles:
                status_note = "no SMILES in Compound Notes"
            rows.append({
                **item,
                "compound": comp,
                "smiles": smiles,
                "original_smiles": original_smiles,
                "kept_counterions": list(ion_treatment.get("kept_counterions", []) or []),
                "ion_handling_summary": str(ion_treatment.get("summary", "") or ""),
                "is_building_block": is_building_block,
                "status_note": status_note,
            })
        return rows

    @staticmethod
    def _finalize_products_for_reactants(products, reactants) -> List[str]:
        counterions: List[str] = []
        for reactant in reactants or []:
            if isinstance(reactant, dict):
                counterions.extend(str(value) for value in reactant.get("kept_counterions", []) or [])
        return ion_handling.append_counterions(list(products or []), counterions)

    @staticmethod
    def _unique_building_rows(rows):
        unique = {}
        for row in rows:
            if row.get("is_building_block"):
                key = str(row.get("chemical", "")).strip().casefold()
                if key not in unique:
                    unique[key] = dict(row)
                else:
                    first = unique[key]
                    first["volume_uL"] = sum(float(core.parse_float(item.get("volume_uL", item.get("volume", 0))) or 0) for item in (first, row))
        return list(unique.values())

    def _grouped_reaction_rows(self):
        by_well: Dict[str, List[Dict[str, object]]] = {}
        reaction = self._reaction()
        for row in self._current_rows(reaction):
            by_well.setdefault(str(row.get("well", "")), []).append(row)

        grouped = []
        for well, well_rows in sorted(by_well.items(), key=lambda kv: core.well_key(kv[0])):
            arity = int(reaction.get("reactant_count", 2) or 2)
            building_rows = self._unique_building_rows(well_rows)
            usable = [row for row in building_rows if row.get("compound") and row.get("smiles")]
            assignments = []
            all_products = set()
            for ordered_rows in itertools.permutations(usable, arity):
                try:
                    mols = tuple(core.canonical_smiles(row.get("smiles", ""))[0] for row in ordered_rows)
                    products = core.run_reaction_ordered(reaction["smarts"], mols)
                    products = self._finalize_products_for_reactants(products, ordered_rows)
                except Exception:
                    products = []
                if not products:
                    continue
                assignments.append((list(ordered_rows), mols, list(products)))
                all_products.update(products)

            if assignments:
                reactants, ordered_mols, _products = assignments[0]
                if len(all_products) == 1:
                    status = "Ready"
                elif self._are_same_mass_selectivity_products(all_products):
                    status = f"Ready: {len(all_products)} possible selectivity products (same formula and mass)"
                else:
                    status = f"Ambiguous: {len(all_products)} products with different formulas or masses generated"
                ignored = [row for row in usable if all(row is not selected for selected in reactants)]
                if ignored:
                    status += "; ignored non-matching material(s): " + ", ".join(
                        str(row.get("chemical", "")) for row in ignored
                    )
            else:
                reactants = usable[:arity]
                ordered_mols = ()
                if len(usable) < arity:
                    status = f"Need {arity} checked building block(s) with SMILES; found {len(usable)}"
                else:
                    status = f"No compatible {arity}-component reactant assignment for {reaction['label']}"
                missing = [
                    f"{row.get('chemical', '')} ({row.get('status_note', 'missing structure')})"
                    for row in building_rows if not row.get("compound") or not row.get("smiles")
                ]
                if missing:
                    status += "; " + ", ".join(missing)
            grouped_row = {
                    "well": well,
                    "reactants": reactants,
                    "reactant1": reactants[0] if len(reactants) >= 1 else None,
                    "reactant2": reactants[1] if len(reactants) >= 2 else None,
                    "reactant3": reactants[2] if len(reactants) >= 3 else None,
                    # Retain these aliases for old project/report code.  Registry
                    # template order is electrophile-like then nucleophile-like.
                    "electrophile": reactants[0] if len(reactants) >= 1 else None,
                    "nucleophile": reactants[1] if len(reactants) >= 2 else (reactants[0] if reactants else None),
                    "ordered_mols": ordered_mols,
                    "candidate_products": sorted(all_products),
                    "status": status,
                    "reaction_name": self.reaction_names.get(well, ""),
                    "raw_rows": well_rows,
                }
            self._apply_saved_reaction_site_selection(grouped_row, reaction)
            grouped.append(grouped_row)
        return grouped

    @staticmethod
    def _are_same_mass_selectivity_products(products) -> bool:
        unique = sorted({str(product or "").strip() for product in products if str(product or "").strip()})
        if len(unique) < 2:
            return False
        signatures = set()
        try:
            for product in unique:
                exact, _mw, formula, _mh, _mna, _neg = core.mass_fields(product)
                signatures.add((formula, exact))
        except Exception:
            return False
        return len(signatures) == 1

    @staticmethod
    def _reaction_site_signature(reaction: Dict[str, object], ordered_mols) -> str:
        structures = [
            [index, Chem.MolToSmiles(mol, canonical=True)]
            for index, mol in enumerate(ordered_mols)
        ]
        return json.dumps(
            [str(reaction.get("id", "")), "template-sites-v2", structures],
            separators=(",", ":"),
        )

    def _reaction_site_options(
        self,
        reaction: Dict[str, object],
        reactants: List[Dict[str, object]],
        ordered_mols,
    ) -> Tuple[str, List[Dict[str, object]]]:
        if not ordered_mols:
            return "", []
        signature = self._reaction_site_signature(reaction, ordered_mols)
        options_cache_signature = json.dumps(
            [
                str(reaction.get("id", "")),
                *[Chem.MolToSmiles(mol, canonical=True) for mol in ordered_mols],
            ],
            separators=(",", ":"),
        )
        cached = self._reaction_site_options_cache.get(options_cache_signature)
        if cached is not None:
            return signature, [dict(option) for option in cached]
        smarts = str(reaction.get("smarts", "") or "")
        try:
            matches_by_reactant = core.reaction_template_matches(smarts, ordered_mols)
        except Exception:
            matches_by_reactant = []
        if not matches_by_reactant or any(not matches for matches in matches_by_reactant):
            self._reaction_site_options_cache[options_cache_signature] = []
            return signature, []

        # A complete option is one template match on every reactant.  Group
        # combinations that produce the same structures so symmetry-equivalent
        # matches do not create a needless question.
        options_by_products: Dict[Tuple[str, ...], Dict[str, object]] = {}
        for selected_matches in itertools.product(*matches_by_reactant):
            products = core.run_reaction_at_template_sites(smarts, ordered_mols, selected_matches)
            products = self._finalize_products_for_reactants(products, reactants)
            product_key = tuple(sorted(set(products)))
            if not product_key or product_key in options_by_products:
                continue
            options_by_products[product_key] = {
                "site_matches": [list(match) for match in selected_matches],
                "products": list(product_key),
            }
        options = list(options_by_products.values())
        self._reaction_site_options_cache[options_cache_signature] = [dict(option) for option in options]
        return signature, options

    def _apply_saved_reaction_site_selection(
        self,
        grouped: Dict[str, object],
        reaction: Dict[str, object],
    ) -> None:
        reactants = list(grouped.get("reactants", []) or [])
        ordered_mols = tuple(grouped.get("ordered_mols", ()) or ())
        signature, options = self._reaction_site_options(reaction, reactants, ordered_mols)
        if len(options) < 2 or not signature:
            return
        selection = self.reaction_site_selections.get(signature)
        if not selection:
            return
        if selection.get("choice") == "all":
            grouped["reaction_site_choice"] = "all"
            grouped["reaction_site_label"] = "All possible reaction sites"
            product_count = len(list(grouped.get("candidate_products", []) or []))
            grouped["status"] = f"Ready: keeping all {product_count} possible products"
            return
        selected_matches = [
            [int(atom_index) for atom_index in match]
            for match in (selection.get("site_matches", []) or [])
        ]
        selected = next((
            option for option in options
            if option.get("site_matches", []) == selected_matches
        ), None)
        if selected is None:
            self.reaction_site_selections.pop(signature, None)
            return
        products = sorted(set(selected.get("products", []) or []))
        if not products:
            return
        grouped["candidate_products"] = products
        grouped["reaction_site_choice"] = "site"
        grouped["reaction_site_label"] = "Selected reaction site"
        grouped["status"] = (
            "Ready (selected reaction site)" if len(products) == 1
            else f"Ready: selected site gives {len(products)} products"
        )

    def _ask_reaction_site(
        self,
        grouped: Dict[str, object],
        options: List[Dict[str, object]],
    ) -> Optional[Dict[str, object]]:
        win = tk.Toplevel(self)
        win.title("Select reaction site")
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        win.grab_set()
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        well = str(grouped.get("well", "") or "")
        ttk.Label(
            body,
            text=(
                f"Reaction well {well} contains more than one product-generating reaction site.\n"
                "Select the intended site combination, or keep every possible product if the site is unknown."
            ),
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        reactants = list(grouped.get("reactants", []) or [])
        ordered_mols = tuple(grouped.get("ordered_mols", ()) or ())
        labelled_mols = []
        legends = []
        site_keys: List[Tuple[int, Tuple[int, ...]]] = []
        for option in options:
            for reactant_index, match in enumerate(option.get("site_matches", []) or []):
                key = (reactant_index, tuple(int(atom_index) for atom_index in match))
                if key not in site_keys:
                    site_keys.append(key)
        site_numbers = {key: index for index, key in enumerate(site_keys, start=1)}
        sites_by_reactant: Dict[int, List[Tuple[int, ...]]] = {}
        for reactant_index, match in site_keys:
            sites_by_reactant.setdefault(reactant_index, []).append(match)

        for reactant_index in range(len(ordered_mols)):
            mol = Chem.Mol(ordered_mols[reactant_index])
            for match in sites_by_reactant.get(reactant_index, []):
                other_atoms = set().union(*(
                    set(other) for other in sites_by_reactant.get(reactant_index, []) if other != match
                )) if len(sites_by_reactant.get(reactant_index, [])) > 1 else set()
                exclusive = [atom_index for atom_index in match if atom_index not in other_atoms]
                candidates = exclusive or list(match)
                halides = [
                    atom_index for atom_index in candidates
                    if mol.GetAtomWithIdx(atom_index).GetAtomicNum() in {9, 17, 35, 53}
                ]
                anchor = (halides or candidates)[0]
                mol.GetAtomWithIdx(anchor).SetAtomMapNum(site_numbers[(reactant_index, match)])
            labelled_mols.append(mol)
            reactant = reactants[reactant_index] if reactant_index < len(reactants) else {}
            legends.append(str(reactant.get("chemical", "") or f"Reactant {reactant_index + 1}"))
        image = Draw.MolsToGridImage(
            labelled_mols,
            molsPerRow=max(1, min(2, len(labelled_mols))),
            subImgSize=(360, 230),
            legends=legends,
            useSVG=False,
        )
        photo = ImageTk.PhotoImage(image)
        image_label = ttk.Label(body, image=photo, anchor="center")
        image_label.image = photo
        image_label.pack(fill="x", pady=(0, 8))

        choice_var = tk.IntVar(value=-1)
        ttk.Radiobutton(
            body,
            text="Reaction site unknown — keep all possible products",
            variable=choice_var,
            value=-1,
        ).pack(anchor="w", pady=2)
        for index, option in enumerate(options):
            option_sites = []
            for reactant_index, match in enumerate(option.get("site_matches", []) or []):
                reactant_sites = sites_by_reactant.get(reactant_index, [])
                if len(reactant_sites) < 2:
                    continue
                reactant = reactants[reactant_index] if reactant_index < len(reactants) else {}
                chemical = str(reactant.get("chemical", "") or f"Reactant {reactant_index + 1}")
                site_number = site_numbers[(reactant_index, tuple(int(atom_index) for atom_index in match))]
                option_sites.append(f"site {site_number} on {chemical}")
            description = " + ".join(option_sites) or f"site combination {index + 1}"
            ttk.Radiobutton(
                body,
                text=f"Option {index + 1}: {description}",
                variable=choice_var,
                value=index,
            ).pack(anchor="w", pady=2)

        result: Dict[str, object] = {"confirmed": False}

        def accept():
            choice = choice_var.get()
            if choice < 0:
                result.update({"confirmed": True, "choice": "all"})
            else:
                option = options[choice]
                result.update({
                    "confirmed": True,
                    "choice": "site",
                    "site_matches": [
                        [int(atom_index) for atom_index in match]
                        for match in (option.get("site_matches", []) or [])
                    ],
                })
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="Use Selection", command=accept, style="ChemAction.TButton").pack(side="right", padx=(0, 6))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self.wait_window(win)
        return dict(result) if result.get("confirmed") else None

    def _ensure_reaction_site_selections(
        self,
        grouped_rows: List[Dict[str, object]],
        reaction: Dict[str, object],
    ) -> bool:
        for grouped in grouped_rows:
            reactants = list(grouped.get("reactants", []) or [])
            ordered_mols = tuple(grouped.get("ordered_mols", ()) or ())
            signature, options = self._reaction_site_options(reaction, reactants, ordered_mols)
            if len(options) < 2 or not signature or signature in self.reaction_site_selections:
                continue
            selection = self._ask_reaction_site(grouped, options)
            if selection is None:
                return False
            self.reaction_site_selections[signature] = selection
        return True

    def _raw_grouped_reaction_rows(self):
        by_well: Dict[str, List[Dict[str, object]]] = {}
        for row in self._custom_current_rows():
            by_well.setdefault(str(row.get("well", "")), []).append(row)

        grouped = []
        for well, well_rows in sorted(by_well.items(), key=lambda kv: core.well_key(kv[0])):
            usable = [
                r for r in self._unique_building_rows(well_rows)
                if r.get("is_building_block") and r.get("compound") and r.get("smiles")
            ]
            grouped.append(
                {
                    "well": well,
                    "reactants": usable[:3],
                    "reactant1": usable[0] if len(usable) >= 1 else None,
                    "reactant2": usable[1] if len(usable) >= 2 else None,
                    "reactant3": usable[2] if len(usable) >= 3 else None,
                    "status": "Select reaction type and click Generate Product Details",
                    "reaction_name": self.reaction_names.get(well, ""),
                    "raw_rows": well_rows,
                }
            )
        return grouped

    def _custom_grouped_reaction_rows(self):
        by_well: Dict[str, List[Dict[str, object]]] = {}
        for row in self._custom_current_rows():
            by_well.setdefault(str(row.get("well", "")), []).append(row)

        grouped = []
        for well, well_rows in sorted(by_well.items(), key=lambda kv: core.well_key(kv[0])):
            building_rows = self._unique_building_rows(well_rows)
            usable = [r for r in building_rows if r.get("compound") and r.get("smiles")]
            if 1 <= len(usable) <= 3:
                status = f"{len(usable)} reactant(s) available; template determines required count"
            else:
                missing = [
                    f"{r.get('chemical', '')} ({r.get('status_note', 'missing SMILES')})"
                    for r in building_rows
                    if not r.get("compound") or not r.get("smiles")
                ]
                status = f"Custom templates support 1 to 3 structural reactants; found {len(usable)}"
                if missing:
                    status += "; " + ", ".join(missing)
            grouped.append(
                {
                    "well": well,
                    "reactants": usable[:3],
                    "reactant1": usable[0] if len(usable) >= 1 else None,
                    "reactant2": usable[1] if len(usable) >= 2 else None,
                    "reactant3": usable[2] if len(usable) >= 3 else None,
                    "status": status,
                    "reaction_name": self.reaction_names.get(well, ""),
                    "raw_rows": well_rows,
                }
            )
        return grouped

    def _parse_name_seed(self) -> Tuple[str, int, int]:
        seed = self.name_start_var.get().strip()
        m = re.search(r"(\d+)$", seed)
        if not m:
            return seed, 1, 1
        start_text = m.group(1)
        return seed[: m.start(1)], int(start_text), len(start_text)

    def _fill_reaction_names(self):
        if not self.name_start_var.get().strip():
            messagebox.showwarning("Reaction name required", "Enter a reaction name before filling down.")
            return
        tree, well_column = self._reaction_name_fill_context()
        wells = []
        selected_well = ""
        if tree is not None:
            for iid in tree.get_children():
                values = tree.item(iid, "values") or ()
                if well_column < len(values):
                    well = _normalize_well(values[well_column])
                    if well:
                        wells.append(well)
            selected_well = self._reaction_name_tree_well(tree, well_column)
        if not wells:
            grouped = self._grouped_reaction_rows() if self.product_details_generated else self._raw_grouped_reaction_rows()
            wells = [_normalize_well(row.get("well", "")) for row in grouped]
            wells = [well for well in wells if well]
        start_index = wells.index(selected_well) if selected_well in wells else 0
        prefix, start, width = self._parse_name_seed()
        for offset, well in enumerate(wells[start_index:]):
            self._store_reaction_name(well, f"{prefix}{start + offset:0{width}d}")
        if selected_well:
            self.reaction_name_edit_well = selected_well
        if hasattr(self, "pyparse_preview"):
            self._refresh_pyparse_preview()

    def _product_smiles_for_grouped_row(self, grouped: Dict[str, object], reaction: Dict[str, str]) -> str:
        if getattr(self, "custom_failures", {}).get(str(grouped.get("well", "")).strip().upper()):
            return ""
        reactants = list(grouped.get("reactants", []) or [])
        if len(reactants) != int(reaction.get("reactant_count", 2) or 2):
            return ""
        try:
            custom_product = self._custom_product_for_well(str(grouped.get("well", "")))
            if custom_product:
                return custom_product
            products = list(grouped.get("candidate_products", []) or [])
            if not products:
                mols = tuple(core.canonical_smiles(row.get("smiles", ""))[0] for row in reactants)
                products = core.run_reaction(reaction["smarts"], mols)
                products = self._finalize_products_for_reactants(products, reactants)
            if len(products) == 1:
                return products[0]
            if self._are_same_mass_selectivity_products(products):
                return " | ".join(sorted(set(products)))
            return ""
        except Exception:
            return ""

    def _refresh_product_details_preview(self, show_products: bool = False):
        if self.retained_results_var.get():
            self.preview.delete(*self.preview.get_children())
            for values in self.retained_detail_rows:
                self.preview.insert("", "end", values=values)
            return
        self.preview.delete(*self.preview.get_children())
        reaction = None
        if show_products:
            try:
                reaction = self._reaction()
            except Exception:
                reaction = None
        rows = self._grouped_reaction_rows() if reaction else self._raw_grouped_reaction_rows()
        preview_rows = list(rows)
        existing_wells = {str(row.get("well", "")).strip().upper() for row in preview_rows}
        for well, detail in sorted(self.imported_product_details.items(), key=lambda kv: core.well_key(kv[0])):
            if str(well).strip().upper() in existing_wells:
                continue
            preview_rows.append({
                "reaction_name": detail.get("reaction_name", ""),
                "well": well,
                "reactant1": {},
                "reactant2": {},
                "reactant3": {},
                "nucleophile": {},
                "electrophile": {},
                "status": "Ready (input product details)",
            })
        for i, row in enumerate(preview_rows):
            r1 = row.get("reactant1") or {}
            r2 = row.get("reactant2") or {}
            r3 = row.get("reactant3") or {}
            imported = self.imported_product_details.get(str(row.get("well", "")).strip().upper(), {})
            if show_products and imported.get("desired product smiles"):
                product_smiles = imported.get("desired product smiles", "")
            else:
                product_smiles = self._product_smiles_for_grouped_row(row, reaction) if show_products and reaction else ""
            self.preview.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    row.get("reaction_name", ""),
                    row.get("well", ""),
                    r1.get("chemical", "") if isinstance(r1, dict) else "",
                    r2.get("chemical", "") if isinstance(r2, dict) else "",
                    r3.get("chemical", "") if isinstance(r3, dict) else "",
                    product_smiles,
                ),
            )
        counts = {}
        for row in preview_rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        if show_products:
            self.logw(f"Generated Product Details preview for {len(preview_rows)} reaction wells: {counts}")
        else:
            self.logw(f"Loaded {len(preview_rows)} pushed reaction well(s); Product SMILES not generated yet.")
        if hasattr(self, "pyparse_preview"):
            self._refresh_pyparse_preview()
        if hasattr(self, "custom_preview"):
            self._refresh_custom_preview()

    def _classify_preview(self):
        self._refresh_product_details_preview(show_products=self.product_details_generated)

    def _custom_product_for_well(self, well: str) -> str:
        return (self.custom_products.get(str(well or "").strip().upper(), {}) or {}).get("smiles", "")

    @staticmethod
    def _custom_template_is_rxn_block(template: str) -> bool:
        text = (template or "").lstrip()
        if not text:
            return False
        markers = ("$RXN", "$MOL", "M  END")
        return any(marker in text for marker in markers) or "\n" in text and ">>" not in text

    def _compile_custom_reaction(self):
        if core.AllChem is None or core.Chem is None:
            raise RuntimeError("RDKit is required for custom reaction templates.")
        template = self.custom_template_text.get("1.0", "end").strip()
        if not template:
            raise ValueError("Paste or load a mapped reaction SMARTS/RXN template first.")
        if self._custom_template_is_rxn_block(template):
            rxn = core.AllChem.ReactionFromRxnBlock(template)
        else:
            rxn = core.AllChem.ReactionFromSmarts(template)
        if rxn is None:
            raise ValueError("Could not parse the reaction template.")
        if rxn.GetNumReactantTemplates() not in {1, 2, 3}:
            raise ValueError("XinPilot custom templates support one, two, or three structural reactants.")
        return rxn

    @staticmethod
    def _reaction_has_atom_maps(rxn) -> bool:
        for mol in list(rxn.GetReactants()) + list(rxn.GetProducts()):
            for atom in mol.GetAtoms():
                if atom.GetAtomMapNum():
                    return True
        return False

    @staticmethod
    def _looks_like_suzuki_pair(first_mol, second_mol) -> bool:
        if SUZUKI_HALIDE_QUERY is None or SUZUKI_BORON_QUERY is None:
            return False
        first_halide = first_mol.HasSubstructMatch(SUZUKI_HALIDE_QUERY)
        first_boron = first_mol.HasSubstructMatch(SUZUKI_BORON_QUERY)
        second_halide = second_mol.HasSubstructMatch(SUZUKI_HALIDE_QUERY)
        second_boron = second_mol.HasSubstructMatch(SUZUKI_BORON_QUERY)
        return (first_halide and second_boron) or (first_boron and second_halide)

    def _run_unmapped_suzuki_fallback(self, first_mol, second_mol) -> List[str]:
        if SUZUKI_HALIDE_QUERY is None or SUZUKI_BORON_QUERY is None:
            return []
        first_halide = first_mol.HasSubstructMatch(SUZUKI_HALIDE_QUERY)
        first_boron = first_mol.HasSubstructMatch(SUZUKI_BORON_QUERY)
        second_halide = second_mol.HasSubstructMatch(SUZUKI_HALIDE_QUERY)
        second_boron = second_mol.HasSubstructMatch(SUZUKI_BORON_QUERY)
        if first_halide and second_boron:
            return core.run_reaction(SUZUKI_GENERIC_SMARTS, first_mol, second_mol)
        if second_halide and first_boron:
            return core.run_reaction(SUZUKI_GENERIC_SMARTS, second_mol, first_mol)
        return []

    def _products_from_custom_reaction(self, rxn, reactants) -> Tuple[List[str], int, List[str]]:
        product_sets = rxn.RunReactants(reactants)
        products = []
        sanitize_errors = []
        for pset in product_sets:
            if not pset:
                continue
            product = pset[0]
            try:
                core.Chem.SanitizeMol(product)
            except Exception as exc:
                if len(sanitize_errors) < 3:
                    raw = ""
                    try:
                        raw = core.Chem.MolToSmiles(product, canonical=False)
                    except Exception:
                        raw = "<could not render product>"
                    sanitize_errors.append(f"{raw}: {exc}")
                continue
            if any(atom.GetAtomicNum() == 0 for atom in product.GetAtoms()):
                if len(sanitize_errors) < 3:
                    raw = core.Chem.MolToSmiles(product, canonical=False)
                    sanitize_errors.append(f"{raw}: ignored placeholder R-group product")
                continue
            products.append(core.Chem.MolToSmiles(product, canonical=True))
        return sorted(set(products)), len(product_sets), sanitize_errors

    @staticmethod
    def _template_canonical_smiles(mol) -> str:
        try:
            smiles = core.Chem.MolToSmiles(mol, canonical=True)
            parsed = core.Chem.MolFromSmiles(smiles)
            if parsed is None:
                return ""
            return core.Chem.MolToSmiles(parsed, canonical=True)
        except Exception:
            return ""

    def _run_unmapped_exact_product_fallback(self, rxn, reactant_smiles: Tuple[str, ...]) -> List[str]:
        if rxn.GetNumProductTemplates() < 1:
            return []
        template_reactants = [self._template_canonical_smiles(mol) for mol in rxn.GetReactants()]
        if len(template_reactants) != len(reactant_smiles) or not all(template_reactants):
            return []
        actual_reactants = list(reactant_smiles)
        if template_reactants != actual_reactants:
            return []
        products = []
        for product_template in rxn.GetProducts():
            product_smiles = self._template_canonical_smiles(product_template)
            if product_smiles:
                products.append(product_smiles)
        return sorted(set(products))

    @staticmethod
    def _template_core_without_dummy_atoms(template_mol):
        editable = core.Chem.EditableMol(core.Chem.Mol(template_mol))
        dummy_indices = [a.GetIdx() for a in template_mol.GetAtoms() if a.GetAtomicNum() == 0]
        for idx in sorted(dummy_indices, reverse=True):
            editable.RemoveAtom(idx)
        core_mol = editable.GetMol()
        core.Chem.SanitizeMol(core_mol, catchErrors=True)
        original_to_core = {}
        core_idx = 0
        for atom in template_mol.GetAtoms():
            if atom.GetAtomicNum() == 0:
                continue
            original_to_core[atom.GetIdx()] = core_idx
            core_idx += 1
        return core_mol, original_to_core

    @staticmethod
    def _fragment_atoms_from_root(mol, root_idx: int, blocked: set) -> set:
        seen = set()
        stack = [root_idx]
        while stack:
            idx = stack.pop()
            if idx in seen or idx in blocked:
                continue
            seen.add(idx)
            for neighbor in mol.GetAtomWithIdx(idx).GetNeighbors():
                neighbor_idx = neighbor.GetIdx()
                if neighbor_idx not in seen and neighbor_idx not in blocked:
                    stack.append(neighbor_idx)
        return seen

    def _rgroup_substituents_from_reactant(self, template_mol, actual_mol):
        dummy_atoms = [a for a in template_mol.GetAtoms() if a.GetAtomicNum() == 0 and a.GetIsotope()]
        if not dummy_atoms:
            return {}
        core_mol, original_to_core = self._template_core_without_dummy_atoms(template_mol)
        matches = actual_mol.GetSubstructMatches(core_mol)
        if not matches:
            return None
        for match in matches:
            matched_actual_atoms = set(match)
            substituents = {}
            ok = True
            for dummy in dummy_atoms:
                neighbors = list(dummy.GetNeighbors())
                if len(neighbors) != 1:
                    ok = False
                    break
                template_attach_idx = neighbors[0].GetIdx()
                if template_attach_idx not in original_to_core:
                    ok = False
                    break
                actual_attach_idx = match[original_to_core[template_attach_idx]]
                roots = [
                    n.GetIdx()
                    for n in actual_mol.GetAtomWithIdx(actual_attach_idx).GetNeighbors()
                    if n.GetIdx() not in matched_actual_atoms
                ]
                if len(roots) != 1:
                    ok = False
                    break
                root_idx = roots[0]
                atoms = self._fragment_atoms_from_root(actual_mol, root_idx, matched_actual_atoms)
                if not atoms:
                    ok = False
                    break
                substituents[dummy.GetIsotope()] = {"mol": actual_mol, "root": root_idx, "atoms": atoms}
            if ok:
                return substituents
        return None

    def _run_unmapped_rgroup_fallback(self, rxn, reactants) -> List[str]:
        if rxn.GetNumProductTemplates() < 1:
            return []
        substituents = {}
        for template_mol, actual_mol in zip(rxn.GetReactants(), reactants):
            found = self._rgroup_substituents_from_reactant(template_mol, actual_mol)
            if found is None:
                return []
            substituents.update(found)
        products = []
        for product_template in rxn.GetProducts():
            dummy_labels = {}
            for atom in product_template.GetAtoms():
                if atom.GetAtomicNum() != 0 or not atom.GetIsotope():
                    continue
                dummy_labels[atom.GetIdx()] = atom.GetIsotope()
            if not dummy_labels or not all(label in substituents for label in dummy_labels.values()):
                continue
            rw_mol = core.Chem.RWMol()
            product_atom_map = {}
            for atom in product_template.GetAtoms():
                if atom.GetAtomicNum() == 0:
                    continue
                new_atom = core.Chem.Atom(atom)
                for prop in list(new_atom.GetPropNames()):
                    if prop == "molInversionFlag":
                        new_atom.ClearProp(prop)
                product_atom_map[atom.GetIdx()] = rw_mol.AddAtom(new_atom)
            for bond in product_template.GetBonds():
                begin_idx = bond.GetBeginAtomIdx()
                end_idx = bond.GetEndAtomIdx()
                if begin_idx in product_atom_map and end_idx in product_atom_map:
                    rw_mol.AddBond(product_atom_map[begin_idx], product_atom_map[end_idx], bond.GetBondType())

            substituent_atom_maps = {}
            substituent_roots = {}
            for label in sorted(set(dummy_labels.values())):
                substituent = substituents[label]
                actual_mol = substituent["mol"]
                substituent_atom_map = {}
                for atom_idx in sorted(substituent["atoms"]):
                    substituent_atom_map[atom_idx] = rw_mol.AddAtom(core.Chem.Atom(actual_mol.GetAtomWithIdx(atom_idx)))
                for bond in actual_mol.GetBonds():
                    begin_idx = bond.GetBeginAtomIdx()
                    end_idx = bond.GetEndAtomIdx()
                    if begin_idx in substituent_atom_map and end_idx in substituent_atom_map:
                        rw_mol.AddBond(substituent_atom_map[begin_idx], substituent_atom_map[end_idx], bond.GetBondType())
                substituent_atom_maps[label] = substituent_atom_map
                substituent_roots[label] = substituent_atom_map[substituent["root"]]

            def mapped_product_endpoint(atom_idx):
                if atom_idx in product_atom_map:
                    return product_atom_map[atom_idx]
                label = dummy_labels.get(atom_idx)
                if label is None:
                    return None
                return substituent_roots.get(label)

            for bond in product_template.GetBonds():
                begin_idx = bond.GetBeginAtomIdx()
                end_idx = bond.GetEndAtomIdx()
                if begin_idx in product_atom_map and end_idx in product_atom_map:
                    continue
                begin_mapped = mapped_product_endpoint(begin_idx)
                end_mapped = mapped_product_endpoint(end_idx)
                if begin_mapped is None or end_mapped is None or begin_mapped == end_mapped:
                    continue
                if rw_mol.GetBondBetweenAtoms(begin_mapped, end_mapped) is None:
                    rw_mol.AddBond(begin_mapped, end_mapped, bond.GetBondType())
            product = rw_mol.GetMol()
            try:
                core.Chem.SanitizeMol(product)
            except Exception:
                continue
            products.append(core.Chem.MolToSmiles(product, canonical=True))
        return sorted(set(products))

    def _run_custom_reaction_variable_arity(self, grouped: Dict[str, object], rxn) -> str:
        arity = rxn.GetNumReactantTemplates()
        available = list(grouped.get("reactants", []) or [])
        if len(available) < arity:
            raise ValueError(f"Template needs {arity} structural reactant(s); this well has {len(available)}.")

        row_orders = [tuple(available[:arity])]
        if self.custom_reactant_order_var.get().startswith("Automatic"):
            row_orders = list(itertools.permutations(available, arity))

        products = set()
        errors = []
        template = self.custom_template_text.get("1.0", "end").strip()
        is_unmapped_rxn = self._custom_template_is_rxn_block(template) and not self._reaction_has_atom_maps(rxn)
        for ordered_rows in row_orders:
            try:
                canonical = [core.canonical_smiles(row.get("smiles") or (row.get("compound", {}) or {}).get("SMILES", "")) for row in ordered_rows]
                mols = tuple(item[0] for item in canonical)
                smiles = tuple(item[1] for item in canonical)
                generated, _count, sanitize_errors = self._products_from_custom_reaction(rxn, mols)
                if not generated and is_unmapped_rxn:
                    generated = self._run_unmapped_rgroup_fallback(rxn, mols)
                if not generated and is_unmapped_rxn:
                    generated = self._run_unmapped_exact_product_fallback(rxn, smiles)
                products.update(self._finalize_products_for_reactants(generated, ordered_rows))
                errors.extend(sanitize_errors[:1])
            except Exception as exc:
                errors.append(str(exc))

        if len(products) > 1:
            raise ValueError(
                f"Template generated {len(products)} distinct products. Define the intended product explicitly: "
                + " | ".join(sorted(products))
            )
        if products:
            return next(iter(products))
        detail = "; ".join(dict.fromkeys(errors)) or "the template did not match the available reactants"
        raise ValueError(f"No valid product generated for this {arity}-component template: {detail}")

    def _run_custom_reaction(self, grouped: Dict[str, object], rxn) -> str:
        template = self.custom_template_text.get("1.0", "end").strip()
        template_is_rxn_block = self._custom_template_is_rxn_block(template)
        if rxn.GetNumReactantTemplates() in {1, 3}:
            return self._run_custom_reaction_variable_arity(grouped, rxn)
        if rxn.GetNumReactantTemplates() != 2:
            raise ValueError(
                f"Template has {rxn.GetNumReactantTemplates()} reactant template(s); "
                "XinPilot supports one, two, or three structural reactants."
            )
        r1 = grouped.get("reactant1")
        r2 = grouped.get("reactant2")
        if not r1 or not r2:
            raise ValueError(str(grouped.get("status", "Need at least 2 building blocks with SMILES")))
        r1_comp = r1["compound"] or {}
        r2_comp = r2["compound"] or {}
        r1_mol, r1_smi = core.canonical_smiles(r1.get("smiles") or r1_comp.get("SMILES", ""))
        r2_mol, r2_smi = core.canonical_smiles(r2.get("smiles") or r2_comp.get("SMILES", ""))
        reactants = (r1_mol, r2_mol)
        ordered = (
            (r1.get("chemical", "Reactant 1"), r1_smi),
            (r2.get("chemical", "Reactant 2"), r2_smi),
        )
        if self.custom_reactant_order_var.get().startswith("Reactant 2"):
            reactants = (r2_mol, r1_mol)
            ordered = (
                (r2.get("chemical", "Reactant 2"), r2_smi),
                (r1.get("chemical", "Reactant 1"), r1_smi),
            )

        products = []
        product_set_count = 0
        sanitize_errors = []
        used_reverse_order = False
        used_unmapped_exact_fallback = False
        used_unmapped_rgroup_fallback = False
        try:
            products, product_set_count, sanitize_errors = self._products_from_custom_reaction(rxn, reactants)
        except Exception as exc:
            names = f"{ordered[0][0]} [{ordered[0][1]}] + {ordered[1][0]} [{ordered[1][1]}]"
            raise ValueError(f"RDKit could not apply template to {names}: {exc}") from exc

        if not products:
            reverse_reactants = (reactants[1], reactants[0])
            try:
                reverse_products, reverse_count, reverse_errors = self._products_from_custom_reaction(rxn, reverse_reactants)
            except Exception as exc:
                reverse_products, reverse_count, reverse_errors = [], 0, [f"Reverse order RDKit error: {exc}"]
            if reverse_products:
                products = reverse_products
                product_set_count = reverse_count
                sanitize_errors = reverse_errors
                used_reverse_order = True
            elif product_set_count == 0 and reverse_count:
                product_set_count = reverse_count
                sanitize_errors.extend(reverse_errors)
        if (
            not products
            and not self._reaction_has_atom_maps(rxn)
            and template_is_rxn_block
        ):
            products = self._run_unmapped_rgroup_fallback(rxn, reactants)
            used_unmapped_rgroup_fallback = bool(products)
            if not products:
                products = self._run_unmapped_rgroup_fallback(rxn, (reactants[1], reactants[0]))
                used_unmapped_rgroup_fallback = bool(products)
                used_reverse_order = used_reverse_order or bool(products)
        if (
            not products
            and not self._reaction_has_atom_maps(rxn)
            and template_is_rxn_block
        ):
            products = self._run_unmapped_exact_product_fallback(rxn, (ordered[0][1], ordered[1][1]))
            used_unmapped_exact_fallback = bool(products)
            if not products:
                products = self._run_unmapped_exact_product_fallback(rxn, (ordered[1][1], ordered[0][1]))
                used_unmapped_exact_fallback = bool(products)
                used_reverse_order = used_reverse_order or bool(products)
        if not products:
            names = f"{ordered[0][0]} [{ordered[0][1]}] + {ordered[1][0]} [{ordered[1][1]}]"
            if product_set_count == 0:
                if not self._reaction_has_atom_maps(rxn) and template_is_rxn_block:
                    raise ValueError(
                        f"No product generated for {names}. The RXN block has no atom-map numbers, so RDKit cannot "
                        "infer the reaction center directly. For reusable drawings, use R1/R2 groups on the reactants "
                        "and product to show which substituents move, or add atom maps for a fully explicit template."
                    )
                raise ValueError(
                    f"No product generated for {names}. The drawn template did not match these reactants in the selected order."
                )
            detail = "; ".join(sanitize_errors) if sanitize_errors else "RDKit returned product sets, but no usable first product."
            raise ValueError(
                f"No valid product for {names}. Product sets returned: {product_set_count}. Sanitization/detail: {detail}"
            )
        if used_reverse_order:
            self.logw("Used reverse reactant order because the selected order did not generate a product.")
        if used_unmapped_rgroup_fallback:
            self.logw("Used R-group substitution fallback because the drawn RXN block had no atom-map numbers.")
        if used_unmapped_exact_fallback:
            self.logw("Used drawn product fallback because the unmapped RXN block reactants matched the actual reactants.")
        return self._finalize_products_for_reactants(products, (r1, r2))[0]

    def _refresh_custom_preview(self, select_wells: Optional[List[str]] = None):
        self.custom_preview.delete(*self.custom_preview.get_children())
        select_wells = [str(well or "").strip().upper() for well in (select_wells or []) if str(well or "").strip()]
        ids_by_well = {}
        for i, row in enumerate(self._custom_grouped_reaction_rows()):
            well = str(row.get("well", "")).strip().upper()
            r1 = row.get("reactant1") or {}
            r2 = row.get("reactant2") or {}
            r3 = row.get("reactant3") or {}
            custom_product = self._custom_product_for_well(well)
            failure = self.custom_failures.get(well, "")
            status = "Custom product ready" if custom_product else ("Failed - see details" if failure else str(row.get("status", "")))
            self.custom_preview.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    well,
                    self.reaction_names.get(well, "") or f"RXN_{well}",
                    r1.get("chemical", "") if isinstance(r1, dict) else "",
                    r2.get("chemical", "") if isinstance(r2, dict) else "",
                    r3.get("chemical", "") if isinstance(r3, dict) else "",
                    custom_product,
                    status,
                ),
            )
            ids_by_well[well] = str(i)
        selection = [ids_by_well[well] for well in select_wells if well in ids_by_well]
        if not selection and len(ids_by_well) == 1:
            selection = list(ids_by_well.values())
        if selection:
            self.custom_preview.selection_set(selection)
            self.custom_preview.focus(selection[0])
            self.custom_preview.see(selection[0])
        self._on_custom_row_select()

    def _on_custom_row_select(self, _event=None):
        if not hasattr(self, "custom_detail"):
            return
        detail = ""
        sel = self.custom_preview.selection()
        if sel:
            self._load_reaction_name_from_tree(
                self.custom_preview,
                well_column=0,
                name_column=1,
            )
            values = self.custom_preview.item(sel[0], "values")
            if values:
                headers = ("Well", "Reaction name", "Reactant 1", "Reactant 2", "Reactant 3", "Custom product", "Status")
                detail_lines = [
                    f"{header}: {value}"
                    for header, value in zip(headers, values)
                    if str(value).strip()
                ]
                well = str(values[0] or "").strip().upper()
                failure = self.custom_failures.get(well, "")
                if failure:
                    detail_lines.append(f"Full failure: {failure}")
                detail = "\n".join(detail_lines)
        self.custom_detail.configure(state="normal")
        self.custom_detail.delete("1.0", "end")
        if detail:
            self.custom_detail.insert("1.0", detail)
        self.custom_detail.configure(state="disabled")

    def _generate_custom_products(self, selected_only: bool):
        try:
            rxn = self._compile_custom_reaction()
            grouped_rows = self._custom_grouped_reaction_rows()
            indices = range(len(grouped_rows))
            if selected_only:
                sel = self.custom_preview.selection()
                if not sel:
                    messagebox.showwarning("No row selected", "Select one or more rows in the custom template table first.")
                    return
                indices = [int(iid) for iid in sel]

            if self.retained_results_var.get():
                if not messagebox.askyesno("Replace retained results", "Generate custom products from current pushed inputs and clear retained previous products and LCMS results?", parent=self):
                    return
                self._replace_retained_results()

            made = 0
            skipped = []
            touched_wells = []
            previous_rows = {
                _normalize_well(row.get("reaction_well", "")): dict(row)
                for row in self._pyparse_rows()
            }
            previous_rows.update(self.__dict__.get("pending_product_identity_rows", {}))
            for idx in indices:
                grouped = grouped_rows[idx]
                well = str(grouped.get("well", "")).strip().upper()
                touched_wells.append(well)
                try:
                    product = self._run_custom_reaction(grouped, rxn)
                    self.custom_products[well] = {"smiles": product, "source": "custom_template"}
                    self.custom_failures.pop(well, None)
                    made += 1
                except Exception as exc:
                    message = f"{well}: {exc}"
                    # A failed regeneration must not keep displaying or exporting
                    # an earlier template's product as a successful new result.
                    self.custom_products.pop(well, None)
                    self.custom_failures[well] = f"Failed: {exc}"
                    skipped.append(message)

            current_rows = {
                _normalize_well(row.get("reaction_well", "")): row
                for row in self._pyparse_rows()
            }
            for well in touched_wells:
                previous = previous_rows.get(well)
                if previous is not None:
                    product = current_rows.get(well, {}).get("desired product smiles", "")
                    self._on_product_structure_changed(previous, product)
                self.__dict__.get("pending_product_identity_rows", {}).pop(well, None)
            self._refresh_product_details_preview(show_products=self.product_details_generated)
            self._refresh_custom_preview(touched_wells)
            self.logw(f"Custom template generated {made} product(s); skipped {len(skipped)}.")
            for item in skipped:
                self.logw("  " + item)
            csv_message = ""
            if not selected_only:
                output_dir_text = self.custom_output_dir_var.get().strip()
                if output_dir_text:
                    out_path, usage_path, skipped_path, written, csv_skipped = self._write_custom_product_csv()
                    self.logw(f"Wrote custom products: {out_path}")
                    self.logw(f"Wrote custom usage: {usage_path}")
                    self.logw(f"Wrote custom skipped: {skipped_path}")
                    csv_message = f"\nCSV products: {written}\nCSV skipped: {csv_skipped}\n{out_path}"
                else:
                    self.logw("Generated custom products in the GUI only; no custom product CSV folder was selected.")
                    csv_message = "\nCSV: not saved"
            messagebox.showinfo("Custom products", f"Generated: {made}\nSkipped: {len(skipped)}{csv_message}")
        except Exception as exc:
            self.logw(f"ERROR custom template: {exc}")
            messagebox.showerror("Custom template failed", str(exc))

    def _clear_custom_products(self):
        if not self.custom_products and not self.custom_failures:
            return
        if not messagebox.askyesno("Clear custom products", "Remove all custom products and failure messages from this session?"):
            return
        self.custom_products.clear()
        self.custom_failures.clear()
        self._refresh_custom_preview()
        self._refresh_pyparse_preview()

    def _clear_custom_input_reaction(self):
        template = self.custom_template_text.get("1.0", "end-1c").strip()
        queue_has_items = not self._ketcher_template_queue.empty()
        if not (
            template
            or self.custom_products
            or self.custom_failures
            or queue_has_items
            or KETCHER_TEMPLATE_PATH.exists()
        ):
            return
        if not messagebox.askyesno(
            "Clear input reaction",
            "Delete the reaction template stored in XinPilot and all custom products derived from it?\n\n"
            "This removes the custom override so Generate Product Details can use the selected reaction type. "
            "The drawing currently visible in the Ketcher browser will not be changed.",
        ):
            return

        self._stage_product_regeneration()
        self.custom_template_text.delete("1.0", "end")
        self.custom_products.clear()
        self.custom_failures.clear()
        while True:
            try:
                self._ketcher_template_queue.get_nowait()
            except queue.Empty:
                break
        try:
            KETCHER_TEMPLATE_PATH.unlink(missing_ok=True)
        except OSError as exc:
            self.logw(f"WARNING: could not delete stored Ketcher reaction template: {exc}")

        self.product_details_generated = False
        self._refresh_product_details_preview(show_products=False)
        self.logw(
            "Cleared the custom input reaction and its generated products. "
            "The selected reaction type is unchanged and can now be used to generate Product Details."
        )

    def _load_custom_template(self):
        p = filedialog.askopenfilename(filetypes=[("Reaction/template", "*.rxn;*.smarts;*.txt"), ("All files", "*.*")])
        if not p:
            return
        path = Path(p)
        text = path.read_text(encoding="utf-8", errors="replace")
        self.custom_template_text.delete("1.0", "end")
        self.custom_template_text.insert("1.0", text)

    def _save_custom_template(self):
        template = self.custom_template_text.get("1.0", "end").strip()
        default_ext = ".rxn" if self._custom_template_is_rxn_block(template) else ".smarts"
        p = filedialog.asksaveasfilename(defaultextension=default_ext, filetypes=[("Reaction/template", "*.rxn;*.smarts;*.txt"), ("All files", "*.*")])
        if not p:
            return
        Path(p).write_text(template + "\n", encoding="utf-8")

    def _load_ketcher_template(self, rxn_block: str):
        self.custom_template_text.delete("1.0", "end")
        self.custom_template_text.insert("1.0", rxn_block.strip() + "\n")
        self.logw(f"Ketcher reaction template loaded from {KETCHER_TEMPLATE_PATH}")
        self._refresh_custom_preview()

    def _poll_ketcher_templates(self):
        try:
            while True:
                self._load_ketcher_template(self._ketcher_template_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(250, self._poll_ketcher_templates)

    def _ensure_ketcher_server(self) -> int:
        bridge_dir = resource_path("ketcher_bridge/dist")
        index_path = bridge_dir / "index.html"
        if not index_path.exists():
            raise FileNotFoundError(
                "Ketcher bridge is not built. Run `npm install` and `npm run build` in the ketcher_bridge folder."
            )
        if self._ketcher_server is not None and self._ketcher_port:
            return self._ketcher_port

        app = self

        class KetcherBridgeHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(bridge_dir), **kwargs)

            def do_POST(self):
                route = urllib.parse.urlparse(self.path).path
                if route != "/template":
                    self.send_error(404, "Unknown endpoint")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    rxn_block = self.rfile.read(length).decode("utf-8", errors="replace")
                    if not rxn_block.strip():
                        self.send_error(400, "Empty RXN template")
                        return
                    KETCHER_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    KETCHER_TEMPLATE_PATH.write_text(rxn_block.strip() + "\n", encoding="utf-8")
                    app._ketcher_template_queue.put(rxn_block)
                    data = b"RXN sent to XinPilot. Return to XinPilot and generate custom products."
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as exc:
                    self.send_error(500, str(exc))

            def log_message(self, format, *args):
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), KetcherBridgeHandler)
        server.daemon_threads = True
        self._ketcher_server = server
        self._ketcher_port = int(server.server_address[1])
        self._ketcher_thread = threading.Thread(target=server.serve_forever, name="XinPilotKetcherBridge", daemon=True)
        self._ketcher_thread.start()
        self.logw(f"Ketcher sketcher bridge started on http://127.0.0.1:{self._ketcher_port}/")
        return self._ketcher_port

    def _open_sketcher_helper(self):
        try:
            port = self._ensure_ketcher_server()
            webbrowser.open(f"http://127.0.0.1:{port}/")
        except Exception as exc:
            messagebox.showerror("Ketcher sketcher unavailable", str(exc))

    @staticmethod
    def _is_valid_pyparse_well(well: str) -> bool:
        return bool(re.fullmatch(r"[A-Z]\d{1,2}", str(well or "").strip().upper()))

    def _pyparse_rows(self):
        if getattr(self, "retained_results_var", None) is not None and self.retained_results_var.get():
            return [dict(row) for row in self.retained_product_rows]
        self._sync_building_block_identity()
        rows = []
        reaction = None
        if self.product_details_generated:
            try:
                reaction = self._reaction()
            except Exception:
                reaction = None
        normal_by_well = {
            str(grouped.get("well", "")).strip().upper(): grouped
            for grouped in (self._grouped_reaction_rows() if reaction else self._raw_grouped_reaction_rows())
            if str(grouped.get("well", "")).strip()
        }
        custom_by_well = {
            str(grouped.get("well", "")).strip().upper(): grouped
            for grouped in self._custom_grouped_reaction_rows()
            if str(grouped.get("well", "")).strip()
        }
        imported_by_well = {
            str(well).strip().upper(): dict(row)
            for well, row in self.imported_product_details.items()
            if str(well).strip()
        }
        all_wells = sorted(set(normal_by_well) | set(custom_by_well) | set(imported_by_well), key=core.well_key)
        for well in all_wells:
            grouped = normal_by_well.get(well, {"well": well, "status": ""})
            custom_grouped = custom_by_well.get(well, {})
            imported_product = imported_by_well.get(well, {})
            reactant_rows = list(grouped.get("reactants", []) or [])
            custom_product = self._custom_product_for_well(well)
            if custom_product and not reactant_rows:
                reactant_rows = list(custom_grouped.get("reactants", []) or [])
            # LCMS well assignment is explicit.  Falling back to the reaction
            # well silently generated plausible but wrong platemaps after an
            # imported project lost its mapping.
            pyparse_well = self.pyparse_wells.get(well, imported_product.get("pyparse_well", ""))
            status = str(grouped.get("status", ""))
            product = ""
            selectivity_products: List[str] = []
            exact = mw = formula = mh = mna = neg = ""
            reaction_name = (
                self.reaction_names.get(well, "")
                or str(imported_product.get("reaction_name", "") or "").strip()
                or f"RXN_{well}"
            )
            reactant_compounds = [
                (row.get("compound", {}) or {}) if isinstance(row, dict) else {}
                for row in reactant_rows[:3]
            ]
            while len(reactant_compounds) < 3:
                reactant_compounds.append({})
            reactant_smiles = [str(comp.get("SMILES", "") or "") for comp in reactant_compounds]
            try:
                if imported_product.get("desired product smiles"):
                    product = str(imported_product.get("desired product smiles", "") or "").strip()
                    imported_selectivity = imported_product.get("selectivity products", [])
                    if isinstance(imported_selectivity, (list, tuple)):
                        selectivity_products = [str(value).strip() for value in imported_selectivity if str(value).strip()]
                    if not selectivity_products and product:
                        selectivity_products = [product]
                    exact = str(imported_product.get("desired product exact mass", "") or "")
                    mw = str(imported_product.get("desired product mw", "") or "")
                    formula = str(imported_product.get("desired product formula", "") or "")
                    mh = str(imported_product.get("desired product mh", "") or "")
                    mna = str(imported_product.get("desired product mna", "") or "")
                    neg = str(imported_product.get("desired product negative mass", "") or "")
                    if not any([exact, mw, formula, mh, mna, neg]):
                        exact, mw, formula, mh, mna, neg = core.mass_fields(product)
                    if not reactant_rows:
                        status = "Ready (input product details)"
                elif reactant_rows:
                    canonical = [core.canonical_smiles(value) for value in reactant_smiles if value]
                    reactant_smiles[:len(canonical)] = [value for _mol, value in canonical]
                    if custom_product:
                        product = custom_product
                        selectivity_products = [product]
                        status = "Ready (custom product)"
                    elif getattr(self, "custom_failures", {}).get(well):
                        status = self.custom_failures[well]
                    elif reaction:
                        products = list(grouped.get("candidate_products", []) or [])
                        if len(products) == 1:
                            product = products[0]
                            selectivity_products = [product]
                        elif len(products) > 1:
                            if grouped.get("reaction_site_choice") == "all":
                                selectivity_products = sorted(set(products))
                                product = selectivity_products[0]
                                status = f"Ready: keeping all {len(selectivity_products)} possible products"
                            elif self._are_same_mass_selectivity_products(products):
                                selectivity_products = sorted(set(products))
                                product = selectivity_products[0]
                                status = f"Ready: {len(selectivity_products)} possible selectivity products (same LCMS mass)"
                            else:
                                status = f"Ambiguous: {len(products)} products with different formulas or masses; define a custom product"
                        else:
                            status = "No product generated"
                    else:
                        status = "Generate Product Details first"
                    if product:
                        exact, mw, formula, mh, mna, neg = core.mass_fields(product)
            except Exception as exc:
                status = f"Product generation failed: {exc}"

            if not self._is_valid_pyparse_well(pyparse_well):
                status = "Assign a valid LCMS well"
            elif (
                product
                and status.startswith("Ready")
                and "selectivity" not in status.lower()
                and "possible products" not in status.lower()
            ):
                status = "Ready"
            elif product and status.startswith("Need"):
                pass

            for index in range(3):
                prefix = f"reactant {index + 1}"
                if not reactant_smiles[index]:
                    reactant_smiles[index] = str(imported_product.get(f"{prefix} smiles", "") or "")
                if not reactant_compounds[index] and reactant_smiles[index]:
                    reactant_compounds[index] = {
                        "SMILES": reactant_smiles[index],
                        "Name": str(imported_product.get(f"{prefix} name", "") or ""),
                        "ID": str(imported_product.get(f"{prefix} id", "") or ""),
                    }

            row_data = {
                "reaction_name": reaction_name,
                "reaction": "custom_template" if custom_product else (reaction["id"] if reaction else ""),
                "reaction_well": well,
                "pyparse_well": str(pyparse_well).strip().upper(),
                "pyparse_product_index": str(len(rows) + 1),
                "product_id": str(imported_product.get("product_id", "") or reaction_name),
                "desired product smiles": product,
                "selectivity products": selectivity_products or ([product] if product else []),
                "desired product name": str(imported_product.get("desired product name", "") or reaction_name),
                "desired product exact mass": exact,
                "desired product mw": mw,
                "desired product formula": formula,
                "desired product mh": mh,
                "desired product mna": mna,
                "desired product negative mass": neg,
                "status": status,
            }
            if well in self.__dict__.get("product_review_wells", {}):
                row_data["status"] = self.product_review_wells[well]
            for index, comp in enumerate(reactant_compounds, start=1):
                prefix = f"reactant {index}"
                row_data[f"{prefix} smiles"] = reactant_smiles[index - 1]
                row_data[f"{prefix} name"] = comp.get("Name", "") or comp.get("ID", "")
                row_data[f"{prefix} id"] = comp.get("ID", "")
            # PyParse's original schema has one starting-material slot. Keep
            # legacy fields for compatibility; all reactants are also supplied
            # as uniquely named byproduct targets when impurity input is built.
            row_data.update({
                "limiting reactant smiles": row_data["reactant 1 smiles"],
                "limiting reactant name": row_data["reactant 1 name"],
                "limiting reactant id": row_data["reactant 1 id"],
                "excess reactant smiles": row_data["reactant 2 smiles"],
                "excess reactant name": row_data["reactant 2 name"],
                "excess reactant id": row_data["reactant 2 id"],
            })
            rows.append(row_data)
        self._last_product_identity_rows = {_normalize_well(row["reaction_well"]): dict(row) for row in rows}
        return rows

    def _refresh_pyparse_preview(self):
        self.pyparse_preview.delete(*self.pyparse_preview.get_children())
        for i, row in enumerate(self._pyparse_rows()):
            self.pyparse_preview.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    row["reaction_name"],
                    row["reaction_well"],
                    row["pyparse_well"],
                    row["product_id"],
                    self._lcms_target_for_row(row),
                ),
            )
        if hasattr(self, "product_structure_table"):
            self._refresh_product_structure_preview()
        if hasattr(self, "impurity_analysis_table"):
            self._refresh_impurity_previews()
    def _refresh_product_structure_preview(self, reset_selection: bool = True):
        self._save_current_product_structure_manual_fields()
        selected_iid = None
        if not reset_selection:
            sel = self.product_structure_table.selection()
            selected_iid = sel[0] if sel else None
        self.product_structure_table.delete(*self.product_structure_table.get_children())
        for i, row in enumerate(self._pyparse_rows()):
            color = self._product_structure_row_color(row)
            tag = self._product_structure_row_color_tag(color)
            key = self._product_structure_manual_key(row)
            has_biology_hit = bool(self._biology_hits_for_key(key))
            tags = tuple(t for t in (tag or stripe_tag(i), "biology_hit" if has_biology_hit else "") if t)
            reaction_name = str(row.get("reaction_name", "") or "")
            if has_biology_hit:
                reaction_name = f"\u25ce {reaction_name}"
            self.product_structure_table.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    reaction_name,
                    row.get("reaction_well", ""),
                    row.get("pyparse_well", ""),
                ),
                tags=tags,
            )
        if selected_iid and self.product_structure_table.exists(selected_iid):
            self.product_structure_table.selection_set(selected_iid)
            self.product_structure_table.focus(selected_iid)
            self._on_product_structure_select()
        elif reset_selection:
            self.product_structure_label.configure(image="", text="Select a product row")
            if hasattr(self, "product_structure_lcms_label"):
                self.product_structure_lcms_label.configure(image="", text="Generate LCMS Input to create target")
            self.product_structure_current_smiles = ""
            self.product_structure_current_lcms_smiles = ""
            self.product_structure_current_manual_key = ""
            self.product_structure_meta_var.set("")
            self.product_structure_pyparse_purity_var.set("UV254 purity from PyParse: ")
            self.product_structure_modified_purity_var.set("UV254 purity from Modified PyParse: ")
            self.product_structure_manual_purity_var.set("")
            self._sync_product_structure_uv_source_for_row(None)
            self._set_product_structure_comment_text("")
            self._render_floating_product_structure()
            self._clear_product_structure_trace_display()
            self._sync_biology_hit_dialog_to_row(None)
        if hasattr(self, "product_impurity_table"):
            self._refresh_product_impurity_preview(reset_selection=reset_selection)

    def _impurity_reaction_rows(self) -> List[Dict[str, object]]:
        product_rows = {
            _normalize_well(row.get("reaction_well", "")): row
            for row in self._pyparse_rows()
        }
        grouped: Dict[str, Dict[str, object]] = {}
        for impurity in self._included_impurity_rows():
            reaction_well = _normalize_well(impurity.get("reaction_well", ""))
            if not reaction_well:
                continue
            entry = grouped.setdefault(reaction_well, {
                "reaction_name": impurity.get("reaction_name", ""),
                "reaction_well": reaction_well,
                "pyparse_well": impurity.get("pyparse_well", ""),
                "product_row": product_rows.get(reaction_well, {}),
                "impurities": [],
            })
            entry["impurities"].append(impurity)
        return [grouped[well] for well in sorted(grouped, key=core.well_key)]

    def _refresh_product_impurity_preview(self, reset_selection: bool = True):
        if not hasattr(self, "product_impurity_table"):
            return
        selected_iid = None
        if not reset_selection:
            selection = self.product_impurity_table.selection()
            selected_iid = selection[0] if selection else None
        self.product_impurity_table.delete(*self.product_impurity_table.get_children())
        for index, row in enumerate(self._impurity_reaction_rows()):
            self.product_impurity_table.insert("", "end", iid=str(index), values=(
                row.get("reaction_name", ""),
                row.get("reaction_well", ""),
                row.get("pyparse_well", ""),
            ))
        if selected_iid and self.product_impurity_table.exists(selected_iid):
            self.product_impurity_table.selection_set(selected_iid)
            self.product_impurity_table.focus(selected_iid)
            self._on_product_impurity_select()

    def _bind_product_structure_detach_events(self, widget):
        widget.bind("<ButtonPress-1>", self._on_product_structure_drag_start, add="+")
        widget.bind("<B1-Motion>", self._on_product_structure_drag_motion, add="+")
        widget.bind("<Double-Button-1>", self._on_product_structure_double_click, add="+")
        for child in widget.winfo_children():
            self._bind_product_structure_detach_events(child)

    def _on_product_structure_drag_start(self, event):
        if isinstance(event.widget, (ttk.Button, ttk.Entry, tk.Text)):
            self.product_structure_drag_start = None
            return
        self.product_structure_drag_start = (event.x_root, event.y_root)

    def _on_product_structure_drag_motion(self, event):
        if self.product_structure_float_window is not None:
            return
        start = self.product_structure_drag_start
        if start is None:
            return
        if abs(event.x_root - start[0]) < 12 and abs(event.y_root - start[1]) < 12:
            return
        self.product_structure_drag_start = None
        self._detach_product_structure_preview(event.x_root, event.y_root)

    def _on_product_structure_double_click(self, event):
        if self.product_structure_float_window is not None or isinstance(event.widget, (ttk.Button, ttk.Entry, tk.Text)):
            return
        self._detach_product_structure_preview(event.x_root, event.y_root)

    def _dock_product_structure_preview(self, _event=None):
        self._save_current_product_structure_manual_fields()
        window = self.product_structure_float_window
        if window is not None:
            self.product_structure_float_window = None
            self.product_structure_float_pin_button = None
            self.product_structure_float_manual_comment_text = None
            try:
                window.attributes("-topmost", False)
                window.destroy()
            except tk.TclError:
                pass
        if hasattr(self, "product_structure_info_box") and not self.product_structure_info_box.winfo_ismapped():
            self.product_structure_info_box.pack(fill="x", before=self.product_structure_trace_box)
        self._load_product_structure_manual_fields(self._selected_product_structure_row())
        if self.product_summary_mode == "impurity":
            selected_impurities = self._selected_product_impurity_row()
            self._render_impurity_structures(list((selected_impurities or {}).get("impurities", []) or []))
        elif self.product_summary_mode == "product_selectivity":
            products = [value.strip() for value in self.product_structure_current_smiles.splitlines() if value.strip()]
            self._render_product_structures(products)
        else:
            self._render_product_structure(self.product_structure_current_smiles)

    def _sync_product_structure_pin(self):
        window = self.product_structure_float_window
        if window is None:
            return
        pinned = bool(self.product_structure_float_pin_var.get())
        try:
            window.attributes("-topmost", pinned)
            window.title("Structure Preview - Pinned" if pinned else "Structure Preview")
            if pinned:
                window.lift()
        except tk.TclError:
            pass

    def _sync_product_structure_detail_wraps(self, available_width: int):
        available_width = max(320, int(available_width or self.product_structure_preview_width))
        meta_wrap = max(260, available_width - 36)
        left_wrap = max(220, int((available_width - 72) * 0.56))
        for attr, wrap in (
            ("product_structure_meta_label", meta_wrap),
            ("product_structure_float_meta_label", meta_wrap),
            ("product_structure_pyparse_purity_label", left_wrap),
            ("product_structure_modified_purity_label", left_wrap),
            ("product_structure_float_pyparse_purity_label", left_wrap),
            ("product_structure_float_modified_purity_label", left_wrap),
        ):
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    widget.configure(wraplength=wrap)
                except tk.TclError:
                    pass

    def _detach_product_structure_preview(self, x_root: Optional[int] = None, y_root: Optional[int] = None):
        self._save_current_product_structure_manual_fields()
        if self.product_structure_float_window is not None:
            try:
                self.product_structure_float_window.lift()
                self.product_structure_float_window.focus_force()
            except tk.TclError:
                pass
            return
        if x_root is None or y_root is None:
            try:
                x_root = self.product_structure_info_box.winfo_rootx() + 80
                y_root = self.product_structure_info_box.winfo_rooty() + 30
            except tk.TclError:
                x_root = self.winfo_rootx() + 120
                y_root = self.winfo_rooty() + 120
        if hasattr(self, "product_structure_info_box"):
            self.product_structure_info_box.pack_forget()
        window = tk.Toplevel(self)
        self.product_structure_float_window = window
        window.title("Structure Preview")
        window.geometry(f"920x430+{max(0, x_root - 80)}+{max(0, y_root - 30)}")
        window.minsize(640, 260)
        window.resizable(True, True)
        window.protocol("WM_DELETE_WINDOW", self._dock_product_structure_preview)
        window.bind("<Double-Button-1>", self._dock_product_structure_preview, add="+")

        body = ttk.Frame(window, padding=8)
        body.pack(fill="both", expand=True)
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)
        tools = ttk.Frame(body)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tools.grid_columnconfigure(0, weight=1)
        ttk.Button(
            tools,
            text="Copy SMILES",
            command=self._copy_current_product_structure_smiles,
        ).grid(row=0, column=1, sticky="e", padx=(0, 6))
        self.product_structure_float_pin_button = ttk.Checkbutton(
            tools,
            text="Pin",
            variable=self.product_structure_float_pin_var,
            command=self._sync_product_structure_pin,
        )
        self.product_structure_float_pin_button.grid(row=0, column=2, sticky="e")
        self.product_structure_float_label = ttk.Label(
            body,
            text="Select a product row",
            anchor="center",
            background="#ffffff",
            relief="solid",
        )
        self.product_structure_float_label.grid(row=1, column=0, sticky="nsew")
        self.product_structure_float_label.bind("<Double-Button-1>", self._dock_product_structure_preview, add="+")
        meta = ttk.Label(body, textvariable=self.product_structure_meta_var, wraplength=880, justify="left")
        self.product_structure_float_meta_label = meta
        meta.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        meta.bind("<Double-Button-1>", self._dock_product_structure_preview, add="+")

        detail = ttk.Frame(body)
        detail.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        detail.grid_columnconfigure(0, weight=3, minsize=340)
        detail.grid_columnconfigure(1, weight=2, minsize=260)
        left_detail = ttk.Frame(detail)
        left_detail.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        manual_detail = ttk.Frame(detail)
        manual_detail.grid(row=0, column=1, sticky="nsew")
        manual_detail.grid_columnconfigure(2, weight=1)

        left_detail.grid_columnconfigure(1, weight=1)
        ttk.Radiobutton(
            left_detail,
            variable=self.product_structure_uv_source_var,
            value="pyparse",
            command=self._set_current_product_structure_uv_source,
        ).grid(row=0, column=0, sticky="nw", padx=(0, 4))
        pyparse = ttk.Label(left_detail, textvariable=self.product_structure_pyparse_purity_var, wraplength=360, justify="left")
        self.product_structure_float_pyparse_purity_label = pyparse
        pyparse.grid(row=0, column=1, sticky="ew")
        pyparse.bind("<Double-Button-1>", self._dock_product_structure_preview, add="+")
        ttk.Radiobutton(
            left_detail,
            variable=self.product_structure_uv_source_var,
            value="modified",
            command=self._set_current_product_structure_uv_source,
        ).grid(row=1, column=0, sticky="nw", padx=(0, 4))
        modified = ttk.Label(left_detail, textvariable=self.product_structure_modified_purity_var, wraplength=360, justify="left")
        self.product_structure_float_modified_purity_label = modified
        modified.grid(row=1, column=1, sticky="ew")
        modified.bind("<Double-Button-1>", self._dock_product_structure_preview, add="+")
        ttk.Button(left_detail, text="Generate Heat Map", command=self._generate_product_structure_heat_maps).grid(
            row=2,
            column=1,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Radiobutton(
            manual_detail,
            variable=self.product_structure_uv_source_var,
            value="manual",
            command=self._set_current_product_structure_uv_source,
        ).grid(row=0, column=0, sticky="w", padx=(0, 4), pady=(0, 4))
        ttk.Label(manual_detail, text="Purity by manual:").grid(row=0, column=1, sticky="w", padx=(0, 6), pady=(0, 4))
        manual_entry = ttk.Entry(manual_detail, textvariable=self.product_structure_manual_purity_var, width=14)
        manual_entry.grid(row=0, column=2, sticky="ew", pady=(0, 4))
        ttk.Label(manual_detail, text="Comments:").grid(row=1, column=1, sticky="nw", padx=(0, 6))
        self.product_structure_float_manual_comment_text = tk.Text(manual_detail, height=3, width=32, wrap="word")
        self.product_structure_float_manual_comment_text.grid(row=1, column=2, sticky="ew")
        for widget in (manual_entry, self.product_structure_float_manual_comment_text):
            widget.bind("<FocusOut>", self._save_current_product_structure_manual_fields, add="+")
            widget.bind("<KeyRelease>", self._save_current_product_structure_manual_fields, add="+")
        self._load_product_structure_manual_fields(self._selected_product_structure_row())
        self._sync_product_structure_pin()
        self._sync_product_structure_detail_wraps(920)

        def _resize_floating_structure(event):
            if event.widget is window:
                wrap = max(280, event.width - 24)
                self._sync_product_structure_detail_wraps(wrap)
                self._render_floating_product_structure()

        window.bind("<Configure>", _resize_floating_structure, add="+")
        self._render_floating_product_structure()

    def _render_structure_to_label(self, label, smiles: str, width: int, height: int, cache: Dict[Tuple[str, int, int], ImageTk.PhotoImage]):
        smiles = (smiles or "").strip()
        if not smiles:
            label.configure(image="", text="No product SMILES")
            return None
        width = max(180, int(width))
        height = max(120, int(height))
        cache_key = (smiles, width, height)
        cached = cache.get(cache_key)
        if cached is not None:
            label.configure(image=cached, text="")
            return cached
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ValueError("Invalid SMILES")
            img = Draw.MolToImage(mol, size=(width, height), fitImage=True).convert("RGBA")
            photo = ImageTk.PhotoImage(img)
            cache[cache_key] = photo
            label.configure(image=photo, text="")
            return photo
        except Exception:
            label.configure(image="", text="Structure preview unavailable")
            return None

    def _render_floating_product_structure(self):
        window = self.product_structure_float_window
        label = getattr(self, "product_structure_float_label", None)
        if window is None or label is None:
            return
        if self.product_summary_mode == "impurity":
            self._render_floating_impurity_structures()
            return
        if self.product_summary_mode == "product_selectivity":
            self._render_floating_selectivity_products()
            return
        width = max(180, label.winfo_width() - 16)
        height = max(120, label.winfo_height() - 16)
        self.product_structure_float_img = self._render_structure_to_label(
            label,
            self.product_structure_current_smiles,
            width,
            height,
            self.product_structure_float_cache,
        )

    def _render_product_structure(self, smiles: str):
        self._set_product_structure_comparison_layout(impurity_mode=False)
        self.product_summary_mode = "product"
        smiles = (smiles or "").strip()
        self.product_structure_current_smiles = smiles
        self.product_structure_img = self._render_structure_to_label(
            self.product_structure_label,
            smiles,
            max(180, (self.product_structure_preview_width - 36) // 2),
            self.product_structure_preview_height,
            self.product_structure_cache,
        )
        self._render_floating_product_structure()

    def _render_lcms_target_structure(self, smiles: str):
        smiles = str(smiles or "").strip()
        self.product_structure_current_lcms_smiles = smiles
        if not hasattr(self, "product_structure_lcms_label"):
            return
        if not smiles:
            self.product_structure_lcms_label.configure(
                image="",
                text="Generate LCMS Input to create target",
            )
            return
        self.product_structure_lcms_img = self._render_structure_to_label(
            self.product_structure_lcms_label,
            smiles,
            max(180, (self.product_structure_preview_width - 36) // 2),
            self.product_structure_preview_height,
            self.product_structure_lcms_cache,
        )

    def _render_product_structures(self, products: List[str]):
        self._set_product_structure_comparison_layout(impurity_mode=False)
        unique = []
        valid = []
        for product in products:
            smiles = str(product or "").strip()
            if not smiles or smiles in unique:
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                unique.append(smiles)
                valid.append(mol)
        if len(unique) <= 1:
            self._render_product_structure(unique[0] if unique else "")
            return
        self.product_summary_mode = "product_selectivity"
        self.product_structure_current_smiles = "\n".join(unique)
        width = max(360, self._product_structure_trace_width() - 24)
        columns = 2 if width >= 480 else 1
        sub_width = max(180, width // columns)
        sub_height = 190
        signature = "|".join(unique)
        cache_key = (signature, width, sub_height)
        photo = self.product_selectivity_structure_cache.get(cache_key)
        if photo is None:
            image = Draw.MolsToGridImage(
                valid,
                molsPerRow=columns,
                subImgSize=(sub_width, sub_height),
                legends=[f"Possible product {index}" for index in range(1, len(valid) + 1)],
                useSVG=False,
            ).convert("RGBA")
            photo = ImageTk.PhotoImage(image)
            self.product_selectivity_structure_cache[cache_key] = photo
        self.product_structure_img = photo
        self.product_structure_label.configure(image=photo, text="")
        self._render_floating_selectivity_products(unique)

    def _render_floating_selectivity_products(self, products: Optional[List[str]] = None):
        window = self.product_structure_float_window
        label = getattr(self, "product_structure_float_label", None)
        if window is None or label is None or self.product_summary_mode != "product_selectivity":
            return
        if products is None:
            products = [value.strip() for value in self.product_structure_current_smiles.splitlines() if value.strip()]
        mols = [Chem.MolFromSmiles(smiles) for smiles in products]
        mols = [mol for mol in mols if mol is not None]
        if not mols:
            label.configure(image="", text="No product structures available")
            return
        width = max(360, label.winfo_width() - 16)
        columns = 2 if width >= 520 else 1
        sub_width = max(180, width // columns)
        image = Draw.MolsToGridImage(
            mols,
            molsPerRow=columns,
            subImgSize=(sub_width, 190),
            legends=[f"Possible product {index}" for index in range(1, len(mols) + 1)],
            useSVG=False,
        ).convert("RGBA")
        self.product_structure_float_img = ImageTk.PhotoImage(image)
        label.configure(image=self.product_structure_float_img, text="")

    def _render_impurity_structures(self, impurities: List[Dict[str, str]]):
        self._set_product_structure_comparison_layout(impurity_mode=True)
        self.product_summary_mode = "impurity"
        valid = []
        for impurity in impurities:
            mol = Chem.MolFromSmiles(str(impurity.get("smiles", "") or ""))
            if mol is not None:
                valid.append((mol, impurity))
        self.product_structure_current_smiles = "\n".join(
            str(impurity.get("smiles", "") or "") for _, impurity in valid
        )
        if not valid:
            self.product_structure_label.configure(image="", text="No impurity structures available")
            self.product_structure_img = None
            self._render_floating_product_structure()
            return
        width = max(360, self._product_structure_trace_width() - 24)
        columns = 2 if width >= 480 else 1
        sub_width = max(180, width // columns)
        sub_height = 175
        signature = "|".join(
            f"{impurity.get('label', '')}:{impurity.get('smiles', '')}" for _, impurity in valid
        )
        cache_key = (signature, width, sub_height)
        photo = self.impurity_structure_cache.get(cache_key)
        if photo is None:
            legends = [
                f"{impurity.get('label', '')}: {impurity.get('category', '')}"
                for _, impurity in valid
            ]
            image = Draw.MolsToGridImage(
                [mol for mol, _ in valid],
                molsPerRow=columns,
                subImgSize=(sub_width, sub_height),
                legends=legends,
                useSVG=False,
            ).convert("RGBA")
            photo = ImageTk.PhotoImage(image)
            self.impurity_structure_cache[cache_key] = photo
        self.product_structure_img = photo
        self.product_structure_label.configure(image=photo, text="")
        self._render_floating_impurity_structures(valid)

    def _set_product_structure_comparison_layout(self, *, impurity_mode: bool):
        """Give impurity grids the full preview width and restore product comparison afterward."""
        required = (
            "product_structure_heading",
            "product_structure_lcms_heading",
            "product_structure_label",
            "product_structure_lcms_label",
        )
        if not all(hasattr(self, attr) for attr in required):
            return
        if impurity_mode:
            self.product_structure_heading.configure(text="Potential impurity structures")
            self.product_structure_heading.grid_configure(columnspan=2)
            self.product_structure_label.grid_configure(columnspan=2)
            self.product_structure_lcms_heading.grid_remove()
            self.product_structure_lcms_label.grid_remove()
            return
        self.product_structure_heading.configure(text="Product Details structure")
        self.product_structure_heading.grid_configure(columnspan=1)
        self.product_structure_label.grid_configure(columnspan=1)
        self.product_structure_lcms_heading.grid()
        self.product_structure_lcms_label.grid()

    def _render_floating_impurity_structures(self, valid=None):
        window = self.product_structure_float_window
        label = getattr(self, "product_structure_float_label", None)
        if window is None or label is None or self.product_summary_mode != "impurity":
            return
        if valid is None:
            rows = self._selected_product_impurity_row()
            valid = []
            for impurity in (rows or {}).get("impurities", []):
                mol = Chem.MolFromSmiles(str(impurity.get("smiles", "") or ""))
                if mol is not None:
                    valid.append((mol, impurity))
        if not valid:
            label.configure(image="", text="No impurity structures available")
            return
        width = max(360, label.winfo_width() - 16)
        columns = 2 if width >= 520 else 1
        sub_width = max(180, width // columns)
        image = Draw.MolsToGridImage(
            [mol for mol, _ in valid],
            molsPerRow=columns,
            subImgSize=(sub_width, 190),
            legends=[f"{item.get('label', '')}: {item.get('category', '')}" for _, item in valid],
            useSVG=False,
        ).convert("RGBA")
        self.product_structure_float_img = ImageTk.PhotoImage(image)
        label.configure(image=self.product_structure_float_img, text="")

    def _on_product_structure_select(self, _event=None):
        self._save_current_product_structure_manual_fields()
        sel = self.product_structure_table.selection()
        if not sel:
            return
        rows = self._pyparse_rows()
        idx = int(sel[0])
        if not (0 <= idx < len(rows)):
            return
        row = rows[idx]
        smiles = row.get("desired product smiles", "")
        reaction_well = _normalize_well(row.get("reaction_well", ""))
        lcms_target = str(self.lcms_target_smiles_by_well.get(reaction_well, "") or "").strip()
        selectivity_products = list(row.get("selectivity products", []) or [])
        exact_mass = self._format_mass_2dp(row.get("desired product exact mass", ""))
        biology_hits = self._biology_hit_summary_for_row(row)
        biology_text = f"   Biology hit: {biology_hits}" if biology_hits else "   Biology hit: None"
        selectivity_text = (
            f"   Possible selectivity products: {len(selectivity_products)}"
            if len(selectivity_products) > 1 else ""
        )
        calculated_mz = self._structure_preview_mz(smiles, row.get("desired product exact mass", ""))
        mz_text = self._format_mz(calculated_mz)
        mz_line = f"\nm/z: {mz_text}" if mz_text else ""
        lcms_line = "\nLCMS target: not generated"
        if lcms_target:
            try:
                target_exact_raw = core.mass_fields(lcms_target)[0]
                target_exact = self._format_mass_2dp(target_exact_raw)
            except Exception:
                target_exact_raw = ""
                target_exact = "N/A"
            lcms_line = f"\nLCMS target exact mass: {target_exact or 'N/A'}"
            target_mz = self._lcms_target_mz_text(lcms_target, target_exact_raw)
            if target_mz:
                lcms_line += f"\nLCMS target m/z: {target_mz}"
        self.product_structure_meta_var.set(
            f"RXN name: {row.get('reaction_name', '')}   "
            f"RXN well: {row.get('reaction_well', '')}   "
            f"LCMS Well: {row.get('pyparse_well', '')}\n"
            f"Exact mass: {exact_mass or 'N/A'}{mz_line}{lcms_line}"
            f"{selectivity_text}{biology_text}"
        )
        self._refresh_product_structure_purity_display(row)
        self._sync_product_structure_uv_source_for_row(row)
        self._load_product_structure_manual_fields(row)
        self._refresh_product_structure_trace_display(row)
        if len(selectivity_products) > 1:
            self._render_product_structures(selectivity_products)
        else:
            self._render_product_structure(smiles)
        self._render_lcms_target_structure(lcms_target)
        self._sync_biology_hit_dialog_to_row(row)

    def _selected_product_impurity_row(self) -> Optional[Dict[str, object]]:
        if not hasattr(self, "product_impurity_table"):
            return None
        selection = self.product_impurity_table.selection()
        if not selection:
            return None
        try:
            index = int(selection[0])
        except (ValueError, TypeError):
            return None
        rows = self._impurity_reaction_rows()
        return rows[index] if 0 <= index < len(rows) else None

    def _on_product_impurity_select(self, _event=None):
        self._save_current_product_structure_manual_fields()
        selected = self._selected_product_impurity_row()
        if selected is None:
            return
        impurities = list(selected.get("impurities", []) or [])
        detail_lines = []
        for impurity in impurities:
            calculated_mz = self._structure_preview_mz(
                impurity.get("smiles", ""), impurity.get("exact_mass", "")
            )
            formatted_mz = self._format_mz(calculated_mz)
            mz_text = f"; m/z: {formatted_mz}" if formatted_mz else ""
            detail_lines.append(
                f"{impurity.get('label', '')}: "
                f"exact mass {self._format_mass_2dp(impurity.get('exact_mass', '')) or 'N/A'}{mz_text}"
            )
        self.product_structure_meta_var.set(
            f"RXN name: {selected.get('reaction_name', '')}   "
            f"RXN well: {selected.get('reaction_well', '')}   "
            f"LCMS Well: {selected.get('pyparse_well', '')}\n"
            f"Potential impurity targets: {len(impurities)}\n" + "\n".join(detail_lines)
        )
        product_row = dict(selected.get("product_row", {}) or {})
        self._refresh_product_structure_purity_display(product_row)
        self.product_structure_current_manual_key = ""
        self.product_structure_manual_purity_var.set("")
        self._set_product_structure_comment_text("")
        self._sync_biology_hit_dialog_to_row(None)
        self._render_impurity_structures(impurities)
        self._refresh_impurity_trace_display(selected)

    @staticmethod
    def _product_summary_rows_match(left: Optional[Dict[str, object]], right: Optional[Dict[str, object]]) -> bool:
        if not left or not right:
            return False
        left_reaction_well = _normalize_well(left.get("reaction_well", ""))
        right_reaction_well = _normalize_well(right.get("reaction_well", ""))
        if left_reaction_well and right_reaction_well:
            return left_reaction_well == right_reaction_well
        left_lcms_well = _normalize_well(left.get("pyparse_well", ""))
        right_lcms_well = _normalize_well(right.get("pyparse_well", ""))
        return bool(left_lcms_well and left_lcms_well == right_lcms_well)

    @staticmethod
    def _format_mass_2dp(value: object) -> str:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value or "")

    def _select_matching_product_summary_row(self, tree: ttk.Treeview, rows: List[Dict[str, object]], source_row: Optional[Dict[str, object]]) -> bool:
        for index, row in enumerate(rows):
            if not self._product_summary_rows_match(source_row, row):
                continue
            iid = str(index)
            if not tree.exists(iid):
                return False
            tree.selection_set(iid)
            tree.focus(iid)
            tree.see(iid)
            return True
        return False

    def _on_product_summary_table_changed(self, _event=None):
        """Refresh the shared preview without discarding either table's selection."""
        if not hasattr(self, "product_summary_tables"):
            return
        try:
            active_tab = self.product_summary_tables.tab("current", "text")
        except tk.TclError:
            return

        if active_tab == "Impurities":
            source_row = self._selected_product_structure_row()
            self.product_impurity_table.selection_remove(*self.product_impurity_table.selection())
            self._select_matching_product_summary_row(
                self.product_impurity_table,
                self._impurity_reaction_rows(),
                source_row,
            )
            if self.product_impurity_table.selection():
                self._on_product_impurity_select()
            return

        source_row = self._selected_product_impurity_row()
        self.product_structure_table.selection_remove(*self.product_structure_table.selection())
        self._select_matching_product_summary_row(
            self.product_structure_table,
            self._pyparse_rows(),
            source_row,
        )
        if self.product_structure_table.selection():
            self._on_product_structure_select()

    def _refresh_product_structure_purity_display(self, row: Optional[Dict[str, object]] = None):
        if row is None:
            sel = self.product_structure_table.selection() if hasattr(self, "product_structure_table") else ()
            if sel:
                rows = self._pyparse_rows()
                idx = int(sel[0])
                if 0 <= idx < len(rows):
                    row = rows[idx]
        well = _normalize_well((row or {}).get("pyparse_well", ""))
        pyparse_value = self._product_structure_purity_for_row(row or {}, "pyparse")
        if self._analysis_is_invalidated(row or {}, "pyparse"):
            pyparse_value = "Reanalysis required (product/target edited)"
        modified_value = self._modified_pyparse_purity_display_for_row(row or {})
        self.product_structure_pyparse_purity_var.set(f"UV254 purity from PyParse: {pyparse_value}")
        self.product_structure_modified_purity_var.set(f"UV254 purity from Modified PyParse: {modified_value}")

    def _clear_product_structure_trace_display(self):
        self._peak_unbind()
        if not hasattr(self, "product_structure_trace_widgets"):
            return
        for lbl in self.product_structure_trace_widgets:
            lbl.configure(image="", text="")
        self.product_structure_trace_images.clear()

    def _product_structure_trace_width(self) -> int:
        canvas = getattr(self, "product_structure_preview_canvas", None)
        if canvas is None:
            return self.product_structure_preview_width
        width = canvas.winfo_width()
        if width <= 1:
            return self.product_structure_preview_width
        return max(320, width - 36)

    def _selected_product_structure_row(self) -> Optional[Dict[str, object]]:
        if not hasattr(self, "product_structure_table"):
            return None
        sel = self.product_structure_table.selection()
        if not sel:
            return None
        rows = self._pyparse_rows()
        try:
            idx = int(sel[0])
        except Exception:
            return None
        if 0 <= idx < len(rows):
            return rows[idx]
        return None

    def _graph_image_dirs(self, output_dir: Path) -> List[Path]:
        graph_dirs: List[Path] = []
        direct_graphs = output_dir / "graphs"
        if direct_graphs.exists():
            graph_dirs.append(direct_graphs)
        try:
            for child in output_dir.iterdir():
                child_graphs = child / "graphs"
                if child_graphs.is_dir():
                    graph_dirs.append(child_graphs)
        except Exception:
            pass
        if not graph_dirs:
            graph_dirs.append(output_dir)
        return sorted(set(graph_dirs), key=lambda p: p.stat().st_mtime, reverse=True)

    @staticmethod
    def _same_smiles(left: object, right: object) -> bool:
        left_text = str(left or "").strip()
        right_text = str(right or "").strip()
        if not left_text or not right_text:
            return False
        try:
            left_mol = Chem.MolFromSmiles(left_text)
            right_mol = Chem.MolFromSmiles(right_text)
            if left_mol is not None and right_mol is not None:
                return Chem.MolToSmiles(left_mol) == Chem.MolToSmiles(right_mol)
        except Exception:
            pass
        return left_text == right_text

    def _pyparse_product_trace_token(
        self,
        output_dir: Optional[Path],
        row: Dict[str, object],
        well: str,
    ) -> str:
        if output_dir is None or not output_dir.exists():
            return ""
        target_smiles = self._lcms_target_for_row(row)
        well = _normalize_well(well)
        if not target_smiles or not well:
            return ""
        for path in _nearby_named_files(output_dir, "compoundtable.csv"):
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as fh:
                    for table_row in csv.DictReader(fh):
                        if not self._same_smiles(table_row.get("g_smiles", ""), target_smiles):
                            continue
                        table_wells = set()
                        table_well = _normalize_well(table_row.get("best_well", ""))
                        if table_well:
                            table_wells.add(table_well)
                        purity_by_well = str(table_row.get("purity_by_well", "") or "").strip()
                        if purity_by_well:
                            try:
                                parsed = ast.literal_eval(purity_by_well)
                            except Exception:
                                parsed = {}
                            if isinstance(parsed, dict):
                                table_wells.update(_normalize_well(key) for key in parsed.keys())
                        if well in table_wells:
                            return str(table_row.get("name", "") or "").strip()
            except Exception:
                continue
        return ""

    @staticmethod
    def _structure_preview_mz(smiles: object, exact_mass: object = "") -> Dict[str, List[float]]:
        """Calculate structure-reference ES-/ES+ m/z, including major Cl/Br isotopes."""
        mol = Chem.MolFromSmiles(str(smiles or ""))
        if mol is None:
            return {}
        try:
            base_mass = float(exact_mass)
        except (TypeError, ValueError):
            try:
                base_mass = float(core.mass_fields(Chem.MolToSmiles(mol))[0])
            except Exception:
                return {}

        isotope_probabilities = {0.0: 1.0}
        isotope_data = {
            "Cl": (0.2422, 1.99705),
            "Br": (0.4931, 1.99795),
        }
        for atom in mol.GetAtoms():
            isotope = isotope_data.get(atom.GetSymbol())
            if isotope is None:
                continue
            heavy_fraction, mass_shift = isotope
            light_fraction = 1.0 - heavy_fraction
            updated: Dict[float, float] = {}
            for offset, abundance in isotope_probabilities.items():
                updated[offset] = updated.get(offset, 0.0) + abundance * light_fraction
                heavy_offset = round(offset + mass_shift, 5)
                updated[heavy_offset] = updated.get(heavy_offset, 0.0) + abundance * heavy_fraction
            isotope_probabilities = updated

        maximum = max(isotope_probabilities.values(), default=1.0)
        neutral_masses = [
            base_mass + offset
            for offset, abundance in sorted(isotope_probabilities.items())
            if abundance >= maximum * 0.20
        ]
        return {
            "minus": [round(mass - core.PROTON, 2) for mass in neutral_masses],
            "plus": [round(mass + core.PROTON, 2) for mass in neutral_masses],
        }

    @staticmethod
    def _format_mz(mz_values: Dict[str, object]) -> str:
        parts = []
        minus = list(mz_values.get("minus", []) or [])
        plus = list(mz_values.get("plus", []) or [])
        if minus:
            parts.append("ES− " + ", ".join(f"{float(value):.2f}" for value in minus))
        if plus:
            parts.append("ES+ " + ", ".join(f"{float(value):.2f}" for value in plus))
        return "; ".join(parts)

    @classmethod
    def _lcms_target_mz_text(cls, smiles: object, exact_mass: object = "") -> str:
        """Format expected m/z from the structure actually sent for LCMS analysis."""
        mol = Chem.MolFromSmiles(str(smiles or ""))
        if mol is None:
            return ""
        formal_charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
        if formal_charge == 0:
            return cls._format_mz(cls._structure_preview_mz(smiles, exact_mass))
        try:
            mass = float(exact_mass)
        except (TypeError, ValueError):
            try:
                mass = float(core.mass_fields(Chem.MolToSmiles(mol))[0])
            except Exception:
                return ""
        charge = abs(formal_charge)
        polarity = "ES+" if formal_charge > 0 else "ES-"
        ion_label = f"[M]{'+' if formal_charge > 0 else '-'}" if charge == 1 else (
            f"[M]{charge}{'+' if formal_charge > 0 else '-'}"
        )
        return f"{polarity} {ion_label} {mass / charge:.2f}"

    def _find_product_trace_path(
        self,
        output_dir: Optional[Path],
        row: Dict[str, object],
        suffix: str,
        *,
        prefer_uv254: bool = False,
        avoid_uv254: bool = False,
        well_only: bool = False,
        original_pyparse: bool = False,
    ) -> Optional[Path]:
        if output_dir is None or not output_dir.exists():
            return None
        graph_dirs = self._graph_image_dirs(output_dir)
        if not graph_dirs:
            return None
        product_tokens = []
        product_index = str(row.get("pyparse_product_index", "") or "").strip()
        if original_pyparse:
            if not product_index or well_only:
                return None
            product_tokens.append(f"Product{product_index}")
        elif product_index and not well_only:
            product_tokens.append(f"Product{product_index}")
        if not well_only and not original_pyparse:
            product_tokens.extend([
                row.get("reaction_name", ""),
                row.get("product_id", ""),
                row.get("desired product name", ""),
            ])
        suffix = _safe_pyparse_graph_token(suffix)
        extensions = (".jpg", ".jpeg", ".png")
        # Product Summary must only accept an exact chromatogram name.  Broad
        # well/name scoring previously allowed heatmaps and impurity images to
        # masquerade as a missing product trace.
        for token in product_tokens:
            token = _safe_pyparse_graph_token(token)
            if not token:
                continue
            for graphs_dir in graph_dirs:
                for ext in extensions:
                    candidate = graphs_dir / f"chroma-{token}-{suffix}{ext}"
                    if candidate.is_file() and not (avoid_uv254 and "uv254" in candidate.name.lower()):
                        return candidate
        return None

    def _load_trace_photo(
        self,
        path: Optional[Path],
        crop: str,
        max_width: Optional[int] = None,
        max_height: int = 95,
    ) -> Optional[ImageTk.PhotoImage]:
        if path is None or not path.is_file():
            return None
        if max_width is None:
            max_width = self.product_structure_preview_width
        cache_key = f"{path}|{crop}|{max_width}|{max_height}|{path.stat().st_mtime_ns}"
        cached = self.product_structure_trace_images.get(cache_key)
        if cached is not None:
            return cached
        try:
            img = Image.open(path).convert("RGB")
            w, h = img.size
            crop_box = _trace_crop_box(crop, w, h)
            if crop_box is not None:
                img = img.crop(crop_box)
            ratio = min(max_width / img.width, max_height / img.height)
            ratio = max(ratio, 0.01)
            new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.product_structure_trace_images[cache_key] = photo
            return photo
        except Exception:
            return None

    def _portable_trace_path(self, well: str, key: str) -> Optional[Path]:
        traces = self.portable_trace_paths.get(_normalize_well(well), {})
        raw = str(traces.get(key, "") or "").strip()
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_file() else None

    def _product_trace_paths(self, row: Dict[str, object], *, include_portable: bool = True) -> Dict[str, Optional[Path]]:
        well = _normalize_well(row.get("pyparse_well", ""))
        if not well:
            return {"pyparse_uv": None, "modified_uv": None, "modified_es": None}

        pyparse_uv = self._portable_trace_path(well, "pyparse_uv") if include_portable else None
        if pyparse_uv is None:
            original_token = self._pyparse_product_trace_token(self.pyparse_result_dir, row, well)
            if original_token:
                original_row = {
                    **row,
                    "reaction_name": "",
                    "product_id": original_token,
                    "desired product name": original_token,
                    "pyparse_product_index": "",
                }
                pyparse_uv = self._find_product_trace_path(
                    self.pyparse_result_dir,
                    original_row,
                    "best",
                    original_pyparse=False,
                )

        modified_row = row
        modified_token = self._pyparse_product_trace_token(self.modified_pyparse_result_dir, row, well)
        if modified_token:
            modified_row = {
                **row,
                "reaction_name": "",
                "product_id": modified_token,
                "desired product name": modified_token,
                "pyparse_product_index": "",
            }

        modified_uv = self._portable_trace_path(well, "modified_uv") if include_portable else None
        if modified_uv is None and modified_token:
            modified_uv = self._find_product_trace_path(
                self.modified_pyparse_result_dir,
                modified_row,
                f"{well}-uv254",
                prefer_uv254=True,
            )

        modified_mass = self._portable_trace_path(well, "modified_es") if include_portable else None
        if modified_mass is None and modified_token:
            modified_mass = self._find_product_trace_path(
                self.modified_pyparse_result_dir,
                modified_row,
                well,
                avoid_uv254=True,
            )

        return {
            "pyparse_uv": None if self._analysis_is_invalidated(row, "pyparse") else pyparse_uv,
            "modified_uv": None if self._analysis_is_invalidated(row, "modified") else modified_uv,
            "modified_es": None if self._analysis_is_invalidated(row, "modified") else modified_mass,
        }

    def _refresh_product_structure_trace_display(self, row: Optional[Dict[str, object]] = None):
        if not hasattr(self, "product_structure_trace_widgets"):
            return
        product_titles = (
            "UV trace from PyParse",
            "UV trace from Modified PyParse",
            "ES+/ES- traces from Modified PyParse",
        )
        for title_widget, title in zip(getattr(self, "product_structure_trace_title_widgets", []), product_titles):
            title_widget.configure(text=title)
        if row is None:
            row = self._selected_product_structure_row()
        if row is None:
            self._clear_product_structure_trace_display()
            return
        trace_paths = self._product_trace_paths(row)
        trace_width = self._product_structure_trace_width()
        photos = [
            # Original PyParse produces one complete figure containing the MS-,
            # MS+, and UV panels.  Preserve that figure as generated; panel
            # cropping is reserved for Modified PyParse views.
            self._load_trace_photo(trace_paths.get("pyparse_uv"), "full", max_width=trace_width, max_height=520),
            self._load_trace_photo(trace_paths.get("modified_uv"), "full", max_width=trace_width, max_height=520),
            self._load_trace_photo(trace_paths.get("modified_es"), "es_trace_panels", max_width=trace_width, max_height=520),
        ]
        labels = self.product_structure_trace_widgets
        for lbl, photo in zip(labels, photos):
            if photo is None:
                lbl.configure(image="", text="No trace available")
            else:
                lbl.configure(image=photo, text="")

        self._peak_bind_trace(row, photos)

    def _find_impurity_trace_path(
        self,
        output_dir: Optional[Path],
        well: str,
        impurities: List[Dict[str, str]],
        *,
        prefer_well: bool = True,
        avoid_uv254: bool = True,
        prefer_uv254: bool = False,
        summary_only: bool = False,
    ) -> Optional[Path]:
        if output_dir is None or not output_dir.exists():
            return None
        well_token = _safe_pyparse_graph_token(well).lower()
        summary_token = _safe_pyparse_graph_token(f"ImpuritySummary__{well}")
        summary_suffix = f"{_safe_pyparse_graph_token(well)}-uv254" if prefer_uv254 else _safe_pyparse_graph_token(well)
        for folder in self._graph_image_dirs(output_dir):
            for extension in (".jpg", ".jpeg", ".png"):
                candidate = folder / f"chroma-{summary_token}-{summary_suffix}{extension}"
                if candidate.is_file() and not (avoid_uv254 and "uv254" in candidate.name.lower()):
                    return candidate
        if summary_only:
            return None
        impurity_tokens = [
            _safe_pyparse_graph_token(row.get("pyparse_name", row.get("label", ""))).lower()
            for row in impurities
        ]
        impurity_tokens.extend(
            _safe_pyparse_graph_token(row.get("label", "")).lower().replace("_", "")
            for row in impurities
        )
        impurity_tokens = [token for token in impurity_tokens if token]
        scored: List[Tuple[int, Path]] = []
        for folder in self._graph_image_dirs(output_dir):
            for path in folder.iterdir():
                if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    continue
                name = path.stem.lower()
                if avoid_uv254 and "uv254" in name:
                    continue
                score = 0
                compact_name = name.replace("_", "").replace("-", "")
                if any(token in name or token.replace("_", "") in compact_name for token in impurity_tokens):
                    score += 20
                elif well_token and well_token in name and ("impurity" in name or "byproduct" in name):
                    # Well-specific fallback for runs whose graph names predate
                    # XinPilot's unique impurity suffix.
                    score += 8
                else:
                    continue
                if well_token and well_token in name:
                    score += 10
                elif prefer_well:
                    score -= 5
                if prefer_uv254:
                    score += 12 if "uv254" in name else -6
                if name.endswith("-best"):
                    score += 2
                scored.append((score, path))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1].stat().st_mtime_ns), reverse=True)
        return scored[0][1]

    def _refresh_impurity_trace_display(self, selected: Dict[str, object]):
        self._peak_unbind()
        impurities = list(selected.get("impurities", []) or [])
        well = _normalize_well(selected.get("pyparse_well", ""))
        product_row = dict(selected.get("product_row", {}) or {})
        product_row["pyparse_well"] = well
        trace_paths = self._product_trace_paths(product_row) if product_row else {}
        standard_path = trace_paths.get("pyparse_uv")
        # Modified PyParse has target-specific product and impurity images.
        # Resolve impurity plots first so clicking the Impurities tab never
        # reuses Product wording from the corresponding product image.
        modified_uv_path = self._find_impurity_trace_path(
            self.modified_pyparse_impurity_result_dir,
            well,
            impurities,
            avoid_uv254=False,
            prefer_uv254=True,
            summary_only=True,
        )
        modified_es_path = self._find_impurity_trace_path(
            self.modified_pyparse_impurity_result_dir,
            well,
            impurities,
            avoid_uv254=True,
            summary_only=True,
        )

        # Backward-compatible fallbacks for projects exported before per-product
        # trace resolution was added.
        if standard_path is None:
            standard_path = self._portable_trace_path(well, "impurity_pyparse")
        if standard_path is None:
            standard_path = self._find_impurity_trace_path(self.pyparse_result_dir, well, impurities)
        if modified_es_path is None:
            modified_es_path = self._portable_trace_path(well, "impurity_modified")
        if modified_es_path is None:
            modified_es_path = self._find_impurity_trace_path(
                self.modified_pyparse_impurity_result_dir, well, impurities, summary_only=True
            )
        if modified_uv_path is None:
            modified_uv_path = self._portable_trace_path(well, "impurity_modified") or modified_es_path
        width = self._product_structure_trace_width()
        photos = [
            self._load_trace_photo(standard_path, "pyparse_uv_panel", max_width=width, max_height=520),
            self._load_trace_photo(
                modified_uv_path,
                "full" if modified_uv_path != modified_es_path else "uv_panel",
                max_width=width,
                max_height=520,
            ),
            self._load_trace_photo(modified_es_path, "es_trace_panels", max_width=width, max_height=520),
        ]
        reaction_label = str(selected.get("reaction_name", "") or selected.get("reaction_well", "") or "Selected reaction")
        context = f"{reaction_label}, LCMS {well}" if well else reaction_label
        titles = (
            f"UV trace from PyParse — {context}",
            f"Annotated impurity UV trace from Modified PyParse — {context}",
            f"Annotated impurity ES-/ES+ traces from Modified PyParse — {context}",
        )
        for title_widget, title in zip(getattr(self, "product_structure_trace_title_widgets", []), titles):
            title_widget.configure(text=title)
        for index, (label, photo) in enumerate(zip(self.product_structure_trace_widgets, photos)):
            if photo is None:
                message = "No trace available"
                if index in (1, 2):
                    message = "Impurity trace not generated for this well. Rerun Modified PyParse with impurity targets."
                label.configure(image="", text=message)
            else:
                label.configure(image=photo, text="")

    def _on_pyparse_row_select(self, _event=None):
        sel = self.pyparse_preview.selection()
        if not sel:
            return
        rows = self._pyparse_rows()
        idx = int(sel[0])
        if 0 <= idx < len(rows):
            self.pyparse_well_var.set(rows[idx]["pyparse_well"])

    def _apply_selected_pyparse_well(self):
        sel = self.pyparse_preview.selection()
        if not sel:
            messagebox.showwarning("No row selected", "Select a reaction row first.")
            return
        well = self.pyparse_well_var.get().strip().upper()
        if not self._is_valid_pyparse_well(well):
            messagebox.showerror("Invalid well", "Use an LCMS well like A1, B3, or H12.")
            return
        rows = self._pyparse_rows()
        idx = int(sel[0])
        if 0 <= idx < len(rows):
            self.pyparse_wells[rows[idx]["reaction_well"]] = well
            self._refresh_pyparse_preview()

    def _pick_pyparse_wells_on_map(self):
        sel = self.pyparse_preview.selection()
        if not sel:
            messagebox.showwarning("No row selected", "Select one or more reaction rows first.")
            return

        rows = self._pyparse_rows()
        selected_indices = sorted(int(iid) for iid in sel)
        initial_labels = []
        for idx in selected_indices:
            if 0 <= idx < len(rows) and self._is_valid_pyparse_well(rows[idx]["pyparse_well"]):
                initial_labels.append(rows[idx]["pyparse_well"])

        dlg = tecan_frame.WellMapDialog(self, 8, 12, ",".join(initial_labels), vertical_view=False)
        self.wait_window(dlg)
        labels = [x.strip().upper() for x in (dlg.result_labels or "").split(",") if x.strip()]
        if not labels:
            return

        if len(selected_indices) == 1 and len(labels) > 1:
            start_idx = selected_indices[0]
            assigned = 0
            for offset, pyparse_well in enumerate(labels):
                row_idx = start_idx + offset
                if row_idx >= len(rows):
                    break
                self.pyparse_wells[rows[row_idx]["reaction_well"]] = pyparse_well
                assigned += 1
            self._refresh_pyparse_preview()
            if assigned < len(labels):
                messagebox.showwarning(
                    "Not enough rows",
                    f"Assigned {assigned} well(s), but {len(labels)} well(s) were selected because the reaction list ended.",
                )
            return

        if len(labels) != len(selected_indices):
            messagebox.showwarning(
                "Selection count mismatch",
                f"Selected {len(selected_indices)} reaction row(s), but chose {len(labels)} well(s).\n"
                "Select one starting row to fill downward, or select the same number of reaction rows as wells.",
            )
            return

        for idx, pyparse_well in zip(selected_indices, labels):
            if 0 <= idx < len(rows):
                self.pyparse_wells[rows[idx]["reaction_well"]] = pyparse_well
        self._refresh_pyparse_preview()

    def _use_reaction_wells_for_pyparse(self):
        self.pyparse_wells.clear()
        rows = self._grouped_reaction_rows() if self.product_details_generated else self._raw_grouped_reaction_rows()
        for row in rows:
            well = str(row.get("well", "")).strip().upper()
            if well:
                self.pyparse_wells[well] = well
        self._refresh_pyparse_preview()

    def _pick_pyparse_output(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialdir=str(PYPARSE_INPUT_DIR),
            initialfile=DEFAULT_PYPARSE_PLATEMAP.name,
            filetypes=[("CSV", "*.csv")],
        )
        if p:
            self.pyparse_output_var.set(p)

    def _pick_impurity_pyparse_output(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialdir=str(PYPARSE_INPUT_DIR),
            initialfile="modified_pyparse_impurity_targets.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if p:
            self.impurity_pyparse_output_var.set(p)

    def _lcms_target_for_row(self, row: Dict[str, object]) -> str:
        self._sync_building_block_identity()
        reaction_well = _normalize_well(row.get("reaction_well", ""))
        product = str(row.get("desired product smiles", "") or "").strip()
        values = getattr(self, "lcms_target_smiles_by_well", {}) or {}
        return str(values.get(reaction_well, product) or product).strip()

    def _lcms_summary_for_row(self, row: Dict[str, object]) -> str:
        reaction_well = _normalize_well(row.get("reaction_well", ""))
        values = getattr(self, "lcms_target_summaries_by_well", {}) or {}
        return str(values.get(reaction_well, "") or "")

    @staticmethod
    def _lcms_unique_products(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
        grouped: Dict[str, Dict[str, object]] = {}
        for row in rows:
            product = str(row.get("desired product smiles", "") or "").strip()
            if not product:
                continue
            try:
                product = ion_handling.analyze_smiles(product)["canonical_smiles"]
                automatic = ion_handling.automatic_lcms_target(product)
            except Exception:
                continue
            entry = grouped.setdefault(product, {
                "product_smiles": product,
                "automatic": automatic,
                "reaction_wells": [],
                "reaction_names": [],
            })
            entry["reaction_wells"].append(_normalize_well(row.get("reaction_well", "")))
            entry["reaction_names"].append(str(row.get("reaction_name", "") or ""))
        return list(grouped.values())

    def _ask_lcms_handling(self, rows: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
        products = self._lcms_unique_products(rows)
        if not products:
            return None
        neutral_count = sum(
            len(item["reaction_wells"])
            for item in products
            if not item["automatic"].get("counterion_count")
            and not item["automatic"].get("neutralizable_count")
            and not item["automatic"].get("permanent_count")
        )
        salt_count = sum(
            len(item["reaction_wells"])
            for item in products
            if item["automatic"].get("counterion_count") or item["automatic"].get("neutralizable_count")
        )
        permanent_count = sum(
            len(item["reaction_wells"])
            for item in products
            if item["automatic"].get("permanent_count")
        )
        win = tk.Toplevel(self)
        win.title("Prepare Structures for LCMS Analysis")
        parent = self.winfo_toplevel()
        win.transient(parent)
        parent.update_idletasks()
        screen_width = max(720, int(win.winfo_screenwidth()))
        screen_height = max(600, int(win.winfo_screenheight()))
        parent_width = max(720, int(parent.winfo_width()))
        parent_height = max(560, int(parent.winfo_height()))
        dialog_width = min(1040, screen_width - 80, parent_width - 40)
        dialog_height = min(760, screen_height - 120, parent_height - 40)
        dialog_width = max(720, dialog_width)
        dialog_height = max(520, dialog_height)
        win.geometry(f"{dialog_width}x{dialog_height}")
        win.minsize(min(720, dialog_width), min(520, dialog_height))
        win.grab_set()
        result: Dict[str, object] = {"value": None}
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        content = ttk.Frame(body)
        content.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            content,
            text=(
                f"{len(rows)} products: {neutral_count} neutral, {salt_count} with counterions or neutralizable "
                f"charges, {permanent_count} with permanent molecular charges."
            ),
            justify="left",
        ).pack(fill="x", anchor="w")
        ttk.Label(
            content,
            text=(
                "This changes only the LCMS input structure. Product Details remains unchanged. "
                "Automatic preparation removes spectator counterions, neutralizes proton-only sites, "
                "and preserves permanent charges."
            ),
            wraplength=max(640, dialog_width - 48),
            justify="left",
        ).pack(fill="x", anchor="w", pady=(4, 8))
        mode_var = tk.StringVar(value=self.lcms_handling_mode if self.lcms_handling_mode in {"automatic", "exact", "review"} else "automatic")
        modes = ttk.Frame(content)
        modes.pack(fill="x")
        ttk.Radiobutton(modes, text="Prepare automatically for LCMS", variable=mode_var, value="automatic").pack(side="left")
        ttk.Radiobutton(modes, text="Use Product Details exactly", variable=mode_var, value="exact").pack(side="left", padx=(16, 0))
        ttk.Radiobutton(modes, text="Review exceptions manually", variable=mode_var, value="review").pack(side="left", padx=(16, 0))

        table_frame = ttk.Frame(content)
        table_frame.pack(fill="both", expand=True, pady=(10, 8))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        table = ttk.Treeview(table_frame, columns=("wells", "product", "automatic", "status"), show="headings", height=6)
        for column, text, width in [
            ("wells", "Products", 80),
            ("product", "Product Details SMILES", 340),
            ("automatic", "Automatic LCMS target", 340),
            ("status", "Transformation", 260),
        ]:
            table.heading(column, text=text)
            table.column(column, width=width, anchor="w")
        table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
        horizontal_scroll.grid(row=1, column=0, sticky="ew")
        table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal_scroll.set)
        for index, item in enumerate(products):
            automatic = item["automatic"]
            status = str(automatic.get("summary", "") or "")
            if automatic.get("permanent_count"):
                status += "; permanent charge retained"
            table.insert("", "end", iid=str(index), values=(
                len(item["reaction_wells"]),
                item["product_smiles"],
                automatic.get("target_smiles", ""),
                status,
            ))

        compare = ttk.LabelFrame(content, text="Selected structure comparison", padding=8)
        compare.pack(fill="x")
        compare.grid_columnconfigure(0, weight=1, uniform="lcmscompare")
        compare.grid_columnconfigure(1, weight=1, uniform="lcmscompare")
        ttk.Label(compare, text="Product Details").grid(row=0, column=0, sticky="w")
        ttk.Label(compare, text="LCMS target").grid(row=0, column=1, sticky="w", padx=(8, 0))
        product_label = ttk.Label(compare, anchor="center", background="#ffffff", relief="solid")
        target_label = ttk.Label(compare, anchor="center", background="#ffffff", relief="solid")
        product_label.grid(row=1, column=0, sticky="nsew", pady=(3, 0))
        target_label.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(3, 0))
        compare_images: Dict[str, ImageTk.PhotoImage] = {}
        overrides: Dict[str, Dict[str, str]] = {}
        custom_var = tk.StringVar(value="")
        review_tools = ttk.Frame(content)
        review_tools.pack(fill="x", pady=(8, 0))
        review_tools.grid_columnconfigure(1, weight=1)
        ttk.Label(review_tools, text="Custom LCMS SMILES for selected product").grid(row=0, column=0, sticky="w")
        custom_entry = ttk.Entry(review_tools, textvariable=custom_var)
        custom_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(6, 0))

        def selected_index() -> Optional[int]:
            selection = table.selection()
            if not selection:
                return None
            try:
                return int(selection[0])
            except Exception:
                return None

        def selected_target(item: Dict[str, object]) -> str:
            product = str(item["product_smiles"])
            if mode_var.get() == "exact":
                return product
            override = overrides.get(product, {}) if mode_var.get() == "review" else {}
            choice = override.get("choice", "automatic")
            if choice == "exact":
                return product
            if choice == "custom":
                return override.get("smiles", product)
            return str(item["automatic"].get("target_smiles", product))

        def render_selected(_event=None):
            index = selected_index()
            if index is None or not (0 <= index < len(products)):
                return
            item = products[index]
            product = str(item["product_smiles"])
            target = selected_target(item)
            for key, label, smiles in (("product", product_label, product), ("target", target_label, target)):
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    label.configure(image="", text="Invalid SMILES")
                    continue
                image = Draw.MolToImage(mol, size=(470, 180), fitImage=True).convert("RGBA")
                photo = ImageTk.PhotoImage(image)
                compare_images[key] = photo
                label.configure(image=photo, text="")
            override = overrides.get(product, {})
            custom_var.set(override.get("smiles", "") if override.get("choice") == "custom" else "")

        def set_selected_choice(choice: str):
            index = selected_index()
            if index is None:
                messagebox.showwarning("No product selected", "Select a product row first.", parent=win)
                return
            product = str(products[index]["product_smiles"])
            if choice == "custom":
                custom = custom_var.get().strip()
                if Chem.MolFromSmiles(custom) is None:
                    messagebox.showerror("Invalid LCMS SMILES", "Enter a valid custom LCMS SMILES.", parent=win)
                    return
                overrides[product] = {"choice": "custom", "smiles": Chem.MolToSmiles(Chem.MolFromSmiles(custom), canonical=True)}
            else:
                overrides[product] = {"choice": choice, "smiles": ""}
            mode_var.set("review")
            render_selected()

        ttk.Button(review_tools, text="Use automatic", command=lambda: set_selected_choice("automatic")).grid(row=1, column=1, sticky="e", pady=(6, 0))
        ttk.Button(review_tools, text="Use Product Details", command=lambda: set_selected_choice("exact")).grid(row=1, column=2, sticky="e", padx=(6, 0), pady=(6, 0))
        ttk.Button(review_tools, text="Use custom", command=lambda: set_selected_choice("custom"), style="RowAction.TButton").grid(row=1, column=3, sticky="e", padx=(6, 0), pady=(6, 0))
        table.bind("<<TreeviewSelect>>", render_selected)
        for radio in modes.winfo_children():
            radio.configure(command=render_selected)
        if products:
            table.selection_set("0")
            table.focus("0")
            render_selected()

        actions = ttk.Frame(body)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        def cancel():
            result["value"] = None
            win.destroy()

        def continue_generation():
            targets: Dict[str, str] = {}
            summaries: Dict[str, str] = {}
            mode = mode_var.get()
            for item in products:
                product = str(item["product_smiles"])
                target = selected_target(item)
                if Chem.MolFromSmiles(target) is None:
                    messagebox.showerror("Invalid LCMS target", f"Invalid LCMS target for {product}", parent=win)
                    return
                if mode == "exact":
                    summary = "Used Product Details exactly"
                elif mode == "review" and overrides.get(product, {}).get("choice") == "custom":
                    summary = "Used custom LCMS target"
                elif mode == "review" and overrides.get(product, {}).get("choice") == "exact":
                    summary = "Used Product Details exactly"
                else:
                    summary = str(item["automatic"].get("summary", "") or "Prepared automatically")
                if item["automatic"].get("permanent_count"):
                    summary += "; permanent charge retained—verify compatibility with PyParse mass assumptions"
                for well in item["reaction_wells"]:
                    targets[_normalize_well(well)] = target
                    summaries[_normalize_well(well)] = summary
            result["value"] = {"mode": mode, "targets": targets, "summaries": summaries}
            win.destroy()

        ttk.Button(actions, text="Cancel", command=cancel).pack(side="right")
        ttk.Button(actions, text="Continue and Generate Input", command=continue_generation, style="ChemAction.TButton").pack(side="right", padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", cancel)
        self.wait_window(win)
        return result.get("value")

    def _prepare_lcms_targets(self, rows: List[Dict[str, object]]) -> bool:
        selection = self._ask_lcms_handling(rows)
        if selection is None:
            return False
        # Changing the analytical form also makes existing assignments stale,
        # even when the stored Product Details structure remains unchanged.
        next_targets = selection.get("targets", {}) or {}
        for row in rows:
            well = _normalize_well(row.get("reaction_well", ""))
            next_target = next_targets.get(well) or row.get("desired product smiles", "")
            if _canonical_smiles_key(self._lcms_target_for_row(row)) != _canonical_smiles_key(next_target):
                self._invalidate_product_analysis(row)
        self.lcms_handling_mode = str(selection.get("mode", "automatic") or "automatic")
        self.lcms_target_smiles_by_well = {
            _normalize_well(key): str(value or "").strip()
            for key, value in (selection.get("targets", {}) or {}).items()
            if _normalize_well(key) and str(value or "").strip()
        }
        self.lcms_target_summaries_by_well = {
            _normalize_well(key): str(value or "").strip()
            for key, value in (selection.get("summaries", {}) or {}).items()
            if _normalize_well(key)
        }
        return True

    def _write_pyparse_platemap(
        self,
        out_path: Path,
        ready_rows: List[Dict[str, object]],
        impurity_rows: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            "well",
            "desired product smiles",
            "desired product name",
            "desired product id",
            "reaction well",
            "reaction",
            "limiting reactant smiles",
            "limiting reactant name",
            "limiting reactant id",
            "excess reactant smiles",
            "excess reactant name",
            "excess reactant id",
            "desired product exact mass",
            "desired product mw",
            "desired product formula",
            "desired product mh",
            "desired product mna",
            "desired product negative mass",
            "uv254_purity_from_pyparse",
            "uv254_purity_from_modified_pyparse",
            "purity by manual",
            "comments",
            "row color",
            "biology assay hits",
        ]
        impurity_rows = list(impurity_rows or [])
        impurities_by_reaction_well: Dict[str, List[Dict[str, str]]] = {}
        for impurity in impurity_rows:
            reaction_well = _normalize_well(impurity.get("reaction_well", ""))
            if reaction_well:
                impurities_by_reaction_well.setdefault(reaction_well, []).append(impurity)
        max_impurities = max((len(values) for values in impurities_by_reaction_well.values()), default=0)
        for index in range(1, max_impurities + 1):
            headers.extend([
                f"byproduct{index} smiles",
                f"byproduct{index} name",
                f"byproduct{index} rt",
            ])
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in ready_rows:
                manual_values = self.product_structure_manual_notes.get(self._product_structure_manual_key(row), {})
                lcms_well = _normalize_well(row.get("pyparse_well", ""))
                lcms_target = self._lcms_target_for_row(row)
                try:
                    target_exact, target_mw, target_formula, target_mh, target_mna, target_neg = core.mass_fields(lcms_target)
                except Exception:
                    target_exact = row["desired product exact mass"]
                    target_mw = row["desired product mw"]
                    target_formula = row["desired product formula"]
                    target_mh = row["desired product mh"]
                    target_mna = row["desired product mna"]
                    target_neg = row["desired product negative mass"]
                output_row = {
                    "well": row["pyparse_well"],
                    "desired product smiles": lcms_target,
                    "desired product name": row["desired product name"],
                    "desired product id": row["product_id"],
                    "reaction well": row["reaction_well"],
                    "reaction": row["reaction"],
                    # In an impurity-target map, starting materials are supplied as
                    # named byproducts below so PyParse does not register the same
                    # structure twice under both Reactant and Impurity labels.
                    "limiting reactant smiles": "" if impurity_rows else row["limiting reactant smiles"],
                    "limiting reactant name": "" if impurity_rows else row["limiting reactant name"],
                    "limiting reactant id": "" if impurity_rows else row["limiting reactant id"],
                    "excess reactant smiles": row["excess reactant smiles"],
                    "excess reactant name": row["excess reactant name"],
                    "excess reactant id": row["excess reactant id"],
                    "desired product exact mass": target_exact,
                    "desired product mw": target_mw,
                    "desired product formula": target_formula,
                    "desired product mh": target_mh,
                    "desired product mna": target_mna,
                    "desired product negative mass": target_neg,
                    "uv254_purity_from_pyparse": self._product_structure_purity_for_row(row, "pyparse"),
                    "uv254_purity_from_modified_pyparse": self._modified_pyparse_purity_for_row(row),
                    "purity by manual": manual_values.get("manual_purity", ""),
                    "comments": manual_values.get("comments", ""),
                    "row color": self._product_structure_row_color(row),
                    "biology assay hits": self._biology_hit_summary_for_row(row),
                }
                reaction_well = _normalize_well(row.get("reaction_well", ""))
                for index, impurity in enumerate(impurities_by_reaction_well.get(reaction_well, []), start=1):
                    output_row[f"byproduct{index} smiles"] = impurity.get("smiles", "")
                    output_row[f"byproduct{index} name"] = impurity.get("pyparse_name", f"Impurity{index}")
                    output_row[f"byproduct{index} rt"] = ""
                writer.writerow(output_row)

    def _generate_impurity_pyparse_input(self):
        try:
            rows = self._pyparse_rows()
            ready_rows = [
                row for row in rows
                if row.get("desired product smiles") and self._is_valid_pyparse_well(row.get("pyparse_well", ""))
            ]
            if not ready_rows:
                messagebox.showwarning("No ready rows", "No reactions have both a product SMILES and valid LCMS well.")
                return
            ready_reaction_wells = {
                _normalize_well(row.get("reaction_well", ""))
                for row in ready_rows
                if _normalize_well(row.get("reaction_well", ""))
            }
            impurities = [
                row for row in self._included_impurity_rows()
                if _normalize_well(row.get("reaction_well", "")) in ready_reaction_wells
            ]
            if not impurities:
                messagebox.showwarning(
                    "No impurity targets",
                    "No valid predicted impurity targets are available for reactions with valid LCMS wells.",
                )
                return
            output_text = self.impurity_pyparse_output_var.get().strip()
            out_path = Path(output_text) if output_text else PYPARSE_INPUT_DIR / "_gui_current_modified_pyparse_impurities.csv"
            self._write_pyparse_platemap(out_path, ready_rows, impurities)
            if self.modified_pyparse_input_callback:
                self.modified_pyparse_input_callback(out_path)
            self.logw(f"Prepared Modified PyParse impurity targets: {out_path}")
            messagebox.showinfo(
                "Modified PyParse impurity targets",
                f"Prepared all {len(impurities)} valid predicted impurity target(s) across "
                f"{len(ready_rows)} reaction row(s):\n{out_path}\n\n"
                "The Modified PyParse runner now points to this platemap.",
            )
        except Exception as exc:
            self.logw(f"ERROR generating impurity targets: {exc}")
            messagebox.showerror("Generate impurity targets failed", str(exc))

    def _run_stock_update(self):
        if not self.pyparse_stock_update_callback:
            messagebox.showwarning("Stock update unavailable", "Stock update is not connected.")
            return
        summary = self.pyparse_stock_update_callback() or ""
        if summary:
            messagebox.showinfo("Stock update", summary)

    def _generate_pyparse_input(self):
        try:
            self._save_current_product_structure_manual_fields()
            rows = self._pyparse_rows()
            ready_rows = [
                row for row in rows
                if row["desired product smiles"] and self._is_valid_pyparse_well(row["pyparse_well"])
            ]
            if not ready_rows:
                messagebox.showwarning("No ready rows", "No reactions have both a product SMILES and valid LCMS well.")
                return
            if not self._prepare_lcms_targets(ready_rows):
                self.logw("LCMS input generation cancelled during structure preparation review.")
                return
            self._refresh_pyparse_preview()

            output_text = self.pyparse_output_var.get().strip()
            save_user_csv = bool(output_text)
            out_path = Path(output_text) if save_user_csv else PYPARSE_INPUT_DIR / "_gui_current_pyparse_platemap.csv"
            self._write_pyparse_platemap(out_path, ready_rows)

            if self.pyparse_input_callback:
                self.pyparse_input_callback(out_path)
            if save_user_csv:
                self.logw(f"Wrote PyParse input: {out_path}")
            else:
                self.logw(f"Prepared internal PyParse input for GUI runners: {out_path}")
            self._refresh_pyparse_preview()
            if save_user_csv:
                message = f"Wrote {len(ready_rows)} row(s):\n{out_path}"
            else:
                message = f"Prepared {len(ready_rows)} row(s) for PyParse and Modified PyParse inside the GUI.\nNo user platemap CSV was saved."
            messagebox.showinfo("PyParse input generated", message)
        except Exception as exc:
            self.logw(f"ERROR generating PyParse input: {exc}")
            messagebox.showerror("Generate PyParse input failed", str(exc))

    def _add_usage(self, usage: Dict[str, Dict[str, float]], role_row: Dict[str, object]):
        comp = role_row.get("compound", {}) or {}
        cid = comp.get("ID", "")
        conc = core.parse_float(comp.get("Conc."))
        vol = core.parse_float(role_row.get("volume_uL"))
        used = conc * vol if conc and vol else 0.0
        entry = usage.setdefault(
            cid,
            {
                "volume": 0.0,
                "used": 0.0,
                "start": core.parse_float(comp.get("Quantity(umol)")),
                "name": comp.get("Name", ""),
            },
        )
        entry["volume"] += vol
        entry["used"] += used

    def _write_product_outputs(
        self,
        out_path: Path,
        product_rows: List[List[object]],
        usage: Dict[str, Dict[str, float]],
        skipped: List[List[object]],
        include_reports: bool = True,
    ) -> Tuple[Optional[Path], Optional[Path]]:
        usage_path = out_path.with_name(out_path.stem + "_usage.csv")
        skipped_path = out_path.with_name(out_path.stem + "_skipped.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "reaction name", "reaction", "reactant 1 ID", "reactant 1 name", "reactant 1 SMILES",
                "reactant 2 ID", "reactant 2 name", "reactant 2 SMILES",
                "reactant 3 ID", "reactant 3 name", "reactant 3 SMILES",
                "Product ID", "product SMILES", "well", "exact mass", "molecular weight",
                "molecular formula", "postive mass: +H", "postive mass: +Na", "negative mass",
                "possible selectivity product SMILES",
            ])
            w.writerows(product_rows)

        if not include_reports:
            return None, None

        with usage_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Name", "dispensed volume uL", "used umol", "starting umol", "remaining umol"])
            for cid, data in sorted(usage.items()):
                start = data["start"]
                used = data["used"]
                w.writerow([cid, data["name"], f"{data['volume']:.6g}", f"{used:.6g}", f"{start:.6g}", f"{start - used:.6g}" if start else ""])

        with skipped_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["well", "stage", "reason"])
            w.writerows(skipped)
        return usage_path, skipped_path

    def _write_custom_product_csv(self) -> Tuple[Path, Path, Path, int, int]:
        output_dir_text = self.custom_output_dir_var.get().strip()
        if not output_dir_text:
            raise ValueError("Select an output folder for custom product CSV files.")
        out_path = Path(output_dir_text) / "custom_products.csv"
        product_rows = []
        skipped = []
        usage: Dict[str, Dict[str, float]] = {}
        for grouped in self._custom_grouped_reaction_rows():
            well = str(grouped.get("well", "")).strip().upper()
            reactants = list(grouped.get("reactants", []) or [])[:3]
            if not reactants:
                skipped.append([well, "reactant_selection", grouped.get("status", "")])
                continue
            product = self._custom_product_for_well(well)
            if not product:
                skipped.append([well, "custom_template", self.custom_failures.get(well, "no custom product generated")])
                continue
            compounds = [(row.get("compound", {}) or {}) for row in reactants]
            try:
                canonical = [core.canonical_smiles(comp.get("SMILES", "")) for comp in compounds]
                exact, mw, formula, mh, mna, neg = core.mass_fields(product)
            except Exception as exc:
                skipped.append([well, "custom_output", str(exc)])
                continue
            reaction_name = self.reaction_names.get(well, "") or f"RXN_{well}"
            product_rows.append([
                reaction_name,
                "custom_template",
                *[
                    value
                    for index in range(3)
                    for value in (
                        compounds[index].get("ID", "") if index < len(compounds) else "",
                        compounds[index].get("Name", "") if index < len(compounds) else "",
                        canonical[index][1] if index < len(canonical) else "",
                    )
                ],
                reaction_name,
                product,
                well,
                exact,
                mw,
                formula,
                mh,
                mna,
                neg,
                product,
            ])
            for reactant in reactants:
                self._add_usage(usage, reactant)
        usage_path, skipped_path = self._write_product_outputs(out_path, product_rows, usage, skipped)
        return out_path, usage_path, skipped_path, len(product_rows), len(skipped)

    def _replace_retained_results(self):
        rows = dict(self.pushed_rows)
        reaction, output, name = self.reaction_var.get(), self.output_var.get(), self.name_start_var.get()
        template = self.custom_template_text.get("1.0", "end-1c")
        order, custom_output = self.custom_reactant_order_var.get(), self.custom_output_dir_var.get()
        signatures = dict(self.pushed_plan_fingerprints)
        self.clear_for_next_synthesis_step()
        self.pushed_rows = rows
        self.pushed_plan_fingerprints = signatures
        self.custom_template_text.insert("1.0", template)
        self.custom_reactant_order_var.set(order)
        self.custom_output_dir_var.set(custom_output)
        self.reaction_var.set(reaction)
        self.output_var.set(output)
        self.name_start_var.set(name)
        if callable(self.pushed_change_callback):
            self.pushed_change_callback("all")

    def _generate(self):
        if self.retained_results_var.get():
            if not self.pushed_rows:
                messagebox.showwarning("No pushed inputs", "Push the synthesis inputs before generating new products.", parent=self)
                return
            if not messagebox.askyesno("Replace retained results", "Generate products from the current pushed inputs and clear the retained previous products and LCMS results?", parent=self):
                return
            self._replace_retained_results()
        try:
            reaction = self._reaction()
            if not self._review_charged_building_blocks(force=False):
                self.logw("Product generation cancelled during charged building-block review.")
                return
            grouped_rows = self._grouped_reaction_rows()
            if not self._ensure_reaction_site_selections(grouped_rows, reaction):
                self.logw("Product generation cancelled while selecting a reaction site.")
                return
            self._stage_product_regeneration()
            # Rebuild after the choices so each well is filtered to its selected
            # halide site before product details and impurity targets are made.
            grouped_rows = self._grouped_reaction_rows()

            output_text = self.output_var.get().strip()
            out_path = Path(output_text) if output_text else None

            product_rows = []
            skipped = []
            usage: Dict[str, Dict[str, float]] = {}

            for grouped in grouped_rows:
                well = grouped["well"]
                reactants = list(grouped.get("reactants", []) or [])
                arity = int(reaction.get("reactant_count", 2) or 2)
                if len(reactants) != arity:
                    skipped.append([well, "role_classification", grouped["status"]])
                    continue
                compounds = [(row.get("compound", {}) or {}) for row in reactants]
                try:
                    canonical = [core.canonical_smiles(comp.get("SMILES", "")) for comp in compounds]
                    custom_product = self._custom_product_for_well(well)
                    products = [custom_product] if custom_product else list(grouped.get("candidate_products", []) or [])
                except Exception as exc:
                    skipped.append([well, "reaction", str(exc)])
                    continue
                if not products:
                    skipped.append([well, "reaction", "no product generated"])
                    continue
                if len(products) > 1:
                    if grouped.get("reaction_site_choice") == "all":
                        products = sorted(set(products))
                        self.logw(
                            f"{well}: retained all {len(products)} possible products from the user's reaction-site choice."
                        )
                    elif self._are_same_mass_selectivity_products(products):
                        products = sorted(set(products))
                        self.logw(
                            f"{well}: retained {len(products)} possible selectivity products with the same formula and LCMS mass."
                        )
                    else:
                        skipped.append([
                            well,
                            "ambiguous_products",
                            f"{len(products)} products with different formulas or masses generated; define a custom product: "
                            + " | ".join(products),
                        ])
                        continue

                product = products[0]
                exact, mw, formula, mh, mna, neg = core.mass_fields(product)
                reaction_name = self.reaction_names.get(well, "") or f"RXN_{well}"
                product_rows.append([
                    reaction_name,
                    reaction["id"],
                    *[
                        value
                        for index in range(3)
                        for value in (
                            compounds[index].get("ID", "") if index < len(compounds) else "",
                            compounds[index].get("Name", "") if index < len(compounds) else "",
                            canonical[index][1] if index < len(canonical) else "",
                        )
                    ],
                    reaction_name,
                    product,
                    well,
                    exact,
                    mw,
                    formula,
                    mh,
                    mna,
                    neg,
                    " | ".join(products),
                ])

                for reactant in reactants:
                    self._add_usage(usage, reactant)

            if out_path:
                usage_path, skipped_path = self._write_product_outputs(out_path, product_rows, usage, skipped, include_reports=False)
                self.logw(f"Wrote products: {out_path}")
                if usage_path:
                    self.logw(f"Wrote usage: {usage_path}")
                if skipped_path:
                    self.logw(f"Wrote skipped: {skipped_path}")
            else:
                self.logw("Generated Product Details in the GUI only; no cheminformatics CSV path was selected.")
            self.product_details_generated = True
            self._complete_product_regeneration(self._pyparse_rows())
            self._refresh_product_details_preview(show_products=True)
            self._refresh_pyparse_preview()
            csv_line = f"\nCSV: {out_path}" if out_path else "\nCSV: not saved"
            messagebox.showinfo("Done", f"Products: {len(product_rows)}\nSkipped: {len(skipped)}{csv_line}")
        except Exception as exc:
            self.logw(f"ERROR: {exc}")
            messagebox.showerror("Generate failed", str(exc))
