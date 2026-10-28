# Previous v1.0.1: explicit pushed reaction records

Originally released as RxnPilot; these behaviors are retained in XinPilot v1.0.2.

Reaction Summary now displays only additions explicitly pushed from Tecan,
Opentrons or Manual. Saving or editing a plan alone does not add it to the summary.
Push All includes reagents as well as building blocks; only checked building
blocks participate in generated product structures. Independent additions remain
separate; re-pushing a source replaces its previous snapshot without duplication.

Clear Pushed Chemicals offers:
- **Clear inputs only:** remove pushed records and summary additions; retain
  products and analytical results with a previous-inputs notice.
- **Clear inputs, products and results:** also clear downstream records in the
  current step. Original plans, external files and reaction conditions remain.
- **Cancel:** leave the project unchanged.

Retained products/results and their notice survive project export/import. They
are not paired with new reactants in Reaction Summary schemes. Generating new
products requests replacement of retained results. Later plan edits are flagged
in Reaction Summary; push again to update its records. Imported older projects
use their stored pushed rows; unpushed native plans are not silently promoted.
Legacy pushes without plan fingerprints cannot report changes predating import.

The earlier automatic reading of native planning records by Reaction Summary is
superseded by this release. The UI renderer and chemistry templates are unchanged.
Version 1.0.0 remains the previous release. Version 1.0.1 is built from the
publication source; the executable has Windows file/product version metadata.
