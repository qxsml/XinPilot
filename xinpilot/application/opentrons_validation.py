"""Pure liquid-handling, nozzle, deck and tip-continuity validation.

All inputs are Python data. Errors retain the messages used by the existing
desktop controllers so callers can report them without translating UI state.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
import math

from .opentrons_domain import (
    BLOWOUT_LOCATIONS,
    FLEX_SLOTS,
    MIX_TIMINGS,
    OT2_SLOTS,
    PIPETTE_MAX_UL,
    PIPETTE_TIPRACK_CAPACITIES,
    TIP_COLUMN_OPTIONS,
    TIP_DEPTH_REFERENCES,
    TIP_WELL_OPTIONS,
    _is_eight_channel_pattern,
    _parse_wells,
    _split_eight_channel_patterns,
    _tiprack_capacity,
    pipette_working_capacity,
)


def labware_by_alias(labware_configs, alias):
    """Resolve the same first matching loaded labware as the UI adapter."""
    wanted = str(alias or "").strip()
    return next((item for item in labware_configs if item.get("alias") == wanted), None)


def validate_used_pipette_tipracks(
    labware_configs: List[Dict[str, str]],
    trash_slot: str,
    robot: str,
    pipettes: Dict[str, Dict[str, object]],
    rows: List[Dict[str, object]],
    module_configs: List[Dict[str, object]],
) -> Set[str]:
    row_numbers_by_mount: Dict[str, List[int]] = {}
    for row_number, row in enumerate(rows, start=1):
        mount = str(row.get("pipette_key", "") or "").strip()
        if mount:
            row_numbers_by_mount.setdefault(mount, []).append(row_number)
    used_mounts = set(row_numbers_by_mount)

    missing_slots = []
    for mount in ("left", "right"):
        if mount not in used_mounts:
            continue
        cfg = pipettes[mount]
        pipette = str(cfg["name"])
        tiprack = str(cfg["tiprack"]).strip()
        if not tiprack:
            raise ValueError(
                f"{mount.title()} tiprack load name is required because transfer rows "
                f"{', '.join(str(number) for number in row_numbers_by_mount[mount])} use {pipette}."
            )
        tip_capacity = _tiprack_capacity(tiprack)
        allowed_capacities = PIPETTE_TIPRACK_CAPACITIES.get(pipette)
        if allowed_capacities is not None and (
            tip_capacity is None or tip_capacity not in allowed_capacities
        ):
            allowed_text = (
                ", ".join(f"{capacity} uL" for capacity in allowed_capacities)
                or "a compatible capacity"
            )
            raise ValueError(
                f"{mount.title()} tiprack {tiprack} is not compatible with {pipette}; "
                f"select a {allowed_text} tiprack."
            )
        if not cfg["tiprack_slots"]:
            missing_slots.append(
                f"{mount} {pipette} (transfer rows "
                f"{', '.join(str(number) for number in row_numbers_by_mount[mount])})"
            )
        if cfg["tip_start_column"] not in TIP_COLUMN_OPTIONS:
            raise ValueError(f"{mount.title()} 8-channel start column must be 1-12.")
        if cfg["tip_start_well"] not in TIP_WELL_OPTIONS:
            raise ValueError(f"{mount.title()} single-tip start well must be A1-H12.")
    if missing_slots:
        details = "\n".join(f"- {detail}" for detail in missing_slots)
        raise ValueError(
            "Add at least one compatible tiprack slot for each pipette selected by the transfer plan:\n"
            f"{details}"
        )

    module_labware_aliases = {
        str(config.get("labware_alias", "") or "").strip()
        for config in module_configs
        if str(config.get("labware_alias", "") or "").strip()
    }
    occupied_slots = [
        str(item.get("slot", "") or "").strip()
        for item in labware_configs
        if str(item.get("alias", "") or "").strip() not in module_labware_aliases
    ]
    occupied_slots.extend(str(config.get("slot", "") or "").strip() for config in module_configs)
    for mount in ("left", "right"):
        if mount in used_mounts:
            occupied_slots.extend(str(slot) for slot in pipettes[mount]["tiprack_slots"])
    if robot == "Flex":
        occupied_slots.append(trash_slot.strip())
    valid_slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
    for slot in occupied_slots:
        if slot not in valid_slots:
            raise ValueError(f"Slot {slot} is not valid for {robot}.")
    if len(set(occupied_slots)) != len(occupied_slots):
        raise ValueError("Deck slots must not overlap.")
    return used_mounts


def required_positive_float(value: object, label: str) -> float:
    text = str("" if value is None else value).strip()
    if not text:
        raise ValueError(f"{label} is required.")
    try:
        number = float(text)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return number


def optional_positive_float(value: object, label: str) -> Optional[float]:
    text = str("" if value is None else value).strip()
    if not text:
        return None
    number = float(text)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return number


def optional_nonnegative_float(value: object, label: str) -> float:
    text = str("" if value is None else value).strip().rstrip("%").strip()
    if not text:
        return 0.0
    number = float(text)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return number


def optional_nonnegative_float_or_none(value: object, label: str) -> Optional[float]:
    text = str("" if value is None else value).strip()
    if not text:
        return None
    number = float(text)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return number


def validated_blowout_settings(labware_configs, row, protocol_rows, *, row_number):
    """Require an intentional excess-liquid destination; never infer the stock."""
    location = str(row.get("blowout_location") or "No blowout").strip()
    if location not in BLOWOUT_LOCATIONS:
        raise ValueError(f"Row {row_number} has an invalid blowout location.")
    extra = optional_nonnegative_float(
        row.get("multi_dispense_extra_percent", "0"), "Extra aspirate percentage"
    )
    if (
        row.get("strategy") == "Multi-dispense"
        and extra > 0
        and location not in {"Source", "Liquid waste"}
    ):
        raise ValueError(
            f"Row {row_number} has extra aspirate volume. Choose Source or Liquid waste for blowout; "
            "Destination would overfill the last well and No blowout would retain excess liquid."
        )
    alias = str(row.get("blowout_labware_alias") or "").strip()
    well = str(row.get("blowout_well") or "").strip().upper()
    if location == "Liquid waste":
        config = labware_by_alias(labware_configs, alias)
        if not config or config.get("role") not in {"destination", "both"}:
            raise ValueError(
                f"Row {row_number}: select loaded destination labware for liquid waste."
            )
        wells = _parse_wells(well, config.get("map_style", "96 well"))
        if len(wells) != 1:
            raise ValueError(f"Row {row_number}: select one liquid-waste well.")
        well = wells[0]
        if any(
            alias
            in {
                str(item.get("source_labware_alias") or "source1"),
                str(item.get("dest_labware_alias") or "dest1"),
            }
            for item in protocol_rows
        ):
            raise ValueError(
                f"Row {row_number}: liquid-waste labware must be separate from all source and reaction labware."
            )
    else:
        alias = well = ""
    return {"blowout_location": location, "blowout_labware_alias": alias, "blowout_well": well}


def validated_mix_settings(
    *,
    enabled: bool,
    strategy: str,
    timing: object,
    repetitions: object,
    volume: object,
    aspirate_rate: object,
    dispense_rate: object,
    aspirate_depth: object,
    aspirate_reference: object,
    dispense_depth: object,
    dispense_reference: object,
    post_source_mix_delay: object = "",
    row_label: str = "Pipette mixing",
) -> Dict[str, object]:
    if not enabled:
        return {
            "mix_enabled": False,
            "mix_timing": "Before aspirating",
            "mix_repetitions": 0,
            "mix_volume_ul": None,
            "post_source_mix_delay_seconds": None,
            "mix_aspirate_rate": None,
            "mix_dispense_rate": None,
            "mix_aspirate_depth_mm": None,
            "mix_aspirate_depth_reference": "from bottom",
            "mix_dispense_depth_mm": None,
            "mix_dispense_depth_reference": "from bottom",
        }
    timing_text = str(timing or "").strip()
    if timing_text not in MIX_TIMINGS:
        raise ValueError(
            f"{row_label} timing must be Before aspirating, After dispensing, or Before and after."
        )
    repetitions_text = str(repetitions or "").strip()
    try:
        repetitions_number = int(repetitions_text)
    except (TypeError, ValueError):
        raise ValueError(f"{row_label} repetitions must be a whole number.") from None
    if repetitions_number <= 0:
        raise ValueError(f"{row_label} repetitions must be greater than zero.")
    mix_volume = optional_positive_float(volume, f"{row_label} volume")
    if mix_volume is None:
        raise ValueError(f"{row_label} volume is required.")
    aspirate_reference_text = str(aspirate_reference or "from bottom")
    dispense_reference_text = str(dispense_reference or "from bottom")
    if aspirate_reference_text not in TIP_DEPTH_REFERENCES:
        raise ValueError(f"{row_label} aspirate depth reference must be from bottom or from top.")
    if dispense_reference_text not in TIP_DEPTH_REFERENCES:
        raise ValueError(f"{row_label} dispense depth reference must be from bottom or from top.")
    return {
        "mix_enabled": True,
        "mix_timing": timing_text,
        "mix_repetitions": repetitions_number,
        "mix_volume_ul": mix_volume,
        "post_source_mix_delay_seconds": optional_nonnegative_float_or_none(
            post_source_mix_delay, f"{row_label} delay after source mixing"
        ),
        "mix_aspirate_rate": optional_positive_float(aspirate_rate, f"{row_label} aspirate speed"),
        "mix_dispense_rate": optional_positive_float(dispense_rate, f"{row_label} dispense speed"),
        "mix_aspirate_depth_mm": optional_nonnegative_float_or_none(
            aspirate_depth, f"{row_label} aspirate depth"
        ),
        "mix_aspirate_depth_reference": aspirate_reference_text,
        "mix_dispense_depth_mm": optional_nonnegative_float_or_none(
            dispense_depth, f"{row_label} dispense depth"
        ),
        "mix_dispense_depth_reference": dispense_reference_text,
    }


def validated_delay_air_gap_settings(
    *,
    post_aspirate_delay: object,
    post_dispense_delay: object,
    pre_move_delay: object,
    air_gap_enabled: bool,
    air_gap_volume: object,
    air_gap_height: object,
    air_gap_flow_rate: object,
    row_label: str = "Liquid handling",
) -> Dict[str, object]:
    values: Dict[str, object] = {
        "post_aspirate_delay_seconds": optional_nonnegative_float(
            post_aspirate_delay, f"{row_label} delay after aspiration"
        ),
        "post_dispense_delay_seconds": optional_nonnegative_float(
            post_dispense_delay, f"{row_label} delay after dispensing"
        ),
        "pre_move_delay_seconds": optional_nonnegative_float(
            pre_move_delay, f"{row_label} delay before plate movement"
        ),
        "air_gap_enabled": bool(air_gap_enabled),
        "air_gap_volume_ul": None,
        "air_gap_height_mm": 5.0,
        "air_gap_flow_rate": None,
    }
    if not air_gap_enabled:
        return values
    air_gap_volume_number = optional_positive_float(air_gap_volume, f"{row_label} air-gap volume")
    if air_gap_volume_number is None:
        raise ValueError(f"{row_label} air-gap volume is required when air gap is enabled.")
    height_text = str(air_gap_height or "").strip()
    air_gap_height_number = optional_nonnegative_float_or_none(
        height_text if height_text else "5", f"{row_label} air-gap height"
    )
    values.update(
        {
            "air_gap_volume_ul": air_gap_volume_number,
            "air_gap_height_mm": 5.0 if air_gap_height_number is None else air_gap_height_number,
            "air_gap_flow_rate": optional_positive_float(
                air_gap_flow_rate, f"{row_label} air-gap speed"
            ),
        }
    )
    return values


def select_pipette_for_row(
    pipettes: Dict[str, Dict[str, object]], row_choice: str, volume: float
) -> str:
    if row_choice in ("left", "right"):
        if row_choice not in pipettes:
            raise ValueError(
                f"The {row_choice} pipette is not mounted. Select Auto or an enabled mount for this row."
            )
        pipette = str(pipettes[row_choice]["name"])
        capacity = pipette_working_capacity(pipettes[row_choice])
        if volume > capacity:
            raise ValueError(
                f"{volume:.1f} uL exceeds {row_choice} pipette/tip capacity ({capacity:.0f} uL)."
            )
        return row_choice
    compatible = []
    for mount, cfg in pipettes.items():
        pipette = str(cfg["name"])
        capacity = pipette_working_capacity(cfg)
        if volume <= capacity:
            # Preserve Auto's preference for the smaller physical pipette once
            # both the pipette and its tips can accommodate the operation.
            compatible.append((PIPETTE_MAX_UL[pipette], mount))
    if not compatible:
        options = ", ".join(
            f"{mount} {cfg['name']} ({pipette_working_capacity(cfg):.0f} uL with configured tips)"
            for mount, cfg in pipettes.items()
        )
        raise ValueError(f"{volume:.1f} uL does not fit any mounted pipette: {options}.")
    return sorted(compatible)[0][1]


def minimum_pipette_volume(volume, strategy, extra_percent, air_gap_volume, mix_volume):
    """Peak volume for one dispense, before multi-dispense batching."""
    liquid = volume * (1.0 + extra_percent / 100.0) if strategy == "Multi-dispense" else volume
    return max(liquid + air_gap_volume, mix_volume)


def nozzle_layout_for_row(
    robot: str,
    pipette_name: str,
    dest_wells: List[str],
    dest_style: str,
    *,
    force_all_channels: bool = False,
    eight_channel_mode: str = "Auto from wells",
) -> str:
    if force_all_channels:
        is_eight_channel = (
            pipette_name.startswith("flex_8channel")
            if robot == "Flex"
            else pipette_name.endswith("_multi_gen2")
        )
        if not is_eight_channel:
            raise ValueError(
                "An 8-Channel Column Transfer row requires a mounted 8-channel pipette."
            )
        if not _split_eight_channel_patterns(dest_wells, dest_style):
            raise ValueError(
                "An 8-Channel Column Transfer destination must contain one or more complete 96-well columns "
                "or alternating 384-well column patterns."
            )
        return "all"
    if robot == "OT-2" and pipette_name.endswith("_multi_gen2"):
        if not _is_eight_channel_pattern(dest_wells, dest_style):
            raise ValueError(
                "OT-2 8-channel transfers require one full 96-well column or one alternating 384-well column pattern."
            )
        return "all"
    if robot != "Flex" or not pipette_name.startswith("flex_8channel"):
        return "default"
    mode = eight_channel_mode
    if mode == "Force single tip":
        return "single"
    if mode == "Force all channels":
        if not _is_eight_channel_pattern(dest_wells, dest_style):
            raise ValueError(
                "Force all channels requires one full 96-well column or one alternating 384-well column pattern."
            )
        return "all"
    if _is_eight_channel_pattern(dest_wells, dest_style):
        return "all"
    return "single"


def current_labware_slot(
    alias: str,
    labware_locations: Dict[str, Tuple[str, str]],
    module_configs_by_key: Dict[str, Dict[str, object]],
) -> str:
    kind, location = labware_locations.get(alias, ("deck", ""))
    if kind == "module":
        module_config = module_configs_by_key.get(location, {})
        return str(module_config.get("slot", "") or "").strip()
    return str(location or "").strip()


def single_nozzle_start_for_row(
    *,
    row_number: int,
    source_alias: str,
    dest_alias: str,
    pipette_key: str,
    pipettes: Dict[str, Dict[str, object]],
    labware_locations: Dict[str, Tuple[str, str]],
    module_configs_by_key: Dict[str, Dict[str, object]],
    waste_alias: str = "",
) -> str:
    accessed_locations: List[Tuple[str, str]] = []
    source_slot = current_labware_slot(source_alias, labware_locations, module_configs_by_key)
    dest_slot = current_labware_slot(dest_alias, labware_locations, module_configs_by_key)
    if source_slot:
        accessed_locations.append((f"source {source_alias}", source_slot))
    if dest_slot:
        accessed_locations.append((f"destination {dest_alias}", dest_slot))
    if waste_alias:
        waste_slot = current_labware_slot(waste_alias, labware_locations, module_configs_by_key)
        if waste_slot:
            accessed_locations.append((f"liquid waste {waste_alias}", waste_slot))
    for slot in pipettes[pipette_key].get("tiprack_slots", []) or []:
        slot_text = str(slot or "").strip()
        if slot_text:
            accessed_locations.append((f"{pipette_key} tip box", slot_text))

    deck_rows = {
        slot[0].upper() for _label, slot in accessed_locations if slot and slot[0].upper() in "ABCD"
    }
    if "A" in deck_rows and "D" in deck_rows:
        location_text = ", ".join(f"{label} at {slot}" for label, slot in accessed_locations)
        raise ValueError(
            f"Row {row_number} uses Flex 8-channel single-tip mode, but one physical nozzle cannot safely "
            f"reach both deck rows A and D ({location_text}). Move the conflicting labware or tip box to "
            "deck row B/C, or use a Flex 1-channel pipette."
        )
    if "A" in deck_rows:
        return "A1"
    return "H1"


def validate_partial_nozzle_clearance(
    *, row_number: int, nozzle: str, accessed_slots: Dict[str, str],
    occupied_slots: Dict[str, str],
) -> None:
    """Require an empty overhang slot for Flex eight-channel single-tip use.

    H1 leaves the other nozzles behind the active nozzle (towards deck A);
    A1 leaves them in front (towards D). This deliberately conservative check
    does not claim to model individual well heights or custom labware geometry.
    Full-channel and one-channel transfers do not use this restriction.
    """
    direction = -1 if nozzle == "H1" else 1
    for label, slot in accessed_slots.items():
        if slot not in FLEX_SLOTS:
            continue
        neighbor_row = "ABCD".index(slot[0]) + direction
        if not 0 <= neighbor_row < 4:
            continue  # Edge reach is checked by single_nozzle_start_for_row.
        neighbor = "ABCD"[neighbor_row] + slot[1:]
        if neighbor in occupied_slots:
            raise ValueError(
                f"Row {row_number}: Flex single-nozzle {nozzle} needs clearance beside "
                f"{label} at {slot}, but slot {neighbor} contains {occupied_slots[neighbor]}. "
                "XinPilot conservatively requires the overhang slot to be empty. "
                "Rearrange the deck to clear that slot, or use a 1-channel pipette "
                "or a compatible full 8-channel transfer. Simulate the revised protocol before use."
            )


def validate_sequence_tip_transitions(rows: List[Dict[str, object]]) -> None:
    for index, row in enumerate(rows[:-1]):
        sequence_id = str(row.get("sequence_id", "") or "").strip()
        if not sequence_id or row.get("tip_policy") != "Keep tip mounted":
            continue
        next_row = rows[index + 1]
        if str(next_row.get("sequence_id", "") or "").strip() != sequence_id:
            continue
        current_configuration = (
            row.get("pipette_key"),
            row.get("pipette_name"),
            row.get("nozzle_layout"),
            row.get("nozzle_start", ""),
        )
        next_configuration = (
            next_row.get("pipette_key"),
            next_row.get("pipette_name"),
            next_row.get("nozzle_layout"),
            next_row.get("nozzle_start", ""),
        )
        if current_configuration != next_configuration:
            name = str(row.get("sequence_name", "") or "Sequence")
            sample = row.get("sequence_sample_index", "?")
            child = (
                row.get("sequence_group_name") or f"Group {row.get('sequence_child_index', '?')}"
            )
            next_sample = next_row.get("sequence_sample_index", "?")
            next_child = (
                next_row.get("sequence_group_name")
                or f"Group {next_row.get('sequence_child_index', '?')}"
            )
            raise ValueError(
                f"Sequence '{name}' keeps a tip after sample {sample}, {child}, but sample "
                f"{next_sample}, {next_child} resolves to a different physical pipette or nozzle layout. "
                "Change the earlier child to Bin/Return tip, or choose compatible pipette settings."
            )
