"""Identity validation and nonblank updates for existing master-stock records."""

STOCK_FIELDS = (
    'MW', 'Density', 'Quantity (mg)', 'Quantity(umol)', 'Quantity input unit',
    'Conc.', 'Solvent', 'Solvent added (uL)', 'Volume',
)


def structure_key(smiles):
    from rdkit import Chem, rdBase

    text = str(smiles or '').strip()
    if not text:
        raise ValueError('SMILES is missing; compound identity cannot be verified')
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(text)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError('SMILES is invalid; compound identity cannot be verified')
    # Atom-map numbers are annotations, not chemical identity. Do not strip
    # counterions, neutralize charges or remove stereochemistry/isotopes.
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def stock_updates(existing, incoming):
    if structure_key(existing.get('SMILES')) != structure_key(incoming.get('SMILES')):
        raise ValueError('SMILES represents a different structure; master record unchanged')
    updates = {}
    for field in STOCK_FIELDS:
        value = incoming.get(field, '')
        if value is not None and str(value).strip():
            updates[field] = value
    if not str(existing.get('Name') or '').strip() and str(incoming.get('Name') or '').strip():
        updates['Name'] = incoming['Name']
    return updates
