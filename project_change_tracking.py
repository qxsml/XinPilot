"""Read-only adapter for meaningful project state, excluding navigation/caches.

Do not call the Tecan or Cheminformatics export methods here: those apply edits
and hydrate files. No source files are read or written by this observer.
"""
import time
from xinpilot.application.project_changes import ProjectChanges


CHEM_FIELDS = (
    'product_details_generated', 'pushed_plan_fingerprints', 'retained_product_rows',
    'retained_detail_rows', 'impurity_exclusions', 'carried_impurity_sources',
    'pyparse_result_dir', 'modified_pyparse_result_dir', 'modified_pyparse_impurity_result_dir',
    'pyparse_wells', 'custom_products', 'custom_failures', 'reaction_site_selections',
    'reaction_names', 'imported_product_details', 'building_block_ion_rules',
    'lcms_target_smiles_by_well', 'lcms_target_summaries_by_well', 'lcms_handling_mode',
    'pushed_rows', 'pyparse_purity_by_well', 'modified_pyparse_purity_by_well',
    'modified_pyparse_purity_by_product', 'modified_pyparse_conflicts_by_product',
    'product_structure_uv_source_by_key', 'invalidated_product_analysis',
    'product_structure_manual_notes', 'product_peak_overrides',
    'product_structure_row_colors', 'product_structure_biology_hits',
    'building_block_identity_by_well', 'product_review_wells', 'pending_product_identity_rows',
)
CHEM_VARS = ('reaction_var', 'retained_results_var', 'output_var', 'name_start_var',
             'pyparse_output_var', 'impurity_pyparse_output_var',
             'custom_reactant_order_var', 'custom_output_dir_var')


def project_edit_state(app):
    compound, tecan, chem = app.compound_tab, app.tecan_tab, app.cheminformatics_tab
    # Records are updated by the existing form callbacks; do not commit or
    # recalculate while merely observing the application.
    entries = []
    active = getattr(tecan, '_active_gwl_index', None)
    for index, entry in enumerate(tecan.exported_gwl_files):
        blocks = [tecan._block_to_dict(b) for b in tecan.blocks] if index == active else entry.get('blocks', [])
        entries.append({'path': entry.get('path', ''), 'name': entry.get('name', ''),
                        'mode': tecan.mode_var.get() if index == active else entry.get('mode', ''),
                        'blocks': blocks, 'content': '' if blocks else entry.get('content', '')})
    tecan_state = {'files': entries, 'aliases': tecan.labware_aliases, 'save_map': tecan.v_save_map.get()}
    if not entries:
        tecan_state.update(mode=tecan.mode_var.get(), blocks=[tecan._block_to_dict(b) for b in tecan.blocks])
    opentrons = app.opentrons_tab.export_state()
    # Row-edit controls are populated when selecting rows. The saved rows,
    # deck and global instrument settings are the authoritative plan.
    global_keys = {'protocol_name', 'notes', 'robot', 'api_level', 'trash_slot', 'flex_gripper',
                   'labware_configs', 'rows', 'eight_channel_mode'}
    global_keys.update(k for k in opentrons if k.startswith(('left_', 'right_', 'module_')))
    global_keys.update(app.opentrons_tab._module_state())
    chemistry = {name: getattr(chem, name, None) for name in CHEM_FIELDS}
    chemistry.update({name: getattr(chem, name).get() for name in CHEM_VARS})
    chemistry['custom_template'] = chem.custom_template_text.get('1.0', 'end-1c')
    return {
        'compounds': [r.values for r in compound.records],
        'workbook': compound.associated_workbook_name(),
        'master_stock': compound.master_stock_excel_var.get(),
        'tecan': tecan_state,
        'manual': app.manual_tab.rows,
        'external_import': app.external_import_tab.export_state() if 'external_import_tab' in app.__dict__ else {},
        'opentrons': {k: v for k, v in opentrons.items() if k in global_keys},
        'chemistry': chemistry,
        'reaction_conditions': {k: v for k, v in app.reaction_summary_tab.export_state().items()
                               if k != 'show_reaction_schemes'},
        'analysis': [frame.export_state() for frame in (app.pyparse_tab, app.modified_pyparse_tab, app.modified_impurity_tab)],
        'step': app.current_synthesis_step,
        'history': app.completed_synthesis_steps,
    }


class ProjectChangeTrackingMixin:
    def _start_project_tracking(self):
        self._project_changes = ProjectChanges({})
        self._project_dirty = False
        self._change_check_error = ''
        self._mark_project_saved()
        self._tracking_job = self.after(1500, self._poll_project_changes)

    def _mark_project_saved(self):
        if '_project_changes' in self.__dict__:
            try:
                self._project_changes.mark_saved(project_edit_state(self))
                self._project_dirty = False
                self._change_check_error = ''
            except Exception as exc:
                self._project_dirty = True
                self._change_check_error = str(exc)
            self._show_project_change_title()

    def _show_project_change_title(self):
        title = 'XinPilot'
        if self.current_project_name:
            title += ' — ' + self.current_project_name
        if self._change_check_error:
            title += ' — Changes not verified'
        elif self._project_dirty:
            title += ' — Unsaved changes'
        self.title(title)

    def _check_project_changes(self):
        try:
            self._project_dirty = self._project_changes.changed(project_edit_state(self))
            self._change_check_error = ''
        except Exception as exc:
            # Never close silently when comparison could not be completed.
            self._project_dirty = True
            self._change_check_error = str(exc)
        self._show_project_change_title()
        return self._project_dirty

    def _poll_project_changes(self):
        started = time.monotonic()
        try:
            if not self._close_prompt_active:
                self._check_project_changes()
        finally:
            # Large projects get a longer interval rather than continuous work.
            delay = max(1500, min(30000, int((time.monotonic() - started) * 20000)))
            self._tracking_job = self.after(delay, self._poll_project_changes)
