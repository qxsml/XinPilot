# XinPilot v1.2.4

This maintenance build retains the application features of v1.2.3. No changes to chemistry calculations, planning behavior or project schema are intended.

- Removes malformed UTF-8 prefixes from four reaction-template scripts (Heck, CuAAC, Mitsunobu and reductive amination), allowing them to compile independently. Reaction SMARTS are unchanged.
- Aligns local and CI renderer build directories for reproducible bundles. Generated JavaScript changes are source-path comments only.
- Includes the approved Apache-2.0 LICENSE and NOTICE, third-party notices and version record inside the executable. A separate notices archive accompanies the release.
- Updates publication-facing documentation and the source checksum inventory.

The Windows executable is `XinPilot-v1.2.4-Windows-x64.exe`. Both PyParse source trees are unchanged. See [validation](validation-1.2.4.md) and [build instructions](../packaging/README.md).

The executable is unsigned. Microsoft Edge WebView2 Runtime is required. This release does not constitute physical robot validation.
