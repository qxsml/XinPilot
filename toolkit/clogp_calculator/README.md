# Molecular Properties & Alerts Calculator

Open Toolkit > Molecular Properties & Alerts Calculator, or Next Step > Product properties & stock preparation > Send products to Properties & Alerts Calculator. All/manual RXN-well/UV254-threshold selection uses Product Details structures, not LCMS reference structures. Project records and synthesis steps are not modified.

## Shared input and result tabs
- Compounds: add/edit individual rows or import CSV (SMILES required; ID, Name and Reaction well optional).
- Properties: Wildman-Crippen cLogP, average MW, TPSA, HBD, HBA and strict rotatable-bond count.
- Drug-likeness: Lipinski violation count and exceeded criteria, Veber check and exceeded criteria, and QED (RDKit default weights).
- Structural alerts: RDKit PAINS A/B/C and Brenk catalog matches. Select a compound, then an alert to highlight matching atoms. Drag the dividers to adjust table, list and structure space.

Selection is shared across tabs. Calculate selected / Calculate all performs all assessments. Editing clears all old results for that row. Hover result headings for definitions. Export CSV writes all rows and results with method, RDKit version and rule definitions; uncalculated or inapplicable values stay blank, unlike zero matches. Results remain separate from the project ZIP and must be exported before closing the calculator.

## Scientific definitions and limits
- cLogP: local RDKit Wildman-Crippen MolLogP, not experimental logP, solubility or pH-dependent logD.
- MW: average molecular weight in g/mol, not monoisotopic exact mass.
- TPSA: RDKit default N/O definition, square angstroms (A^2).
- HBD/HBA: RDKit Lipinski donor/acceptor definitions.
- Rotatable bonds: explicit RDKit Strict option.
- Lipinski violations: number of MW > 500, cLogP > 5, HBD > 5, HBA > 10. No compound is labelled a drug based on this count.
- Veber: within limits if rotatable bonds <= 10 AND TPSA <= 140; TPSA variant. Threshold decisions use unrounded values.
- QED: RDKit default mean weights, 0-1; not a probability of efficacy, safety or approval.
- PAINS/Brenk counts: matched catalog entries, not atom count or number of occurrences. Highlights combine atom matches for the selected entry. A match is a review flag, not proof of assay interference or toxicity. No match does not establish safety.

No automatic neutralization, desalting or tautomer standardization. Neutral single-fragment structures receive all calculations. Charged single-fragment structures receive descriptors and alerts, with cLogP, Lipinski/Veber and QED left blank. Invalid and multi-fragment structures are flagged without calculated results. Changes to the calculator's input never modify XinPilot Product Details.

## Implementation
The Toolkit window remains native Tk in both development editions. The clogp-calculator tool key and file path remain stable. New transfers use the XinPilot schema; legacy SynTrack transfer schemas are also accepted. molecular_properties.py contains descriptor, rule and alert logic. Existing toolkit inclusion/RDKit collection in build specs covers the new module; no executable has been rebuilt for this change.

References:
- RDKit Crippen: https://www.rdkit.org/docs/source/rdkit.Chem.Crippen.html
- RDKit QED: https://www.rdkit.org/docs/source/rdkit.Chem.QED.html
- RDKit filter catalogs: https://www.rdkit.org/docs/source/rdkit.Chem.rdfiltercatalog.html
- Filter sources/references: https://github.com/rdkit/rdkit/blob/master/Code/GraphMol/FilterCatalog/README
