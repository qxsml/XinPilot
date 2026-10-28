# AutoLynx sample-list export

Version 1.2.2 extends Unified Plate GitHub v1.2.1. Launch
`Launch_XinPilot.bat`, then open **Cheminformatics > LCMS Input > Export AutoLynx
sample list**. The matching v1.2.2 executable also includes this feature.

Assign LCMS wells and reaction names before exporting. All LCMS Input samples
are exported. Reaction names become FILE_NAME; only LCMS wells become
SAMPLE_LOCATION (for example `2:A,1`). Reaction wells are not substituted.
Names and wells must be nonempty and unique. Choose the Waters tray position,
LCMS plate format (48: A–F/1–8; 96: A–H/1–12), and injection order.

Enter acquisition/inlet methods and optional processing settings. Loading an
example CSV copies only uniform MS_FILE, MS_TUNE_FILE, INLET_FILE, PROCESS and
PROCESS_PARAMS values. It never copies names, positions or injection volume.
Injection volume starts blank whenever the dialog opens and must be entered.
Export CSV opens a save dialog for the user-selected CSV filename.

The output retains the 21-column schema of the supplied accepted examples,
including unused blank columns, UTF-8 BOM and quoted location fields. This is
a MassLynx/AutoLynx CSV export, not an instrument controller or a claim of
compatibility with every Waters installation. Confirm tray geometry and method
names in the receiving installation. The exporter does not create methods.

Architecture: `xinpilot/application/autolynx.py` owns parsing, validation and CSV
serialization. `autolynx_dialog.py` owns the popup and file dialogs; the existing
TypeScript bridge renders these controls. `cheminformatics_frame.py` supplies
the existing LCMS Input records. Chemistry and PyParse are unchanged.

Validation: unit tests cover required fields, duplicate/missing names and wells,
plate bounds, injection volume and method-only template loading. All three
user-supplied accepted CSV examples round-tripped field-for-field. The desktop
controller projected the popup and loaded methods with blank injection volume.
Actual acquisition/import on a Waters instrument remains a user check.

Regression run: 530 tests, 528 passed initially; two native-dialog tests lacked
the local WebView dependency path. With the configured path, all six tests in
that module passed. Save-file writing and fresh-volume reopening also passed.
Both PyParse trees are unchanged from v1.2.1. See release/BUILD_INFO.json for release validation.
