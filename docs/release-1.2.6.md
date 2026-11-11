# XinPilot v1.2.6

Patch release for Compound Notes master-list updates.

- Nonblank incoming Name and Nature values replace existing values after the
  existing chemical-identity check. Blank values preserve existing values.
- ID identifies one physical stock. New IDs are accepted even when chemical
  name, structure, solvent and concentration match another stock.
- Existing-ID solvent or concentration changes require explicit confirmation
  as corrections, showing old and new values. Cancel leaves the entire ID unchanged.
- Concentration is compared numerically in M; 0.1 and 0.100 are equivalent.
- All repeated incoming IDs are blocked, including identical duplicates; the
  warning identifies the incoming record rows to correct.
- Existing master-ID structure checks remain mandatory and cannot be overridden.
  Blank incoming values preserve existing values; quantity zero remains valid.

No project schema, chemistry calculations, AutoLynx export logic or PyParse
engine changes. See [master-list rules](master-stock-updates.md) and
[validation results](validation-1.2.6.md).

The Windows executable is unsigned and requires Microsoft Edge WebView2 Runtime.
This release does not establish physical robot or Waters acquisition validation.
