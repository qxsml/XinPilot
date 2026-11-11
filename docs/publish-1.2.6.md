# Publishing the corrected 1.2.6 release

This corrected build replaces the earlier unpublished local 1.2.6 build. Older
versions are unchanged. Do not distribute the superseded executable or checksums.

1. Commit and push this folder's source changes using Git/GitHub Desktop. Keep
   .gitignore in effect: release assets, artifacts and local data are not source.
2. On https://github.com/qxsml/XinPilot/releases choose Draft a new release.
3. Create tag v1.2.6 targeting the commit containing these corrections. Use title
   XinPilot v1.2.6. If that tag already exists, stop and check its target; do not
   silently retag a published version.
4. Use the release description below, and attach these four files from release/:
   XinPilot-v1.2.6-Windows-x64.exe, XinPilot-v1.2.6-Licenses.zip,
   SHA256SUMS-1.2.6.txt and BUILD_INFO-1.2.6.json.
5. Verify filenames and checksums against SHA256SUMS-1.2.6.txt, then publish.

The build record identifies the exact source inventory and the base commit,
not a guessed future release commit. Its pre-commit status describes build time.
Do not edit the build record without updating its checksum.

## Release description

Patch release for master-list stock identity and corrections.

- ID identifies a physical stock. Different IDs can have identical chemical
  names, structures, solvents and concentrations.
- Nonblank Name and Nature values update existing records; blanks preserve them.
- Changes to an existing ID's solvent or concentration require confirmation as
  corrections, with old/new values displayed. Cancel leaves that ID unchanged.
- Concentration uses M only; numerically equivalent values do not prompt.
- Repeated IDs within an incoming batch are rejected, even if identical.
- Existing-ID chemical structure checks remain mandatory.

No project schema, chemistry calculation, AutoLynx export or PyParse engine changes.

Windows x64 and Microsoft Edge WebView2 Runtime are required; Python is not.
The executable is unsigned. Checksums, licenses and build information are attached.
No independent clean-PC, physical robot or live Waters acquisition test was performed.

See https://github.com/qxsml/XinPilot/blob/v1.2.6/docs/validation-1.2.6.md
for validation results.
