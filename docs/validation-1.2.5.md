# Version 1.2.5 validation

Built and checked locally on Windows on 3 November 2026.

- All 574 root regression tests passed after the approved fixes and CSV import.
- All 192 distributed Python files compiled in memory.
- Before the CSV addition, thirteen desktop scripts and five shutdown cases
  passed, with one optional private-RPT subcheck skipped. CSV import was then
  checked through the actual Compound Notes table as well as regression tests.
- All 56 checked bundled application modules and 41 selected resources match
  source, including the new CSV reader, module validation and callback helper.
- Windows file/product version and executable filename are 1.2.5.
- Both PyParse entry points start from an isolated executable folder with Python
  removed from the runtime PATH. All five original PyParse engine resources
  inside the executable match the pinned upstream files exactly.
- The packaged WebView2 scientific diagnostic passed: project loading, traces,
  manual assignment/restoration and adjustable peak-inspection layout.
- The actual TypeScript interface connected to the packaged controller loaded
  a CSV through Load Excel, preserved a leading-zero ID and quoted name, and
  saved the records to a valid Excel workbook.

See [release notes](release-1.2.5.md) and [detailed source changes](review-fixes-20261102.md).
The original PyParse engine retains upstream bugs; XinPilot detects and reports
failed analysis rather than modifying that engine. Modified PyParse is unchanged.

The executable was built from the approved source changes; its release commit
and source inventory are recorded in BUILD_INFO.json. The executable is unsigned. No independent clean-PC, live Waters
import, live PubChem lookup or physical robot validation was performed.
