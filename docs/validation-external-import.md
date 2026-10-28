# External-import source and executable validation

The results below describe earlier releases. This edition includes the
[13 October corrections](source-fixes-20261013.md) in v1.2.0; see the current
[unified-plate validation](validation-unified-plate.md).

## Version 1.1.2 - 12 October 2026

The matching source and executable address nine reproduced defects in product
and sample identity, unsaved project replacement, workbook updates, robot volume
and source-well handling, and terminal-alkyne impurity generation. See
[release notes](release-1.1.2.md) for the behavior changes.

- **473 root regression tests passed**, including the new identity, project,
  Excel, tip-capacity, rounding, source-occupancy and impurity cases.
- Desktop bridge checks and all five native close/save cases passed. Fresh,
  imported and cleared projects remain clean during read-only viewing.
  One optional dataset-specific UV check was skipped because its private RPT
  fixture was not supplied; the synthetic trace checks passed.
- Eight newly generated protocols passed the installed Opentrons 8.8.0 offline
  simulator, covering 50/200 uL tips, batches, air gaps, mixing, extra aspiration,
  full-column source wells and shared/separate reservoir geometries.
- The one changed robot byte contract was reviewed: only the two physical-source
  metadata maps expand from A1 to A1-H1; the emitted robot commands are unchanged.
- The standalone EXE passed both PyParse startup checks, the scientific-viewer
  diagnostic, and the rendered External Import workflow using its frozen
  controller. These run from isolated folders with Python paths removed.
- All 51 checked bundled application modules and four selected
  resources match the published source. Windows file/product versions are 1.1.2.
- Original and Modified PyParse engines and the TypeScript renderer are
  unchanged. Source inventory and release SHA-256 checks passed.

Testing used synthetic data and isolated copies. No hardware execution, private
experimental-file modification, GitHub upload or clean second-PC test occurred.
Existing Tk fixture teardown warnings remain; the native close/save tests passed.
Performance checks on synthetic 14-, 96- and 192-well projects also verified that
structure checks reuse compound lookups within each check, without a stale cache.

## Version 1.1.1 — 11 October 2026

The source now preserves saved Chemical ID overrides during revalidation,
rejects ambiguous flattened JSON fields, and validates destination geometry at
the shared push boundary before modifying records. Changed building-block IDs
invalidate affected automatic custom-template products and their analytical
associations. Explicit imported/manual product records and intentionally retained
results are preserved; review those records when changing the experiment.

These fixes are included in the matching v1.1.1 executable. Its embedded
application modules were verified against the source; Windows file and product
versions are 1.1.1. Both bundled PyParse startup checks, the packaged scientific
viewer, and the External Import workflow using the frozen controller passed.
The separate historical section below describes the preceding 9 October build.
All 440 root regression tests passed for the corrected source, including new
mapping-revalidation, push-order, JSON-ambiguity and custom-product lifecycle
checks. Test projects and logs are kept outside the publication source tree.
The actual TypeScript WebView import-to-export check also passed: three stock
records, repeated push without duplicates, 48-well summary and byte-exact
preservation of the imported file in the exported project.

## Previous release validation

Prepared 9 October 2026, version 1.1.0. This publication tree includes External
Import and project change tracking. Private workbooks, settings, experimental
projects, downloaded papers/datasets, environments and development artifacts
are excluded. The executable is built from this tree using
`packaging/TypeScript.spec`; the release checksum and build record identify it.

## Checks

- **436 root regression tests passed**, with no failures, errors or skips.
  Tests cover the existing chemistry/workflow features, archive round trips,
  external-transfer/source-stock validation, repeat-push replacement, mixed
  manual/external reaction records and project change tracking.
- **TypeScript type checking passed.** Rebuilding the renderer produced a
  byte-identical `desktop/live_ui/dist/app.js`.
- Native WebView checks passed all seven main tabs, four synthesis editors,
  adding compound rows and five unchanged/edited close-save cases. A preliminary
  editor assertion ran before rendering completed; the test now waits for the
  selected editor's own controls. No renderer behavior was changed.
- The standalone EXE passed standard/modified PyParse startup checks and a
  native scientific-viewer check from an isolated folder with Python environment
  paths removed: project loading, trace display, peak inspection, manual
  assignment/restoration, resizing and layout persistence.
- The EXE controller passed the rendered External Import workflow: import,
  source-stock template generation/import, three compound additions, repeat
  push without duplicates, 48-well summary and export preserving original bytes.
- Verification of the executable archive matched 51 bundled application modules
  against the published Python source. Bundled renderer, both PyParse scripts
  and simulator script also matched their source files exactly.
- The bundled Opentrons simulator opened its native window and closed with exit
  code zero, without a separate simulator EXE or Python environment paths.
- Original and Modified PyParse Python files are byte-identical to the preceding
  publication source and the development trial. No analysis engine was edited.
- External-import application services and controller are unchanged from the
  tested trial. The publication version retains the source-based Opentrons
  simulator launcher; its frozen tool dispatch is explicitly registered and
  regression-tested, so no private nested simulator executable is required.

The regression suite creates and destroys many Tk fixtures, producing some
teardown warnings. Native desktop checks assess actual close/save behavior
separately. A preliminary test referenced an obsolete packaging spec; the
publication test now checks the active desktop spec and simulator dispatch.

## Earlier public-data exercise

A development validation used Supplementary Data 2 from
[DOI 10.1038/s42004-021-00550-x](https://www.nature.com/articles/s42004-021-00550-x).
The wide dispense-volume CSV was converted into transfer rows, with published
chemical identities and concentrations. Two projects, each containing 576
transfers and 96 product records, passed structure-generation and archive/display
checks. Source/destination display coordinates were reconstructed, not verified
physical deck positions. Expected product connectivity was checked without E/Z
assignment; no analytical spectra or experimental results were invented.
This was not direct native Chemspeed import or instrument execution. Those
downloaded inputs and generated projects are not included in this repository.

## Limits

The checks do not prove all configurations are bug-free, analytical assignments
are chemically correct, or robot protocols execute correctly on hardware.
Independent testing on a clean Windows computer remains outstanding. The app
requires Microsoft Edge WebView2 Runtime. CI workflows are included but have not
run on GitHub because this preparation does not publish the repository.

The owner must approve a software license, authors/citation metadata and the
repository/archive identifiers before describing the release as open source.
Version 1.1.0 introduced External Import. Its version-only rebuild preserved the
9 October application behavior. Version 1.1.1 adds the fixes described above.
