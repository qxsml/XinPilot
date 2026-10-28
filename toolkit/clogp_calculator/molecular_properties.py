"""Explicit RDKit descriptor/rule definitions and structural-alert atom matches."""
from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

PROPERTY_KEYS = ("MW (g/mol)", "TPSA (A^2)", "HBD", "HBA", "Rotatable bonds")
RULE_KEYS = ("Lipinski violations", "Lipinski criteria exceeded", "Veber", "Veber criteria exceeded", "QED")
EXPORT_KEYS = PROPERTY_KEYS + RULE_KEYS + ("PAINS count", "PAINS alerts", "Brenk count", "Brenk alerts")
RULE_METHOD = "Lipinski: MW<=500, cLogP<=5, HBD<=5, HBA<=10; Veber: rotatable bonds<=10, TPSA<=140; QED: RDKit default weights"
HELP = {
    "MW (g/mol)": "Average molecular weight of the supplied structure, in g/mol (not exact mass).",
    "TPSA (A^2)": "Topological polar surface area in square angstroms; RDKit default N/O contribution definition.",
    "HBD": "Hydrogen-bond donor count using RDKit Lipinski definitions.",
    "HBA": "Hydrogen-bond acceptor count using RDKit Lipinski definitions.",
    "Rotatable bonds": "RDKit strict rotatable-bond count; excludes amide and ester bonds.",
    "cLogP (RDKit)": "Wildman-Crippen calculated octanol/water logP. Not measured logP, solubility or pH-dependent logD.",
    "Lipinski violations": "Number of criteria exceeded: MW > 500, cLogP > 5, HBD > 5, HBA > 10. Shows violations rather than a drug/safety verdict.",
    "Lipinski criteria exceeded": "Lists each exceeded Lipinski threshold. Rules are calculated using unrounded values.",
    "Veber": "Within limits if strict rotatable bonds <= 10 and TPSA <= 140 square angstroms. This is the TPSA variant of the rule.",
    "Veber criteria exceeded": "Lists which of the rotatable-bond and TPSA limits are exceeded.",
    "QED": "Quantitative estimate of drug-likeness, 0 to 1, using RDKit default weights. Not a probability of efficacy, safety or approval.",
    "PAINS count": "Number of matched RDKit PAINS catalog entries (A, B and C). Flags for review, not proof of assay interference.",
    "Brenk count": "Number of matched RDKit Brenk catalog entries. Structural flags for review, not proof of toxicity.",
}


@lru_cache(maxsize=2)
def catalog(name):
    return FilterCatalog(getattr(FilterCatalogParams.FilterCatalogs, name))


def rule_values(mw, logp, hbd, hba, rotatable, tpsa):
    lipinski = [label for exceeded, label in ((mw > 500, "MW > 500"), (logp > 5, "cLogP > 5"),
                (hbd > 5, "HBD > 5"), (hba > 10, "HBA > 10")) if exceeded]
    veber = [label for exceeded, label in ((rotatable > 10, "Rotatable bonds > 10"),
              (tpsa > 140, "TPSA > 140")) if exceeded]
    return {"Lipinski violations": len(lipinski), "Lipinski criteria exceeded": "; ".join(lipinski) or "None",
            "Veber": "Outside limits" if veber else "Within limits", "Veber criteria exceeded": "; ".join(veber) or "None"}


def assess(mol, neutral):
    """Accept the exact parsed input. Never standardize, neutralize or desalt."""
    mw = Descriptors.MolWt(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    hbd, hba = Lipinski.NumHDonors(mol), Lipinski.NumHAcceptors(mol)
    rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol, rdMolDescriptors.NumRotatableBondsOptions.Strict)
    result = dict(zip(PROPERTY_KEYS, (f"{mw:.3f}", f"{tpsa:.2f}", hbd, hba, rotatable)))
    result.update({key: "" for key in RULE_KEYS})
    if neutral:
        result.update(rule_values(mw, Crippen.MolLogP(mol), hbd, hba, rotatable, tpsa))
        result["QED"] = f"{QED.qed(mol):.3f}"
    alerts = []
    for name, label in (("PAINS", "PAINS"), ("BRENK", "Brenk")):
        entries = catalog(name).GetMatches(mol)
        result[label + " count"] = len(entries)
        result[label + " alerts"] = "; ".join(e.GetDescription() for e in entries) or "None"
        for entry in entries:
            atoms = sorted({int(pair.target) for match in entry.GetFilterMatches(mol) for pair in match.atomPairs})
            alerts.append({"catalog": label, "name": entry.GetDescription(), "atoms": atoms})
    result["alerts"] = alerts
    return result
