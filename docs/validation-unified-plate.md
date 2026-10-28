# Unified reaction plate validation — v1.2.0

The implementation changes two shared Python modules: reaction-format validation
in `xinpilot/application/heatmap_layout.py`, and common destination-map selection
in `reaction_summary_frame.py`. Original destination modes remain on transfer
records. Tecan indexing, GWL generation, both PyParse engines and the TypeScript
renderer are unchanged.

Regression coverage includes every well in the supported 48- and 96-well Tecan
maps; mixed horizontal/vertical additions to B2; retention of distinct numeric
Tecan addresses; repeated pushes; state export/import; clearing pushed records;
and combining manual, Opentrons and External Import additions in either push
order. Incompatible plate sizes must fail before replacing existing records.

Validation uses synthetic data and isolated copies. No experimental files are
modified and no instrument is operated. Executable checks on the development
laptop do not substitute for testing on an independent clean Windows computer.

See `release/BUILD_INFO.json` for the matching executable's checks and checksum.
Release files are distributed as GitHub Release assets; generated validation
files and build intermediates are kept outside the source upload folder.

## Completed checks

- 518 root regression tests passed.
- Source desktop bridge, GWL dialog, scientific viewer and External Import
  checks passed, as did all five native close/save scenarios.
- The executable was copied to an isolated directory and passed original and
  modified PyParse startup checks plus the native scientific-viewer diagnostic.
- 51 bundled application modules matched the source;
  selected bundled resources and Windows version metadata were also verified.
- Protected PyParse trees, renderer, Ketcher, Tecan indexing and GWL generator
  matched the preceding source. The original source directory was not modified.

An optional private-RPT desktop test was skipped. Existing Tk teardown warnings
and a WebView disposal warning appeared in the synthetic desktop tests; all
native close/save controller logs were empty. No clean second-PC test or robot
execution is claimed.


## Version 1.2.1 rebuild - 14 October 2026

The unchanged application source had passed 526 regression tests and the live
bridge import-dialog/duplicate-name checks earlier on 14 October. The rebuild
changes version and release metadata only; it does not repeat that full suite.
The new executable passed bundled-module/source comparison, selected resource
comparison (including both PyParse engines and compiled renderer), Windows
version metadata checks, isolated standard/modified PyParse startup, and the
packaged scientific-viewer diagnostic. This is not an exhaustive interactive
workflow test or a test on an independent clean Windows computer.
