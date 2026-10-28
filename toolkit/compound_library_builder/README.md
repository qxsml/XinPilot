# Bulk Cheminformatics

A standalone desktop tool for enumerating virtual products from one, two, or
three building-block lists. It is intended for making libraries for docking and
does not write to XinPilot.

## What it does

- Includes a self-contained snapshot of 43 reaction templates used by XinPilot.
- Reads building blocks from CSV, Excel (`.xlsx`/`.xlsm`), or SDF.
- Lets each reaction role use either a file or one manually entered molecule.
- Checks that each molecule matches the selected reaction-role pattern before
  enumeration.
- Retains each building block's ID, SMILES, and all original columns/SDF
  properties with `BB1_`, `BB2_`, or `BB3_` prefixes.
- Gives every result a new product ID and records reaction and combination IDs.
- Flags multiple products from one combination and duplicate product structures
  without discarding their lineage.
- Exports the complete library as CSV, Excel, or SDF. Invalid inputs,
  incompatible blocks, and failed reactions are retained as warnings/failures.

The program does **not** protonate, tautomerize, generate conformers, minimize,
or otherwise prepare structures for docking. Those steps should be done as a
separate, explicit workflow after enumeration.

## Input format

For CSV or Excel, the first row must contain column names. Select one column for
the building block ID and one for SMILES. Other columns are preserved.

For SDF, the molecular structure supplies the SMILES. Select `_Name` or any SDF
property as the ID field. All other SDF properties are preserved.

## Output fields

The leading fields are:

- `Product_ID`, `Product_SMILES`
- `Reaction_ID`, `Reaction_Type`, `Combination_ID`
- `Product_Ordinal`, `Products_From_Combination`, `Ambiguous`
- `Duplicate_Product`, `First_Product_ID`
- molecular formula, molecular weight, and exact mass
- `BB1_Role`, `BB1_ID`, `BB1_SMILES`, and all `BB1_...` source properties
- equivalent `BB2_...` and `BB3_...` fields when applicable

CSV and SDF exports put failures in a sibling file named
`<output>_failures.csv`. Excel stores Products, Failures, and Summary in separate
worksheets.

## Run

Double-click `Launch_Bulk_Cheminformatics.bat`, or run:

```powershell
python bulk_gui.py
```

Required Python packages are RDKit and openpyxl. The existing `ai-agent`
environment already contains both.

For a quick check, choose **Amide Coupling**, load
`example_inputs/carboxylic_acids.csv` for the first role and
`example_inputs/amines.csv` for the second role, then generate the nine-member
example library.

## Performance notes

File loading and chemistry run in a background thread so the window remains
responsive. The on-screen tables show at most 1,000 rows to avoid a GUI slowdown;
exports always contain every row. Enumerations above 250,000 compatible
combinations require confirmation because their full results may need substantial
time and memory.

## Important chemistry limitation

Reaction SMARTS provide deterministic virtual transformations, not a prediction
that a real experiment will succeed or that one regioisomer is preferred. Review
the selected reaction template and validate representative products before using
a large library downstream.
