"""Headless Opentrons transfer records, labware geometry and robot limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import re

from .tecan_domain import WELL_LABEL_RE, index_to_label

FLEX_SLOTS = ("A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3", "D1", "D2", "D3")

OT2_SLOTS = tuple(str(i) for i in range(1, 12))

LABWARE_MAP_PROFILES = {
    "384 well": (16, 24, frozenset()),
    "96 well": (8, 12, frozenset()),
    "48 well": (6, 8, frozenset()),
    "40 position mixed rack": (
        8,
        13,
        frozenset(
            f"{row}{column}"
            for row in "ABCDEFGH"
            for column in range(1, 14)
            if not (column in {1, 13} or (row in "ABCD" and column in {3, 4, 5, 6, 7, 8}))
        ),
    ),
    "24 well": (4, 6, frozenset()),
    "15 tube rack": (3, 5, frozenset()),
    "12 well plate": (3, 4, frozenset()),
    "12 well reservoir": (1, 12, frozenset()),
    "10 tube rack": (3, 4, frozenset({"C3", "C4"})),
    "8 well reservoir": (8, 1, frozenset()),
    "6 well": (2, 3, frozenset()),
    "4 well reservoir": (1, 4, frozenset()),
    "2 position (2 x 1)": (2, 1, frozenset()),
    "2 position (1 x 2)": (1, 2, frozenset()),
    "1 well": (1, 1, frozenset()),
}

PLATE_STYLES = tuple(LABWARE_MAP_PROFILES)

MIX_TIMINGS = ("Before aspirating", "After dispensing", "Before and after")

TIP_POLICIES = ("Bin tip after row", "Return tip to box", "Keep tip mounted")

BLOWOUT_LOCATIONS = ("No blowout", "Destination", "Source", "Liquid waste")

TIP_DEPTH_REFERENCES = ("from bottom", "from top")

TIP_COLUMN_OPTIONS = tuple(str(i) for i in range(1, 13))

TIP_WELL_OPTIONS = tuple(f"{row}{col}" for col in range(1, 13) for row in "ABCDEFGH")

PIPETTE_MAX_UL = {
    "flex_1channel_50": 50.0,
    "flex_1channel_1000": 1000.0,
    "flex_8channel_50": 50.0,
    "flex_8channel_1000": 1000.0,
    "flex_96channel_200": 200.0,
    "flex_96channel_1000": 1000.0,
    "p20_single_gen2": 20.0,
    "p300_single_gen2": 300.0,
    "p1000_single_gen2": 1000.0,
    "p20_multi_gen2": 20.0,
    "p300_multi_gen2": 300.0,
}

PIPETTE_MIN_UL = {
    "flex_1channel_50": 1.0,
    "flex_1channel_1000": 5.0,
    "flex_8channel_50": 1.0,
    "flex_8channel_1000": 5.0,
    "flex_96channel_200": 5.0,
    "flex_96channel_1000": 5.0,
    "p20_single_gen2": 1.0,
    "p300_single_gen2": 20.0,
    "p1000_single_gen2": 100.0,
    "p20_multi_gen2": 1.0,
    "p300_multi_gen2": 20.0,
}

PIPETTE_TIPRACK_CAPACITIES = {
    "flex_1channel_50": (50,),
    "flex_8channel_50": (50,),
    "flex_1channel_1000": (50, 200, 1000),
    "flex_8channel_1000": (50, 200, 1000),
}


def _tiprack_capacity(load_name: str) -> int | None:
    match = re.search(r"_(20|50|200|300|1000)ul$", str(load_name or "").lower())
    return int(match.group(1)) if match else None


def pipette_working_capacity(config: Dict[str, object]) -> float:
    """Liquid and air share the smaller of the pipette and attached tip volumes."""
    maximum = PIPETTE_MAX_UL[str(config["name"])]
    tip_capacity = _tiprack_capacity(str(config.get("tiprack", "")))
    return min(maximum, tip_capacity) if tip_capacity is not None else maximum


def _style_dims(style: str) -> Tuple[int, int]:
    profile = LABWARE_MAP_PROFILES.get(str(style or ""))
    if profile is None:
        return 8, 12
    return profile[0], profile[1]


def _style_disabled_labels(style: str) -> Set[str]:
    profile = LABWARE_MAP_PROFILES.get(str(style or ""))
    return set(profile[2]) if profile else set()


def _style_well_labels(style: str) -> List[str]:
    rows, cols = _style_dims(style)
    disabled = _style_disabled_labels(style)
    return [
        index_to_label(index, rows, cols, "row-major")
        for index in range(1, rows * cols + 1)
        if index_to_label(index, rows, cols, "row-major") not in disabled
    ]


def _parse_wells(expr: str, style: str) -> List[str]:
    text = str(expr or "").strip()
    if not text:
        return []
    valid_labels = _style_well_labels(style)
    valid_set = set(valid_labels)
    parsed: List[str] = []
    for part in [value.strip() for value in text.split(",") if value.strip()]:
        normalized = part.upper()
        if WELL_LABEL_RE.match(normalized):
            if normalized not in valid_set:
                raise ValueError(f"Well {normalized} is not available in the {style} map.")
            parsed.append(normalized)
            continue
        if "-" in part and part[0].isdigit():
            range_part, _, step_part = part.partition(":")
            step = int(step_part) if step_part else 1
            if step <= 0:
                raise ValueError(f"Invalid step in '{part}'")
            start_text, end_text = range_part.split("-", 1)
            start, end = int(start_text), int(end_text)
            parsed.extend(
                valid_labels[index - 1]
                for index in range(
                    start, end + (1 if start <= end else -1), step if start <= end else -step
                )
                if 1 <= index <= len(valid_labels)
            )
            if not 1 <= start <= len(valid_labels) or not 1 <= end <= len(valid_labels):
                raise ValueError(f"Well index range in '{part}' is outside 1..{len(valid_labels)}")
            continue
        index = int(part)
        if not 1 <= index <= len(valid_labels):
            raise ValueError(f"Well index {index} out of range 1..{len(valid_labels)}")
        parsed.append(valid_labels[index - 1])

    result: List[str] = []
    seen = set()
    for label in parsed:
        if label not in seen:
            result.append(label)
            seen.add(label)
    return result


def _py_string(value: object) -> str:
    return repr(str(value or ""))


def _well_parts(label: object) -> Tuple[str, int]:
    text = str(label or "").strip().upper()
    m = re.match(r"^([A-Z]+)\s*0*([1-9][0-9]*)$", text)
    if not m:
        raise ValueError(f"Invalid well label: {label}")
    return m.group(1), int(m.group(2))


def _row_number(row_label: str) -> int:
    number = 0
    for ch in row_label:
        number = number * 26 + (ord(ch) - ord("A") + 1)
    return number


def _is_single_96_column(wells: List[str]) -> bool:
    if len(wells) != 8:
        return False
    try:
        parts = [_well_parts(well) for well in wells]
    except ValueError:
        return False
    cols = {col for _row, col in parts}
    rows = sorted(_row_number(row) for row, _col in parts)
    return len(cols) == 1 and rows == list(range(1, 9))


def _eight_channel_patterns(style: str) -> List[List[str]]:
    if style == "96 well":
        return [[f"{row}{column}" for row in "ABCDEFGH"] for column in range(1, 13)]
    if style == "384 well":
        patterns: List[List[str]] = []
        for column in range(1, 25):
            patterns.append([f"{row}{column}" for row in "ACEGIKMO"])
            patterns.append([f"{row}{column}" for row in "BDFHJLNP"])
        return patterns
    return []


def _is_eight_channel_pattern(wells: List[str], style: str) -> bool:
    wanted = [str(well or "").strip().upper() for well in wells]
    return any(wanted == pattern for pattern in _eight_channel_patterns(style))


def _split_eight_channel_patterns(wells: List[str], style: str) -> List[List[str]]:
    """Return ordered 8-well destination patterns, or an empty list for invalid geometry."""
    wanted = [str(well or "").strip().upper() for well in wells]
    if not wanted or len(wanted) % 8:
        return []
    groups = [wanted[index : index + 8] for index in range(0, len(wanted), 8)]
    if not all(_is_eight_channel_pattern(group, style) for group in groups):
        return []
    return groups


def all_channel_source_wells(anchor: str, style: str, load_name: str) -> List[str]:
    """Physical wells reached by an eight-nozzle aspiration at the anchor.

    Tall reservoir troughs share one liquid source. The NEST eight-trough map
    instead has eight separate wells at 9 mm spacing, like a plate column.
    """
    anchor = str(anchor).strip().upper()
    is_reservoir = "reservoir" in str(load_name).lower()
    if is_reservoir and style in {"1 well", "4 well reservoir", "12 well reservoir"}:
        return _parse_wells(anchor, style)
    patterns = _eight_channel_patterns(style)
    if is_reservoir and style == "8 well reservoir":
        patterns = [[f"{letter}1" for letter in "ABCDEFGH"]]
    for pattern in patterns:
        if anchor == pattern[0]:
            return pattern
    raise ValueError(
        "An all-channel source must be a shared reservoir trough, an A-row well "
        "of a 96-well plate, an A/B-row well of a 384-well plate, or A1 of an 8-well reservoir."
    )


@dataclass
class OpentronsTransferRow:
    source_well: str
    dest_wells: str
    volume_ul: float
    strategy: str
    step_name: str = ""
    pipette_key: str = "Auto"
    chemical: str = ""
    reaction_umol: str = ""
    is_building_block: bool = False
    source_labware_alias: str = "source1"
    dest_labware_alias: str = "dest1"
    tip_policy: str = "Bin tip after row"
    blowout_location: str = "No blowout"
    blowout_labware_alias: str = ""
    blowout_well: str = ""
    aspirate_rate: str = ""
    dispense_rate: str = ""
    aspirate_depth_mm: str = ""
    aspirate_depth_reference: str = "from bottom"
    dispense_depth_mm: str = ""
    dispense_depth_reference: str = "from top"
    multi_dispense_extra_percent: str = "0"
    tip_touch: bool = False
    pre_wet_tip: bool = False
    mix_enabled: bool = False
    mix_timing: str = "Before aspirating"
    mix_repetitions: str = "3"
    mix_volume_ul: str = ""
    post_source_mix_delay_seconds: str = ""
    mix_aspirate_rate: str = ""
    mix_dispense_rate: str = ""
    mix_aspirate_depth_mm: str = ""
    mix_aspirate_depth_reference: str = "from bottom"
    mix_dispense_depth_mm: str = ""
    mix_dispense_depth_reference: str = "from bottom"
    delay_air_gap_enabled: bool = False
    post_aspirate_delay_seconds: str = ""
    post_dispense_delay_seconds: str = ""
    pre_move_delay_seconds: str = ""
    air_gap_enabled: bool = False
    air_gap_volume_ul: str = ""
    air_gap_height_mm: str = "5"
    air_gap_flow_rate: str = ""
    move_plate: bool = False
    move_labware_alias: str = ""
    move_to_slot: str = ""
    move_use_gripper: bool = False
    note: str = ""
    batch_transfer_kind: str = ""
    batch_source_wells: str = ""


from .values import coerce_bool


def module_key_from_move_target(target: str) -> Optional[str]:
    if target.startswith("Temperature Module GEN2 @ "):
        return "temperature"
    if target.startswith("Heater-Shaker Module @ "):
        return "heater_shaker"
    return None


def normalize_tip_policy(value: object) -> str:
    text = str(value or "").strip()
    legacy = {
        "New tip each row": "Bin tip after row",
        "Reuse tip for row": "Bin tip after row",
    }
    return legacy.get(text, text if text in TIP_POLICIES else "Bin tip after row")


def delay_air_gap_feature_enabled(data: Dict[str, object]) -> bool:
    if "delay_air_gap_enabled" in data:
        return bool(data.get("delay_air_gap_enabled"))
    if bool(data.get("air_gap_enabled", False)):
        return True
    for key in (
        "post_aspirate_delay_seconds",
        "post_dispense_delay_seconds",
        "pre_move_delay_seconds",
    ):
        value = str(data.get(key, "") or "").strip()
        if value and value not in {"0", "0.0"}:
            return True
    return False


def batch_chemical_map(row: Dict[str, object]) -> Dict[str, str]:
    return {
        str(key).strip().upper(): str(value or "").strip()
        for key, value in dict(row.get("batch_source_chemicals", {}) or {}).items()
        if str(key).strip()
    }


def batch_building_block_map(row: Dict[str, object]) -> Dict[str, bool]:
    return {
        str(key).strip().upper(): coerce_bool(value)
        for key, value in dict(row.get("batch_source_building_blocks", {}) or {}).items()
        if str(key).strip()
    }
