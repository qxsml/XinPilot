# XinPilot v1.2.6

Patch release for Compound Notes master-list updates.

- Nonblank incoming Name and Nature values replace existing values after the
  existing chemical-identity check. Blank values preserve existing values.
- Repeated incoming IDs are checked together before writing. Missing, invalid
  or conflicting SMILES block that ID and report incoming record row numbers.
- Equivalent structures retain first-occurrence processing. Existing master-ID
  identity checks, duplicate-name rules and stock-field updates are unchanged.

No project schema, chemistry calculations, AutoLynx export logic or PyParse
engine changes. See [master-list rules](master-stock-updates.md) and
[validation results](validation-1.2.6.md).

The Windows executable is unsigned and requires Microsoft Edge WebView2 Runtime.
This release does not establish physical robot or Waters acquisition validation.
