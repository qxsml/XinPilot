# XinPilot v1.2.3

Released 25 October 2026. This patch retains unified reaction-plate mapping, external transfer import and AutoLynx CSV export from v1.2.2.

- Corrects six reaction-template scope/stereochemistry issues: Heck, CuAAC, Mitsunobu, oxime formation, generic reductive amination and carbonyl reduction.
- Preserves compatible Opentrons tip-rack selections when a pipette changes.
- Rejects Flex single-nozzle transfers with occupied adjacent overhang slots before protocol export.

See [detailed behavior and limitations](source-fixes-20261025.md) and [validation](validation-1.2.3.md). Saved reaction IDs and project schema are unchanged. Existing product records are not silently regenerated. Both PyParse engines are unchanged.

The Windows executable is `XinPilot-v1.2.3-Windows-x64.exe`. Upload it as a GitHub Release asset; `release/` and executables are intentionally Git-ignored and are not repository source files. Source packaging instructions are in `packaging/README.md`.
