from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Mapping, Sequence

from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize


def _canonical(mol) -> str:
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def _fragment_rank(mol) -> tuple:
    atoms = list(mol.GetAtoms())
    heavy = sum(1 for atom in atoms if atom.GetAtomicNum() > 1)
    carbon = sum(1 for atom in atoms if atom.GetAtomicNum() == 6)
    organic = 1 if carbon else 0
    return organic, heavy, carbon, len(atoms)


def _split_parent_and_counterions(mol):
    fragments = list(Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True))
    if not fragments:
        return Chem.Mol(mol), []
    parent_index = max(range(len(fragments)), key=lambda index: _fragment_rank(fragments[index]))
    parent = fragments[parent_index]
    counterions = [fragment for index, fragment in enumerate(fragments) if index != parent_index]
    return parent, counterions


def _neutralized_parent(parent):
    uncharger = rdMolStandardize.Uncharger(protonationOnly=True)
    return uncharger.uncharge(Chem.Mol(parent))


def _is_carbonyl_carbon(atom) -> bool:
    if atom.GetAtomicNum() != 6:
        return False
    return any(
        bond.GetBondType() == Chem.BondType.DOUBLE
        and bond.GetOtherAtom(atom).GetAtomicNum() == 8
        for bond in atom.GetBonds()
    )


def _is_sulfonyl_sulfur(atom) -> bool:
    if atom.GetAtomicNum() != 16:
        return False
    return sum(
        1
        for bond in atom.GetBonds()
        if bond.GetBondType() == Chem.BondType.DOUBLE
        and bond.GetOtherAtom(atom).GetAtomicNum() == 8
    ) >= 2


def _site_chemotype(atom, neutralizable: bool) -> tuple[str, str]:
    symbol = atom.GetSymbol()
    charge = atom.GetFormalCharge()
    if symbol == "N" and charge > 0:
        if neutralizable:
            if atom.GetIsAromatic():
                return "protonated_aromatic_nitrogen", "Protonated aromatic nitrogen"
            return "protonated_amine", "Protonated amine"
        if atom.GetIsAromatic():
            return "permanent_aromatic_nitrogen", "Permanent aromatic nitrogen charge"
        if atom.GetDegree() >= 4:
            return "quaternary_ammonium", "Quaternary ammonium (permanent)"
        return "permanent_positive_nitrogen", "Permanent positive nitrogen"
    if symbol == "O" and charge < 0:
        neighbors = list(atom.GetNeighbors())
        if any(_is_carbonyl_carbon(neighbor) for neighbor in neighbors):
            return "carboxylate", "Carboxylate"
        if any(_is_sulfonyl_sulfur(neighbor) for neighbor in neighbors):
            return "sulfonate", "Sulfonate"
        return "deprotonated_oxygen", "Deprotonated oxygen"
    if symbol == "P" and charge > 0:
        return "phosphonium", "Phosphonium (permanent)"
    if symbol == "S" and charge > 0:
        return "sulfonium", "Sulfonium (permanent)"
    permanence = "Neutralizable" if neutralizable else "Permanent"
    sign = "+" if charge > 0 else ""
    key = f"{'neutralizable' if neutralizable else 'permanent'}_{symbol}_{charge}"
    return key, f"{permanence} {symbol} charge ({sign}{charge})"


def analyze_smiles(smiles: object) -> Dict[str, object]:
    text = str(smiles or "").strip()
    mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {text}")
    canonical = _canonical(mol)
    parent, counterion_mols = _split_parent_and_counterions(mol)
    parent_smiles = _canonical(parent)
    # Reparse the canonical parent so stored atom indices remain stable when a
    # rule is later applied from serialized project state.
    parent = Chem.MolFromSmiles(parent_smiles)
    counterions = [_canonical(fragment) for fragment in counterion_mols]
    neutral = _neutralized_parent(parent)
    sites: List[Dict[str, object]] = []
    for atom in parent.GetAtoms():
        charge = int(atom.GetFormalCharge())
        if charge == 0:
            continue
        neutral_atom = neutral.GetAtomWithIdx(atom.GetIdx())
        neutralizable = (
            neutral_atom.GetFormalCharge() == 0
            and neutral_atom.GetFormalCharge() != atom.GetFormalCharge()
        )
        chemotype, label = _site_chemotype(atom, neutralizable)
        sites.append({
            "atom_index": int(atom.GetIdx()),
            "atom_number": int(atom.GetIdx()) + 1,
            "symbol": atom.GetSymbol(),
            "formal_charge": charge,
            "neutralizable": bool(neutralizable),
            "permanent": not bool(neutralizable),
            "chemotype": chemotype,
            "label": label,
        })
    all_charged_atoms = [atom for atom in mol.GetAtoms() if atom.GetFormalCharge()]
    return {
        "original_smiles": text,
        "canonical_smiles": canonical,
        "parent_smiles": parent_smiles,
        "counterion_smiles": counterions,
        "counterion_text": " . ".join(counterions),
        "formal_charge": int(Chem.GetFormalCharge(mol)),
        "parent_formal_charge": int(Chem.GetFormalCharge(parent)),
        "charged": bool(all_charged_atoms),
        "sites": sites,
    }


def default_rule(analysis: Mapping[str, object]) -> Dict[str, object]:
    return {
        "counterion_action": "remove",
        "counterion": str(analysis.get("counterion_text", "") or ""),
        "site_actions": {
            str(site["atom_index"]): ("keep" if site.get("permanent") else "neutralize")
            for site in analysis.get("sites", []) or []
        },
    }


def _copy_neutral_atom_properties(target, source) -> None:
    target.SetFormalCharge(int(source.GetFormalCharge()))
    target.SetNumExplicitHs(int(source.GetNumExplicitHs()))
    target.SetNoImplicit(bool(source.GetNoImplicit()))
    target.SetNumRadicalElectrons(int(source.GetNumRadicalElectrons()))


def _canonical_components(components: Iterable[str]) -> str:
    text = ".".join(str(value or "").strip() for value in components if str(value or "").strip())
    if not text:
        return ""
    mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise ValueError(f"Invalid combined SMILES: {text}")
    return _canonical(mol)


def apply_rule(smiles: object, rule: Mapping[str, object]) -> Dict[str, object]:
    analysis = analyze_smiles(smiles)
    parent = Chem.MolFromSmiles(str(analysis["parent_smiles"]))
    neutral = _neutralized_parent(parent)
    editable = Chem.RWMol(parent)
    actions = {
        str(key): str(value or "keep")
        for key, value in (rule.get("site_actions", {}) or {}).items()
    }
    neutralized_labels: List[str] = []
    permanent_labels: List[str] = []
    for site in analysis.get("sites", []) or []:
        atom_index = int(site["atom_index"])
        action = actions.get(str(atom_index), "keep")
        if action == "neutralize" and site.get("neutralizable"):
            _copy_neutral_atom_properties(
                editable.GetAtomWithIdx(atom_index),
                neutral.GetAtomWithIdx(atom_index),
            )
            neutralized_labels.append(str(site.get("label", "charged site")))
        elif site.get("permanent"):
            permanent_labels.append(str(site.get("label", "permanent charge")))
    Chem.SanitizeMol(editable)
    reaction_smiles = _canonical(editable)
    counterions = list(analysis.get("counterion_smiles", []) or [])
    entered_counterion = str(rule.get("counterion", "") or "").strip()
    if entered_counterion and entered_counterion.casefold() != "unknown":
        entered_mol = Chem.MolFromSmiles(entered_counterion.replace(" . ", "."))
        if entered_mol is not None:
            counterions = [_canonical(fragment) for fragment in Chem.GetMolFrags(entered_mol, asMols=True)]
    keep_counterions = str(rule.get("counterion_action", "remove")) == "keep"
    kept_counterions = counterions if keep_counterions else []
    product_form_smiles = _canonical_components([reaction_smiles, *kept_counterions])
    summary: List[str] = []
    if counterions:
        summary.append(("kept" if keep_counterions else "removed") + " counterion(s)")
    if neutralized_labels:
        summary.append("neutralized " + ", ".join(neutralized_labels))
    if permanent_labels:
        summary.append("preserved " + ", ".join(permanent_labels))
    if not summary:
        summary.append("kept charged structure as entered")
    return {
        "reaction_smiles": reaction_smiles,
        "product_form_smiles": product_form_smiles,
        "kept_counterions": kept_counterions,
        "summary": "; ".join(summary),
        "analysis": analysis,
    }


def append_counterions(products: Sequence[str], counterions: Sequence[str]) -> List[str]:
    required = Counter(str(value) for value in counterions if str(value or "").strip())
    if not required:
        return sorted({str(product) for product in products if str(product or "").strip()})
    finalized: List[str] = []
    for product in products:
        product_mol = Chem.MolFromSmiles(str(product or ""))
        if product_mol is None:
            continue
        existing = Counter(_canonical(fragment) for fragment in Chem.GetMolFrags(product_mol, asMols=True))
        additions: List[str] = []
        for counterion, count in required.items():
            additions.extend([counterion] * max(0, count - existing[counterion]))
        finalized.append(_canonical_components([_canonical(product_mol), *additions]))
    return sorted(set(finalized))


def automatic_lcms_target(smiles: object) -> Dict[str, object]:
    analysis = analyze_smiles(smiles)
    parent = Chem.MolFromSmiles(str(analysis["parent_smiles"]))
    target = _neutralized_parent(parent)
    target_smiles = _canonical(target)
    neutralized = [site for site in analysis.get("sites", []) or [] if site.get("neutralizable")]
    permanent = [site for site in analysis.get("sites", []) or [] if site.get("permanent")]
    summary: List[str] = []
    counterions = list(analysis.get("counterion_smiles", []) or [])
    if counterions:
        summary.append(f"removed {len(counterions)} counterion fragment(s)")
    if neutralized:
        summary.append(f"neutralized {len(neutralized)} neutralizable charge site(s)")
    if permanent:
        summary.append(f"preserved {len(permanent)} permanent charge site(s)")
    if not summary:
        summary.append("same as Product Details")
    return {
        "product_smiles": str(analysis["canonical_smiles"]),
        "target_smiles": target_smiles,
        "summary": "; ".join(summary),
        "changed": target_smiles != str(analysis["canonical_smiles"]),
        "counterion_count": len(counterions),
        "neutralizable_count": len(neutralized),
        "permanent_count": len(permanent),
        "analysis": analysis,
    }
