from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from rdkit import Chem, rdBase
from rdkit.Chem import AllChem

import integrated_tecan_compound_cheminformatics as core


# Conservative, structure-triggered impurity knowledge base.  These are possible
# products to search for, not predictions that an impurity must be present.
IMPURITY_RULES: Sequence[Dict[str, object]] = (
    {
        "id": "electrophile_dehalogenation",
        "name": "Electrophile dehalogenation",
        "category": "Side reaction",
        "source": "electrophile",
        "mode": "single",
        "reactions": (
            "suzuki", "sonogashira", "heck", "buchwald_hartwig", "snar", "ullmann_cn",
            "sn2_alkylation", "williamson_ether", "n_alkylation", "o_alkylation",
        ),
        "smarts": "[*:1][Br,Cl,I:2]>>[*:1][H]",
    },
    {
        "id": "sulfonyl_halide_hydrolysis",
        "name": "Sulfonyl halide hydrolysis",
        "category": "Hydrolysis product",
        "source": "electrophile",
        "mode": "single",
        "smarts": "[*:1]S(=O)(=O)[Cl,Br:2]>>[*:1]S(=O)(=O)O",
    },
    {
        "id": "acyl_halide_hydrolysis",
        "name": "Acyl halide hydrolysis",
        "category": "Hydrolysis product",
        "source": "electrophile",
        "mode": "single",
        "smarts": "[*:1]C(=O)[Cl,Br,I:2]>>[*:1]C(=O)O",
    },
    {
        "id": "boronic_acid_protodeboronation",
        "name": "Protodeboronation",
        "category": "Side reaction",
        "source": "nucleophile",
        "mode": "single",
        "smarts": "[*:1]B([O])[O]>>[*:1][H]",
    },
    {
        "id": "aryl_halide_homocoupling",
        "name": "Aryl-halide homocoupling",
        "category": "Homocoupling product",
        "source": "electrophile",
        "mode": "homo",
        "reactions": ("suzuki", "sonogashira", "heck", "buchwald_hartwig", "snar", "ullmann_cn"),
        "smarts": "[*:1][Br,Cl,I,F:2].[*:3][Br,Cl,I,F:4]>>[*:1][*:3]",
    },
    {
        "id": "boronic_acid_homocoupling",
        "name": "Boronic-acid homocoupling",
        "category": "Homocoupling product",
        "source": "nucleophile",
        "mode": "homo",
        "reactions": ("suzuki",),
        "smarts": "[*:1]B([O])[O].[*:3]B([O])[O]>>[*:1][*:3]",
    },
    {
        "id": "terminal_alkyne_homocoupling",
        "name": "Terminal-alkyne oxidative homocoupling",
        "category": "Homocoupling product",
        "source": "nucleophile",
        "mode": "homo",
        "reactions": ("sonogashira", "click_triazole"),
        "smarts": "[*:1][C:2]#[CH:3].[*:4][C:5]#[CH:6]>>[*:1][C:2]#[C:3][C:6]#[C:5][*:4]",
    },
    {
        "id": "carboxylic_acid_anhydride",
        "name": "Carboxylic-acid anhydride formation",
        "category": "Condensation product",
        "source": "electrophile",
        "mode": "homo",
        "reactions": ("amide_coupling", "esterification"),
        "smarts": "[*:1]C(=O)O.[*:3]C(=O)O>>[*:1]C(=O)OC(=O)[*:3]",
    },
    {
        "id": "isocyanate_hydrolysis",
        "name": "Isocyanate hydrolysis to amine",
        "category": "Hydrolysis product",
        "source": "electrophile",
        "mode": "single",
        "reactions": ("urea_isocyanate", "carbamate_isocyanate"),
        "smarts": "[*:1][N:2]=C=O>>[*:1][N:2]",
    },
    {
        "id": "curtius_isocyanate_intermediate",
        "name": "Isocyanate intermediate",
        "category": "Reaction intermediate",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("curtius", "acid_to_amine"),
        "smarts": "[*:1][C:2](=O)[O;H1]>>[*:1]N=C=O",
    },
    {
        "id": "chan_lam_protodeboronation",
        "name": "Protodeboronation",
        "category": "Side reaction",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("chan_lam",),
        "smarts": "[*:1]B([O])[O]>>[*:1][H]",
    },
    {
        "id": "chan_lam_boronic_homocoupling",
        "name": "Boronic-acid homocoupling",
        "category": "Homocoupling product",
        "source": "reactant1",
        "mode": "homo",
        "reactions": ("chan_lam",),
        "smarts": "[*:1]B([O])[O].[*:3]B([O])[O]>>[*:1][*:3]",
    },
    {
        "id": "petasis_protodeboronation",
        "name": "Protodeboronation",
        "category": "Side reaction",
        "source": "reactant3",
        "mode": "single",
        "reactions": ("petasis",),
        "smarts": "[*:1]B([O])[O]>>[*:1][H]",
    },
    {
        "id": "petasis_boronic_homocoupling",
        "name": "Boronic-acid homocoupling",
        "category": "Homocoupling product",
        "source": "reactant3",
        "mode": "homo",
        "reactions": ("petasis",),
        "smarts": "[*:1]B([O])[O].[*:3]B([O])[O]>>[*:1][*:3]",
    },
    {
        "id": "nitro_partial_reduction_nitroso",
        "name": "Partially reduced nitroso intermediate",
        "category": "Partial reduction product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("nitro_reduction",),
        "smarts": "[*:1][N+:2](=[O:3])[O-:4]>>[*:1][N+0:2]=O",
    },
    {
        "id": "nitro_partial_reduction_hydroxylamine",
        "name": "Partially reduced hydroxylamine intermediate",
        "category": "Partial reduction product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("nitro_reduction",),
        "smarts": "[*:1][N+:2](=[O:3])[O-:4]>>[*:1][N+0H:2]O",
    },
    {
        "id": "primary_alcohol_overoxidation",
        "name": "Carboxylic acid overoxidation product",
        "category": "Overoxidation product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("alcohol_oxidation",),
        "smarts": "[C;H2:1][O;H1:2]>>[C:1](=O)O",
    },
    {
        "id": "carbonyl_deoxygenation",
        "name": "Carbonyl deoxygenation product",
        "category": "Overreduction product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("carbonyl_reduction",),
        "smarts": "[C:1]=[O:2]>>[CH2:1]",
    },
    {
        "id": "ester_alcohol_fragment",
        "name": "Alcohol fragment from ester hydrolysis",
        "category": "Hydrolysis product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("ester_hydrolysis",),
        "smarts": "[C](=O)[O:1][*:2]>>[OH:1][*:2]",
    },
    {
        "id": "amide_amine_fragment",
        "name": "Amine fragment from amide hydrolysis",
        "category": "Hydrolysis product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("amide_hydrolysis",),
        "smarts": "[C](=O)[N:1][*:2]>>[NH:1][*:2]",
    },
    {
        "id": "reductive_amination_imine",
        "name": "Unreduced imine intermediate",
        "category": "Incomplete reaction product",
        "sources": ("reactant1", "reactant2"),
        "mode": "pair",
        "reactions": ("reductive_amination", "reductive_amination_aldehyde", "reductive_amination_ketone", "petasis"),
        "smarts": "[C:2]=[O:3].[N;H1,H2:4]>>[C:2]=[N:4]",
    },
    {
        "id": "carbonyl_to_alcohol_during_reductive_amination",
        "name": "Direct carbonyl reduction product",
        "category": "Competing reduction product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("reductive_amination", "reductive_amination_aldehyde", "reductive_amination_ketone"),
        "smarts": "[C:1]=[O:2]>>[C:1][O:2]",
    },
    {
        "id": "alkyl_halide_elimination",
        "name": "Alkene elimination product",
        "category": "Elimination product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("sn2_alkylation", "williamson_ether", "n_alkylation", "o_alkylation"),
        "smarts": "[C;H1,H2:1][C;H1,H2:2][Cl,Br,I]>>[C:1]=[C:2]",
    },
    {
        "id": "isothiocyanate_hydrolysis",
        "name": "Isothiocyanate hydrolysis/decomposition to amine",
        "category": "Hydrolysis product",
        "source": "reactant1",
        "mode": "single",
        "reactions": ("thiourea_isothiocyanate",),
        "smarts": "[*:1][N:2]=C=S>>[*:1][N:2]",
    },
)


def _canonical(smiles: object) -> str:
    text = str(smiles or "").strip()
    if not text:
        return ""
    mol = Chem.MolFromSmiles(text)
    if mol is None:
        return ""
    return Chem.MolToSmiles(mol, canonical=True)


def _reaction_products(smarts: str, reactants: Sequence[Chem.Mol]) -> List[str]:
    if not smarts or not reactants:
        return []
    products: List[str] = []
    with rdBase.BlockLogs():
        rxn = AllChem.ReactionFromSmarts(smarts)
        if rxn is None:
            return []
        for product_set in rxn.RunReactants(tuple(reactants)):
            if not product_set:
                continue
            product = product_set[0]
            try:
                Chem.SanitizeMol(product)
                products.append(Chem.MolToSmiles(product, canonical=True))
            except Exception:
                continue
    return sorted(set(products))


def predict_impurities(
    reaction_id: str,
    desired_product_smiles: str,
    nucleophile_smiles: str,
    electrophile_smiles: str,
    *,
    nucleophile_name: str = "",
    electrophile_name: str = "",
    reaction_smarts: str = "",
    reactants: Optional[Sequence[Dict[str, str]]] = None,
    accepted_product_smiles: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    """Return conservative LCMS target candidates for one reaction.

    RDKit applies explicit SMARTS rules.  It does not estimate probability,
    kinetics, retention time, or whether a candidate is actually present.
    """

    reaction_id = str(reaction_id or "").strip()
    desired = _canonical(desired_product_smiles)
    if reactants is None:
        reactants = [
            {"smiles": electrophile_smiles, "name": electrophile_name or "Unreacted starting material 1"},
            {"smiles": nucleophile_smiles, "name": nucleophile_name or "Unreacted starting material 2"},
        ]
    normalized_reactants = []
    for index, reactant in enumerate(reactants[:3], start=1):
        smiles = _canonical(reactant.get("smiles", ""))
        if smiles:
            normalized_reactants.append({
                "smiles": smiles,
                "name": str(reactant.get("name", "") or reactant.get("id", "") or f"Unreacted starting material {index}"),
                "id": str(reactant.get("id", "") or ""),
            })
    mols = {
        f"reactant{index}": Chem.MolFromSmiles(reactant["smiles"])
        for index, reactant in enumerate(normalized_reactants, start=1)
    }
    mols["electrophile"] = mols.get("reactant1")
    mols["nucleophile"] = mols.get("reactant2")

    candidates: List[Dict[str, str]] = []
    if isinstance(accepted_product_smiles, str):
        accepted_product_smiles = [accepted_product_smiles]
    accepted_products = {
        canonical
        for canonical in (_canonical(value) for value in (accepted_product_smiles or []))
        if canonical
    }
    if desired:
        accepted_products.add(desired)
    seen = set(accepted_products)

    def add(smiles: object, category: str, name: str, basis: str, rule_id: str) -> None:
        canonical = _canonical(smiles)
        if not canonical or canonical in seen:
            return
        try:
            exact, mw, formula, mh, mna, neg = core.mass_fields(canonical)
        except Exception:
            return
        seen.add(canonical)
        candidates.append({
            "smiles": canonical,
            "category": category,
            "name": name,
            "basis": basis,
            "rule_id": rule_id,
            "exact_mass": exact,
            "mw": mw,
            "formula": formula,
            "mass_plus_h": mh,
            "mass_plus_na": mna,
            "mass_minus_h": neg,
        })

    for index, reactant in enumerate(normalized_reactants, start=1):
        add(
            reactant["smiles"],
            "Unreacted starting material",
            reactant["name"],
            f"Structural reactant {index} supplied to this reaction",
            f"unreacted_reactant{index}",
        )

    for rule in IMPURITY_RULES:
        allowed = tuple(rule.get("reactions", ()) or ())
        if allowed and reaction_id not in allowed:
            continue
        sources = tuple(rule.get("sources", ()) or ())
        if sources:
            rule_reactants = tuple(mols.get(str(source)) for source in sources)
            if any(mol is None for mol in rule_reactants):
                continue
        else:
            source = str(rule["source"])
            mol = mols.get(source)
            if mol is None:
                continue
            rule_reactants = (mol, mol) if rule.get("mode") == "homo" else (mol,)
        try:
            products = _reaction_products(str(rule["smarts"]), rule_reactants)
        except Exception:
            products = []
        for product in products:
            add(
                product,
                str(rule["category"]),
                str(rule["name"]),
                f"RDKit SMARTS knowledge rule: {rule['name']}",
                str(rule["id"]),
            )

    # Products from alternative reactive sites with the same formula/mass are
    # valid selectivity possibilities, not impurities.  Re-apply the selected
    # reaction once to those first-stage products to identify plausible
    # over-reaction products (for example, double coupling at a dihalide).
    ordered_mols = tuple(mols.get(f"reactant{index}") for index in range(1, len(normalized_reactants) + 1))
    if reaction_smarts and ordered_mols and all(mol is not None for mol in ordered_mols):
        first_stage_products = set(accepted_products)
        if not first_stage_products:
            try:
                first_stage_products.update(_reaction_products(reaction_smarts, ordered_mols))
            except Exception:
                pass
        for first_stage in sorted(first_stage_products):
            product_mol = Chem.MolFromSmiles(first_stage)
            if product_mol is None:
                continue
            for slot in range(len(ordered_mols)):
                repeated_reactants = list(ordered_mols)
                repeated_reactants[slot] = product_mol
                try:
                    over_products = _reaction_products(reaction_smarts, tuple(repeated_reactants))
                except Exception:
                    over_products = []
                for over_product in over_products:
                    add(
                        over_product,
                        "Over-reaction product",
                        "Further reaction at another compatible site",
                        "The selected reaction SMARTS can react again with a retained compatible site",
                        "repeated_main_reaction_overreaction",
                    )

    priority = {
        "Unreacted starting material": 0,
        "Over-reaction product": 1,
        "Side reaction": 2,
        "Hydrolysis product": 2,
        "Oxidation product": 2,
        "Reduction product": 2,
        "Homocoupling product": 3,
    }
    candidates = sorted(
        enumerate(candidates),
        key=lambda item: (priority.get(str(item[1].get("category", "")), 4), item[0]),
    )
    candidates = [candidate for _original_index, candidate in candidates[:8]]
    for index, candidate in enumerate(candidates, start=1):
        candidate["label"] = f"Impurity {index}"
        candidate["pyparse_name"] = f"Impurity{index}"
    return candidates


def _append_unique_text(existing: object, incoming: object) -> str:
    values: List[str] = []
    for raw in (existing, incoming):
        for value in str(raw or "").split(" | "):
            value = value.strip()
            if value and value not in values:
                values.append(value)
    return " | ".join(values)


def _merge_impurity_candidates(
    candidates: Iterable[Dict[str, object]],
    accepted_product_smiles: Sequence[object],
) -> List[Dict[str, str]]:
    excluded = {_canonical(value) for value in accepted_product_smiles}
    excluded.discard("")
    merged: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for raw in candidates:
        canonical = _canonical(raw.get("smiles", ""))
        if not canonical or canonical in excluded:
            continue
        candidate = {str(key): str(value or "") for key, value in raw.items()}
        candidate["smiles"] = canonical
        if canonical not in merged:
            merged[canonical] = candidate
            order.append(canonical)
            continue
        current = merged[canonical]
        for field in ("origin", "lineage", "basis", "carryover_status", "source_compound_id"):
            current[field] = _append_unique_text(current.get(field, ""), candidate.get(field, ""))
        if candidate.get("category") and candidate.get("category") != current.get("category"):
            current["category"] = "Multiple possible origins"
    return [merged[canonical] for canonical in order]


def carried_impurity_candidates(
    reaction_row: Dict[str, object],
    reaction_smarts: str,
    carried_sources: Mapping[str, Dict[str, object]],
    current_step: int,
) -> List[Dict[str, str]]:
    """Return unchanged and transformed impurity candidates for one route well.

    A carried impurity source is attached to the promoted product Chemical ID.
    It therefore follows only reaction wells that actually use that ID.  The
    current reaction SMARTS is also attempted with the prior impurity replacing
    the promoted product in its matching reactant slot.
    """
    normalized_sources = {
        str(key or "").strip().casefold(): dict(value)
        for key, value in (carried_sources or {}).items()
        if str(key or "").strip() and isinstance(value, dict)
    }
    reactants: List[Dict[str, str]] = []
    for index in range(1, 4):
        smiles = _canonical(reaction_row.get(f"reactant {index} smiles", ""))
        chemical_id = str(reaction_row.get(f"reactant {index} id", "") or "").strip()
        if smiles:
            reactants.append({"smiles": smiles, "id": chemical_id})

    candidates: List[Dict[str, object]] = []
    for slot, reactant in enumerate(reactants):
        source = normalized_sources.get(reactant["id"].casefold())
        if not source:
            continue
        source_step = int(source.get("source_step", max(1, current_step - 1)) or max(1, current_step - 1))
        source_well = str(source.get("source_reaction_well", "") or "").strip()
        material_state = str(source.get("carryover_status", "") or "Crude or purification not recorded").strip()
        compound_id = str(source.get("compound_id", "") or reactant["id"]).strip()
        for prior in source.get("impurities", []) or []:
            if not isinstance(prior, dict):
                continue
            prior_smiles = _canonical(prior.get("smiles", ""))
            prior_mol = Chem.MolFromSmiles(prior_smiles) if prior_smiles else None
            if prior_mol is None:
                continue
            prior_lineage = str(prior.get("lineage", "") or "").strip()
            if not prior_lineage:
                prior_lineage = f"Generated in Step {source_step}, RXN well {source_well or 'unknown'}"
            exact, mw, formula, mh, mna, neg = core.mass_fields(prior_smiles)
            candidates.append({
                "smiles": prior_smiles,
                "category": "Carried impurity",
                "name": str(prior.get("name", "") or prior.get("label", "") or "Earlier-step impurity"),
                "basis": f"Possible residual impurity carried with {compound_id}; material state: {material_state}",
                "rule_id": "multistep_unchanged_carryover",
                "exact_mass": exact,
                "mw": mw,
                "formula": formula,
                "mass_plus_h": mh,
                "mass_plus_na": mna,
                "mass_minus_h": neg,
                "origin": f"Carried from Step {source_step}, RXN well {source_well or 'unknown'}",
                "lineage": f"{prior_lineage} -> carried unchanged into Step {current_step}",
                "carryover_status": material_state,
                "source_compound_id": compound_id,
            })

            if not reaction_smarts:
                continue
            substituted = [Chem.MolFromSmiles(item["smiles"]) for item in reactants]
            if any(mol is None for mol in substituted):
                continue
            substituted[slot] = prior_mol
            try:
                products = _reaction_products(reaction_smarts, substituted)
            except Exception:
                products = []
            for product in products:
                exact, mw, formula, mh, mna, neg = core.mass_fields(product)
                candidates.append({
                    "smiles": product,
                    "category": "Descendant impurity",
                    "name": f"Next-step product of {prior.get('name', '') or prior.get('label', '') or 'earlier impurity'}",
                    "basis": f"The Step {current_step} reaction SMARTS accepts an earlier-step impurity in place of {compound_id}",
                    "rule_id": "multistep_impurity_descendant",
                    "exact_mass": exact,
                    "mw": mw,
                    "formula": formula,
                    "mass_plus_h": mh,
                    "mass_plus_na": mna,
                    "mass_minus_h": neg,
                    "origin": f"Descendant of Step {source_step} impurity",
                    "lineage": f"{prior_lineage} -> reacted in Step {current_step}, RXN well {reaction_row.get('reaction_well', '') or 'unknown'}",
                    "carryover_status": material_state,
                    "source_compound_id": compound_id,
                })

    accepted = list(reaction_row.get("selectivity products", []) or [])
    accepted.append(reaction_row.get("desired product smiles", ""))
    return _merge_impurity_candidates(candidates, accepted)


def flatten_impurity_rows(
    reaction_rows: Iterable[Dict[str, object]],
    reaction_lookup,
    *,
    carried_sources: Optional[Mapping[str, Dict[str, object]]] = None,
    current_step: int = 1,
) -> List[Dict[str, str]]:
    flattened: List[Dict[str, str]] = []
    for row in reaction_rows:
        reaction_id = str(row.get("reaction", "") or "")
        reaction = reaction_lookup(reaction_id) if reaction_lookup else None
        reaction_smarts = str((reaction or {}).get("smarts", "") or "")
        reactants = []
        for index in range(1, 4):
            smiles = str(row.get(f"reactant {index} smiles", "") or "")
            if smiles:
                reactants.append({
                    "smiles": smiles,
                    "name": str(row.get(f"reactant {index} name", "") or ""),
                    "id": str(row.get(f"reactant {index} id", "") or ""),
                })
        candidates: List[Dict[str, object]] = predict_impurities(
            reaction_id,
            str(row.get("desired product smiles", "") or ""),
            str(row.get("limiting reactant smiles", "") or ""),
            str(row.get("excess reactant smiles", "") or ""),
            nucleophile_name=str(row.get("limiting reactant name", "") or row.get("limiting reactant id", "") or ""),
            electrophile_name=str(row.get("excess reactant name", "") or row.get("excess reactant id", "") or ""),
            reaction_smarts=reaction_smarts,
            reactants=reactants or None,
            accepted_product_smiles=row.get("selectivity products", []) or [
                str(row.get("desired product smiles", "") or "")
            ],
        )
        for candidate in candidates:
            candidate["origin"] = f"Generated in Step {current_step}"
            candidate["lineage"] = (
                f"Generated in Step {current_step}, RXN well {row.get('reaction_well', '') or 'unknown'}"
            )
        candidates.extend(carried_impurity_candidates(
            row,
            reaction_smarts,
            carried_sources or {},
            current_step,
        ))
        accepted = list(row.get("selectivity products", []) or [])
        accepted.append(str(row.get("desired product smiles", "") or ""))
        candidates = _merge_impurity_candidates(candidates, accepted)
        for index, candidate in enumerate(candidates, start=1):
            candidate["label"] = f"Impurity {index}"
            candidate["pyparse_name"] = f"Impurity{index}"
        for candidate in candidates:
            flattened.append({
                **candidate,
                "reaction_name": str(row.get("reaction_name", "") or ""),
                "reaction_well": str(row.get("reaction_well", "") or ""),
                "pyparse_well": str(row.get("pyparse_well", "") or ""),
                "reaction": reaction_id,
            })
    return flattened
