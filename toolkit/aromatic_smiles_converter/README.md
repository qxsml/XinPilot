# Aromatic SMILES Converter

Independent XinPilot Toolkit utility for converting one SMILES per line in either direction:

- Aromatic notation to explicit alternating bonds: `c1ccccc1` → `C1=CC=CC=C1`
- Explicit alternating bonds to aromatic notation: `C1=CC=CC=C1` → `c1ccccc1`

The converter uses RDKit aromaticity perception and canonical SMILES output. Canonicalization may change atom order without changing molecular identity. The utility runs as a separate process and does not read or modify XinPilot project data.
