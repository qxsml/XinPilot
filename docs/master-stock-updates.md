# Compound names and master stock updates

The interface calls the legacy `Name` field **Chemical name**. Excel imports,
exports and project records continue to use `Name`, so existing spreadsheets
remain compatible. Applying a CAS lookup fills a blank name with the retrieved
IUPAC name and preserves an existing name. PubChem CID is not added to the table.

**Add to Master List** treats ID as the unique physical-stock identifier. New IDs
are added even if Name, structure, solvent and concentration match another stock.
An existing ID updates its existing row, without appending another row, only
after RDKit confirms matching structures. Comparison accepts different SMILES
representations of the same molecule and ignores atom-map annotations, but
preserves stereochemistry, isotope, charge and salt differences. Missing or
invalid SMILES, different structures or duplicate master IDs block that row's
update and are reported. Other valid records can still be processed.

The updatable stock fields are molecular weight, density, quantity in mg and
micromoles, quantity input unit, concentration, solvent, solvent added and volume
left. Nonblank values replace existing values; blank values do not erase them.
Zero is a value, not a blank. Nonblank incoming Name and Nature values also
replace existing values; blanks preserve them. Other identity/reference fields
remain unchanged.

For an existing ID, changing solvent or concentration requires a confirmation
showing old and new values. OK confirms a correction to that physical stock;
Cancel leaves the entire ID unchanged, including Name, Nature and quantity.
The default is Cancel. Filling a previously blank solvent or concentration also
requires confirmation. Different physical stocks must use different IDs.
Structure mismatches cannot be overridden by this confirmation.

Concentration is always in M. Numeric equivalents such as 0.1 and 0.100 do not
require confirmation; invalid, negative or nonfinite incoming concentrations
block an existing-ID update. Solvent comparison ignores case and outer whitespace,
but does not guess synonyms or mixture equivalence. Blank incoming fields preserve
existing values and do not prompt.

Repeated input IDs are invalid even when every field matches. All additions or
updates for that ID are blocked before writing; the warning lists the incoming
record row numbers (one-based, excluding the header). Other valid IDs can proceed.
IDs are matched using the existing
case-insensitive comparison. The workbook is saved atomically; unrelated cells
and formulas remain in place. If Excel locks the workbook, close it and retry.
