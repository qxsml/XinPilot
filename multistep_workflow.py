from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Set


def normalize_well(value: object) -> str:
    text = str(value or "").strip().upper()
    match = re.fullmatch(r"([A-Z])\s*0*([1-9]|[1-9]\d*)", text)
    if not match:
        return text
    return f"{match.group(1)}{int(match.group(2))}"


def parse_percent(value: object) -> Optional[float]:
    text = str("" if value is None else value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 100.0 else None


def build_product_candidate(row: Dict[str, object], purity: object, purity_source: str) -> Dict[str, object]:
    return {
        "reaction_well": normalize_well(row.get("reaction_well", "")),
        "lcms_well": normalize_well(row.get("pyparse_well", "")),
        "product_id": str(row.get("product_id", "") or row.get("reaction_name", "") or "").strip(),
        "product_name": str(row.get("desired product name", "") or row.get("reaction_name", "") or "").strip(),
        "reaction_name": str(row.get("reaction_name", "") or "").strip(),
        "product_smiles": str(row.get("desired product smiles", "") or "").strip(),
        "product_formula": str(row.get("desired product formula", "") or "").strip(),
        "product_exact_mass": str(row.get("desired product exact mass", "") or "").strip(),
        "product_mw": str(row.get("desired product mw", "") or "").strip(),
        "purity": str("" if purity is None else purity).strip(),
        "purity_percent": parse_percent(purity),
        "purity_source": str(purity_source or "").strip(),
    }


def select_candidates_by_threshold(candidates: Iterable[Dict[str, object]], threshold: float) -> List[Dict[str, object]]:
    threshold = float(threshold)
    if not 0.0 <= threshold <= 100.0:
        raise ValueError("UV254 purity threshold must be between 0 and 100%.")
    return [
        dict(candidate)
        for candidate in candidates
        if (purity := parse_percent(candidate.get("purity_percent"))) is not None
        and purity >= threshold
    ]


def unique_compound_id(preferred: object, reaction_well: object, source_step: int, existing_ids: Set[str]) -> str:
    base = str(preferred or "").strip() or f"Step{source_step}_{normalize_well(reaction_well) or 'Product'}"
    candidate = base
    suffix = 2
    occupied = {str(value or "").strip().casefold() for value in existing_ids}
    while candidate.casefold() in occupied:
        candidate = f"{base}_{suffix}"
        suffix += 1
    existing_ids.add(candidate)
    return candidate


def candidate_to_compound_values(
    candidate: Dict[str, object],
    *,
    source_step: int,
    data_headers: Sequence[str],
    existing_ids: Set[str],
) -> Dict[str, str]:
    values = {header: "" for header in data_headers}
    reaction_well = normalize_well(candidate.get("reaction_well", ""))
    product_id = unique_compound_id(candidate.get("product_id", ""), reaction_well, source_step, existing_ids)
    purity = str(candidate.get("purity", "") or "").strip()
    source = str(candidate.get("purity_source", "") or "").strip()
    provenance = f"Product carried forward from synthesis step {source_step}, RXN well {reaction_well or 'unknown'}"
    if purity:
        provenance += f"; {source or 'UV254 purity'}: {purity}"
    values.update({
        "ID": product_id,
        "MW": str(candidate.get("product_mw", "") or "").strip(),
        "SMILES": str(candidate.get("product_smiles", "") or "").strip(),
        "Name": str(candidate.get("product_name", "") or product_id).strip(),
        "Nature": provenance,
    })
    return values
