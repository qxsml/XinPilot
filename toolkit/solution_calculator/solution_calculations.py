from __future__ import annotations

import re
import math
from dataclasses import dataclass

try:
    from rdkit import Chem
except ImportError:
    Chem = None


AMOUNT_UNITS = ("umol", "mg")
CONCENTRATION_UNITS = ("uM", "mM", "M")
VOLUME_UNITS = ("uL", "mL")


@dataclass(frozen=True)
class StockPreparationResult:
    active_umol: float
    exact_volume_ul: float
    final_volume_ul: float
    achieved_concentration_mm: float


@dataclass(frozen=True)
class ConcentrationResult:
    active_umol: float
    concentration_mm: float


@dataclass(frozen=True)
class RequiredAmountResult:
    active_umol: float
    weighed_umol: float
    required_mg: float


def positive_number(value: object, label: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number greater than zero.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a number greater than zero.")
    return number


def purity_fraction(value: object) -> float:
    percent = positive_number(value, "Mass purity")
    if percent > 100:
        raise ValueError("Mass purity must be between 0 and 100%.")
    return positive_number(percent / 100.0, "Mass purity fraction")


def concentration_to_mm(value: object, unit: str) -> float:
    number = positive_number(value, "Concentration")
    factors = {"uM": 0.001, "mM": 1.0, "M": 1000.0}
    if unit not in factors:
        raise ValueError(f"Unsupported concentration unit: {unit}")
    return positive_number(number * factors[unit], "Converted concentration")


def volume_to_ml(value: object, unit: str) -> float:
    number = positive_number(value, "Final volume")
    factors = {"uL": 0.001, "mL": 1.0}
    if unit not in factors:
        raise ValueError(f"Unsupported volume unit: {unit}")
    return positive_number(number * factors[unit], "Converted final volume")


def amount_to_umol(
    value: object,
    unit: str,
    *,
    molecular_weight: object = "",
    mass_purity_percent: object = 100,
) -> float:
    amount = positive_number(value, "Amount")
    fraction = purity_fraction(mass_purity_percent)
    if unit == "umol":
        return positive_number(amount * fraction, "Active amount")
    if unit == "mg":
        mw = positive_number(molecular_weight, "Molecular weight")
        return positive_number(amount * 1000.0 / mw * fraction, "Active amount")
    raise ValueError(f"Unsupported amount unit: {unit}")


def _rounded_volume(exact_volume_ul: float, rounding_increment_ul: object) -> float:
    text = str(rounding_increment_ul or "").strip()
    if not text:
        return exact_volume_ul
    try:
        increment = float(text)
    except ValueError as exc:
        raise ValueError("Volume rounding increment must be zero or a positive number.") from exc
    if not math.isfinite(increment) or increment < 0:
        raise ValueError("Volume rounding increment must be zero or a positive number.")
    if increment == 0:
        return exact_volume_ul
    ratio = positive_number(exact_volume_ul / increment, "Rounded volume ratio")
    rounded = round(ratio) * increment
    if rounded <= 0:
        raise ValueError("The rounding increment is too large for this final volume.")
    return positive_number(rounded, "Rounded final volume")


def prepare_stock(
    *,
    amount: object,
    amount_unit: str,
    target_concentration: object,
    concentration_unit: str,
    molecular_weight: object = "",
    mass_purity_percent: object = 100,
    rounding_increment_ul: object = 0,
) -> StockPreparationResult:
    active_umol = amount_to_umol(
        amount,
        amount_unit,
        molecular_weight=molecular_weight,
        mass_purity_percent=mass_purity_percent,
    )
    target_mm = concentration_to_mm(target_concentration, concentration_unit)
    exact_volume_ul = positive_number(active_umol / target_mm * 1000.0, "Calculated final volume")
    final_volume_ul = _rounded_volume(exact_volume_ul, rounding_increment_ul)
    final_volume_ml = positive_number(final_volume_ul / 1000.0, "Calculated final volume in mL")
    achieved_mm = positive_number(active_umol / final_volume_ml, "Achieved concentration")
    return StockPreparationResult(active_umol, exact_volume_ul, final_volume_ul, achieved_mm)


def check_concentration(
    *,
    amount: object,
    amount_unit: str,
    final_volume: object,
    volume_unit: str,
    molecular_weight: object = "",
    mass_purity_percent: object = 100,
) -> ConcentrationResult:
    active_umol = amount_to_umol(
        amount,
        amount_unit,
        molecular_weight=molecular_weight,
        mass_purity_percent=mass_purity_percent,
    )
    volume_ml = volume_to_ml(final_volume, volume_unit)
    return ConcentrationResult(active_umol, positive_number(active_umol / volume_ml, "Calculated concentration"))


def required_amount(
    *,
    target_concentration: object,
    concentration_unit: str,
    final_volume: object,
    volume_unit: str,
    molecular_weight: object,
    mass_purity_percent: object = 100,
) -> RequiredAmountResult:
    target_mm = concentration_to_mm(target_concentration, concentration_unit)
    volume_ml = volume_to_ml(final_volume, volume_unit)
    active_umol = positive_number(target_mm * volume_ml, "Required active amount")
    fraction = purity_fraction(mass_purity_percent)
    weighed_umol = positive_number(active_umol / fraction, "Required weighed amount")
    mw = positive_number(molecular_weight, "Molecular weight")
    required_mg = positive_number(weighed_umol * mw / 1000.0, "Required mass")
    return RequiredAmountResult(active_umol, weighed_umol, required_mg)


def format_number(value: float, significant_digits: int = 6) -> str:
    return f"{float(value):.{significant_digits}g}"


def formula_molecular_weight(formula: object) -> float:
    """Return average molar mass for a conventional molecular formula."""
    text = str(formula or "").strip().replace(" ", "").replace("·", ".")
    if not text:
        raise ValueError("Molecular formula is required.")
    if Chem is None:
        raise ValueError("RDKit is required to calculate molecular weight from a formula.")
    periodic_table = Chem.GetPeriodicTable()

    def segment_counts(segment: str) -> dict[str, int]:
        segment = re.sub(r"(?:\^\d*[+-]|[+-]\d+)$", "", segment)
        segment = re.sub(r"[+-]$", "", segment)
        leading = re.match(r"^(\d+)(?=[A-Z(])", segment)
        coefficient = int(leading.group(1)) if leading else 1
        if leading:
            segment = segment[leading.end():]
        tokens = re.findall(r"[A-Z][a-z]?|\d+|[()]", segment)
        if not tokens or "".join(tokens) != segment:
            raise ValueError(f"Unsupported molecular formula: {text}")

        def parse_group(index: int, nested: bool = False):
            counts: dict[str, int] = {}
            while index < len(tokens):
                token = tokens[index]
                if token == ")":
                    if not nested:
                        raise ValueError(f"Unmatched ')' in molecular formula: {text}")
                    return counts, index + 1
                if token == "(":
                    child, index = parse_group(index + 1, True)
                    multiplier = 1
                    if index < len(tokens) and tokens[index].isdigit():
                        multiplier = int(tokens[index])
                        index += 1
                    for symbol, count in child.items():
                        counts[symbol] = counts.get(symbol, 0) + count * multiplier
                    continue
                if token.isdigit():
                    raise ValueError(f"Unexpected number in molecular formula: {text}")
                try:
                    atomic_number = periodic_table.GetAtomicNumber(token)
                except Exception as exc:
                    raise ValueError(f"Unknown element '{token}' in molecular formula: {text}") from exc
                if not atomic_number:
                    raise ValueError(f"Unknown element '{token}' in molecular formula: {text}")
                index += 1
                count = 1
                if index < len(tokens) and tokens[index].isdigit():
                    count = int(tokens[index])
                    index += 1
                counts[token] = counts.get(token, 0) + count
            if nested:
                raise ValueError(f"Unmatched '(' in molecular formula: {text}")
            return counts, index

        counts, _ = parse_group(0)
        return {symbol: count * coefficient for symbol, count in counts.items()}

    total_counts: dict[str, int] = {}
    for segment in text.split("."):
        if not segment:
            raise ValueError(f"Unsupported molecular formula: {text}")
        for symbol, count in segment_counts(segment).items():
            total_counts[symbol] = total_counts.get(symbol, 0) + count
    return sum(periodic_table.GetAtomicWeight(symbol) * count for symbol, count in total_counts.items())
