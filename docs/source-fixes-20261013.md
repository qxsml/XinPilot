# Source corrections included in v1.2.0 - 13 October 2026

These corrections follow v1.1.2. They are present in the Python controllers used
by the TypeScript interface. They are included in this edition's v1.2.0 executable; the earlier v1.1.2 executable did not include them.
Both PyParse engines and the TypeScript renderer are unchanged.

## Behavior changes

- Selecting the active GWL again keeps applied edits and its unsaved state.
  Switching to another GWL retains the existing save/discard/cancel prompt.
- A changed reaction or cleared custom template retains the preceding product
  identity until regeneration can compare the structures. Mismatched pending
  results are hidden. Actual product changes invalidate old assignments and
  purity; unchanged products keep their reviewed targets and results. Pending
  comparisons survive project export/import. Sample numerical traces and
  comments are retained.
- Full Compound Notes Excel saves locate loaded compounds by their original
  Chemical ID and structure rather than their former row position. Local ID
  and structure edits remain possible. Saves preserve unrelated columns,
  formulas and externally added rows, merge nonconflicting field changes, and
  reject ambiguous identities or conflicting edits before writing. Failed
  saves leave the workbook and saved record baselines unchanged and display an
  explanation. The editor refreshes safely merged values after a successful save.
- GWL import rejects an aspiration block that dispenses to multiple destination
  labware instead of silently assigning every transfer to the last one.
  Separate aspiration blocks retain their existing destination support.
- Repeated GWL dispenses and their ordering survive import, editing, project
  round trips and export. Repeated volumes count toward totals and aspiration
  validation. The existing transfer-block format is reused.
- Product Details CSV remapping installs all new associations before looking up
  destination results. Product-and-sample automatic evidence survives mapping
  permutations. Old manual assignments are not transferred to a different
  sample; comments remain attached to their sample. Well-only standard PyParse
  values require reanalysis for a changed mapping.
- Opentrons 8-channel behavior participates in project change tracking. Changing
  it prompts before closing and is preserved through project export/import.

## Validation scope

- **515 root regression tests passed**, including the seven corrected behaviors,
  workbook conflict/rollback handling and merged-value editor refresh.
- Source desktop bridge checks passed. The native GWL-dialog, scientific-viewer
  and External Import checks passed, including manual peak assignment/restoration
  and preservation of the original imported file. A test now waits for actual
  projected rows and peak controls instead of relying on fixed rendering delays.
- All five native close/save cases passed (unchanged, discard, cancel, cancelled
  export and successful export), with empty controller logs and normal exits.
- The optional private-RPT check was skipped because its dataset-specific fixture
  was not supplied. Synthetic numerical-trace checks passed.

Tests use synthetic compounds, workbooks, transfers and portable projects in
isolated copies. No experimental input files, instrument execution or release
rebuild are part of this correction. The root Tk fixtures emit teardown warnings;
the GWL-dialog test also logged a WebView2 evaluation after its window closed,
while its dialog assertions passed. These checks are not a clean-computer or
physical-instrument validation.

The changes retain the existing controller/application-service architecture and
do not introduce another chemistry engine or require a renderer rebuild.
