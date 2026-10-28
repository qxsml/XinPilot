# Historical source validation through 6 October 2026

This document records the preceding source edition. See
[unified-plate release validation](validation-unified-plate.md) for the
current source and matching executable.

Prepared 5 October 2026; updated 6 October 2026 from the Better Frame TypeScript implementation.
Validation runs in a separate copy so the distributed source folder stays clean.

## Software checks

- **413 Python regressions passed:** no failures, errors or skipped root tests.
  Includes the current project/robot services, custom-template corrections and
  public-source simulator launching.
- Reaction heat maps now use the pushed destination format and orientation;
  LC-MS heat maps retain the 96-well layout. Added checks cover 24/48/96/384 wells,
  vertical well placement, compatible format aliases and conflicting formats.
  Legacy records without destination metadata retain the 96-well default.
- Stock-update checks cover equivalent/different SMILES, stereo/isotope/charge/
  salt distinctions, unverifiable structures, nonblank stock updates, duplicate
  skipping, workbook formula preservation and legacy `Name` imports. CAS lookup
  fills blank names without overwriting existing names; the displayed heading
  is Chemical name while the stored field remains `Name`.
- **TypeScript type checking passed.** Rebuilding with the pinned TypeScript
  and esbuild versions produced a byte-identical checked-in JavaScript bundle.
- **Native desktop checks passed:** all seven main tabs, the three synthesis
  editors, editable dropdowns, new-GWL dialogs, project handling, interactive
  peak assignment/restoration, plot resizing and all four close/save cases.
  One optional private-RPT fixture was skipped; synthetic trace checks passed.
- **Source inventory checks passed:** Python syntax, local documentation links,
  private-data exclusions and unchanged application/renderer/science source.
  A SHA-256 manifest is included for verification after download.
- Git checkout testing could not run because Git is not installed in this
  environment. `.gitattributes` disables line-ending conversion to preserve
  the bundled engines and the manifest's exact file hashes.

The root test suite creates/destroys many Tk fixtures and emitted teardown
messages despite passing. Actual app close/save behavior is assessed separately
by the native subprocess checks rather than inferred from those fixtures.

## Prior real-data acceptance of the same implementation

Before source preparation, the Better Frame implementation reproduced a
14-reaction Suzuki example, including three Tecan worklists, expected product
and LC-MS target structures, analytical values and portable project data.
Custom SMARTS/RXN, counterion handling, failed-regeneration invalidation,
interactive peak review and archive roundtrips were checked. Both PyParse
engines remained unchanged by the refactor and source preparation.

A separate blank-session test entered a 14-sample Opentrons workup through the
visible TypeScript controls using mouse/keyboard automation, without importing
the project or injecting controller state. All 42 compiled transfers and actual
Opentrons 8.8.0 simulation actions matched the saved-settings reference,
including mixing, delays and one tip reused per sample. Original experimental
projects, reports, screenshots and private logs are not part of this repository.

The public tree retains the existing source-based simulator launcher, dependency
and packaging support, while the core application, modular renderer and science
engines match Better Frame. Publication documentation/build metadata are separate
from experimental data.

## Limits

These results do not prove every possible configuration is bug-free. Simulator
success is not a physical robot test. Independent clean-Windows installation
testing remains outstanding. A public EXE was rebuilt from this source after
the heat-map and stock-update corrections; its native desktop diagnostic passed project loading,
trace display, manual assignment/restoration and inspector layout checks.
CI workflows are supplied but have not run on GitHub because no upload occurred.
License/authorship/repository/archive metadata still require the owner's input.
