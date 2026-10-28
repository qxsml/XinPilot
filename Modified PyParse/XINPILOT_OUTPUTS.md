# Modified PyParse outputs for XinPilot

Updated 12 September 2026 in the GPT6 development copy only.

The normal XinPilot command now writes only the images consumed by its display:

- Product analysis: `graphs/chroma-<product>-<well>.jpg` and the corresponding
  `<well>-uv254.jpg` for each submitted product/well.
- Impurity analysis (a platemap containing byproduct targets): combined
  `graphs/chroma-ImpuritySummary__<well>-<well>.jpg` and `<well>-uv254.jpg` images.

Image names and composite image geometry are retained because XinPilot resolves
images by product/well and crops the composite image for its ES panels. This
preserves compatibility with existing XinPilot trace displays.

`aTable.csv`, `compoundtable.csv`, `outputTable.csv`, and `logfile.txt` remain.
Product analysis also writes `xinpilot_peaks.json` for interactive peak inspection
and reversible manual product assignment; see `../PEAK_INSPECTION.md`. This stores
per-well numerical traces, integrated peaks and retained spectra, automatic target
assignments, exclusions, and UV image-axis coordinates. XinPilot embeds these data
in project exports so inspection does not depend on the original output folder.
The GUI also writes its existing run marker. Identification, purity, exclusion,
split-peak, target-ion and frequent-impurity table calculations are retained.
Frequent-impurity discovery still adds its original table rows; only its unused
illustrations are omitted. The product/impurity classification follows the same
byproduct-target distinction used by XinPilot's analysis pages.

The normal workflow no longer renders best-well duplicates, individual reactant
or byproduct plots, hit-validation charts, pie charts, histograms, donut charts,
structure images, location maps, standalone HTML, or a duplicate output ZIP.
Existing CLI arguments remain accepted, including the GUI's `-z True`; they do
not re-enable the standalone report/ZIP. CSV/analytical-table and UV254 options
retain their existing behavior; XinPilot supplies them explicitly.

Always use a fresh output folder. This change does not delete old reports,
rewrite imported projects, or change results already stored in projects.

Backup: `../backups/Modified_PyParse_before_output_simplification_20260912_002929_385047.zip`.
It contains the original folder and per-file SHA256 hashes.

Validation scripts and evidence are under `../ui_review/`. Synthetic CLI checks
cover product/impurity outputs, identical baseline CSV values and complete retained
image pixels, one-well and zero-product runs, split peaks and UV exclusions.
The output-simplification change affected `main` and the plot switch in
`findImpurities`. The later peak-inspection change also returns UV-axis geometry
from `plotChroma`; automatic calculations and rendered image pixels are retained.

Final checks: all 297 existing GPT6 regression tests passed. The real 24-sample
Waters fixture with 12 product rows produced exactly 24 display images; all three
CSV tables and the pixels displayed by XinPilot matched the earlier full-report
output. Analysis time was about 50 seconds versus about 254 seconds in that earlier
run (not a controlled performance benchmark). Evidence:
`../ui_review/display-output-real-20260912-092519/validation.json` and
`../ui_review/display-output-check-20260912-092342/validation.json`.
