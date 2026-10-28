# XinPilot v1.1.0

This release adds External Import to the TypeScript desktop application and
includes project change tracking. The Windows executable is
`XinPilot-v1.1.0-Windows-x64.exe`.

- Import compatible CSV/TSV/text, Excel and JSON transfer tables.
- Map source labware/wells to Chemical IDs and import source-stock information
  using the generated Excel template.
- Combine pushed external records with existing synthesis workflows, generate
  expected structures, and preserve original import files in portable projects.
- Indicate unsaved project changes while preserving the explicit export workflow.

External Import supports one reaction destination plate per import and requires
review of units, geometry and source identities. It does not interpret arbitrary
native robot programs or control additional instruments. See
[External Import](EXTERNAL_IMPORT_TRIAL.md), [change tracking](CHANGE_TRACKING_TRIAL.md)
and [validation](validation-external-import.md).

The original and modified PyParse engines are unchanged. Application behavior is
identical to the validated external-import source snapshot; the version change
updates the executable name, Windows version resources and release records.

Use `release/BUILD_INFO.json` and `release/SHA256SUMS.txt` to identify the matching
binary. Historical v1.0.x release notes remain as historical documentation.
