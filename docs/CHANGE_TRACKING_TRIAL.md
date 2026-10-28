# Project change tracking

This source snapshot and its matching executable include project change
tracking. The historical document filename is retained for existing links.

The title gains **Unsaved changes** when meaningful project state differs from
the baseline. Startup and successful project import/export establish a baseline.
Reverting an edit to that baseline clears the indication. Cancelled or failed
exports do not reset it. Closing an unchanged project skips the export prompt;
changed projects retain the existing Yes (export), No (discard), Cancel choices.
No automatic save, overwrite, new archive format or Save-to-original is added.

## Implementation

`xinpilot/application/project_changes.py` compares canonical content hashes,
including tuple-keyed controller records. It imports no UI or chemistry engine.
`project_change_tracking.py` is the read-only controller adapter and title/lifetime
integration. It does not call the mutating Tecan/Cheminformatics export methods.
`integrated_full_software.py` establishes baselines and checks changes on close.

The observer compares records, plans, reaction conditions, product/analysis
assignments and annotations, analysis configuration, and synthesis history.
Navigation, searches, row selections, plot layout, visible editor forms loaded
by row selection, and lazily loaded trace/render caches are excluded. Existing
Apply/Add operations are still required for transient editor/dialog drafts;
this trial does not add draft persistence. External files changed by another
program are not monitored. This is change detection, not an audit trail or
multi-user synchronization.

Checks run about every 1.5 seconds, with a longer interval for expensive states.
Closing always checks again after pending compound-form callbacks are flushed.
If a comparison fails, the title says **Changes not verified** and closing still
prompts. A failed baseline check cannot turn a successful file export into a
reported export failure.

## Suggested user checks

1. Import a project, view tabs and traces, and close: no export prompt.
2. Edit a compound or reaction condition: title indicates unsaved changes.
3. Restore the original value: the indicator clears.
4. Add/delete an addition or manually assign a product peak: indicator appears.
5. Cancel export: indicator remains. Successfully export: indicator clears.
6. Close after editing: Yes/No/Cancel retain their existing meanings.

Automated coverage includes synthetic import/export round trips, cancelled
exports, edits/reversions, compound-independent plan/analysis changes, tuple
keys and conservative comparison failures. Native WebView2 tests cover trace
viewing, manual assignment and all five unchanged/edited close cases. A private
Suzuki acceptance copy also stayed clean while switching synthesis editors;
comparison averaged approximately 8 ms on the development laptop.
