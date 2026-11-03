# AutoLynx sample-list export

AutoLynx export was introduced in v1.2.2 and is included in v1.2.5. Launch
`Launch_XinPilot.bat`, then open **Cheminformatics > LCMS Input > Export AutoLynx
sample list**. The matching executable includes this feature.

Assign LCMS wells and reaction names before exporting. All LCMS Input samples
are exported. Reaction names become FILE_NAME; only LCMS wells become
SAMPLE_LOCATION (for example `2:A,1`). Reaction wells are not substituted.
Names and wells must be nonempty and unique. Choose the Waters tray position,
LCMS plate format (48: A–F/1–8; 96: A–H/1–12), and injection order.

Enter acquisition/inlet methods and optional processing settings. Loading an
example CSV copies only uniform MS_FILE, MS_TUNE_FILE, INLET_FILE, PROCESS and
PROCESS_PARAMS values. It never copies names, positions or injection volume.
Injection volume starts blank whenever the dialog opens and must be entered.
Volumes are written as plain decimals without six-digit rounding. Set the optional
instrument maximum injection volume to match your configured Waters system;
XinPilot does not infer the instrument's physical limits. The broad CSV numeric
range (0.000000001 to 1000000 uL) is a serialization guard, not an operating range.
Windows reserved filenames are rejected and sample names are limited to 200
UTF-16 code units. Short names also help avoid Windows full-path limits.
The default processing program is OpenLynx; a loaded template retains its spelling.
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
Those statements describe the original v1.2.2 validation. See the current release validation document for subsequent changes.
