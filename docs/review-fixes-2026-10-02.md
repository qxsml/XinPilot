# Review fixes ? 2 October 2026 (source update)

This source snapshot contains fixes developed in the new `XinPilot/Local` and
`XinPilot/Upload to GitHub` folders. The earlier source folders were preserved.
The existing copied executable has NOT been rebuilt with these changes.
Launch this source using `Launch_XinPilot.bat` to review the fixes.

## Included fixes

- **Opentrons air gap:** generated single and multi-dispense commands expel the
  air gap above the destination before delivering the requested liquid volume.
- **Opentrons blowout:** Liquid handling now offers No blowout, Destination,
  Source and Liquid waste. New rows and legacy rows without a saved choice default
  to No blowout. Extra liquid in a multi-dispense requires explicit Source or
  Liquid waste; it cannot be silently added to the last destination.
  Add a dedicated destination labware/reservoir to the deck for Liquid waste,
  then select its alias and well. Source/reaction labware cannot double as liquid
  waste. An all-channel waste destination must be a compatible reservoir.
  Source is an explicit option; choose it only when returning liquid is appropriate.
  Review these choices before regenerating an older protocol. Already exported
  Python protocols are unchanged and must be regenerated to use the fixes.
- **CAS lookup:** current and legacy full SMILES fields take precedence over
  connectivity-only representations, preserving available stereochemistry and
  isotope labels. Exact CAS checking and compound-field application are unchanged.
- **Analysis job ownership:** completion uses the original job's output folder
  and kind. Inputs are disabled during processing. Imports/new synthesis steps,
  changed analytical targets, changed RPT selection or modified platemaps prevent
  old results from attaching to the current project. The completed files remain
  in their original output folder.
- **Edited products:** a changed product SMILES detaches the affected product's
  old analytical assignments, original-PyParse purity and annotated images.
  Raw extracted sample traces, sample comments, impurity imagery and unaffected
  wells are retained. Equivalent SMILES do not invalidate results. Regenerate the
  LC-MS input and rerun product analysis after a substantive structure correction.
  The invalidation state survives project export/import.
- **Archived steps:** portable exports now package supported earlier-step
  worklists, chemical maps, trace images and identity/result tables in distinct
  per-step directories. Imports resolve those assets locally, and re-export is
  supported. Original RPT/acquisition files are not copied by this mechanism.
  Already missing legacy assets cannot be recovered; export reports those gaps.

## Boundaries

The bundled original `PyParse/` files are unchanged. No new executable was built.
The previously reviewed blank-Chemical-ID Opentrons sequence limitation and
synchronous PubChem lookup delay remain outside this update's requested scope.
Unit/controller checks and local protocol simulation do not establish physical
liquid-handling accuracy or execution on a robot.
