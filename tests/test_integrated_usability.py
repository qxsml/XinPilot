import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrated_full_software import IntegratedFullApp  # noqa: E402
from xinpilot_theme import COLORS


class IntegratedUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = IntegratedFullApp()
            cls.app.update()
            cls.app.state("normal")
            cls.app.geometry("1200x760+0+0")
            cls.app.update()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        app = getattr(cls, "app", None)
        if app is not None:
            for after_id in app.tk.call("after", "info"):
                try:
                    # Cancel the Tcl timer without deleting its registered Python
                    # command; widget destruction performs that cleanup safely.
                    app.tk.call("after", "cancel", after_id)
                except tk.TclError:
                    pass
            app.destroy()

    def test_main_navigation_stays_stable_when_an_editor_opens(self):
        expected = [
            "Compound Notes",
            "Synthesis Plan",
            "Cheminformatics",
            "LCMS Analysis",
            "Reaction Summary",
            "Product Summary",
            "Next Step",
        ]
        self.app.nb.select(self.app.synthesis_tab)
        self.app._show_synthesis_editor("Manual")
        self.app.update()

        self.assertEqual(expected, [self.app.nb.tab(tab, "text") for tab in self.app.nb.tabs()])
        self.assertTrue(self.app.synthesis_editor_bar.winfo_ismapped())
        self.assertEqual({}, self.app.synthesis_inline_tabs)

        reachable = set()
        for x_position in range(self.app.nb.winfo_width()):
            try:
                reachable.add(self.app.nb.index(f"@{x_position},20"))
            except tk.TclError:
                pass
        self.assertEqual(set(range(len(expected))), reachable)

    def test_toolkit_and_project_actions_share_navigation_line_without_covering_next_step(self):
        self.assertIs(self.app.nb, self.app.project_bar.master)
        labels = {
            child.cget("text")
            for child in self.app.project_bar.winfo_children()
            if isinstance(child, ttk.Button)
        }
        self.assertEqual({"Export Project", "Import Project"}, labels)
        self.assertEqual("Toolkit", self.app.toolkit_button.cget("text"))
        self.assertEqual("Toolkit.TMenubutton", self.app.toolkit_button.cget("style"))
        self.assertEqual(
            [
                "Compound Library Builder\N{HORIZONTAL ELLIPSIS}",
                "Aromatic SMILES Converter\N{HORIZONTAL ELLIPSIS}",
                "Opentrons Protocol Simulator\N{HORIZONTAL ELLIPSIS}",
            ],
            [self.app.toolkit_menu.entrycget(index, "label") for index in range(3)],
        )
        self.assertTrue(self.app.project_bar.winfo_ismapped())
        self.assertLessEqual(abs(self.app.project_bar.winfo_rooty() - self.app.nb.winfo_rooty()), 4)

        next_step_x = []
        for x_position in range(self.app.nb.winfo_width()):
            try:
                if self.app.nb.index(f"@{x_position},20") == self.app.nb.index(self.app.next_step_tab):
                    next_step_x.append(x_position)
            except tk.TclError:
                pass
        project_left = self.app.project_bar.winfo_rootx() - self.app.nb.winfo_rootx()
        self.assertTrue(next_step_x)
        self.assertLess(max(next_step_x), project_left)

    def test_toolkit_menu_items_use_isolated_launchers(self):
        targets = (
            (0, "integrated_full_software.launch_compound_library_builder"),
            (1, "integrated_full_software.launch_aromatic_smiles_converter"),
            (2, "integrated_full_software.launch_opentrons_simulator"),
        )
        for menu_index, target in targets:
            with self.subTest(target=target), patch(target, return_value=True) as launch:
                self.app.toolkit_menu.invoke(menu_index)
                launch.assert_called_once_with(parent=self.app)

    def test_imported_project_name_can_be_shown_in_window_title(self):
        self.assertEqual(
            "Project Alpha",
            self.app._project_name_from_path(Path("Project Alpha.xinpilot.zip")),
        )
        old_title = self.app.title()
        old_project_name = self.app.current_project_name
        try:
            self.app._set_imported_project_title(Path("Project Alpha.xinpilot.zip"))
            self.assertEqual("Project Alpha", self.app.current_project_name)
            self.assertEqual("XinPilot — Project Alpha", self.app.title())
        finally:
            self.app.current_project_name = old_project_name
            self.app.title(old_title)

    def test_compound_workbook_project_metadata_is_portable_and_backward_compatible(self):
        compound = self.app.compound_tab
        old_source = compound.source_excel
        old_loaded = compound.excel_loaded
        old_name = compound.associated_workbook_name()
        try:
            compound.source_excel = Path(r"C:\sender\private\Project_A_Compounds.xlsx")
            compound.excel_loaded = True
            compound._set_associated_workbook_name(compound.source_excel)

            payload = self.app._project_payload()
            exported_name = payload["compound_notes"]["associated_workbook_name"]
            self.assertEqual("Project_A_Compounds.xlsx", exported_name)
            self.assertNotIn("\\", exported_name)
            self.assertNotIn("/", exported_name)

            self.app._apply_project_data(payload)
            self.assertIsNone(compound.source_excel)
            self.assertFalse(compound.excel_loaded)
            self.assertEqual("Project_A_Compounds.xlsx", compound.associated_workbook_name())
            self.assertEqual("Project_A_Compounds.xlsx", compound.associated_workbook_name_var.get())
            self.assertEqual(
                "Records Table: Project_A_Compounds.xlsx",
                compound.records_table_frame.cget("text"),
            )

            legacy_payload = dict(payload)
            legacy_payload["compound_notes"] = dict(payload["compound_notes"])
            legacy_payload["compound_notes"].pop("associated_workbook_name")
            self.app._apply_project_data(legacy_payload)
            self.assertEqual("", compound.associated_workbook_name())
            self.assertEqual("Not specified", compound.associated_workbook_name_var.get())
            self.assertEqual("Records Table: Not specified", compound.records_table_frame.cget("text"))
        finally:
            compound.source_excel = old_source
            compound.excel_loaded = old_loaded
            compound._set_associated_workbook_name(old_name)

    def test_synthesis_selector_is_one_line_and_has_no_redundant_combined_mode(self):
        choice_labels = set()

        def collect_buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    choice_labels.add(str(child.cget("text")))
                collect_buttons(child)

        collect_buttons(self.app.synthesis_choice_frame)
        self.assertTrue({"Tecan", "Opentrons", "Manual"}.issubset(choice_labels))
        self.assertNotIn("Combined Synthesis", choice_labels)

        self.app.nb.select(self.app.synthesis_tab)
        self.app._show_synthesis_editor("Tecan")
        self.app.update()
        self.assertEqual(
            self.app.change_synthesis_editor_button.grid_info()["row"],
            self.app.combined_synthesis_tab_bar.grid_info()["row"],
        )
        change_midpoint = self.app.change_synthesis_editor_button.winfo_rooty() + self.app.change_synthesis_editor_button.winfo_height() // 2
        selectors_midpoint = self.app.combined_synthesis_tab_bar.winfo_rooty() + self.app.combined_synthesis_tab_bar.winfo_height() // 2
        self.assertLessEqual(abs(change_midpoint - selectors_midpoint), 4)

    def test_opentrons_two_column_workspace_fits_small_window(self):
        self.app.nb.select(self.app.synthesis_tab)
        self.app._show_synthesis_editor("Opentrons")
        self.app.update()
        opentrons = self.app.opentrons_tab
        pane_widths = [
            opentrons.nametowidget(name).winfo_width()
            for name in opentrons.lower_plan_panes.panes()
        ]

        self.assertTrue(opentrons._lower_sash_initialized)
        self.assertEqual(2, len(pane_widths))
        self.assertTrue(all(width >= 400 for width in pane_widths))
        self.assertLess(
            int(opentrons.transfer_fields_panel.grid_info()["row"]),
            int(opentrons.liquid_handling_panel.grid_info()["row"]),
        )
        self.assertEqual(0, int(opentrons.row_action_toolbar.grid_info()["row"]))
        self.assertEqual(1, int(opentrons.transfer_fields_panel.grid_info()["row"]))
        self.assertTrue(opentrons.transfer_row_scrollbar.winfo_ismapped())
        self.assertTrue(opentrons.plan_x_scrollbar.winfo_ismapped())
        self.assertGreaterEqual(opentrons.tree.winfo_height(), 250)
        app_right = self.app.winfo_rootx() + self.app.winfo_width()
        self.assertLessEqual(
            opentrons.protocol_plan_panel.winfo_rootx() + opentrons.protocol_plan_panel.winfo_width(),
            app_right,
        )
        transfer_panel_right = opentrons.transfer_row_panel.winfo_rootx() + opentrons.transfer_row_panel.winfo_width()
        for button in (
            opentrons.create_single_button,
            opentrons.create_batch_button,
            opentrons.create_sequence_button,
        ):
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), transfer_panel_right)
        plan_panel_right = opentrons.protocol_plan_panel.winfo_rootx() + opentrons.protocol_plan_panel.winfo_width()
        for button in (
            opentrons.push_cheminformatics_button,
            opentrons.add_to_sequence_button,
            opentrons.ungroup_sequence_button,
            opentrons.remove_row_button,
        ):
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), plan_panel_right)
        self.assertEqual("Delete", opentrons.remove_row_button.cget("text"))

    def test_cheminformatics_tabs_and_custom_controls_fit_small_window(self):
        self.app.nb.select(self.app.cheminformatics_tab)
        self.app.cheminformatics_tab.inner_nb.select(1)
        self.app.update()
        inner = self.app.cheminformatics_tab.inner_nb
        expected = [
            "Product Details",
            "Custom Template",
            "Update Stock",
            "LCMS Input",
            "Impurity Input & Analysis",
        ]
        self.assertEqual(expected, [inner.tab(tab, "text") for tab in inner.tabs()])

        reachable = set()
        for x_position in range(inner.winfo_width()):
            try:
                reachable.add(inner.index(f"@{x_position},20"))
            except tk.TclError:
                pass
        self.assertEqual(set(range(len(expected))), reachable)
        self.assertGreaterEqual(self.app.cheminformatics_tab.custom_preview.winfo_height(), 80)
        clear_reaction_button = self.app.cheminformatics_tab.clear_custom_input_reaction_button
        self.assertEqual("Clear Input Reaction", clear_reaction_button.cget("text"))
        self.assertTrue(clear_reaction_button.winfo_ismapped())
        export_button = self.app.cheminformatics_tab.product_results_export_button
        self.assertEqual("Export CSV", export_button.cget("text"))
        self.assertTrue(str(export_button).startswith(str(self.app.product_summary_tab)))

    def test_lcms_preparation_dialog_keeps_generation_footer_visible(self):
        chem = self.app.cheminformatics_tab
        measurement = {}

        def inspect_dialog(_frame, window):
            window.update_idletasks()

            def descendants(widget):
                found = []
                for child in widget.winfo_children():
                    found.append(child)
                    found.extend(descendants(child))
                return found

            button = next(
                child for child in descendants(window)
                if isinstance(child, ttk.Button)
                and child.cget("text") == "Continue and Generate Input"
            )
            measurement["dialog_height"] = window.winfo_height()
            measurement["parent_height"] = self.app.winfo_height()
            measurement["button_mapped"] = bool(button.winfo_ismapped())
            measurement["button_bottom"] = button.winfo_rooty() + button.winfo_height()
            measurement["window_bottom"] = window.winfo_rooty() + window.winfo_height()
            window.destroy()

        self.app.geometry("900x600+0+0")
        self.app.update()
        try:
            with patch.object(type(chem), "wait_window", new=inspect_dialog):
                result = chem._ask_lcms_handling([{
                    "reaction_name": "RXN-1",
                    "reaction_well": "A1",
                    "desired product smiles": "CC[NH3+]",
                }])
        finally:
            self.app.geometry("1200x760+0+0")
            self.app.update()

        self.assertIsNone(result)
        self.assertLessEqual(measurement["dialog_height"], measurement["parent_height"] - 40)
        self.assertTrue(measurement["button_mapped"])
        self.assertLessEqual(measurement["button_bottom"], measurement["window_bottom"])

    def test_contextual_background_styles_do_not_create_gray_text_blocks(self):
        style = ttk.Style(self.app)
        next_labels = [child for child in self.app.next_step_tab.winfo_children() if isinstance(child, ttk.Label)]
        self.assertTrue(next_labels)
        self.assertTrue(all(child.cget("style") == "Chem.TLabel" for child in next_labels))
        self.assertEqual(COLORS["bg"], style.lookup("Chem.TLabel", "background").lower())

        hints = []
        radios = []

        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label) and "Right-click a product row" in str(child.cget("text")):
                    hints.append(child)
                if isinstance(child, ttk.Radiobutton):
                    radios.append(child)
                collect(child)

        collect(self.app.product_summary_tab)
        self.assertEqual(1, len(hints))
        self.assertEqual("RowRegion.Muted.TLabel", hints[0].cget("style"))
        self.assertTrue(radios)
        self.assertTrue(all(str(radio.cget("style")).endswith(".TRadiobutton") for radio in radios))

    def test_all_notebook_tabs_use_native_rendering(self):
        style = ttk.Style(self.app)
        self.assertEqual(style.layout("TNotebook.Tab"), style.layout("Main.TNotebook.Tab"))
        self.assertEqual(7, len(self.app.nb.tabs()))
        for name in ("Chem.TNotebook.Tab", "CompactChem.TNotebook.Tab", "TNotebook.Tab"):
            layout = repr(style.layout(name))
            self.assertIn("Notebook.tab", layout)
            self.assertNotIn("XinPilotRounded", layout)
        for name in ("Main.TNotebook.Tab", "Chem.TNotebook.Tab", "CompactChem.TNotebook.Tab", "TNotebook.Tab"):
            self.assertNotEqual(style.lookup(name, "background"), style.lookup(name, "background", ("selected",)))
            self.assertNotEqual(style.lookup(name, "foreground", ("selected",)), style.lookup(name, "background", ("selected",)))

    def test_buttons_keep_native_styles_and_clear_action_hierarchy(self):
        style = ttk.Style(self.app)
        for attr in ("_xinpilot_rounded_button_geometry", "_xinpilot_rounded_button_images",
                     "_xinpilot_rounded_button_surface_styles", "_xinpilot_rounded_button_map_installed"):
            self.assertFalse(hasattr(self.app, attr))
        for name in ("TButton", "CompoundToolbar.TButton", "FileAction.TButton", "ChemAction.TButton",
                     "RowAction.TButton", "Danger.TButton", "Accent.TButton", "DrawReaction.TButton",
                     "Blue.TButton", "Violet.TButton", "SynthesisSelector.TButton", "SynthesisSelectorSelected.TButton"):
            layout = repr(style.layout(name))
            self.assertIn("Button.border", layout)
            self.assertNotIn("XinPilotRounded", layout)
            self.assertNotIn("XinPilotSurface", layout)
        self.assertNotEqual(style.lookup("ChemAction.TButton", "background"), style.lookup("FileAction.TButton", "background"))
        self.assertNotEqual(style.lookup("Danger.TButton", "foreground"), style.lookup("FileAction.TButton", "foreground"))
        self.assertEqual("Toolkit.TMenubutton", self.app.toolkit_button.cget("style"))
        export_button = self.app.cheminformatics_tab.product_results_export_button
        self.assertEqual("FileAction.TButton", export_button.cget("style"))
        self.assertGreaterEqual(export_button.winfo_reqheight(), 28)
        self.assertLessEqual(export_button.winfo_reqheight(), 36)
        selectors = list(self.app.combined_synthesis_tab_buttons.values())
        heights = [button.winfo_reqheight() for button in selectors]
        self.app.nb.select(self.app.synthesis_tab)
        self.app._show_synthesis_editor("Tecan")
        self.app.update()
        self.assertEqual(heights, [button.winfo_reqheight() for button in selectors])

    def test_next_step_tab_waits_for_explicit_start(self):
        calls = []
        original = self.app._start_next_synthesis_step
        self.app._start_next_synthesis_step = lambda: calls.append("started")
        try:
            self.app.nb.select(self.app.next_step_tab)
            self.app.update()
        finally:
            self.app._start_next_synthesis_step = original

        self.assertEqual([], calls)
        self.assertEqual(str(self.app.next_step_tab), self.app.nb.select())
        self.assertFalse(self.app._next_step_dialog_active)

    def test_next_step_keeps_start_action_separate_from_solution_calculator_send(self):
        self.app.nb.select(self.app.next_step_tab)
        self.app.update()
        button_texts = []

        def collect_buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    button_texts.append(str(child.cget("text")))
                collect_buttons(child)

        collect_buttons(self.app.next_step_tab)
        self.assertIn("Start next synthesis step", button_texts)
        self.assertIn("Send products to Solution Calculator", button_texts)
        self.assertIn("does not archive the step", self.app.solution_calculator_description_var.get())
        self.assertIn("Compound Notes", self.app.next_step_description_var.get())

        menu_labels = [
            self.app.toolkit_menu.entrycget(index, "label")
            for index in range(self.app.toolkit_menu.index("end") + 1)
        ]
        self.assertIn("Solution & Stock Calculator…", menu_labels)

    def test_manual_96_well_map_keeps_last_row_reachable(self):
        self.app.nb.select(self.app.synthesis_tab)
        self.app._show_synthesis_editor("Manual")
        self.app.manual_tab._set_initial_manual_split()
        self.app.update()

        cell = self.app.manual_tab.map_cells["H12"]
        map_bottom = self.app.manual_tab.map_box.winfo_rooty() + self.app.manual_tab.map_box.winfo_height()
        self.assertTrue(cell.winfo_ismapped())
        self.assertLessEqual(cell.winfo_rooty() + cell.winfo_height(), map_bottom)
        self.assertTrue(self.app.manual_tab.tree.winfo_ismapped())
        self.assertGreaterEqual(self.app.manual_tab.tree.winfo_height(), 80)

    def test_product_summary_table_remains_inside_the_window(self):
        self.app.nb.select(self.app.product_summary_tab)
        self.app.cheminformatics_tab._set_initial_product_summary_split()
        self.app.update()

        tables = self.app.cheminformatics_tab.product_summary_tables
        root_right = self.app.winfo_rootx() + self.app.winfo_width()
        self.assertTrue(tables.winfo_ismapped())
        self.assertLessEqual(tables.winfo_rootx() + tables.winfo_width(), root_right)
        self.assertGreaterEqual(tables.winfo_width(), 280)

    def test_reaction_name_editor_is_wired_to_product_row_selection(self):
        frame = self.app.cheminformatics_tab
        labels = []

        def collect_labels(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label):
                    labels.append(str(child.cget("text")))
                collect_labels(child)

        collect_labels(frame)
        self.assertNotIn("Reaction name start", labels)
        self.assertGreaterEqual(labels.count("Reaction name"), 2)
        self.assertTrue(frame.preview.bind("<<TreeviewSelect>>"))
        self.assertTrue(frame.product_reaction_name_entry.bind("<KeyRelease>"))
        self.assertTrue(frame.custom_reaction_name_entry.bind("<KeyRelease>"))

    def test_impurity_preview_uses_full_structure_width_and_restores_lcms_comparison(self):
        self.app.nb.select(self.app.product_summary_tab)
        frame = self.app.cheminformatics_tab
        try:
            frame._set_product_structure_comparison_layout(impurity_mode=True)
            self.app.update()

            self.assertEqual(2, int(frame.product_structure_heading.grid_info()["columnspan"]))
            self.assertEqual(2, int(frame.product_structure_label.grid_info()["columnspan"]))
            self.assertFalse(frame.product_structure_lcms_heading.winfo_ismapped())
            self.assertFalse(frame.product_structure_lcms_label.winfo_ismapped())
        finally:
            frame._set_product_structure_comparison_layout(impurity_mode=False)
            self.app.update()

        self.assertEqual(1, int(frame.product_structure_heading.grid_info()["columnspan"]))
        self.assertEqual(1, int(frame.product_structure_label.grid_info()["columnspan"]))
        self.assertTrue(frame.product_structure_lcms_heading.winfo_ismapped())
        self.assertTrue(frame.product_structure_lcms_label.winfo_ismapped())

    def test_product_purity_source_uses_exclusive_radio_controls(self):
        radio_values = set()
        checkbutton_variables = []

        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Radiobutton):
                    radio_values.add(str(child.cget("value")))
                elif isinstance(child, ttk.Checkbutton):
                    checkbutton_variables.append(str(child.cget("variable")))
                collect(child)

        collect(self.app.product_summary_tab)
        self.assertTrue({"pyparse", "modified", "manual"}.issubset(radio_values))
        self.assertNotIn(str(self.app.cheminformatics_tab.product_structure_uv_source_var), checkbutton_variables)

    def test_cheminformatics_heading_accepts_every_synthesis_editor(self):
        headings = []

        def collect(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.LabelFrame):
                    headings.append(str(child.cget("text")))
                collect(child)

        collect(self.app.cheminformatics_tab)
        self.assertIn("Cheminformatics from current pushed synthesis plan", headings)
        self.assertNotIn("Cheminformatics from current Tecan table", headings)

    def test_tecan_controls_describe_their_scope(self):
        tecan = self.app.tecan_tab
        self.assertEqual("Save As New GWL...", tecan.save_gwl_as_button.cget("text"))
        self.assertEqual("Save Current GWL", tecan.save_gwl_edits_button.cget("text"))
        self.assertEqual("Push Listed GWLs to Cheminformatics", tecan.push_all_cheminformatics_button.cget("text"))
        self.assertEqual("Validate / Apply Block Now", tecan.apply_block_button.cget("text"))

    def test_reaction_summary_has_an_explicit_refresh_action(self):
        summary = self.app.reaction_summary_tab
        summary.status_var.set("not refreshed")
        summary.refresh_button.invoke()
        self.app.update()
        self.assertNotEqual("not refreshed", summary.status_var.get())


if __name__ == "__main__":
    unittest.main()
