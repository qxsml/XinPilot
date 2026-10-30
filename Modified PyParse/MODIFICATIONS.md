# XinPilot modifications to PyParse

This directory derives from the Apache-2.0 PyParse baseline identified in
`../PyParse/PROVENANCE.md`. Changed files are `PyParse.py`, `getWatersData.py`,
`getShimadzuData.py`, and `templates/html_template.html`; each carries a visible modification notice.

XinPilot modifications made in 2026 include:

- CSV and frozen-application integration.
- Waters UV, ES+, and ES- trace handling and defensive parsing.
- Desired-product and impurity trace visualisation and extended HTML reports.
- UV254 product-purity fields and per-well purity maps.
- Product-aware purity keyed by canonical desired-product/LC-MS-target structure
  plus well, preventing unrelated compounds in the same well from being reported
  as product purity.
- Product/reactant mass-conflict metadata for downstream review.
- Product/impurity evidence labels and separate display-only observed m/z labels
  for strong local ES trace maxima. Display-only labels do not contribute to hit
  selection, impurity matching, UV254 purity, or exported numerical results.

XinPilot's Product Details/LC-MS target preparation and result association are
implemented outside these files. The upstream `../PyParse/` runtime remains a
separate protected baseline.


## 9 September 2026 update

- Sum multiple accepted product peaks in the analytical table and compound summary;
  retain a representative RT/ion record and correct XinPilot detection gating.
- Share accepted-hit, exclusion-aware purity with the main output calculation.
- Select the explicitly identified Waters 254 nm DAD channel; populate absolute
  area totals independently of optional RT filtering in both vendor parsers.
- Use a 20% base-peak target-label threshold while retaining accepted-peak shading;
  remove product shading/labels for rejected evidence-only fallback candidates.
- Align impurity annotation tolerance and charge handling, and include the fragment
  masses used in identification among annotation targets.
- Remove the plate-analysis heatmap generation and HTML carousel, retaining location maps.

The expected retention-time matching, clustering and hit-selection functions were
not changed. The separate original PyParse runtime was not edited in this update.

## Interactive inspection

The current integration writes numerical UV/MS peak bundles, distinguishes UV integration from MS-only records, and retains starting-material mass-conflict metadata. Reversible manual overrides are managed in XinPilot without overwriting automatic analysis outputs. See XINPILOT_OUTPUTS.md and ../docs/peak-inspection.md.

## 30 October 2026 attribution update

Explicit Xin Qiu/XinPilot modification notices were added to all four files listed above. Existing upstream headers were retained. These notice additions do not change Python statements or analytical behavior. The separate bundled PyParse integration is documented in `../PyParse/MODIFICATIONS.md`.
