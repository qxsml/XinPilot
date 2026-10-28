# XinPilot 1.2.0 — unified reaction plate

Horizontal and vertical Tecan worklists now contribute to the same reaction
plate when pushed to Cheminformatics. B2 remains B2 in either orientation;
Tecan numerical positions and generated GWL commands remain orientation-specific.
The common reaction map and reaction heat map use the horizontal orientation.

Plate sizes must match. A 48-well plan cannot be combined with a 96-well plan.
Manual, Opentrons and External Import additions can join the same reaction wells.
Repeated pushes replace that route's previous pushed records without duplicating
transfers; separate additions to the same well remain separate records.

Original transfer orientation is retained in project records. No linking checkbox
or new project schema is required. Both 48-well HPLC-vial and 96-well Tecan formats
are supported. The LC-MS map remains independent of the reaction plate.

This release also includes the [13 October controller corrections](source-fixes-20261013.md)
that were not present in the v1.1.2 executable. Both PyParse engines, Tecan indexing,
the GWL generator and the TypeScript renderer are unchanged.

See [validation](validation-unified-plate.md) for test coverage and limits.


## 1.2.1 - 14 October 2026

Raw GWL imports now require an explicit plate size and orientation. GWL filenames
must be unique within a project (case-insensitive); conflicting imports and
ambiguous legacy records are rejected before changing the project.

This patch packages the reviewed source fixes. It does not change either PyParse
engine, chemistry, plate indexing or the TypeScript renderer.

Known limitations retained in this release: a partially successful Tecan push
can replace previously pushed records for skipped worklists; transfers with
missing Chemical IDs can be omitted when other rows are valid; and a chemical-map
write failure after a GWL write can leave the files and project out of sync.
Review warnings and pushed records, and verify both exported files after errors.
