"""Identity validation and nonblank updates for existing master-stock records."""

from decimal import Decimal, InvalidOperation

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
    for field in (*STOCK_FIELDS, 'Name', 'Nature'):
        value = incoming.get(field, '')
        if value is not None and str(value).strip():
            updates[field] = value
    return updates


def batch_identity_errors(records, normalize_id):
    """Return blocked repeated IDs before any master rows are changed."""
    groups = {}
    for row, record in enumerate(records, start=1):
        key = normalize_id(record.get('ID', ''))
        if key:
            groups.setdefault(key, []).append((row, record))
    errors = {}
    for key, entries in groups.items():
        if len(entries) < 2:
            continue
        rows = ', '.join(str(row) for row, _ in entries)
        errors[key] = (
            f"{entries[0][1].get('ID')}: incoming record rows {rows}: "
            'duplicate ID; correct the batch before updating this ID')
    return errors


def stock_corrections(existing, updates):
    """Return solvent/concentration replacements requiring explicit approval.

    Concentrations are numeric M values. Blank incoming fields are already
    excluded by stock_updates; filling an unknown master value also needs approval.
    """
    changes = {}
    for field in ('Solvent', 'Conc.'):
        if field not in updates:
            continue
        old, new = existing.get(field), updates[field]
        old_text = '' if old is None else str(old).strip()
        new_text = str(new).strip()
        if field == 'Solvent':
            equal = old_text.casefold() == new_text.casefold()
        else:
            try:
                new_number = Decimal(new_text)
                if not new_number.is_finite() or new_number < 0:
                    raise InvalidOperation
            except InvalidOperation:
                raise ValueError('Concentration must be a finite nonnegative number in M') from None
            try:
                old_number = Decimal(old_text)
                equal = old_number.is_finite() and old_number == new_number
            except InvalidOperation:
                equal = False
        if not equal:
            changes[field] = (old, new)
    return changes
