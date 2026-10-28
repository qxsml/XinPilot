from __future__ import annotations

import os
import json
import tempfile
import uuid

from xinpilot.application.project_archive import (
    TraceAsset,
    load_project_package,
    package_project_assets,
    prepare_imported_gwl_entries,
    safe_extract_project_zip,
    save_project_package,
)
from xinpilot.application.project_state import (
    build_project_payload,
    create_synthesis_step_snapshot,
    project_name_from_path,
    synthesis_progress,
    validate_project_data,
)

from PIL import ImageFont
from xinpilot_tooltips import install_tooltips
from page_presentation import install_page_presentation
from project_change_tracking import ProjectChangeTrackingMixin

from xinpilot_shared import *
from cheminformatics_frame import CheminformaticsFrame
from manual_workflow_frame import ManualWorkflowFrame
from external_import_frame import ExternalImportFrame
from opentrons_frame import OpentronsFrame
from pyparse_runner_frame import PyParseRunnerFrame, _pyparse_platemap_kind
from reaction_summary_frame import ReactionSummaryFrame
from tools_launcher import (
    launch_aromatic_smiles_converter,
    launch_compound_library_builder,
    launch_opentrons_simulator,
    launch_solution_calculator,
    launch_clogp_calculator,
)
from multistep_workflow import (
    build_product_candidate,
    candidate_to_compound_values,
    parse_percent,
    select_candidates_by_threshold,
)


class IntegratedFullApp(ProjectChangeTrackingMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("XinPilot")
        try:
            self.iconbitmap(default=str(resource_path("xinpilot_logo.ico")))
        except Exception:
            pass
        self.geometry("1500x930")
        self.minsize(1200, 760)
        self.after(0, self._maximize_on_open)
        configure_modern_theme(self)
        install_notebook_tab_feedback(self)
        self.tab_icons = make_tab_icons(self)
        style = ttk.Style(self)
        style.configure(
            "SynthesisSelector.TButton",
            padding=(10, 3),
            relief="flat",
            borderwidth=1,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "SynthesisSelectorSelected.TButton",
            padding=(10, 3),
            relief="flat",
            borderwidth=1,
            background=COLORS["accent"],
            foreground="#ffffff",
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "SynthesisSelectorSelected.TButton",
            background=[("active", COLORS["accent_dark"]), ("pressed", COLORS["accent_dark"])],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )

        self.project_status_var = tk.StringVar(value="")
        self.current_project_name = ""
        self.current_synthesis_step = 1
        self.completed_synthesis_steps: List[Dict[str, object]] = []
        self._last_main_tab = ""
        self._next_step_dialog_active = False
        self._solution_calculator_dialog_active = False
        self._close_prompt_active = False

        self.nb = ttk.Notebook(self, style="Main.TNotebook", takefocus=0)
        self.nb.pack(fill="both", expand=True, padx=(2, 8), pady=(4, 8))

        # Project actions share the main navigation line so they do not consume a
        # separate strip of vertical space.  The stable seven workflow tabs still
        # belong to the notebook; these remain ordinary buttons, not pseudo-tabs.
        self.project_bar = ttk.Frame(self.nb, style="Chem.TFrame")
        self.toolkit_button = ttk.Menubutton(
            self.project_bar,
            text="Toolkit",
            style="Toolkit.TMenubutton",
        )
        self.toolkit_menu = tk.Menu(self.toolkit_button, tearoff=False)
        self.toolkit_menu.add_command(
            label="Compound Library Builder\N{HORIZONTAL ELLIPSIS}",
            command=self._launch_compound_library_builder,
        )
        self.toolkit_menu.add_command(
            label="Aromatic SMILES Converter\N{HORIZONTAL ELLIPSIS}",
            command=self._launch_aromatic_smiles_converter,
        )
        self.toolkit_menu.add_command(
            label="Opentrons Protocol Simulator\N{HORIZONTAL ELLIPSIS}",
            command=self._launch_opentrons_simulator,
        )
        self.toolkit_menu.add_command(
            label="Solution & Stock Calculator\N{HORIZONTAL ELLIPSIS}",
            command=self._launch_solution_calculator,
        )
        self.toolkit_menu.add_command(label="Molecular Properties & Alerts Calculator...", command=lambda: launch_clogp_calculator(parent=self))
        self.toolkit_button.configure(menu=self.toolkit_menu)
        self.toolkit_button.pack(side="left", padx=(0, 18))
        ttk.Button(
            self.project_bar,
            text="Export Project",
            command=self._export_project,
            style="FileAction.TButton",
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            self.project_bar,
            text="Import Project",
            command=self._import_project,
            style="FileAction.TButton",
        ).pack(side="left")
        self.project_bar.place(relx=1.0, x=-8, y=2, anchor="ne")
        self.project_bar.lift()

        self.compound_tab = compound_notes_frame.CompoundNotesFrame(self.nb)
        self.nb.add(self.compound_tab, text="Compound Notes", image=self.tab_icons["compound"], compound="top")

        self.synthesis_tab = ttk.Frame(self.nb, style="Chem.TFrame")
        self.synthesis_choice_frame = ttk.Frame(self.synthesis_tab, style="Chem.TFrame", padding=16)
        self.synthesis_editor_bar = ttk.Frame(self.synthesis_tab, style="Chem.TFrame", padding=(6, 4, 6, 2))
        self.synthesis_content = ttk.Frame(self.synthesis_tab, style="Chem.TFrame")
        self.synthesis_active_editor = None
        self.combined_synthesis_active_editor = None
        self.synthesis_editor_hosts = {
            "Tecan": ttk.Frame(self.synthesis_content, style="Chem.TFrame"),
            "Manual": ttk.Frame(self.synthesis_content, style="Chem.TFrame"),
            "Opentrons": ttk.Frame(self.synthesis_content, style="Chem.TFrame"),
            "External Import": ttk.Frame(self.synthesis_content, style="Chem.TFrame"),
        }

        self.tecan_tab = tecan_frame.TecanFrame(
            self.synthesis_editor_hosts["Tecan"],
            compound_provider=lambda: self.compound_tab.records,
            push_callback=self._push_tecan_to_cheminformatics,
        )
        self.tecan_tab.pack(fill="both", expand=True)

        self.manual_tab = ManualWorkflowFrame(
            self.synthesis_editor_hosts["Manual"],
            compound_provider=lambda: self.compound_tab.records,
            push_callback=self._push_manual_to_cheminformatics,
        )
        self.manual_tab.pack(fill="both", expand=True)

        self.opentrons_tab = OpentronsFrame(
            self.synthesis_editor_hosts["Opentrons"],
            compound_provider=lambda: self.compound_tab.records,
            push_callback=self._push_opentrons_to_cheminformatics,
        )
        self.opentrons_tab.pack(fill="both", expand=True)
        self.external_import_tab = ExternalImportFrame(
            self.synthesis_editor_hosts["External Import"],
            compound_provider=lambda: self.compound_tab.records,
            add_compounds=self._add_external_compounds,
            push_callback=self._push_external_to_cheminformatics,
        )
        self.external_import_tab.pack(fill="both", expand=True)
        self.synthesis_editors = dict(self.synthesis_editor_hosts)
        ttk.Label(self.synthesis_choice_frame, text="Choose synthesis editor", font=("", 12, "bold")).pack(anchor="w", pady=(0, 10))
        choice_buttons = ttk.Frame(self.synthesis_choice_frame, style="Chem.TFrame")
        choice_buttons.pack(anchor="w")
        ttk.Button(choice_buttons, text="External Import", command=lambda: self._show_synthesis_editor("External Import"), style="FileAction.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(choice_buttons, text="Tecan", command=lambda: self._show_synthesis_editor("Tecan"), style="FileAction.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(choice_buttons, text="Opentrons", command=lambda: self._show_synthesis_editor("Opentrons"), style="FileAction.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(choice_buttons, text="Manual", command=lambda: self._show_synthesis_editor("Manual"), style="FileAction.TButton").pack(side="left", padx=(0, 8))
        self.synthesis_editor_bar.columnconfigure(1, weight=1)
        self.change_synthesis_editor_button = ttk.Button(
            self.synthesis_editor_bar,
            text="Change synthesis editor",
            command=self._show_synthesis_choice,
            style="FileAction.TButton",
        )
        self.change_synthesis_editor_button.grid(row=0, column=0, sticky="w")
        self.combined_synthesis_tab_bar = ttk.Frame(self.synthesis_editor_bar, style="Chem.TFrame")
        self.combined_synthesis_tab_bar.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.combined_synthesis_tab_buttons = {}
        for column, editor_name in enumerate(("Tecan", "Opentrons", "Manual", "External Import")):
            self.combined_synthesis_tab_bar.columnconfigure(column, weight=1, uniform="synthesis_editor_tab")
            btn = ttk.Button(
                self.combined_synthesis_tab_bar,
                text=editor_name,
                width=9,
                command=lambda name=editor_name: self._select_synthesis_editor_from_bar(name),
                style="SynthesisSelector.TButton",
            )
            btn.grid(row=0, column=column, sticky="ew", padx=(0, 1) if column < 2 else 0)
            self.combined_synthesis_tab_buttons[editor_name] = btn
        self._show_synthesis_choice()
        self.nb.add(self.synthesis_tab, text="Synthesis Plan", image=self.tab_icons["tecan"], compound="top")
        # Synthesis editor controls stay inside Synthesis Plan. Keeping action-like
        # controls out of the main notebook leaves the global workflow tabs stable.
        self.synthesis_inline_tabs = {}
        self.synthesis_change_tab_image = None
        self.synthesis_combined_tab_images = {}
        self.synthesis_combined_tab_width = 228
        self.synthesis_combined_tab_top_height = 23
        self._syncing_synthesis_inline_tabs = False

        self.product_summary_tab = ttk.Frame(self.nb, style="Chem.TFrame")
        self.cheminformatics_tab = CheminformaticsFrame(
            self.nb,
            compound_provider=lambda: self.compound_tab.records,
            tecan_provider=lambda: self.tecan_tab.get_building_block_table(),
            pyparse_input_callback=self._set_pyparse_input,
            modified_pyparse_input_callback=self._set_modified_pyparse_input,
            pyparse_stock_update_callback=self._prompt_and_update_stock_after_pyparse_input,
            product_structure_parent=self.product_summary_tab,
            synthesis_step_provider=lambda: self.current_synthesis_step,
        )
        self.nb.add(self.cheminformatics_tab, text="Cheminformatics", image=self.tab_icons["chem"], compound="top")

        pyparse_target = PYPARSE_DIR / "PyParse.exe"
        if not pyparse_target.exists():
            pyparse_target = PYPARSE_DIR / "PyParse.py"
        self.lcms_tab = ttk.Frame(self.nb, style="Chem.TFrame")
        self.lcms_nb = ttk.Notebook(self.lcms_tab, style="Chem.TNotebook", takefocus=0)
        self.lcms_nb.pack(fill="both", expand=True, padx=6, pady=6)

        self.pyparse_tab = PyParseRunnerFrame(
            self.lcms_nb,
            title="PyParse",
            default_target=pyparse_target,
            modified=False,
            result_callback=lambda output_dir, _kind: self.cheminformatics_tab.set_pyparse_result_dir("standard", output_dir),
            input_change_callback=lambda path: self._sync_lcms_input("standard", path),
            result_context_callback=self.cheminformatics_tab.analysis_context_signature,
        )
        self.lcms_nb.add(self.pyparse_tab, text="PyParse")

        modified_target = MODIFIED_PYPARSE_DIR / "PyParse.py"
        if not modified_target.exists():
            modified_target = MODIFIED_PYPARSE_DIR / "PyParse.exe"
        self.modified_pyparse_tab = PyParseRunnerFrame(
            self.lcms_nb,
            title="Modified PyParse - Product analysis",
            analysis_kind="product",
            default_target=modified_target,
            modified=True,
            result_callback=lambda output_dir, kind: self.cheminformatics_tab.set_pyparse_result_dir(
                "modified_impurity" if kind == "impurity" else "modified", output_dir
            ),
            input_change_callback=lambda path: self._sync_lcms_input("modified", path),
            result_context_callback=self.cheminformatics_tab.analysis_context_signature,
        )
        self.lcms_nb.add(self.modified_pyparse_tab, text="Modified PyParse - Product analysis")
        self.modified_impurity_tab = PyParseRunnerFrame(
            self.lcms_nb, title="Modified PyParse - Impurity analysis",
            default_target=modified_target, modified=True, analysis_kind="impurity",
            result_callback=lambda output_dir, _kind: self.cheminformatics_tab.set_pyparse_result_dir("modified_impurity", output_dir),
            input_change_callback=lambda path: self._sync_lcms_input("impurity", path),
            result_context_callback=self.cheminformatics_tab.analysis_context_signature,
        )
        self.lcms_nb.add(self.modified_impurity_tab, text="Modified PyParse - Impurity analysis")
        self.nb.add(self.lcms_tab, text="LCMS Analysis", image=self.tab_icons["pyparse"], compound="top")

        self.reaction_summary_tab = ReactionSummaryFrame(
            self.nb,
            tecan_provider=lambda: self.tecan_tab,
            compound_provider=lambda: self.compound_tab.records,
            reaction_provider=lambda: self.cheminformatics_tab._reaction(),
            pushed_provider=lambda: list(self.cheminformatics_tab.pushed_rows.values()),
            product_provider=lambda: ([] if self.cheminformatics_tab.retained_results_var.get() else self.cheminformatics_tab._pyparse_rows()),
            manual_provider=lambda: self.manual_tab,
            opentrons_provider=lambda: self.opentrons_tab,
        )
        self.nb.add(self.reaction_summary_tab, text="Reaction Summary", image=self.tab_icons["map"], compound="top")
        self.cheminformatics_tab.pushed_change_callback = self._pushed_records_changed
        self.reaction_summary_tab.plan_status_provider = self._pushed_plan_status

        self.nb.add(self.product_summary_tab, text="Product Summary", image=self.tab_icons["chem"], compound="top")

        self.next_step_tab = ttk.Frame(self.nb, style="Chem.TFrame", padding=24)
        ttk.Label(
            self.next_step_tab,
            text="Continue a multistep synthesis",
            font=("Segoe UI", 16, "bold"),
            style="Chem.TLabel",
        ).pack(anchor="w", pady=(0, 10))
        next_synthesis_box = ttk.LabelFrame(
            self.next_step_tab,
            text="Start next synthesis step",
            padding=14,
        )
        next_synthesis_box.pack(fill="x", anchor="w", pady=(0, 14))
        self.next_step_description_var = tk.StringVar()
        ttk.Label(
            next_synthesis_box,
            textvariable=self.next_step_description_var,
            wraplength=850,
            justify="left",
            style="TLabel",
        ).pack(anchor="w", pady=(0, 18))
        ttk.Button(
            next_synthesis_box,
            text="Start next synthesis step",
            command=self._start_next_synthesis_step,
            style="ChemAction.TButton",
        ).pack(anchor="w")
        ttk.Label(self.next_step_tab, text="Product properties & stock preparation",
                  font=("Segoe UI", 16, "bold"), style="Chem.TLabel").pack(anchor="w", pady=(10, 10))
        clogp_box = ttk.LabelFrame(self.next_step_tab, text="Molecular Properties & Alerts Calculator", padding=14)
        clogp_box.pack(fill="x", anchor="w", pady=(0, 14))
        ttk.Label(clogp_box, text="Calculate molecular properties, drug-likeness checks and structural alerts from Product Details structures.",
                  wraplength=850).pack(anchor="w", pady=(0, 18))
        ttk.Button(clogp_box, text="Send products to Properties & Alerts Calculator",
                   command=self._send_products_to_clogp_calculator, style="FileAction.TButton").pack(anchor="w")
        solution_box = ttk.LabelFrame(
            self.next_step_tab,
            text="Solution & Stock Calculator",
            padding=14,
        )
        solution_box.pack(fill="x", anchor="w")
        self.solution_calculator_description_var = tk.StringVar()
        ttk.Label(
            solution_box,
            textvariable=self.solution_calculator_description_var,
            wraplength=850,
            justify="left",
            style="TLabel",
        ).pack(anchor="w", pady=(0, 18))
        ttk.Button(
            solution_box,
            text="Send products to Solution Calculator",
            command=self._send_products_to_solution_calculator,
            style="FileAction.TButton",
        ).pack(anchor="w")
        self.nb.add(self.next_step_tab, text="Next Step", image=self.tab_icons["template"], compound="top")
        self._update_next_step_tab_text()

        self.nb.bind("<ButtonPress-1>", self._on_main_notebook_button_press)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.lcms_nb.bind("<<NotebookTabChanged>>", self._on_lcms_tab_changed)
        self.protocol("WM_DELETE_WINDOW", self._confirm_close)
        self.after(50, lambda: style_plain_widgets(self))
        self.after(60, self._raise_project_actions)
        install_tooltips(self)
        install_page_presentation(self)
        self._start_project_tracking()

    def _raise_project_actions(self, _event=None):
        try:
            self.project_bar.lift()
        except tk.TclError:
            pass

    def _launch_compound_library_builder(self):
        return launch_compound_library_builder(parent=self)

    def _launch_aromatic_smiles_converter(self):
        return launch_aromatic_smiles_converter(parent=self)

    def _launch_opentrons_simulator(self):
        return launch_opentrons_simulator(parent=self)

    def _launch_solution_calculator(self):
        return launch_solution_calculator(parent=self)

    def _confirm_close(self):
        if self._close_prompt_active:
            return
        if '_project_changes' in self.__dict__:
            self.compound_tab._commit_pending_form_update()
            self.compound_tab._commit_pending_quantity_update()
            if not self._check_project_changes():
                self.destroy()
                return
        self._close_prompt_active = True
        try:
            choice = messagebox.askyesnocancel(
                "Save progress before closing?",
                "Would you like to export a portable XinPilot project before closing?\n\n"
                "Yes: Export the project, then close.\n"
                "No: Close without exporting.\n"
                "Cancel: Return to XinPilot.",
                parent=self,
            )
            if choice is None:
                return
            if choice and not self._export_project():
                return
            self.destroy()
        finally:
            self._close_prompt_active = False

    def _plan_fingerprint(self, source):
        import hashlib
        frame = {"Tecan": self.tecan_tab, "Manual workflow": self.manual_tab, "Opentrons": self.opentrons_tab,
                 "External Import": self.external_import_tab}[source]
        state = frame.export_state()
        keys = {"Tecan": ("blocks", "exported_gwl_files", "mode"),
                "Manual workflow": ("rows", "plate_size"),
                "Opentrons": ("rows", "labware_configs"),
                "External Import": ("transfers", "sources", "settings")}[source]
        return hashlib.sha256(json.dumps({key: state.get(key) for key in keys}, sort_keys=True, default=str).encode()).hexdigest()

    def _pushed_plan_status(self):
        changed = [source for source, signature in self.cheminformatics_tab.pushed_plan_fingerprints.items()
                   if source in {"Tecan", "Manual workflow", "Opentrons", "External Import"} and signature != self._plan_fingerprint(source)]
        return ("Changed since last push: " + ", ".join(changed) + ". Push again to update this summary.") if changed else ""

    def _pushed_records_changed(self, action):
        if action.startswith("push:"):
            source = action.split(":", 1)[1]
            self.cheminformatics_tab.pushed_plan_fingerprints[source] = self._plan_fingerprint(source)
        if action == "all":
            for name in ("pyparse_tab", "modified_pyparse_tab", "modified_impurity_tab"):
                runner = getattr(self, name, None)
                if runner is not None and hasattr(runner, "output_dir_var"):
                    runner.output_dir_var.set("")
        if hasattr(self, "reaction_summary_tab"):
            self.reaction_summary_tab.refresh()

    def _push_tecan_to_cheminformatics(self, rows: Optional[List[Dict[str, object]]] = None):
        self.cheminformatics_tab.push_from_tecan(rows)

    def _push_manual_to_cheminformatics(self, rows: List[Dict[str, object]]):
        self.cheminformatics_tab.push_from_manual(rows)

    def _add_external_compounds(self, records):
        from rdkit import Chem
        from rdkit.Chem import Descriptors
        additions = []
        for record in records:
            values = {key: "" for key in compound_notes_frame.DATA_HEADERS}
            values.update(record)
            if values.get("SMILES"):
                values["MW"] = f"{Descriptors.MolWt(Chem.MolFromSmiles(values['SMILES'])):.6g}"
            additions.append(compound_notes_frame.CompoundRecord(values))
        self.compound_tab.records.extend(additions)
        self.compound_tab._refresh_tree()

    def _push_external_to_cheminformatics(self, rows):
        self.cheminformatics_tab.push_from_external(rows)

    def _push_opentrons_to_cheminformatics(self, rows: List[Dict[str, object]]):
        if hasattr(self.cheminformatics_tab, "push_from_opentrons"):
            self.cheminformatics_tab.push_from_opentrons(rows)
        else:
            self.cheminformatics_tab.push_from_manual(rows)

    def _synthesis_view_contains_tecan(self, name: Optional[str] = None) -> bool:
        active = self.synthesis_active_editor if name is None else name
        return active == "Tecan"

    def _clear_synthesis_display(self):
        for host in getattr(self, "synthesis_editor_hosts", {}).values():
            host.pack_forget()

    def _refresh_visible_synthesis_editors(self):
        active = getattr(self, "synthesis_active_editor", None)
        if active == "Manual":
            self.manual_tab._refresh_compound_choices()
        if active == "External Import":
            self.external_import_tab._refresh_sources()
        if active == "Opentrons":
            self.opentrons_tab._refresh_compound_choices()

    def _set_combined_synthesis_tab_button_states(self):
        selected = self.synthesis_active_editor
        for name, button in getattr(self, "combined_synthesis_tab_buttons", {}).items():
            button.state(["!disabled"])
            button_style = "SynthesisSelectorSelected.TButton" if name == selected else "SynthesisSelector.TButton"
            button.configure(
                style=button_style
            )
        for name in ("Tecan", "Opentrons", "Manual"):
            frame = getattr(self, "synthesis_inline_tabs", {}).get(name)
            if frame is not None and str(frame) in self.nb.tabs():
                self.nb.tab(frame, state="disabled" if name == selected else "normal")
        selector = getattr(self, "synthesis_inline_tabs", {}).get("Change synthesis editor")
        if (
            self.synthesis_active_editor == "Combined Synthesis"
            and selector is not None
            and str(selector) in self.nb.tabs()
        ):
            self._configure_synthesis_inline_tab("Change synthesis editor", selector)

    def _select_synthesis_editor_from_bar(self, name: str):
        self._show_synthesis_editor(name)

    def _hide_synthesis_inline_tabs(self):
        if getattr(self, "_syncing_synthesis_inline_tabs", False):
            return
        self._syncing_synthesis_inline_tabs = True
        try:
            visible_tabs = set(self.nb.tabs())
            for frame in getattr(self, "synthesis_inline_tabs", {}).values():
                if str(frame) in visible_tabs:
                    self.nb.forget(frame)
        finally:
            self._syncing_synthesis_inline_tabs = False

    def _make_synthesis_change_tab_image(self, text: str):
        """Render one colored notebook tab without changing every main-tab style."""
        try:
            font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuib.ttf"
            font = ImageFont.truetype(str(font_path), 13)
        except Exception:
            font = ImageFont.load_default()
        probe = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(probe)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        width = right - left + 14
        height = max(24, bottom - top + 10)
        image = Image.new("RGB", (width, height), COLORS["file_action"])
        draw = ImageDraw.Draw(image)
        draw.text(
            ((width - (right - left)) / 2 - left, (height - (bottom - top)) / 2 - top),
            text,
            fill="#ffffff",
            font=font,
        )
        return ImageTk.PhotoImage(image, master=self)

    def _make_combined_synthesis_tab_image(self, selected: str):
        """Draw the compact two-level Combined Synthesis control as one tab."""
        width = self.synthesis_combined_tab_width
        top_height = self.synthesis_combined_tab_top_height
        bottom_height = 23
        height = top_height + bottom_height
        try:
            font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeuib.ttf"
            font = ImageFont.truetype(str(font_path), 12)
            small_font = ImageFont.truetype(str(font_path), 11)
        except Exception:
            font = ImageFont.load_default()
            small_font = font

        image = Image.new("RGB", (width, height), COLORS["panel"])
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, top_height - 1), fill=COLORS["file_action"])

        change_text = "Change synthesis editor"
        box = draw.textbbox((0, 0), change_text, font=font)
        draw.text(
            ((width - (box[2] - box[0])) / 2 - box[0], (top_height - (box[3] - box[1])) / 2 - box[1]),
            change_text,
            fill="#ffffff",
            font=font,
        )

        labels = ("Tecan", "Opentrons", "Manual")
        cell_width = width / len(labels)
        for index, label in enumerate(labels):
            left = round(index * cell_width)
            right = round((index + 1) * cell_width) - 1
            fill = COLORS["accent"] if label == selected else COLORS["panel"]
            foreground = "#ffffff" if label == selected else COLORS["text"]
            draw.rectangle(
                (left, top_height, right, height - 1),
                fill=fill,
                outline=COLORS["line"],
                width=1,
            )
            box = draw.textbbox((0, 0), label, font=small_font)
            draw.text(
                (
                    left + (right - left + 1 - (box[2] - box[0])) / 2 - box[0],
                    top_height + (bottom_height - (box[3] - box[1])) / 2 - box[1],
                ),
                label,
                fill=foreground,
                font=small_font,
            )
        return ImageTk.PhotoImage(image, master=self)

    def _configure_synthesis_inline_tab(self, label: str, frame):
        if label == "Change synthesis editor":
            image = self.synthesis_change_tab_image
            if self.synthesis_active_editor == "Combined Synthesis":
                selected = self.combined_synthesis_active_editor or "Tecan"
                image = self.synthesis_combined_tab_images.get(selected)
                if image is None:
                    image = self._make_combined_synthesis_tab_image(selected)
                    self.synthesis_combined_tab_images[selected] = image
            self.nb.tab(
                frame,
                text="",
                image=image,
                compound="center",
                padding=(0, 0) if self.synthesis_active_editor == "Combined Synthesis" else (2, 2),
            )
        else:
            self.nb.tab(frame, text=label, image="", padding=(7, 7))

    def _sync_synthesis_inline_tabs(self):
        if not hasattr(self, "synthesis_inline_tabs") or getattr(self, "_syncing_synthesis_inline_tabs", False):
            return
        if not self.synthesis_inline_tabs:
            return
        if self.nb.select() != str(self.synthesis_tab) or self.synthesis_active_editor is None:
            self._hide_synthesis_inline_tabs()
            return

        # Keep one compact selector beside Synthesis Plan.  In Combined mode its
        # image has Change editor on top and the three editor tabs underneath.
        labels = ["Change synthesis editor"]

        self._syncing_synthesis_inline_tabs = True
        try:
            visible_tabs = set(self.nb.tabs())
            for label, frame in self.synthesis_inline_tabs.items():
                if label not in labels and str(frame) in visible_tabs:
                    self.nb.forget(frame)

            insert_at = self.nb.index(self.synthesis_tab) + 1
            for label in labels:
                frame = self.synthesis_inline_tabs[label]
                if str(frame) not in self.nb.tabs():
                    self.nb.insert(insert_at, frame)
                else:
                    self.nb.insert(insert_at, frame)
                self._configure_synthesis_inline_tab(label, frame)
                insert_at += 1
            self._set_combined_synthesis_tab_button_states()
        finally:
            self._syncing_synthesis_inline_tabs = False

    def _activate_synthesis_inline_tab(self, tab_id: str, event=None, target_idx: Optional[int] = None):
        for label, frame in getattr(self, "synthesis_inline_tabs", {}).items():
            if str(frame) != tab_id:
                continue
            if label == "Change synthesis editor":
                if self.synthesis_active_editor == "Combined Synthesis" and event is not None:
                    # Find the click's horizontal position within this composite tab.
                    left = event.x
                    while left > 0:
                        try:
                            if self.nb.index(f"@{left - 1},{event.y}") != target_idx:
                                break
                        except tk.TclError:
                            break
                        left -= 1
                    top = event.y
                    while top > 0:
                        try:
                            if self.nb.index(f"@{event.x},{top - 1}") != target_idx:
                                break
                        except tk.TclError:
                            break
                        top -= 1
                    right = event.x
                    while right < self.nb.winfo_width() - 1:
                        try:
                            if self.nb.index(f"@{right + 1},{event.y}") != target_idx:
                                break
                        except tk.TclError:
                            break
                        right += 1
                    bottom = event.y
                    while bottom < self.nb.winfo_height() - 1:
                        try:
                            if self.nb.index(f"@{event.x},{bottom + 1}") != target_idx:
                                break
                        except tk.TclError:
                            break
                        bottom += 1
                    tab_width = right - left + 1
                    tab_height = bottom - top + 1
                    image_left = max(0, (tab_width - self.synthesis_combined_tab_width) // 2)
                    image_top = max(0, (tab_height - 46) // 2)
                    local_x = max(0, min(self.synthesis_combined_tab_width - 1, event.x - left - image_left))
                    local_y = max(0, event.y - top - image_top)
                    if local_y < self.synthesis_combined_tab_top_height:
                        self._show_synthesis_choice()
                    else:
                        names = ("Tecan", "Opentrons", "Manual")
                        section = min(2, int(local_x * 3 / max(1, self.synthesis_combined_tab_width)))
                        self._show_combined_synthesis_tab(names[section])
                else:
                    self._show_synthesis_choice()
            elif self.synthesis_active_editor == "Combined Synthesis":
                self._show_combined_synthesis_tab(label)
            return

    def _show_synthesis_choice(self):
        if self._synthesis_view_contains_tecan() and not self.tecan_tab.confirm_leave_current_gwl():
            return
        self._clear_synthesis_display()
        self.synthesis_content.pack_forget()
        self.synthesis_editor_bar.pack_forget()
        self.synthesis_choice_frame.pack(fill="both", expand=True)
        self.synthesis_active_editor = None
        self._sync_synthesis_inline_tabs()

    def _show_synthesis_editor(self, name: str):
        if name not in self.synthesis_editors:
            return
        if self._synthesis_view_contains_tecan() and not self._synthesis_view_contains_tecan(name) and not self.tecan_tab.confirm_leave_current_gwl():
            return
        self.synthesis_choice_frame.pack_forget()
        self.synthesis_editor_bar.pack_forget()
        self.synthesis_content.pack_forget()
        self._clear_synthesis_display()
        self.synthesis_editor_bar.pack(fill="x")
        self.combined_synthesis_active_editor = None
        self.synthesis_content.pack(fill="both", expand=True)
        self.synthesis_editor_hosts[name].pack(fill="both", expand=True)
        self.synthesis_active_editor = name
        self._refresh_visible_synthesis_editors()
        self._set_combined_synthesis_tab_button_states()
        self._sync_synthesis_inline_tabs()

    def _show_combined_synthesis_tab(self, name: str, force: bool = False):
        if name not in self.synthesis_editor_hosts:
            return
        if not force and self.synthesis_active_editor == "Combined Synthesis" and self.combined_synthesis_active_editor == "Tecan" and name != "Tecan":
            if not self.tecan_tab.confirm_leave_current_gwl():
                return
        for host in self.synthesis_editor_hosts.values():
            host.pack_forget()
        self.synthesis_editor_hosts[name].pack(fill="both", expand=True)
        self.combined_synthesis_active_editor = name
        self._set_combined_synthesis_tab_button_states()
        self._refresh_visible_synthesis_editors()
        self._sync_synthesis_inline_tabs()

    def _on_main_notebook_button_press(self, event):
        try:
            target_idx = self.nb.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return None
        target_tab = self.nb.tabs()[target_idx]
        if target_tab in {str(frame) for frame in getattr(self, "synthesis_inline_tabs", {}).values()}:
            self._activate_synthesis_inline_tab(target_tab, event=event, target_idx=target_idx)
            return "break"
        current_tab = self.nb.select()
        try:
            current_idx = self.nb.index(current_tab)
        except tk.TclError:
            return None
        if target_idx == current_idx:
            return None
        if current_tab == str(self.compound_tab):
            if not self.compound_tab.confirm_leave_compound_notes():
                return "break"
            return None
        if current_tab != str(getattr(self, "synthesis_tab", "")):
            return None
        if not self._synthesis_view_contains_tecan():
            return None
        if not self.tecan_tab.confirm_leave_current_gwl():
            return "break"
        return None

    def _on_tab_changed(self, _event=None):
        if getattr(self, "_syncing_synthesis_inline_tabs", False):
            return
        selected_tab = self.nb.select()
        if hasattr(self, "next_step_tab") and selected_tab == str(self.next_step_tab):
            return
        self._last_main_tab = selected_tab
        if self.nb.select() == str(self.cheminformatics_tab):
            self.cheminformatics_tab._classify_preview()
        if hasattr(self, "synthesis_tab") and self.nb.select() == str(self.synthesis_tab):
            self._on_synthesis_tab_changed()
            self._sync_synthesis_inline_tabs()
        else:
            self._hide_synthesis_inline_tabs()
        if hasattr(self, "reaction_summary_tab") and self.nb.select() == str(self.reaction_summary_tab):
            self.reaction_summary_tab.refresh()

    def _on_synthesis_tab_changed(self, _event=None):
        self._refresh_visible_synthesis_editors()

    def _on_lcms_tab_changed(self, _event=None):
        pass

    def _set_pyparse_input(self, path: Path):
        if hasattr(self, "pyparse_tab"):
            self.pyparse_tab.set_platemap(path)
        if hasattr(self, "modified_pyparse_tab"):
            self.modified_pyparse_tab.set_platemap(path)

    def _set_modified_pyparse_input(self, path: Path):
        target = self.modified_pyparse_tab
        if _pyparse_platemap_kind(path) == "impurity" and hasattr(self, "modified_impurity_tab"):
            target = self.modified_impurity_tab
        target.set_platemap(path)

    def _sync_lcms_input(self, source: str, path: str):
        if source != "standard" and hasattr(self, "pyparse_tab"):
            self.pyparse_tab.input_data_var.set(path)
        if source != "modified" and hasattr(self, "modified_pyparse_tab"):
            self.modified_pyparse_tab.input_data_var.set(path)
        if source != "impurity" and hasattr(self, "modified_impurity_tab"):
            self.modified_impurity_tab.input_data_var.set(path)

    def _prompt_and_update_stock_after_pyparse_input(self) -> str:
        try:
            experiment_count = int((self.cheminformatics_tab.pyparse_experiment_count_var.get() or "").strip())
        except ValueError:
            messagebox.showwarning("Stock update skipped", "Experiment count must be a whole number greater than 0.")
            return "Stock lists were not updated: invalid experiment count."
        if experiment_count <= 0:
            messagebox.showwarning("Stock update skipped", "Experiment count must be greater than 0.")
            return "Stock lists were not updated: invalid experiment count."

        options = {
            "experiment_count": experiment_count,
            "update_current": bool(self.cheminformatics_tab.pyparse_update_current_stock_var.get()),
            "update_master": bool(self.cheminformatics_tab.pyparse_update_master_stock_var.get()),
        }
        if not options["update_current"] and not options["update_master"]:
            return "Stock lists were not updated."

        deductions = self._stock_deductions_from_exported_gwl_files(options["experiment_count"])
        if not deductions:
            return "Stock lists were not updated: no exported GWL files with Chemical ID and aspirate volume were found."

        messages = []
        if options["update_current"]:
            updated = self._deduct_current_compound_stock(deductions)
            messages.append(f"Compound stock list updated for {updated} ID(s).")
        if options["update_master"]:
            current_path = Path(self.compound_tab.source_excel).resolve() if getattr(self.compound_tab, "source_excel", None) else None
            master_text = (self.compound_tab.master_stock_excel_var.get() or "").strip()
            master_path = Path(master_text).resolve() if master_text else None
            if options["update_current"] and current_path and master_path and current_path == master_path:
                messages.append("Master stock list is the same file as the current stock list, so it was not deducted twice.")
            else:
                updated = self._deduct_master_stock_list(deductions)
                messages.append(f"Master stock list updated for {updated} ID(s).")
        if not messages:
            return "Stock lists were not updated."
        return "Stock update:\n" + "\n".join(messages)

    def _ask_stock_update_options(self) -> Optional[Dict[str, object]]:
        win = tk.Toplevel(self)
        win.title("Update stock lists")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="How many times was this experiment conducted?").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        count_var = tk.StringVar(value="1")
        count_entry = ttk.Entry(body, textvariable=count_var, width=10)
        count_entry.grid(row=1, column=0, sticky="w", pady=(0, 8))

        update_current_var = tk.BooleanVar(value=False)
        update_master_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Update current Compound Notes stock list?", variable=update_current_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(body, text="Update master stock list?", variable=update_master_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        status = ttk.Label(body, text="", foreground="#b00020")
        status.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        result: Dict[str, object] = {}

        def continue_clicked():
            raw = count_var.get().strip()
            try:
                experiment_count = int(raw)
            except ValueError:
                status.configure(text="Enter a whole number.")
                return
            if experiment_count <= 0:
                status.configure(text="Enter a number greater than 0.")
                return
            result.update({
                "experiment_count": experiment_count,
                "update_current": bool(update_current_var.get()),
                "update_master": bool(update_master_var.get()),
            })
            win.destroy()

        def skip_clicked():
            win.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Continue", command=continue_clicked).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Skip Updates", command=skip_clicked).pack(side="left")
        win.bind("<Return>", lambda _e: continue_clicked())
        win.bind("<Escape>", lambda _e: skip_clicked())

        try:
            self.update_idletasks()
            win.geometry(f"+{self.winfo_rootx() + 220}+{self.winfo_rooty() + 140}")
        except Exception:
            pass
        count_entry.focus_set()
        count_entry.selection_range(0, "end")
        self.wait_window(win)
        return result or None

    def _stock_deductions_by_chemical_id(self, experiment_count: int) -> Dict[str, float]:
        if hasattr(self, "tecan_tab") and self.tecan_tab.listbox.curselection():
            self.tecan_tab._apply_current(silent=True)
        deductions: Dict[str, float] = {}
        for block in getattr(self.tecan_tab, "blocks", []):
            chemical_id = str(getattr(block, "chemical_name", "") or "").strip()
            if not chemical_id:
                continue
            try:
                aspirate_volume = float(getattr(block, "source_volume", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if aspirate_volume <= 0:
                continue
            key = chemical_id.upper()
            deductions[key] = deductions.get(key, 0.0) + aspirate_volume * experiment_count
        return deductions

    def _stock_deductions_from_exported_gwl_files(self, experiment_count: int) -> Dict[str, float]:
        deductions: Dict[str, float] = {}
        for entry in getattr(self.tecan_tab, "exported_gwl_files", []) or []:
            try:
                snapshot_blocks = [
                    self.tecan_tab._block_from_dict(block_data)
                    for block_data in (entry.get("blocks", []) or [])
                    if isinstance(block_data, dict)
                ]
                if snapshot_blocks:
                    blocks = snapshot_blocks
                else:
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
                    _mode, blocks = self.tecan_tab._blocks_from_gwl_content(
                        content,
                        source_path=path if path and path.exists() else None,
                        ask_mode=False,
                        ask_csv=False,
                    )
            except Exception:
                continue
            for block in blocks:
                chemical_id = str(getattr(block, "chemical_name", "") or "").strip()
                if not chemical_id:
                    continue
                try:
                    aspirate_volume = float(getattr(block, "source_volume", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                if aspirate_volume <= 0:
                    continue
                key = chemical_id.upper()
                deductions[key] = deductions.get(key, 0.0) + aspirate_volume * experiment_count
        return deductions

    @staticmethod
    def _format_stock_volume(value: float) -> str:
        return f"{value:.1f}"

    def _deduct_current_compound_stock(self, deductions: Dict[str, float]) -> int:
        updates = []
        insufficient = []
        for rec in self.compound_tab.records:
            data = rec.values
            cid = str(data.get("ID", "") or "").strip().upper()
            if cid not in deductions:
                continue
            current = core.parse_float(data.get("Volume"))
            if current is None:
                continue
            remaining = current - deductions[cid]
            if remaining < -1e-9:
                insufficient.append(f"{cid}: available {current:.1f} uL, required {deductions[cid]:.1f} uL")
            else:
                updates.append((data, remaining))
        if insufficient:
            raise ValueError("Insufficient current stock; nothing was deducted:\n" + "\n".join(insufficient))
        source_excel = getattr(self.compound_tab, "source_excel", None)
        if getattr(self.compound_tab, "excel_loaded", False) and source_excel is not None:
            self._write_stock_volume_column(Path(source_excel), deductions)
        for data, remaining in updates:
            data["Volume"] = self._format_stock_volume(max(0.0, remaining))
        self.compound_tab._refresh_tree()
        return len(updates)

    def _deduct_master_stock_list(self, deductions: Dict[str, float]) -> int:
        master_path_text = (self.compound_tab.master_stock_excel_var.get() or "").strip()
        if not master_path_text:
            messagebox.showwarning("Master stock list not selected", "Master stock list was not updated because no master stock list is selected.")
            return 0
        master_path = Path(master_path_text)
        if not master_path.exists():
            messagebox.showwarning("Master stock list not found", f"Master stock list was not updated because this file was not found:\n{master_path}")
            return 0
        return self._write_stock_volume_column(master_path, deductions)

    def _write_stock_volume_column(self, path: Path, deductions: Dict[str, float]) -> int:
        wb = openpyxl.load_workbook(path)
        try:
            ws = wb[wb.sheetnames[0]]
            header_to_col = {}
            for c in range(1, ws.max_column + 1):
                name = str(ws.cell(1, c).value or "").strip()
                if name:
                    header_to_col[name] = c
            id_col = header_to_col.get("ID")
            volume_col = header_to_col.get("Volume")
            if not id_col or not volume_col:
                raise ValueError("Stock list must contain ID and Volume columns.")
            updates = []
            insufficient = []
            for r in range(2, ws.max_row + 1):
                cid = str(ws.cell(r, id_col).value or "").strip().upper()
                if cid not in deductions:
                    continue
                current = core.parse_float(ws.cell(r, volume_col).value)
                if current is None:
                    continue
                remaining = current - deductions[cid]
                if remaining < -1e-9:
                    insufficient.append(f"{cid}: available {current:.1f} uL, required {deductions[cid]:.1f} uL")
                else:
                    updates.append((r, remaining))
            if insufficient:
                raise ValueError(f"Insufficient stock in {path.name}; nothing was deducted:\n" + "\n".join(insufficient))
            for row, remaining in updates:
                ws.cell(row, volume_col).value = self._format_stock_volume(max(0.0, remaining))
            self.compound_tab._atomic_save_workbook(wb, path)
            return len(updates)
        finally:
            wb.close()

    def _update_next_step_tab_text(self):
        next_step = max(2, int(self.current_synthesis_step) + 1)
        if hasattr(self, "next_step_tab"):
            self.nb.tab(self.next_step_tab, text="Next Step")
        if hasattr(self, "next_step_description_var"):
            self.next_step_description_var.set(
                f"Archive synthesis step {self.current_synthesis_step}, choose the product wells to carry forward, "
                f"and prepare a blank workspace for synthesis step {next_step}. Selected products will be added "
                "to Compound Notes; concentration and available volume must be entered after the material is assessed."
            )
        if hasattr(self, "solution_calculator_description_var"):
            self.solution_calculator_description_var.set(
                "Send current Product Details to the standalone calculator using all products, manual RXN-well "
                "selection, or automatic UV254-purity selection. This does not archive the step, clear any data, "
                "advance the synthesis, or write to Compound Notes or stock lists."
            )

    def _return_from_next_step_tab(self):
        target = self._last_main_tab
        if not target or target == str(getattr(self, "next_step_tab", "")):
            target = str(self.product_summary_tab)
        try:
            self.nb.select(target)
        except tk.TclError:
            self.nb.select(self.compound_tab)

    def _next_step_product_candidates(self) -> List[Dict[str, object]]:
        candidates: List[Dict[str, object]] = []
        for row in self.cheminformatics_tab._pyparse_rows():
            if not str(row.get("desired product smiles", "") or "").strip():
                continue
            source = self.cheminformatics_tab._product_structure_uv_source_for_row(row)
            purity = self.cheminformatics_tab._product_structure_purity_for_row(row, source)
            source_label = self.cheminformatics_tab._product_structure_uv_source_label(source)
            candidate = build_product_candidate(row, purity, source_label)
            reaction_well = _normalize_well(row.get("reaction_well", ""))
            candidate["lcms_reference_smiles"] = str(
                self.cheminformatics_tab.lcms_target_smiles_by_well.get(reaction_well, "") or ""
            ).strip()
            candidates.append(candidate)
        return sorted(candidates, key=lambda item: core.well_key(str(item.get("reaction_well", ""))))

    def _choose_solution_calculator_selection_mode(self) -> str:
        win = tk.Toplevel(self)
        win.title("Send products to calculator")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result = {"mode": ""}
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Which Product Details rows should be sent?",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 12))
        ttk.Label(
            body,
            text=(
                "Send All transfers every current product. Manual selection chooses RXN wells. "
                "Auto-selection uses each row's selected UV254 purity source."
            ),
            wraplength=620,
            justify="left",
        ).pack(anchor="w", pady=(0, 14))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")

        def choose(mode: str):
            result["mode"] = mode
            win.destroy()

        ttk.Button(buttons, text="Send All", command=lambda: choose("all"), style="ChemAction.TButton").pack(side="left")
        ttk.Button(buttons, text="Manual RXN-well selection", command=lambda: choose("manual")).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Auto-select by UV254 purity", command=lambda: choose("auto")).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=(20, 0))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Escape>", lambda _event: win.destroy())
        self.wait_window(win)
        return result["mode"]

    def _choose_next_step_selection_mode(self) -> str:
        win = tk.Toplevel(self)
        win.title("Select products for the next synthesis step")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result = {"mode": ""}
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="How should XinPilot select the Step " + str(self.current_synthesis_step) + " product wells?",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 12))
        ttk.Label(
            body,
            text="Manual selection lets you choose individual RXN wells. Auto-selection uses each row's selected UV254 purity source.",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 14))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")

        def choose(mode: str):
            result["mode"] = mode
            win.destroy()

        ttk.Button(buttons, text="Manual RXN-well selection", command=lambda: choose("manual"), style="ChemAction.TButton").pack(side="left")
        ttk.Button(buttons, text="Auto-select by UV254 purity", command=lambda: choose("auto"), style="FileAction.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=(20, 0))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Escape>", lambda _event: win.destroy())
        self.wait_window(win)
        return result["mode"]

    def _manual_product_selection(
        self,
        candidates: List[Dict[str, object]],
        *,
        title: str,
        instruction: str,
        action_text: str,
    ) -> List[Dict[str, object]]:
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        win.geometry("1050x520")
        win.minsize(780, 380)
        win.grab_set()
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)
        result: List[Dict[str, object]] = []
        body = ttk.Frame(win, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            body,
            text=instruction,
            wraplength=950,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        columns = ("rxn_well", "lcms_well", "product_id", "product_name", "purity", "source")
        tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="extended", height=16)
        for column, heading, width in (
            ("rxn_well", "RXN well", 85),
            ("lcms_well", "LCMS well", 85),
            ("product_id", "Product ID", 150),
            ("product_name", "Product name", 220),
            ("purity", "UV254 purity", 105),
            ("source", "Purity source", 270),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="w")
        ybar = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ybar.set)
        tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="left", fill="y")
        for index, candidate in enumerate(candidates):
            tree.insert("", "end", iid=str(index), values=(
                candidate.get("reaction_well", ""),
                candidate.get("lcms_well", ""),
                candidate.get("product_id", ""),
                candidate.get("product_name", ""),
                candidate.get("purity", "") or "Not available",
                candidate.get("purity_source", ""),
            ))

        controls = ttk.Frame(win, padding=(12, 0, 12, 12))
        controls.grid(row=1, column=0, sticky="ew")

        def use_selected():
            chosen = [candidates[int(iid)] for iid in tree.selection()]
            if not chosen:
                messagebox.showwarning("No RXN wells selected", "Select at least one product well to continue.", parent=win)
                return
            result.extend(chosen)
            win.destroy()

        ttk.Button(controls, text="Select All", command=lambda: tree.selection_set(tree.get_children())).pack(side="left")
        ttk.Button(controls, text="Clear Selection", command=lambda: tree.selection_remove(tree.selection())).pack(side="left", padx=(6, 0))
        ttk.Button(controls, text=action_text, command=use_selected, style="ChemAction.TButton").pack(side="right")
        ttk.Button(controls, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.bind("<Return>", lambda _event: use_selected())
        self.wait_window(win)
        return result

    def _manual_next_step_product_selection(self, candidates: List[Dict[str, object]]) -> List[Dict[str, object]]:
        return IntegratedFullApp._manual_product_selection(
            self,
            candidates,
            title="Select RXN wells for the next synthesis step",
            instruction=(
                "Select the Step " + str(self.current_synthesis_step)
                + " product wells to use as starting materials. Use Ctrl or Shift to select multiple rows."
            ),
            action_text="Use Selected Products",
        )

    def _manual_solution_calculator_product_selection(
        self,
        candidates: List[Dict[str, object]],
    ) -> List[Dict[str, object]]:
        return IntegratedFullApp._manual_product_selection(
            self,
            candidates,
            title="Select RXN wells for calculator",
            instruction=(
                "Select the Product Details rows to copy into the standalone calculator. "
                "Use Ctrl or Shift to select multiple RXN wells."
            ),
            action_text="Send Selected Products",
        )

    def _ask_uv254_threshold_dialog(
        self,
        *,
        heading: str,
        explanation: str,
        action_text: str,
    ) -> Optional[float]:
        win = tk.Toplevel(self)
        win.title("Auto-select by UV254 purity")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        result: Dict[str, float] = {}
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=heading, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=explanation).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        value_var = tk.DoubleVar(value=30.0)
        text_var = tk.StringVar(value="30.0")
        scale = ttk.Scale(body, from_=0, to=100, variable=value_var, orient="horizontal", length=380)
        scale.grid(row=2, column=0, sticky="ew", padx=(0, 10))
        entry = ttk.Entry(body, textvariable=text_var, width=8)
        entry.grid(row=2, column=1, sticky="e")
        ttk.Label(body, text="%", style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=(3, 0))
        status = ttk.Label(body, text="", foreground="#b00020")
        status.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        syncing = {"value": False}

        def scale_changed(*_args):
            if syncing["value"]:
                return
            syncing["value"] = True
            text_var.set(f"{value_var.get():.1f}")
            syncing["value"] = False

        def entry_changed(*_args):
            if syncing["value"]:
                return
            parsed = parse_percent(text_var.get())
            if parsed is None:
                return
            syncing["value"] = True
            value_var.set(parsed)
            syncing["value"] = False

        value_var.trace_add("write", scale_changed)
        text_var.trace_add("write", entry_changed)

        def continue_clicked():
            threshold = parse_percent(text_var.get())
            if threshold is None:
                status.configure(text="Enter a number from 0 to 100.")
                return
            result["threshold"] = threshold
            win.destroy()

        controls = ttk.Frame(body)
        controls.grid(row=4, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(controls, text=action_text, command=continue_clicked, style="ChemAction.TButton").pack(side="left")
        ttk.Button(controls, text="Cancel", command=win.destroy).pack(side="left", padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.bind("<Return>", lambda _event: continue_clicked())
        entry.focus_set()
        entry.selection_range(0, "end")
        self.wait_window(win)
        return result.get("threshold")

    def _ask_uv254_threshold(self) -> Optional[float]:
        return IntegratedFullApp._ask_uv254_threshold_dialog(
            self,
            heading="Minimum UV254 purity for carry-forward",
            explanation="Wells with purity equal to or higher than this value will be selected.",
            action_text="Select Wells",
        )

    def _ask_solution_calculator_uv254_threshold(self) -> Optional[float]:
        return IntegratedFullApp._ask_uv254_threshold_dialog(
            self,
            heading="Minimum UV254 purity to send",
            explanation="Product Details rows with purity equal to or higher than this value will be sent.",
            action_text="Send Matching Products",
        )

    def _solution_calculator_payload(self, selected: List[Dict[str, object]]) -> Dict[str, object]:
        return {
            "schema": "xinpilot_solution_calculator.v1",
            "delete_after_load": True,
            "source": {
                "project_name": str(self.current_project_name or ""),
                "synthesis_step": int(self.current_synthesis_step),
            },
            "products": [dict(candidate) for candidate in selected],
        }

    def _write_solution_calculator_payload(self, selected: List[Dict[str, object]]) -> str:
        payload = self._solution_calculator_payload(selected)
        path = os.path.join(
            tempfile.gettempdir(),
            f"xinpilot_solution_calculator_{uuid.uuid4().hex}.json",
        )
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path

    def _send_products_to_solution_calculator(self):
        if self._solution_calculator_dialog_active:
            return False
        self._solution_calculator_dialog_active = True
        payload_path = ""
        try:
            candidates = self._next_step_product_candidates()
            if not candidates:
                messagebox.showwarning(
                    "No products available",
                    "No reaction wells currently contain a Product Details structure. Generate or import Product Details before sending products to the calculator.",
                    parent=self,
                )
                return False

            mode = self._choose_solution_calculator_selection_mode()
            if not mode:
                return False
            if mode == "all":
                selected = [dict(candidate) for candidate in candidates]
            elif mode == "manual":
                selected = self._manual_solution_calculator_product_selection(candidates)
            else:
                threshold = self._ask_solution_calculator_uv254_threshold()
                if threshold is None:
                    return False
                selected = select_candidates_by_threshold(candidates, threshold)
                if not selected:
                    numeric_count = sum(candidate.get("purity_percent") is not None for candidate in candidates)
                    messagebox.showwarning(
                        "No wells met the threshold",
                        f"No product wells had UV254 purity equal to or higher than {threshold:g}%. "
                        f"Numeric purity was available for {numeric_count} of {len(candidates)} Product Details rows.",
                        parent=self,
                    )
                    return False

            if not selected:
                return False
            payload_path = self._write_solution_calculator_payload(selected)
            if not launch_solution_calculator(payload_path, parent=self):
                try:
                    os.unlink(payload_path)
                except OSError:
                    pass
                return False
            self.project_status_var.set(
                f"Sent {len(selected)} Product Details row(s) to Solution & Stock Calculator; XinPilot data was unchanged."
            )
            return True
        except Exception as exc:
            if payload_path:
                try:
                    os.unlink(payload_path)
                except OSError:
                    pass
            messagebox.showerror("Send to Solution Calculator failed", str(exc), parent=self)
            return False
        finally:
            self._solution_calculator_dialog_active = False

    def _clogp_calculator_payload(self, selected: List[Dict[str, object]]) -> Dict[str, object]:
        return {
            "schema": "xinpilot_clogp_calculator.v1",
            "delete_after_load": True,
            "source": {
                "project_name": str(self.current_project_name or ""),
                "synthesis_step": int(self.current_synthesis_step),
            },
            "products": [dict(candidate) for candidate in selected],
        }

    def _write_clogp_calculator_payload(self, selected: List[Dict[str, object]]) -> str:
        payload = self._clogp_calculator_payload(selected)
        path = os.path.join(
            tempfile.gettempdir(),
            f"xinpilot_clogp_calculator_{uuid.uuid4().hex}.json",
        )
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path

    def _send_products_to_clogp_calculator(self):
        if self._solution_calculator_dialog_active:
            return False
        self._solution_calculator_dialog_active = True
        payload_path = ""
        try:
            candidates = self._next_step_product_candidates()
            if not candidates:
                messagebox.showwarning(
                    "No products available",
                    "No reaction wells currently contain a Product Details structure. Generate or import Product Details before sending products to the calculator.",
                    parent=self,
                )
                return False

            mode = self._choose_solution_calculator_selection_mode()
            if not mode:
                return False
            if mode == "all":
                selected = [dict(candidate) for candidate in candidates]
            elif mode == "manual":
                selected = self._manual_solution_calculator_product_selection(candidates)
            else:
                threshold = self._ask_solution_calculator_uv254_threshold()
                if threshold is None:
                    return False
                selected = select_candidates_by_threshold(candidates, threshold)
                if not selected:
                    numeric_count = sum(candidate.get("purity_percent") is not None for candidate in candidates)
                    messagebox.showwarning(
                        "No wells met the threshold",
                        f"No product wells had UV254 purity equal to or higher than {threshold:g}%. "
                        f"Numeric purity was available for {numeric_count} of {len(candidates)} Product Details rows.",
                        parent=self,
                    )
                    return False

            if not selected:
                return False
            payload_path = self._write_clogp_calculator_payload(selected)
            if not launch_clogp_calculator(payload_path, parent=self):
                try:
                    os.unlink(payload_path)
                except OSError:
                    pass
                return False
            self.project_status_var.set(
                f"Sent {len(selected)} Product Details row(s) to Molecular Properties & Alerts Calculator; XinPilot data was unchanged."
            )
            return True
        except Exception as exc:
            if payload_path:
                try:
                    os.unlink(payload_path)
                except OSError:
                    pass
            messagebox.showerror("Send to Molecular Properties & Alerts Calculator failed", str(exc), parent=self)
            return False
        finally:
            self._solution_calculator_dialog_active = False

    def _archive_current_synthesis_step(self, selected: List[Dict[str, object]], selection_method: str):
        self.completed_synthesis_steps.append(create_synthesis_step_snapshot(
            self._project_payload(),
            step_number=self.current_synthesis_step,
            selected_products=selected,
            selection_method=selection_method,
        ))

    def _attach_selected_impurity_history(self, selected: List[Dict[str, object]]) -> int:
        by_well: Dict[str, List[Dict[str, object]]] = {}
        for impurity in self.cheminformatics_tab._included_impurity_rows():
            well = _normalize_well(impurity.get("reaction_well", ""))
            if well:
                by_well.setdefault(well, []).append(dict(impurity))
        total = 0
        for candidate in selected:
            well = _normalize_well(candidate.get("reaction_well", ""))
            impurities = [dict(item) for item in by_well.get(well, [])]
            candidate["carried_impurities"] = impurities
            total += len(impurities)
        return total

    @staticmethod
    def _carried_impurity_sources(
        selected: List[Dict[str, object]],
        source_step: int,
        carryover_status: str,
    ) -> Dict[str, Dict[str, object]]:
        sources: Dict[str, Dict[str, object]] = {}
        for candidate in selected:
            compound_id = str(candidate.get("promoted_compound_id", "") or "").strip()
            impurities = [
                dict(item)
                for item in (candidate.get("carried_impurities", []) or [])
                if isinstance(item, dict) and str(item.get("smiles", "") or "").strip()
            ]
            if not compound_id or not impurities:
                continue
            sources[compound_id] = {
                "compound_id": compound_id,
                "source_step": int(source_step),
                "source_reaction_well": _normalize_well(candidate.get("reaction_well", "")),
                "source_lcms_well": _normalize_well(candidate.get("lcms_well", "")),
                "carryover_status": str(carryover_status or "Crude or purification not recorded"),
                "impurities": impurities,
            }
        return sources

    def _promote_products_to_compound_notes(self, selected: List[Dict[str, object]]) -> int:
        existing_ids = {
            str(record.values.get("ID", "") or "").strip()
            for record in self.compound_tab.records
            if str(record.values.get("ID", "") or "").strip()
        }
        added = 0
        for candidate in selected:
            values = candidate_to_compound_values(
                candidate,
                source_step=self.current_synthesis_step,
                data_headers=compound_notes_frame.DATA_HEADERS,
                existing_ids=existing_ids,
            )
            candidate["promoted_compound_id"] = values.get("ID", "")
            self.compound_tab.records.append(compound_notes_frame.CompoundRecord(values))
            added += 1
        self.compound_tab.search_var.set("")
        self.compound_tab._refresh_tree()
        if added:
            index = len(self.compound_tab.records) - added
            iid = str(index)
            if self.compound_tab.tree.exists(iid):
                self.compound_tab.tree.selection_set(iid)
                self.compound_tab.tree.focus(iid)
                self.compound_tab.tree.see(iid)
                self.compound_tab._load_record_into_form(self.compound_tab.records[index].values, index)
        return added

    def _clear_workflow_for_next_synthesis_step(
        self,
        carried_impurity_sources: Optional[Dict[str, Dict[str, object]]] = None,
    ):
        self.tecan_tab.import_state({})
        self.manual_tab.import_state({})
        self.external_import_tab.import_state({})
        self.opentrons_tab.import_state({})
        self.cheminformatics_tab.clear_for_next_synthesis_step(carried_impurity_sources)
        self.reaction_summary_tab.import_state({})
        self.pyparse_tab.import_state({})
        self.modified_pyparse_tab.import_state({})
        self.modified_impurity_tab.import_state({})
        self._show_synthesis_choice()
        self.manual_tab._refresh_compound_choices()
        self.opentrons_tab._refresh_compound_choices()

    def _start_next_synthesis_step(self):
        if self._next_step_dialog_active:
            return
        self._next_step_dialog_active = True
        try:
            next_step = self.current_synthesis_step + 1
            if not messagebox.askyesno(
                f"Start synthesis step {next_step}?",
                f"Ready to finish synthesis step {self.current_synthesis_step} and start step {next_step}?",
                parent=self,
            ):
                return

            save_choice = messagebox.askyesnocancel(
                f"Save synthesis step {self.current_synthesis_step}",
                f"Save a portable copy of synthesis step {self.current_synthesis_step} before selecting products?\n\n"
                "Yes: export the current project now.\nNo: continue with an internal archived copy only.\nCancel: stop.",
                parent=self,
            )
            if save_choice is None:
                return
            if save_choice and not self._export_project():
                return

            candidates = self._next_step_product_candidates()
            if not candidates:
                messagebox.showwarning(
                    "No products available",
                    "No reaction wells currently contain a generated or imported product structure. Generate Product Details before starting the next synthesis step.",
                    parent=self,
                )
                return

            mode = self._choose_next_step_selection_mode()
            if not mode:
                return
            selection_method = "Manual RXN-well selection"
            if mode == "manual":
                selected = self._manual_next_step_product_selection(candidates)
            else:
                threshold = self._ask_uv254_threshold()
                if threshold is None:
                    return
                selected = select_candidates_by_threshold(candidates, threshold)
                selection_method = f"UV254 purity >= {threshold:g}%"
                if not selected:
                    numeric_count = sum(candidate.get("purity_percent") is not None for candidate in candidates)
                    messagebox.showwarning(
                        "No wells met the threshold",
                        f"No product wells had UV254 purity equal to or higher than {threshold:g}%. "
                        f"Numeric purity was available for {numeric_count} of {len(candidates)} product wells.",
                        parent=self,
                    )
                    return

            if not selected:
                return
            carried_impurity_count = self._attach_selected_impurity_history(selected)
            purification_choice = messagebox.askyesnocancel(
                "Material preparation for the next step",
                "Were the selected products purified or worked up before they will be used in the next synthesis step?\n\n"
                "Yes: record them as purified/worked up. Earlier impurity candidates will remain as possible residual guidance.\n"
                "No: record them as crude or purification not recorded.\n"
                "Cancel: stop.",
                parent=self,
            )
            if purification_choice is None:
                return
            carryover_status = (
                "Purified/worked up before carry-forward"
                if purification_choice
                else "Crude or purification not recorded"
            )
            wells = ", ".join(str(item.get("reaction_well", "")) for item in selected)
            if not messagebox.askyesno(
                f"Create synthesis step {next_step}",
                f"Carry forward {len(selected)} product(s) from RXN well(s):\n{wells}\n\n"
                "The current synthesis, cheminformatics, LC–MS and summary workspace will be archived and cleared. "
                "Selected products will be added to Compound Notes.\n\n"
                f"XinPilot will carry forward {carried_impurity_count} impurity target(s) associated with these wells "
                "and combine them with the next step's impurity guidance.",
                parent=self,
            ):
                return

            self.compound_tab._commit_pending_form_update()
            self._archive_current_synthesis_step(selected, selection_method)
            added = self._promote_products_to_compound_notes(selected)
            carried_sources = self._carried_impurity_sources(
                selected,
                self.current_synthesis_step,
                carryover_status,
            )
            if self.completed_synthesis_steps:
                self.completed_synthesis_steps[-1]["selected_products"] = [dict(item) for item in selected]
                self.completed_synthesis_steps[-1]["carryover_status"] = carryover_status
                self.completed_synthesis_steps[-1]["carried_impurity_target_count"] = carried_impurity_count
            self._clear_workflow_for_next_synthesis_step(carried_sources)
            self.current_synthesis_step = next_step
            self._update_next_step_tab_text()
            self.project_status_var.set(f"Synthesis step {next_step} started; {added} product(s) carried forward.")
            self.nb.select(self.compound_tab)
            messagebox.showinfo(
                f"Synthesis step {next_step} ready",
                f"Added {added} selected product(s) to Compound Notes and cleared the working tabs for synthesis step {next_step}.\n\n"
                "Enter the concentration and available volume of each carried-forward product before planning transfers.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Start next synthesis step failed", str(exc), parent=self)
        finally:
            self._next_step_dialog_active = False
            if self.nb.select() == str(getattr(self, "next_step_tab", "")):
                self._return_from_next_step_tab()

    def _project_payload(self) -> Dict[str, object]:
        return build_project_payload({
            "compound_notes": {
                "records": [dict(rec.values) for rec in self.compound_tab.records],
                "associated_workbook_name": self.compound_tab.associated_workbook_name(),
                "master_stock_excel": self.compound_tab.master_stock_excel_var.get(),
                "search": self.compound_tab.search_var.get(),
            },
            "tecan": self.tecan_tab.export_state(),
            "manual_workflow": self.manual_tab.export_state() if hasattr(self, "manual_tab") else {},
            "external_import": self.external_import_tab.export_state() if hasattr(self, "external_import_tab") else {},
            "opentrons": self.opentrons_tab.export_state() if hasattr(self, "opentrons_tab") else {},
            "cheminformatics": self.cheminformatics_tab.export_state(),
            "reaction_summary": self.reaction_summary_tab.export_state() if hasattr(self, "reaction_summary_tab") else {},
            "pyparse_runner": self.pyparse_tab.export_state() if hasattr(self, "pyparse_tab") else {},
            "modified_pyparse_runner": self.modified_pyparse_tab.export_state() if hasattr(self, "modified_pyparse_tab") else {},
            "modified_impurity_runner": self.modified_impurity_tab.export_state() if hasattr(self, "modified_impurity_tab") else {},
        }, current_step=self.current_synthesis_step, completed_steps=self.completed_synthesis_steps)

    def _add_portable_project_assets(self, zf: zipfile.ZipFile, payload: Dict[str, object]) -> Dict[str, object]:
        """Adapt controller-owned trace selection to the portable archive service."""
        traces = IntegratedFullApp._portable_trace_assets(self) if hasattr(self, "cheminformatics_tab") else None
        return package_project_assets(zf, payload, traces)

    def _portable_trace_assets(self) -> List[TraceAsset]:
        """Resolve trace identity in the scientific controller, then pass file data."""
        chem = self.cheminformatics_tab
        traces: List[TraceAsset] = []
        for row in chem._cheminformatics_result_export_rows():
            well = _normalize_well(row.get("pyparse_well", ""))
            if not well:
                continue
            paths = chem._product_trace_paths(row)
            safe_well = _safe_pyparse_graph_token(well) or "well"
            for kind, suffix in (("pyparse_uv", "pyparse_uv"), ("modified_uv", "modified_uv254"), ("modified_es", "modified_es")):
                traces.append(TraceAsset(well, kind, paths.get(kind), f"{safe_well}_{suffix}"))
        for row in chem._impurity_reaction_rows():
            well = _normalize_well(row.get("pyparse_well", ""))
            impurities = list(row.get("impurities", []) or [])
            if not well or not impurities:
                continue
            safe_well = _safe_pyparse_graph_token(well) or "well"
            product_row = dict(row.get("product_row", {}) or {})
            product_row["pyparse_well"] = well
            resolved = chem._product_trace_paths(product_row) if product_row else {}
            standard_path = resolved.get("pyparse_uv")
            modified_path = chem._find_impurity_trace_path(
                chem.modified_pyparse_impurity_result_dir, well, impurities, summary_only=True,
            )
            if standard_path is None:
                standard_path = chem._find_impurity_trace_path(chem.pyparse_result_dir, well, impurities)
            traces.append(TraceAsset(well, "impurity_pyparse", standard_path, f"{safe_well}_impurity_pyparse", True))
            traces.append(TraceAsset(well, "impurity_modified", modified_path, f"{safe_well}_impurity_modified", True))
        return traces

    def _safe_extract_project_zip(self, zf: zipfile.ZipFile, dest: Path):
        """Compatibility entry point for portable archive extraction."""
        safe_extract_project_zip(zf, dest)

    @staticmethod
    def _prepare_imported_gwl_entries(data: Dict[str, object], extract_root: Optional[Path]):
        prepare_imported_gwl_entries(data, extract_root)

    def _load_project_package(self, path: Path) -> Tuple[Dict[str, object], Optional[Path]]:
        return load_project_package(path, OUTPUT_DIR, normalize_well=_normalize_well)

    @staticmethod
    def _validate_project_data(data: object):
        validate_project_data(data)

    def _apply_project_data(self, data: Dict[str, object]):
        self.current_synthesis_step, self.completed_synthesis_steps = synthesis_progress(data)
        compound = data.get("compound_notes", {}) or {}
        compound_records = []
        for item in compound.get("records", []) or []:
            values = {
                h: str(item.get(h, "") or "")
                for h in compound_notes_frame.DATA_HEADERS
            }
            compound_records.append(compound_notes_frame.CompoundRecord(values))
        self.compound_tab.records = compound_records
        self.compound_tab.source_excel = None
        self.compound_tab.excel_loaded = False
        self.compound_tab._set_associated_workbook_name(compound.get("associated_workbook_name", ""))
        self.compound_tab._deleted_source_rows.clear()
        self.compound_tab._deleted_source_records = []
        self.compound_tab.master_stock_excel_var.set(str(compound.get("master_stock_excel", "") or ""))
        self.compound_tab.search_var.set(str(compound.get("search", "") or ""))
        self.compound_tab._refresh_tree()
        if self.compound_tab.records:
            first_iid = str(self.compound_tab.filtered_indices[0]) if self.compound_tab.filtered_indices else "0"
            if self.compound_tab.tree.exists(first_iid):
                self.compound_tab.tree.selection_set(first_iid)
                self.compound_tab.tree.focus(first_iid)
                self.compound_tab.tree.see(first_iid)
                self.compound_tab._load_record_into_form(self.compound_tab.records[int(first_iid)].values, int(first_iid))
            else:
                self.compound_tab._clear_form()
        else:
            self.compound_tab._clear_form()
        self.compound_tab._mark_saved_snapshot()

        self.tecan_tab.import_state(data.get("tecan", {}) or {})
        if hasattr(self, "external_import_tab"):
            self.external_import_tab.import_state(data.get("external_import", {}) or {})
        if hasattr(self, "manual_tab"):
            self.manual_tab.import_state(data.get("manual_workflow", {}) or {})
        if hasattr(self, "opentrons_tab"):
            self.opentrons_tab.import_state(data.get("opentrons", {}) or {})
        self.cheminformatics_tab.import_state(data.get("cheminformatics", {}) or {})
        if hasattr(self, "reaction_summary_tab"):
            self.reaction_summary_tab.import_state(data.get("reaction_summary", {}) or {})
        if hasattr(self, "pyparse_tab"):
            self.pyparse_tab.import_state(data.get("pyparse_runner", {}) or {})
        if hasattr(self, "modified_pyparse_tab"):
            self.modified_pyparse_tab.import_state(data.get("modified_pyparse_runner", {}) or {})
        if hasattr(self, "modified_impurity_tab"):
            impurity_state = data.get("modified_impurity_runner", {}) or {}
            legacy = data.get("modified_pyparse_runner", {}) or {}
            if not impurity_state and legacy.get("platemap") and _pyparse_platemap_kind(Path(legacy["platemap"])) == "impurity":
                impurity_state = legacy
                self.modified_pyparse_tab.import_state({})
            self.modified_impurity_tab.import_state(impurity_state)
        if hasattr(self, "reaction_summary_tab"):
            self.reaction_summary_tab.refresh()
        self._update_next_step_tab_text()

    def _capture_import_rollback_state(self) -> Dict[str, object]:
        self.compound_tab._commit_pending_form_update()
        return {
            "payload": self._project_payload(),
            "compound_records": [
                compound_notes_frame.CompoundRecord(
                    dict(rec.values), source_row=rec.source_row,
                    source_values=dict(rec.source_values) if rec.source_values is not None else None,
                    source_cells=dict(rec.source_cells) if rec.source_cells is not None else None,
                )
                for rec in self.compound_tab.records
            ],
            "source_excel": self.compound_tab.source_excel,
            "excel_loaded": self.compound_tab.excel_loaded,
            "deleted_source_rows": set(self.compound_tab._deleted_source_rows),
            "deleted_source_records": list(self.compound_tab._deleted_source_records),
            "saved_snapshot": list(self.compound_tab._saved_records_snapshot),
        }

    def _restore_import_rollback_state(self, state: Dict[str, object]):
        self._apply_project_data(state["payload"])
        self.compound_tab.records = list(state["compound_records"])
        self.compound_tab.source_excel = state["source_excel"]
        self.compound_tab.excel_loaded = bool(state["excel_loaded"])
        self.compound_tab._deleted_source_rows = set(state["deleted_source_rows"])
        self.compound_tab._deleted_source_records = list(state.get("deleted_source_records", []))
        self.compound_tab._saved_records_snapshot = list(state["saved_snapshot"])
        self.compound_tab._refresh_tree()
        if self.compound_tab.records and self.compound_tab.filtered_indices:
            index = self.compound_tab.filtered_indices[0]
            self.compound_tab.tree.selection_set(str(index))
            self.compound_tab._load_record_into_form(self.compound_tab.records[index].values, index)

    def _export_project(self):
        try:
            self.compound_tab._commit_pending_form_update()
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            out = filedialog.asksaveasfilename(
                title="Export XinPilot project",
                defaultextension=".xinpilot.zip",
                initialdir=str(OUTPUT_DIR),
                filetypes=[
                    ("XinPilot portable project", "*.xinpilot.zip"),
                    ("Zip archive", "*.zip"),
                    ("All files", "*.*"),
                ],
            )
            if not out:
                return False
            out_path = Path(out)
            payload = self._project_payload()
            assets = save_project_package(out_path, payload, package_assets=self._add_portable_project_assets)
            if '_project_changes' in self.__dict__:
                self._mark_project_saved()
            self.project_status_var.set(f"Project exported: {out_path.name}")
            warnings = assets.get("archived_step_warnings", [])
            warning_text = (
                "\n\nSome archived-step files were already unavailable and could not be included:\n"
                + "\n".join(warnings[:8])
                + (f"\n...and {len(warnings) - 8} more (recorded in project.json)." if len(warnings) > 8 else "")
            ) if warnings else ""
            messagebox.showinfo("Project exported", f"Saved portable project package:\n{out_path}{warning_text}")
            return True
        except Exception as exc:
            messagebox.showerror("Export project failed", str(exc))
            return False

    def _import_project(self):
        p = filedialog.askopenfilename(
            title="Import XinPilot project",
            filetypes=[
                ("XinPilot projects", "*.xinpilot.zip *.rxnpilot.zip *.syntrack.zip *.oneclick.zip *.zip *.oneclick.json *.json"),
                ("XinPilot portable project", "*.xinpilot.zip *.rxnpilot.zip *.syntrack.zip *.oneclick.zip"),
                ("XinPilot legacy JSON", "*.oneclick.json"),
                ("Zip archive", "*.zip"),
                ("JSON", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not p:
            return
        extracted_to = None
        rollback_state = None
        try:
            path = Path(p)
            data, extracted_to = self._load_project_package(path)
            if data.get("format") != "oneclick_synthesis_project":
                if not messagebox.askyesno(
                    "Unknown project format",
                    "This does not look like a XinPilot project file. Try importing it anyway?",
                ):
                    if extracted_to is not None and Path(extracted_to).exists():
                        shutil.rmtree(extracted_to, ignore_errors=True)
                    return
            self._validate_project_data(data)
            if not self._confirm_project_replacement():
                if extracted_to is not None and Path(extracted_to).exists():
                    shutil.rmtree(extracted_to, ignore_errors=True)
                return
            rollback_state = self._capture_import_rollback_state()
            self._apply_project_data(data)
            self.compound_tab.status_var.set(f"Imported {len(self.compound_tab.records)} project compound record(s).")
            self.project_status_var.set(f"Project imported: {path.name}")
            extra = f"\n\nBundled files extracted to:\n{extracted_to}" if extracted_to else ""
            messagebox.showinfo("Project imported", f"Loaded project file:\n{path}{extra}")
            self._set_imported_project_title(path)
            if '_project_changes' in self.__dict__:
                self._mark_project_saved()
        except Exception as exc:
            rollback_error = None
            if rollback_state is not None:
                try:
                    self._restore_import_rollback_state(rollback_state)
                except Exception as restore_exc:
                    rollback_error = restore_exc
            if extracted_to is not None and Path(extracted_to).exists():
                shutil.rmtree(extracted_to, ignore_errors=True)
            details = str(exc)
            if rollback_error is not None:
                details += f"\n\nRollback also failed: {rollback_error}"
            else:
                details += "\n\nThe previous project state was restored."
            messagebox.showerror("Import project failed", details)

    def _confirm_project_replacement(self):
        """Protect all saved project records before accepting an import."""
        self.compound_tab._commit_pending_form_update()
        self.compound_tab._commit_pending_quantity_update()
        if '_project_changes' not in self.__dict__:
            return self.compound_tab.confirm_leave_compound_notes()
        if not self._check_project_changes():
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved project changes",
            "Export the current project before importing another?\n\n"
            "Yes: Export the current project, then import.\n"
            "No: Discard changes and import.\n"
            "Cancel: Keep the current project open.",
            parent=self,
        )
        if choice is None:
            return False
        return bool(self._export_project()) if choice else True

    @staticmethod
    def _project_name_from_path(path: Path | str) -> str:
        return project_name_from_path(path)

    def _set_imported_project_title(self, path: Path | str):
        self.current_project_name = self._project_name_from_path(path)
        self.title(f"XinPilot — {self.current_project_name}")

    def _maximize_on_open(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass


def _run_bundled_pyparse(kind: str, args: List[str]) -> int:
    if kind == "modified":
        script_path = MODIFIED_PYPARSE_DIR / "PyParse.py"
    else:
        script_path = PYPARSE_DIR / "PyParse.py"
    if not script_path.exists():
        print(f"Bundled PyParse script was not found: {script_path}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(script_path.parent))
    sys.argv = [str(script_path)] + list(args)
    runpy.run_path(str(script_path), run_name="__main__")
    return 0


def _run_bundled_tool(kind: str, tool_args: Optional[List[str]] = None) -> int:
    relative_paths = {
        "compound-library-builder": "toolkit/compound_library_builder/bulk_gui.py",
        "aromatic-smiles-converter": "toolkit/aromatic_smiles_converter/aromatic_smiles_converter.py",
        "solution-calculator": "toolkit/solution_calculator/solution_calculator.py",
        "clogp-calculator": "toolkit/clogp_calculator/clogp_calculator.py",
        "opentrons-protocol-simulator": "toolkit/opentrons_protocol_simulator/opentrons_protocol_simulator_gui.py",
    }
    relative_path = relative_paths.get(kind)
    if relative_path is None:
        print(f"Unknown bundled XinPilot tool: {kind}", file=sys.stderr)
        return 2
    script_path = resource_path(relative_path)
    if not script_path.exists():
        print(f"Bundled XinPilot tool was not found: {script_path}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(script_path.parent))
    sys.argv = [str(script_path), *(tool_args or [])]
    runpy.run_path(str(script_path), run_name="__main__")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--oneclick-run-pyparse":
        raise SystemExit(_run_bundled_pyparse(sys.argv[2], sys.argv[3:]))
    if len(sys.argv) >= 3 and sys.argv[1] in ("--xinpilot-run-tool", "--rxnpilot-run-tool", "--syntrack-run-tool"):
        raise SystemExit(_run_bundled_tool(sys.argv[2], sys.argv[3:]))
    IntegratedFullApp().mainloop()

