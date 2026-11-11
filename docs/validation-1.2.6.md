# Version 1.2.6 validation

Corrected physical-stock rules prepared on 11 November 2026. This supersedes
the earlier unpublished local 1.2.6 build and its validation record.

- Full root suite: 578 tests, zero failures, errors or skips (231.976 seconds).
- All 192 distributed Python sources compile in memory.
- All six desktop bridge regression scripts passed. One optional private-RPT
  subtest was skipped; no private data was required.
- Workbook tests cover Name/Nature, blank preservation, zero, equivalent SMILES,
  duplicate incoming ID rejection (including identical records), and new IDs
  with identical stock contents. Structure conflicts cannot be approved.
- Solvent/concentration approval and cancellation cover whole-record behavior,
  numeric equivalence in M, invalid concentrations and approved changes smaller
  than the legacy display tolerance.
- Packaged original/modified PyParse startup and native WebView2 scientific
  diagnostic passed from an isolated folder with Python removed from PATH.
- The real desktop correction dialog passed against the packaged controller:
  Cancel preserved the entire existing ID, OK applied the correction, and a new
  physical-stock ID with identical contents was added. An initial test-harness
  file-selection race was corrected; no application change was needed.
- Direct extracted-module checks verified numeric concentration equivalence,
  tiny correction detection and rejection of identical duplicate incoming IDs.
- Embedded VERSION and Windows file/product metadata remain 1.2.6.

Evidence is retained locally under artifacts/python-tests,
artifacts/build-1.2.6-corrected-final.log, artifacts/pkg-46614b and
artifacts/stock-correction-window/result.json. Tk teardown warnings appeared
during the passing tests. PowerShell marked redirected native logging as an
error; PyInstaller logged successful completion and its output passed validation.

Release assets use versioned BUILD_INFO-1.2.6.json and SHA256SUMS-1.2.6.txt so
previous release records remain intact. The source is a local uncommitted patch;
no GitHub commit, tag, push or release was performed by these checks.

Use Git, respecting .gitignore, rather than uploading the whole working folder
manually. See [publishing instructions](publish-1.2.6.md).

The executable is unsigned. No independent clean-PC, physical robot, live Waters
acquisition or live PubChem validation was performed. Project schema, chemistry
calculations, AutoLynx export and both PyParse engines are unchanged by this patch.
