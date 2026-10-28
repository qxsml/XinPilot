# Product peak inspection

In Product Summary, click the Modified PyParse UV trace. The window shows the
integrated peaks, UV chromatogram and available MS+ / MS− spectra for the inspected
peak. Click another peak on the plot or select it in the table. Plot controls
allow zooming and saving a figure; the spectra are those retained by the analysis
parser, not a replacement for the original RPT file.

**Assign as product** replaces the automatic assignment for that LCMS target and
well with the selected existing peak. It uses the instrument's integrated area
and the same UV exclusion policy. Excluded peaks cannot be assigned. Only one
peak is manually assigned at a time; restoring automatic assignment restores any
original split-peak assignment too. The main UV and ES views follow the manual
selection, and the purity is marked **Manually assigned**. Product Results CSV
identifies a manual assignment in its purity-source column when Modified PyParse
is the selected purity source.

**Restore automatic assignment** restores the original result. Numerical data,
the override and its timestamp travel with an exported XinPilot project. The
automatic CSVs, images and RPT are not overwritten. Export the project explicitly
to save your changes. Running a new product analysis clears the previous analysis's
overrides; running impurity analysis does not clear product overrides.

New product analyses write `xinpilot_peaks.json`. Older image-only analyses need
to be rerun once for inspection and reassignment; their existing display still
works. No new third-party dependency is required.

Before-change backup: `backups/Peak_assignment_before_changes_20260912.zip`.
GUI/portable-project validation: `ui_review/validate_peak_inspection.py`.

## Adjustable trace layout (TypeScript desktop)

The inspector prioritizes plots: UV and mass spectra occupy the upper area,
with a compact peak table underneath. Drag the divider between UV and mass
plots to change their relative heights, or the divider above the table to change
its share of the window. Each plot panel retains its own zoom/pan toolbar.
Use **Hide peak table** / **Show peak table** in the fixed action row to reclaim
plot space. Peak assignment, restore and close controls remain visible.

Window size, plot proportions and table visibility are remembered locally in
`outputs/peak_inspection_layout.json`. These preferences are not included in
project exports and do not affect peak integration or product assignment.
On smaller windows, plot panels retain readable minimum heights with scrolling.
Native WebView2 validation: both plots visible, resize controls, hidden table
restored on reopening, assignment 70% ? 30% ? automatic 70%, and visible footer.
