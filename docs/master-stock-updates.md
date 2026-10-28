# Compound names and master stock updates

The interface calls the legacy `Name` field **Chemical name**. Excel imports,
exports and project records continue to use `Name`, so existing spreadsheets
remain compatible. Applying a CAS lookup fills a blank name with the retrieved
IUPAC name and preserves an existing name. PubChem CID is not added to the table.

**Add to Master List** adds new IDs unless the chemical name is already present.
An existing ID updates its existing row, without appending another row, only
after RDKit confirms matching structures. Comparison accepts different SMILES
representations of the same molecule and ignores atom-map annotations, but
preserves stereochemistry, isotope, charge and salt differences. Missing or
invalid SMILES, different structures or duplicate master IDs block that row's
update and are reported. Other valid records can still be processed.

The updatable stock fields are molecular weight, density, quantity in mg and
micromoles, quantity input unit, concentration, solvent, solvent added and volume
left. Nonblank values replace existing values; blank values do not erase them.
Zero is a value, not a blank. A blank master name can be filled, but an existing
name is preserved. Other identity/reference fields remain unchanged.

Repeated input IDs are processed once. IDs are matched using the existing
case-insensitive comparison. The workbook is saved atomically; unrelated cells
and formulas remain in place. If Excel locks the workbook, close it and retry.
