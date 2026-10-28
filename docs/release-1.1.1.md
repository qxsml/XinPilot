# XinPilot v1.1.1

Patch release, 11 October 2026. Windows executable:
`XinPilot-v1.1.1-Windows-x64.exe`.

- Preserve corrected source Chemical IDs and building-block flags when reloading
  mappings or revalidating imported transfers.
- Reject conflicting reaction destination formats before changing pushed records,
  regardless of which synthesis route is pushed last.
- Reject ambiguous nested/dotted JSON fields rather than silently overwriting a
  source well.
- Invalidate affected automatic custom-template products when building-block
  identities change. Explicit manual/imported products and intentionally retained
  results remain user-controlled.

All 440 source regression tests and the TypeScript external-import acceptance
workflow passed. Original and Modified PyParse engines and the TypeScript
renderer are unchanged. See `validation-external-import.md` for validation scope.
