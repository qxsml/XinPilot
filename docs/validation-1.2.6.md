# Version 1.2.6 validation

Built and checked locally on Windows on 10 November 2026.

- Full root suite: 576 tests, zero failures, errors or skips.
- All 192 distributed Python sources compile in memory.
- All six desktop bridge regression scripts passed. One optional private-RPT
  subtest was skipped; no private data was required.
- New workbook tests cover nonblank Name/Nature replacement, blank preservation,
  numeric zero, equivalent SMILES, and conflicting/missing/invalid SMILES across
  repeated incoming IDs. Blocked IDs are neither updated nor added; unrelated
  valid IDs continue to be processed.
- Packaged original and modified PyParse help/startup checks passed with Python
  removed from the runtime PATH.
- Packaged native WebView2 scientific diagnostic passed from an isolated folder.
- Extracted packaged stock-update code passed direct Name/Nature and conflicting
  duplicate-ID checks. Embedded VERSION and Windows file/product versions are 1.2.6.
- The previous 1.2.5 executable was preserved and its recorded checksum verified.

Evidence is retained locally under artifacts/python-tests, artifacts/build-1.2.6.log
and artifacts/pkg-7f5c35. Tk teardown warnings appeared during the passing suite.
PowerShell reported a NativeCommandError while redirecting PyInstaller logging;
the build log reports completion and the resulting executable passed the checks above.

Release assets use versioned BUILD_INFO-1.2.6.json and SHA256SUMS-1.2.6.txt so
previous release records remain intact. The source is a local uncommitted patch;
no GitHub commit, tag, push or release was performed by these checks.

The Git candidate list excludes generated outputs, executables, DLLs and local
settings. A tracked-file scan found no common API-token/private-key patterns;
this is not a comprehensive security audit. Use Git, respecting .gitignore,
rather than uploading the whole working folder manually.

The executable is unsigned. No independent clean-PC, physical robot, live Waters
acquisition or live PubChem validation was performed. Project schema, chemistry
calculations, AutoLynx export and both PyParse engines are unchanged by this patch.
