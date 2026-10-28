"""Compile a validated Opentrons configuration and expanded transfer plan.

``OpentronsCompileRequest`` is the explicit controller/service boundary: no Tk
variables, file dialogs, filesystem access or global application state cross it.
The compiler validates physical operations before rendering the same ordered
Opentrons commands as the legacy controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .opentrons_domain import (
    FLEX_SLOTS,
    OT2_SLOTS,
    PIPETTE_MAX_UL,
    PIPETTE_MIN_UL,
    all_channel_source_wells,
    pipette_working_capacity,
    TIP_DEPTH_REFERENCES,
    TIP_POLICIES,
    _is_eight_channel_pattern,
    _parse_wells,
    _py_string,
    _split_eight_channel_patterns,
    batch_building_block_map as row_building_block_map,
    batch_chemical_map as row_chemical_map,
    coerce_bool,
    delay_air_gap_feature_enabled as is_delay_air_gap_enabled,
    module_key_from_move_target,
    normalize_tip_policy,
)
from .opentrons_validation import (
    labware_by_alias,
    current_labware_slot,
    nozzle_layout_for_row,
    optional_nonnegative_float,
    optional_nonnegative_float_or_none,
    optional_positive_float,
    select_pipette_for_row,
    minimum_pipette_volume,
    single_nozzle_start_for_row,
    validate_partial_nozzle_clearance,
    validate_sequence_tip_transitions,
    validate_used_pipette_tipracks,
    validated_blowout_settings,
    validated_delay_air_gap_settings,
    validated_mix_settings,
)


@dataclass(frozen=True)
class OpentronsCompileRequest:
    """Plain-data snapshot collected and validated by the controller.

    ``rows`` must already be expanded into execution order. ``deck_occupants``
    includes every mounted tiprack, including mounts unused by the final plan,
    so movement collision checks preserve the configured physical deck.
    Compilation does not mutate any input collections.
    """

    robot: str
    pipettes: Dict[str, Dict[str, object]]
    labware_configs: List[Dict[str, str]]
    module_configs: List[Dict[str, object]]
    rows: List[Dict[str, object]]
    deck_occupants: Dict[str, str]
    api_level: str
    protocol_name: str = "Opentrons_Protocol"
    source_style: str = "96 well"
    dest_style: str = "96 well"
    eight_channel_mode: str = "Auto from wells"
    tip_policy: str = "Bin tip after row"
    flex_gripper: bool = True
    trash_slot: str = "A3"


def compile_protocol(request: OpentronsCompileRequest) -> str:
    robot = request.robot
    pipettes = request.pipettes
    module_configs = request.module_configs
    rows = []
    uses_flex_8_channel = False
    api_parts = tuple(int(part) for part in request.api_level.strip().split("."))
    module_configs_by_key = {str(config["key"]): config for config in module_configs}
    starting_module_by_alias = {
        str(config["labware_alias"]): str(config["key"])
        for config in module_configs
        if config.get("labware_alias")
    }
    labware_locations: Dict[str, Tuple[str, str]] = {}
    for item in request.labware_configs:
        alias = str(item.get("alias", "") or "").strip()
        if not alias:
            continue
        if alias in starting_module_by_alias:
            labware_locations[alias] = ("module", starting_module_by_alias[alias])
        else:
            labware_locations[alias] = ("deck", str(item.get("slot", "") or "").strip())
    deck_occupants = dict(request.deck_occupants)
    module_occupants: Dict[str, Optional[str]] = {
        str(config["key"]): (str(config["labware_alias"]) if config.get("labware_alias") else None)
        for config in module_configs
    }
    held_tip_configuration_by_mount: Dict[str, Tuple[str, str]] = {}
    source_chemicals: Dict[Tuple[str, str], Set[str]] = {}
    partial_clearance_checks = []
    protocol_rows = request.rows
    for row in protocol_rows:
        blowout_settings = validated_blowout_settings(
            request.labware_configs, row, protocol_rows, row_number=len(rows) + 1
        )
        source_labware = labware_by_alias(
            request.labware_configs, row.get("source_labware_alias", "source1")
        )
        dest_labware = labware_by_alias(
            request.labware_configs, row.get("dest_labware_alias", "dest1")
        )
        if not source_labware:
            raise ValueError(f"Row {len(rows) + 1} has an invalid source labware alias.")
        if not dest_labware:
            raise ValueError(f"Row {len(rows) + 1} has an invalid destination labware alias.")
        if source_labware.get("role") not in {"source", "both"}:
            raise ValueError(
                f"Row {len(rows) + 1} uses {source_labware.get('alias', '')} as a source, "
                "but its labware role is destination-only."
            )
        if dest_labware.get("role") not in {"destination", "both"}:
            raise ValueError(
                f"Row {len(rows) + 1} uses {dest_labware.get('alias', '')} as a destination, "
                "but its labware role is source-only."
            )
        source_wells = _parse_wells(
            str(row.get("source_well", "")), source_labware.get("map_style", request.source_style)
        )
        if len(source_wells) != 1:
            raise ValueError(f"Row {len(rows) + 1} source well must be a single well.")
        dest_wells = _parse_wells(
            str(row.get("dest_wells", "")), dest_labware.get("map_style", request.dest_style)
        )
        is_batch_8_channel = str(row.get("batch_transfer_kind", "") or "") == "8-channel"
        batch_destination_groups: List[List[str]] = []
        if is_batch_8_channel:
            batch_source_wells = _parse_wells(
                str(row.get("batch_source_wells", "")),
                source_labware.get("map_style", request.source_style),
            )
            if (
                not _is_eight_channel_pattern(
                    batch_source_wells,
                    str(source_labware.get("map_style", request.source_style)),
                )
                or source_wells[0] != batch_source_wells[0]
            ):
                raise ValueError(
                    f"Row {len(rows) + 1} no longer has a valid 8-channel source pattern. Recreate it with Batch Transfer."
                )
            batch_destination_groups = _split_eight_channel_patterns(
                dest_wells,
                str(dest_labware.get("map_style", request.dest_style)),
            )
            if not batch_destination_groups:
                raise ValueError(
                    f"Row {len(rows) + 1} no longer contains complete 8-channel destination patterns. "
                    "Recreate it with Batch Transfer."
                )
        chemical = str(row.get("chemical", "") or "").strip()
        batch_chemical_map = row_chemical_map(row) if is_batch_8_channel else {}
        batch_building_block_map = row_building_block_map(row) if is_batch_8_channel else {}
        volume = float(row.get("volume_ul", 0.0))
        row_strategy = str(row.get("strategy", "Single transfer") or "Single transfer")
        row_extra_percent = optional_nonnegative_float(
            row.get("multi_dispense_extra_percent", "0"),
            f"Extra aspirate volume percentage for row {len(rows) + 1}",
        )
        mix_settings = validated_mix_settings(
            enabled=bool(row.get("mix_enabled", False)),
            strategy=row_strategy,
            timing=row.get("mix_timing", "Before aspirating"),
            repetitions=row.get("mix_repetitions", "3"),
            volume=row.get("mix_volume_ul", ""),
            post_source_mix_delay=row.get("post_source_mix_delay_seconds", ""),
            aspirate_rate=row.get("mix_aspirate_rate", ""),
            dispense_rate=row.get("mix_dispense_rate", ""),
            aspirate_depth=row.get("mix_aspirate_depth_mm", ""),
            aspirate_reference=row.get("mix_aspirate_depth_reference", "from bottom"),
            dispense_depth=row.get("mix_dispense_depth_mm", ""),
            dispense_reference=row.get("mix_dispense_depth_reference", "from bottom"),
            row_label=f"Pipette mixing for row {len(rows) + 1}",
        )
        delay_air_gap_feature_enabled = is_delay_air_gap_enabled(row)
        delay_air_gap_settings = validated_delay_air_gap_settings(
            post_aspirate_delay=(
                row.get("post_aspirate_delay_seconds", "") if delay_air_gap_feature_enabled else ""
            ),
            post_dispense_delay=(
                row.get("post_dispense_delay_seconds", "") if delay_air_gap_feature_enabled else ""
            ),
            pre_move_delay=(
                row.get("pre_move_delay_seconds", "") if delay_air_gap_feature_enabled else ""
            ),
            air_gap_enabled=(
                delay_air_gap_feature_enabled and bool(row.get("air_gap_enabled", False))
            ),
            air_gap_volume=row.get("air_gap_volume_ul", ""),
            air_gap_height=row.get("air_gap_height_mm", "5"),
            air_gap_flow_rate=row.get("air_gap_flow_rate", ""),
            row_label=f"Liquid handling for row {len(rows) + 1}",
        )
        air_gap_volume = float(delay_air_gap_settings["air_gap_volume_ul"] or 0.0)
        required_pipette_volume = minimum_pipette_volume(
            volume, row_strategy, row_extra_percent, air_gap_volume,
            float(mix_settings["mix_volume_ul"] or 0.0),
        )
        pipette_key = select_pipette_for_row(
            pipettes,
            str(row.get("pipette_key", "Auto")),
            required_pipette_volume,
        )
        pipette_name = str(pipettes[pipette_key]["name"])
        nozzle_layout = nozzle_layout_for_row(
            robot,
            pipette_name,
            dest_wells,
            dest_labware.get("map_style", request.dest_style),
            force_all_channels=is_batch_8_channel,
            eight_channel_mode=request.eight_channel_mode,
        )
        is_flex_8_channel = robot == "Flex" and pipette_name.startswith("flex_8channel")
        uses_flex_8_channel = uses_flex_8_channel or is_flex_8_channel
        nozzle_start = ""
        if is_flex_8_channel and nozzle_layout == "single":
            nozzle_start = single_nozzle_start_for_row(
                row_number=len(rows) + 1,
                source_alias=str(source_labware.get("alias", "") or ""),
                dest_alias=str(dest_labware.get("alias", "") or ""),
                pipette_key=pipette_key,
                pipettes=pipettes,
                labware_locations=labware_locations,
                module_configs_by_key=module_configs_by_key,
                waste_alias=blowout_settings["blowout_labware_alias"],
            )
            # Capture locations before this row's optional plate move. Validate
            # once all used mounts are known, so unused tip racks are excluded.
            occupied = {
                current_labware_slot(alias, labware_locations, module_configs_by_key): alias
                for alias in labware_locations
            }
            occupied.update({str(c["slot"]): str(c["key"]) for c in module_configs})
            occupied[request.trash_slot] = "trash"
            accessed = {
                f"source {source_labware['alias']}": current_labware_slot(
                    source_labware["alias"], labware_locations, module_configs_by_key),
                f"destination {dest_labware['alias']}": current_labware_slot(
                    dest_labware["alias"], labware_locations, module_configs_by_key),
            }
            waste_alias = blowout_settings["blowout_labware_alias"]
            if waste_alias:
                accessed[f"liquid waste {waste_alias}"] = current_labware_slot(
                    waste_alias, labware_locations, module_configs_by_key)
            for index, slot in enumerate(pipettes[pipette_key].get("tiprack_slots", []), 1):
                accessed[f"{pipette_key} tip rack {index}"] = str(slot)
            partial_clearance_checks.append((len(rows) + 1, nozzle_start, accessed, occupied))
        if is_flex_8_channel and nozzle_layout == "single" and api_parts < (2, 20):
            raise ValueError(
                "Flex 8-channel single-tip pickup requires Opentrons API level 2.20 or newer."
            )
        if nozzle_layout == "all":
            if blowout_settings["blowout_location"] == "Liquid waste":
                waste_config = labware_by_alias(
                    request.labware_configs, blowout_settings["blowout_labware_alias"]
                )
                if "reservoir" not in str(waste_config.get("load_name", "")).lower():
                    raise ValueError(
                        f"Row {len(rows) + 1}: all-channel liquid-waste blowout requires a reservoir "
                        "that accommodates all active nozzles."
                    )
            try:
                physical_source_wells = all_channel_source_wells(
                    source_wells[0], str(source_labware.get("map_style", request.source_style)),
                    str(source_labware.get("load_name", "")),
                )
            except ValueError as exc:
                raise ValueError(
                    f"Row {len(rows) + 1} uses all 8 channels. {exc}"
                ) from exc
        else:
            physical_source_wells = source_wells
        for physical_source_well in physical_source_wells:
            physical_chemical = batch_chemical_map.get(physical_source_well, chemical)
            chemical_key = physical_chemical.casefold()
            source_location = (str(source_labware.get("alias", "")), physical_source_well)
            used_chemicals = source_chemicals.setdefault(source_location, set())
            if used_chemicals and (not chemical_key or used_chemicals != {chemical_key}):
                raise ValueError(
                    f"Source well {source_location[0]}:{source_location[1]} is assigned to multiple Chemical IDs. "
                    "Use one Chemical ID per physical source well."
                )
            used_chemicals.add(chemical_key)
        max_ul = pipette_working_capacity(pipettes[pipette_key])
        row_tip_policy = normalize_tip_policy(row.get("tip_policy", request.tip_policy))
        if row_tip_policy not in TIP_POLICIES:
            raise ValueError(
                f"Tip policy for row {len(rows) + 1} must be Bin tip after row, Return tip to box, or Keep tip mounted."
            )
        nozzle_configuration = (nozzle_layout, nozzle_start if nozzle_layout == "single" else "")
        held_configuration = held_tip_configuration_by_mount.get(pipette_key)
        if held_configuration is not None and held_configuration != nozzle_configuration:
            previous_layout, previous_start = held_configuration
            previous_label = (
                f"{previous_layout}/{previous_start}" if previous_start else previous_layout
            )
            current_label = f"{nozzle_layout}/{nozzle_start}" if nozzle_start else nozzle_layout
            raise ValueError(
                f"Row {len(rows) + 1} needs nozzle configuration {current_label}, but the {pipette_key} pipette "
                f"still holds a tip from {previous_label}. Change the earlier row's tip policy so it bins or "
                "returns the tip before the nozzle configuration changes."
            )
        if row_tip_policy == "Keep tip mounted":
            held_tip_configuration_by_mount[pipette_key] = nozzle_configuration
        else:
            held_tip_configuration_by_mount.pop(pipette_key, None)
        row_aspirate_rate = optional_positive_float(
            row.get("aspirate_rate", ""), f"Aspirate rate for row {len(rows) + 1}"
        )
        row_dispense_rate = optional_positive_float(
            row.get("dispense_rate", ""), f"Dispense rate for row {len(rows) + 1}"
        )
        row_aspirate_depth_mm = optional_nonnegative_float_or_none(
            row.get("aspirate_depth_mm", ""), f"Aspirate depth for row {len(rows) + 1}"
        )
        row_dispense_depth_mm = optional_nonnegative_float_or_none(
            row.get("dispense_depth_mm", ""), f"Dispense depth for row {len(rows) + 1}"
        )
        row_aspirate_depth_reference = str(
            row.get("aspirate_depth_reference", "from bottom") or "from bottom"
        )
        row_dispense_depth_reference = str(
            row.get("dispense_depth_reference", "from top") or "from top"
        )
        if row_aspirate_depth_reference not in TIP_DEPTH_REFERENCES:
            raise ValueError(
                f"Aspirate from for row {len(rows) + 1} must be from bottom or from top."
            )
        if row_dispense_depth_reference not in TIP_DEPTH_REFERENCES:
            raise ValueError(
                f"Dispense from for row {len(rows) + 1} must be from bottom or from top."
            )
        move_plate = bool(row.get("move_plate", False))
        move_labware_alias = str(row.get("move_labware_alias", "") or "").strip()
        move_to_slot = str(row.get("move_to_slot", "") or "").strip()
        move_target_kind = "deck"
        move_target_key = ""
        move_from_module_key = ""
        if move_plate:
            slots = FLEX_SLOTS if robot == "Flex" else OT2_SLOTS
            if move_labware_alias not in {
                item.get("alias", "") for item in request.labware_configs
            }:
                raise ValueError(f"Move plate labware alias for row {len(rows) + 1} is invalid.")
            current_kind, current_location = labware_locations.get(move_labware_alias, ("deck", ""))
            if current_kind == "module":
                move_from_module_key = current_location
                source_module = module_configs_by_key.get(current_location)
                if source_module and not source_module.get("adapter"):
                    raise ValueError(
                        f"Row {len(rows) + 1} moves {move_labware_alias} off {source_module['type']}. "
                        "Select a module adapter so Opentrons has a movable labware location."
                    )
            target_module_key = module_key_from_move_target(move_to_slot)
            if target_module_key:
                target_module = module_configs_by_key.get(target_module_key)
                if target_module is None:
                    raise ValueError(
                        f"Move plate module target for row {len(rows) + 1} is no longer configured. Select it again."
                    )
                if not target_module.get("adapter"):
                    raise ValueError(
                        f"Row {len(rows) + 1} moves labware onto {target_module['type']}. "
                        "Select an adapter for that module first."
                    )
                move_target_kind = "module"
                move_target_key = target_module_key
                move_to_slot = str(target_module["slot"])
                target_occupant = module_occupants.get(target_module_key)
                if current_kind == "module" and current_location == target_module_key:
                    move_plate = False
                elif target_occupant and target_occupant != move_labware_alias:
                    raise ValueError(
                        f"Move plate target {target_module['type']} for row {len(rows) + 1} already holds {target_occupant}."
                    )
                else:
                    if (
                        current_kind == "deck"
                        and deck_occupants.get(current_location) == move_labware_alias
                    ):
                        deck_occupants.pop(current_location, None)
                    elif (
                        current_kind == "module"
                        and module_occupants.get(current_location) == move_labware_alias
                    ):
                        module_occupants[current_location] = None
                    module_occupants[target_module_key] = move_labware_alias
                    labware_locations[move_labware_alias] = ("module", target_module_key)
            else:
                if move_to_slot not in slots:
                    raise ValueError(
                        f"Move plate target location for row {len(rows) + 1} is invalid."
                    )
                occupant = deck_occupants.get(move_to_slot)
                if current_kind == "deck" and move_to_slot == current_location:
                    move_plate = False
                elif occupant and occupant != move_labware_alias:
                    raise ValueError(
                        f"Move plate target slot {move_to_slot} for row {len(rows) + 1} is already occupied by {occupant}."
                    )
                else:
                    if (
                        current_kind == "deck"
                        and deck_occupants.get(current_location) == move_labware_alias
                    ):
                        deck_occupants.pop(current_location, None)
                    elif (
                        current_kind == "module"
                        and module_occupants.get(current_location) == move_labware_alias
                    ):
                        module_occupants[current_location] = None
                    deck_occupants[move_to_slot] = move_labware_alias
                    labware_locations[move_labware_alias] = ("deck", move_to_slot)
        if row_strategy == "Multi-dispense":
            aspirate_multiplier = 1.0 + (row_extra_percent / 100.0)
            destination_mix_volume = (
                float(mix_settings["mix_volume_ul"] or 0.0)
                if mix_settings["mix_enabled"]
                and mix_settings["mix_timing"] in {"After dispensing", "Before and after"}
                else 0.0
            )
            destination_mix_reserve = max(0.0, destination_mix_volume - volume)
            available_liquid_capacity = max_ul - air_gap_volume - destination_mix_reserve
            batch = int(available_liquid_capacity // (volume * aspirate_multiplier))
            if batch < 1:
                raise ValueError(
                    f"Air gap, extra aspirate percentage, and destination mixing leave no capacity for "
                    f"{volume:.1f} uL dispenses on {pipette_name}."
                )
        else:
            batch = 1
        rows.append(
            {
                "step_name": str(row.get("step_name", "") or "").strip(),
                "chemical": chemical,
                "source_labware_alias": source_labware.get("alias", ""),
                "dest_labware_alias": dest_labware.get("alias", ""),
                "source_well": source_wells[0],
                "dest_wells": dest_wells,
                "channel_target_wells": (
                    [group[0] for group in batch_destination_groups]
                    if is_batch_8_channel
                    else ([dest_wells[0]] if nozzle_layout == "all" else dest_wells)
                ),
                "channel_source_wells": batch_source_wells if is_batch_8_channel else [],
                "channel_destination_groups": batch_destination_groups
                if is_batch_8_channel
                else [],
                "source_chemical_ids": (
                    batch_chemical_map if is_batch_8_channel else {well: chemical for well in physical_source_wells}
                ),
                "source_building_blocks": (
                    batch_building_block_map
                    if is_batch_8_channel
                    else {well: coerce_bool(row.get("is_building_block", False)) for well in physical_source_wells}
                ),
                "volume_ul": volume,
                "strategy": row_strategy,
                "pipette_key": pipette_key,
                "pipette_name": pipette_name,
                "tip_policy": row_tip_policy,
                **blowout_settings,
                "aspirate_rate": row_aspirate_rate,
                "dispense_rate": row_dispense_rate,
                "batch_size": batch,
                "aspirate_depth_mm": row_aspirate_depth_mm,
                "aspirate_depth_reference": row_aspirate_depth_reference,
                "dispense_depth_mm": row_dispense_depth_mm,
                "dispense_depth_reference": row_dispense_depth_reference,
                "multi_dispense_extra_percent": row_extra_percent,
                "tip_touch": bool(row.get("tip_touch", False)),
                "pre_wet_tip": bool(row.get("pre_wet_tip", False)),
                **mix_settings,
                "delay_air_gap_enabled": delay_air_gap_feature_enabled,
                **delay_air_gap_settings,
                "move_plate": move_plate,
                "move_labware_alias": move_labware_alias,
                "move_to_slot": move_to_slot,
                "move_target_kind": move_target_kind,
                "move_target_key": move_target_key,
                "move_from_module_key": move_from_module_key,
                "move_use_gripper": bool(row.get("move_use_gripper", False))
                and robot == "Flex"
                and bool(request.flex_gripper),
                "below_recommended_min": volume < PIPETTE_MIN_UL.get(pipette_name, 0.0),
                "nozzle_layout": nozzle_layout,
                "nozzle_start": nozzle_start,
                "tip_start_column": str(pipettes[pipette_key].get("tip_start_column", "1") or "1"),
                "tip_start_well": str(
                    pipettes[pipette_key].get("tip_start_well", "A1") or "A1"
                ).upper(),
                "sequence_id": str(row.get("sequence_id", "") or ""),
                "sequence_name": str(row.get("sequence_name", "") or ""),
                "sequence_sample_index": row.get("sequence_sample_index"),
                "sequence_sample_count": row.get("sequence_sample_count"),
                "sequence_child_index": row.get("sequence_child_index"),
                "sequence_child_count": row.get("sequence_child_count"),
                "sequence_group_id": str(row.get("sequence_group_id", "") or ""),
                "sequence_group_name": str(row.get("sequence_group_name", "") or ""),
                "sequence_group_index": row.get("sequence_group_index"),
                "sequence_group_count": row.get("sequence_group_count"),
                "sequence_group_member_index": row.get("sequence_group_member_index"),
                "sequence_group_member_position": row.get("sequence_group_member_position"),
                "sequence_group_member_position_count": row.get(
                    "sequence_group_member_position_count"
                ),
            }
        )
    validate_sequence_tip_transitions(rows)
    used_mounts = validate_used_pipette_tipracks(
        request.labware_configs,
        request.trash_slot,
        robot,
        pipettes,
        rows,
        module_configs,
    )
    pipettes = {mount: pipettes[mount] for mount in ("left", "right") if mount in used_mounts}
    for row_number, nozzle, accessed, occupied in partial_clearance_checks:
        for mount, config in pipettes.items():
            for slot in config.get("tiprack_slots", []):
                occupied[str(slot)] = f"{mount} tip rack"
        validate_partial_nozzle_clearance(
            row_number=row_number, nozzle=nozzle, accessed_slots=accessed,
            occupied_slots=occupied,
        )
    protocol_name = request.protocol_name.strip() or "Opentrons_Protocol"
    robot_type = "Flex" if robot == "Flex" else "OT-2"
    tip_starts = {
        mount: {
            "column": str(cfg.get("tip_start_column", "1") or "1"),
            "well": str(cfg.get("tip_start_well", "A1") or "A1").upper(),
        }
        for mount, cfg in pipettes.items()
    }
    tip_layouts_by_mount = {
        mount: sorted(
            {
                "all" if row.get("nozzle_layout") == "all" else "single"
                for row in rows
                if row.get("pipette_key") == mount
            }
        )
        for mount in pipettes
    }
    first_single_nozzle_by_mount = {
        mount: next(
            (
                str(row.get("nozzle_start", "") or "H1")
                for row in rows
                if row.get("pipette_key") == mount and row.get("nozzle_layout") == "single"
            ),
            "H1",
        )
        for mount in pipettes
    }
    flex_8_channel_mounts = [
        mount
        for mount, cfg in pipettes.items()
        if str(cfg.get("name", "")).startswith("flex_8channel")
    ]
    lines = [
        "from opentrons import protocol_api",
    ]
    if uses_flex_8_channel:
        lines.append("from opentrons.protocol_api import ALL, SINGLE")
    lines += [
        "",
        f"requirements = {{'robotType': {_py_string(robot_type)}, 'apiLevel': {_py_string(request.api_level.strip())}}}",
        f"metadata = {{'protocolName': {_py_string(protocol_name)}, 'author': 'Opentrons Protocol Generator'}}",
        "",
        f"LABWARE_CONFIGS = {repr(request.labware_configs)}",
        f"MODULE_CONFIGS = {repr(module_configs)}",
        f"TRANSFER_ROWS = {repr(rows)}",
        f"TIP_STARTS = {repr(tip_starts)}",
        f"TIP_LAYOUTS_BY_MOUNT = {repr(tip_layouts_by_mount)}",
        f"FIRST_SINGLE_NOZZLE_BY_MOUNT = {repr(first_single_nozzle_by_mount)}",
        f"FLEX_8_CHANNEL_MOUNTS = {repr(flex_8_channel_mounts)}",
        "",
        "def run(protocol: protocol_api.ProtocolContext):",
        "    # Well labels are interpreted by the loaded Opentrons labware definition.",
        "    # For custom plates, confirm the labware JSON geometry matches the physical plate before running.",
        "    labware = {}",
        "    module_contexts = {}",
        "    module_adapters = {}",
        "    module_labware_aliases = set()",
        "    for module_config in MODULE_CONFIGS:",
        "        key = module_config['key']",
        "        module_context = protocol.load_module(module_config['load_name'], location=module_config['slot'])",
        "        module_contexts[key] = module_context",
        "        module_parent = module_context",
        "        if module_config.get('adapter'):",
        "            module_adapter = module_context.load_adapter(module_config['adapter'])",
        "            module_adapters[key] = module_adapter",
        "            module_parent = module_adapter",
        "        module_labware_alias = module_config['labware_alias']",
        "        if module_labware_alias:",
        "            module_labware_aliases.add(module_labware_alias)",
        "            module_labware_config = next(cfg for cfg in LABWARE_CONFIGS if cfg['alias'] == module_labware_alias)",
        "            labware[module_labware_alias] = module_parent.load_labware(module_labware_config['load_name'])",
        "    for cfg in LABWARE_CONFIGS:",
        "        if cfg['alias'] not in module_labware_aliases:",
        "            labware[cfg['alias']] = protocol.load_labware(cfg['load_name'], cfg['slot'])",
    ]
    if robot == "Flex":
        lines.append(
            f"    trash = protocol.load_trash_bin({_py_string(request.trash_slot.strip())})"
        )
    else:
        lines.append("    trash = None")
    for mount, cfg in pipettes.items():
        tiprack_vars = []
        for idx, slot in enumerate(cfg["tiprack_slots"], start=1):
            name = f"{mount}_tiprack_{idx}"
            tiprack_vars.append(name)
            lines.append(
                f"    {name} = protocol.load_labware({_py_string(cfg['tiprack'])}, {_py_string(slot)})"
            )
        tiprack_names = ", ".join(tiprack_vars)
        lines.append(
            f"    pipette_{mount} = protocol.load_instrument({_py_string(cfg['name'])}, mount={_py_string(mount)}, tip_racks=[{tiprack_names}])"
        )
    pipette_items = ", ".join(f"{mount!r}: pipette_{mount}" for mount in pipettes)
    tiprack_items = ", ".join(
        f"{mount!r}: [{', '.join(f'{mount}_tiprack_{idx}' for idx, _slot in enumerate(cfg['tiprack_slots'], start=1))}]"
        for mount, cfg in pipettes.items()
    )
    lines += [
        f"    pipettes = {{{pipette_items}}}",
        f"    tipracks = {{{tiprack_items}}}",
        "    default_flow_rates = {mount: {'aspirate': pipette.flow_rate.aspirate, 'dispense': pipette.flow_rate.dispense} for mount, pipette in pipettes.items()}",
        "    active_nozzle_layout = {mount: ('default', '') for mount in pipettes}",
        "    tip_state = {",
        "        mount: {'initialized': False, 'used': [set() for _rack in racks], 'replacement_cycle': 0}",
        "        for mount, racks in tipracks.items()",
        "    }",
    ]
    for module_config in module_configs:
        module_ref = f"module_contexts[{module_config['key']!r}]"
        if module_config["key"] == "temperature":
            command = (
                "set_temperature" if module_config["wait_until_ready"] else "start_set_temperature"
            )
            lines.append(
                f"    {module_ref}.{command}(celsius={module_config['target_temperature']!r})"
            )
        else:
            if module_config.get("labware_alias"):
                lines.append(f"    {module_ref}.close_labware_latch()")
            if module_config.get("target_temperature") is not None:
                command = (
                    "set_and_wait_for_temperature"
                    if module_config["wait_until_ready"]
                    else "set_target_temperature"
                )
                lines.append(
                    f"    {module_ref}.{command}(celsius={module_config['target_temperature']!r})"
                )
            if module_config.get("shake_speed") is not None and module_config.get("labware_alias"):
                command = (
                    "set_and_wait_for_shake_speed"
                    if module_config["wait_until_ready"]
                    else "set_shake_speed"
                )
                lines.append(f"    {module_ref}.{command}({module_config['shake_speed']!r})")
                lines.append(
                    f"    protocol.delay(minutes={module_config['shake_duration_minutes']!r})"
                )
                lines.append(f"    {module_ref}.deactivate_shaker()")
    lines += [
        "",
        "    def apply_flow_rates(row):",
        "        mount = row['pipette_key']",
        "        pipette = pipettes[mount]",
        "        defaults = default_flow_rates[mount]",
        "        pipette.flow_rate.aspirate = row['aspirate_rate'] if row.get('aspirate_rate') is not None else defaults['aspirate']",
        "        pipette.flow_rate.dispense = row['dispense_rate'] if row.get('dispense_rate') is not None else defaults['dispense']",
        "",
        "    def ensure_nozzle_layout(row):",
        "        pipette = pipettes[row['pipette_key']]",
        "        layout = row.get('nozzle_layout', 'default')",
        "        if layout == 'default' or not hasattr(pipette, 'configure_nozzle_layout'):",
        "            return",
        "        mount = row['pipette_key']",
        "        nozzle_start = row.get('nozzle_start', '') if layout == 'single' else ''",
        "        requested_configuration = (layout, nozzle_start)",
        "        if active_nozzle_layout.get(mount) == requested_configuration:",
        "            return",
        "        if pipette.has_tip:",
        '            raise RuntimeError(f"Cannot change nozzle layout for {mount} pipette while a kept tip is mounted. Bin or return the tip before this row.")',
        "        if layout == 'single':",
        "            pipette.configure_nozzle_layout(style=SINGLE, start=row.get('nozzle_start', 'A1'), tip_racks=tipracks[mount])",
        "        elif layout == 'all':",
        "            pipette.configure_nozzle_layout(style=ALL, tip_racks=tipracks[mount])",
        "        active_nozzle_layout[mount] = requested_configuration",
        "",
        "    def single_tip_names(nozzle_start):",
        "        row_order = 'HGFEDCBA' if nozzle_start == 'A1' else 'ABCDEFGH'",
        "        return [f'{row_label}{col}' for col in range(1, 13) for row_label in row_order]",
        "",
        "    def tip_names_for_layout(layout, nozzle_start):",
        "        return [f'A{col}' for col in range(1, 13)] if layout == 'all' else single_tip_names(nozzle_start)",
        "",
        "    def required_tip_names(layout, pickup_name):",
        "        if layout == 'all':",
        "            column = int(pickup_name[1:])",
        "            return {f'{row_label}{column}' for row_label in 'ABCDEFGH'}",
        "        return {pickup_name}",
        "",
        "    def initialize_tip_state(mount):",
        "        state = tip_state[mount]",
        "        if state['initialized']:",
        "            return",
        "        state['initialized'] = True",
        "        if not state['used']:",
        "            return",
        "        unavailable = state['used'][0]",
        "        starts = TIP_STARTS[mount]",
        "        layouts = TIP_LAYOUTS_BY_MOUNT.get(mount, [])",
        "        if 'single' in layouts:",
        "            first_nozzle = FIRST_SINGLE_NOZZLE_BY_MOUNT.get(mount, 'H1')",
        "            names = single_tip_names(first_nozzle)",
        "            start_name = starts.get('well', 'A1')",
        "            if start_name in names:",
        "                unavailable.update(names[:names.index(start_name)])",
        "            preceding_names = names[:names.index(start_name)] if start_name in names else []",
        "            if mount in FLEX_8_CHANNEL_MOUNTS and preceding_names:",
        "                protocol.pause(",
        "                    f'Before using {mount} Flex 8-channel in SINGLE mode, confirm every tip before '",
        "                    f'{start_name} in the {first_nozzle} pickup order is absent (starting with {preceding_names[0]}). '",
        "                    f'Single-tip pickup uses physical nozzle {first_nozzle}. Resume only after the pickup path is clear.'",
        "                )",
        "        if 'all' in layouts:",
        "            start_column = int(starts.get('column', '1'))",
        "            for column in range(1, start_column):",
        "                unavailable.update(f'{row_label}{column}' for row_label in 'ABCDEFGH')",
        "",
        "    def find_next_tip(mount, layout, nozzle_start):",
        "        initialize_tip_state(mount)",
        "        for rack_index, rack in enumerate(tipracks[mount]):",
        "            wells_by_name = rack.wells_by_name()",
        "            used = tip_state[mount]['used'][rack_index]",
        "            for pickup_name in tip_names_for_layout(layout, nozzle_start):",
        "                required = required_tip_names(layout, pickup_name)",
        "                if required.isdisjoint(used) and pickup_name in wells_by_name:",
        "                    used.update(required)",
        "                    return wells_by_name[pickup_name]",
        "        return None",
        "",
        "    def next_tip_location(row):",
        "        mount = row['pipette_key']",
        "        layout = 'all' if row.get('nozzle_layout') == 'all' else 'single'",
        "        nozzle_start = row.get('nozzle_start', '') or 'H1'",
        "        location = find_next_tip(mount, layout, nozzle_start)",
        "        if location is not None:",
        "            return location",
        "        protocol.pause(",
        "            f'All configured {mount} tip boxes are exhausted. Replace every configured {mount} tip box '",
        "            'with a full new box, then resume. Replacement boxes are assumed full; no start location is applied.'",
        "        )",
        "        tip_state[mount]['used'] = [set() for _rack in tipracks[mount]]",
        "        tip_state[mount]['replacement_cycle'] += 1",
        "        location = find_next_tip(mount, layout, nozzle_start)",
        "        if location is None:",
        "            raise RuntimeError(f'No {mount} tip location is available after tip-box replacement.')",
        "        return location",
        "",
        "    def pick_up_tip_for_row(pipette, row):",
        "        location = next_tip_location(row)",
        "        pipette.pick_up_tip(location)",
        "",
        "    def drop_current_tip(pipette):",
        "        if trash is None:",
        "            pipette.drop_tip()",
        "        else:",
        "            pipette.drop_tip(trash)",
        "",
        "    def ensure_tip_for_row(pipette, row):",
        "        if not pipette.has_tip:",
        "            pick_up_tip_for_row(pipette, row)",
        "",
        "    def finish_tip_for_row(pipette, row):",
        "        action = row.get('tip_policy') or 'Bin tip after row'",
        "        if action == 'Keep tip mounted':",
        "            return",
        "        if not pipette.has_tip:",
        "            return",
        "        if action == 'Return tip to box':",
        "            pipette.return_tip()",
        "        else:",
        "            drop_current_tip(pipette)",
        "",
        "    def after_dispense(pipette, target, row):",
        "        if row.get('tip_touch'):",
        "            pipette.touch_tip(target)",
        "",
        "    def well_location(well, mm_from_reference, reference):",
        "        if mm_from_reference is None:",
        "            return well",
        "        if reference == 'from top':",
        "            return well.top(-float(mm_from_reference))",
        "        return well.bottom(float(mm_from_reference))",
        "",
        "    def pre_wet_tip(pipette, source_well, volume, row):",
        "        if row.get('pre_wet_tip'):",
        "            pipette.aspirate(volume, source_well)",
        "            pipette.dispense(volume, source_well)",
        "",
        "    def mix_well(pipette, well, row):",
        "        if not row.get('mix_enabled'):",
        "            return",
        "        aspirate_location = well_location(",
        "            well, row.get('mix_aspirate_depth_mm'), row.get('mix_aspirate_depth_reference', 'from bottom')",
        "        )",
        "        dispense_location = well_location(",
        "            well, row.get('mix_dispense_depth_mm'), row.get('mix_dispense_depth_reference', 'from bottom')",
        "        )",
        "        previous_aspirate_rate = pipette.flow_rate.aspirate",
        "        previous_dispense_rate = pipette.flow_rate.dispense",
        "        try:",
        "            if row.get('mix_aspirate_rate') is not None:",
        "                pipette.flow_rate.aspirate = row['mix_aspirate_rate']",
        "            if row.get('mix_dispense_rate') is not None:",
        "                pipette.flow_rate.dispense = row['mix_dispense_rate']",
        "            for _repeat in range(row['mix_repetitions']):",
        "                pipette.aspirate(row['mix_volume_ul'], aspirate_location)",
        "                pipette.dispense(row['mix_volume_ul'], dispense_location)",
        "        finally:",
        "            pipette.flow_rate.aspirate = previous_aspirate_rate",
        "            pipette.flow_rate.dispense = previous_dispense_rate",
        "",
        "    def mix_before_aspirating(pipette, source_well, row):",
        "        if row.get('mix_enabled') and row.get('mix_timing') in ('Before aspirating', 'Before and after'):",
        "            mix_well(pipette, source_well, row)",
        "            timed_delay(row.get('post_source_mix_delay_seconds'))",
        "",
        "    def mix_after_dispensing(pipette, destination_well, row):",
        "        if row.get('mix_timing') in ('After dispensing', 'Before and after'):",
        "            mix_well(pipette, destination_well, row)",
        "",
        "    def timed_delay(seconds):",
        "        if seconds is not None and float(seconds) > 0:",
        "            protocol.delay(seconds=float(seconds))",
        "",
        "    def add_air_gap(pipette, row):",
        "        if not row.get('air_gap_enabled'):",
        "            return",
        "        previous_aspirate_rate = pipette.flow_rate.aspirate",
        "        try:",
        "            if row.get('air_gap_flow_rate') is not None:",
        "                pipette.flow_rate.aspirate = row['air_gap_flow_rate']",
        "            pipette.air_gap(volume=row['air_gap_volume_ul'], height=row['air_gap_height_mm'])",
        "        finally:",
        "            pipette.flow_rate.aspirate = previous_aspirate_rate",
        "",
        "    def release_air_gap_above_destination(pipette, destination_well, row):",
        "        if row.get('air_gap_enabled'):",
        "            pipette.dispense(row['air_gap_volume_ul'], destination_well.top())",
        "",
        "    def blow_out_at_selected_location(pipette, source_well, destination_well, row):",
        "        location = row.get('blowout_location', 'No blowout')",
        "        if location == 'No blowout':",
        "            return",
        "        if location == 'Source':",
        "            target = source_well",
        "        elif location == 'Destination':",
        "            target = destination_well",
        "        elif location == 'Liquid waste':",
        "            target = labware[row['blowout_labware_alias']][row['blowout_well']]",
        "        else:",
        "            raise ValueError('Invalid blowout location')",
        "        pipette.blow_out(target.top())",
        "",
        "    for i, row in enumerate(TRANSFER_ROWS, start=1):",
        "        pipette = pipettes[row['pipette_key']]",
        "        source_labware = labware[row['source_labware_alias']]",
        "        dest_labware = labware[row['dest_labware_alias']]",
        "        src = source_labware[row['source_well']]",
        "        src_location = well_location(src, row.get('aspirate_depth_mm'), row.get('aspirate_depth_reference', 'from bottom'))",
        "        dests = [dest_labware[name] for name in row['dest_wells']]",
        "        targets = [dest_labware[name] for name in row.get('channel_target_wells', row['dest_wells'])]",
        "        dispense_volume = row['volume_ul']",
        "        step_name = str(row.get('step_name') or f'Transfer {i}')",
        "        source_chemical_ids = row.get('source_chemical_ids', {})",
        "        source_building_blocks = row.get('source_building_blocks', {})",
        "        assigned_source_chemicals = ', '.join(f\"{well}={chemical}{' (building block)' if source_building_blocks.get(well, False) else ''}\" for well, chemical in source_chemical_ids.items() if chemical)",
        "        label = row.get('chemical') or assigned_source_chemicals or f\"{row['source_labware_alias']}:{row['source_well']}\"",
        "        if row.get('below_recommended_min'):",
        "            protocol.comment(f\"Warning row {i}: {dispense_volume} uL is below the recommended range for {row['pipette_name']}.\")",
        "        apply_flow_rates(row)",
        "        ensure_nozzle_layout(row)",
        "        if row.get('sequence_id'):",
        "            protocol.comment(f\"Sequence {row.get('sequence_name') or 'Sequence'}: sample {row.get('sequence_sample_index')}/{row.get('sequence_sample_count')}, Group {row.get('sequence_group_index')}/{row.get('sequence_group_count')} ({row.get('sequence_group_name') or 'Group'})\")",
        '        protocol.comment(f"Step {i}: {step_name}")',
        "        nozzle_description = row.get('nozzle_layout', 'default')",
        "        if row.get('nozzle_start'):",
        "            nozzle_description += f\"/{row['nozzle_start']}\"",
        "        protocol.comment(f\"Row {i}: {label}, dispense volume {dispense_volume} uL with {row['pipette_name']} to {len(dests)} destination well(s); nozzle layout {nozzle_description}\")",
        "        if row.get('channel_destination_groups'):",
        "            source_column = ','.join(row.get('channel_source_wells', []))",
        "            destination_columns = '; '.join(','.join(group) for group in row['channel_destination_groups'])",
        '            protocol.comment(f"All 8 nozzles act simultaneously. Source column: {source_column}. Destination columns: {destination_columns}. Opentrons commands and simulation display each column by its anchor well only.")',
    ]
    lines += [
        "        ensure_tip_for_row(pipette, row)",
        "        if row['strategy'] == 'Multi-dispense':",
        "            batch_size = max(1, row['batch_size'])",
        "            for start in range(0, len(targets), batch_size):",
        "                batch = targets[start:start + batch_size]",
        "                total_dispense_volume = dispense_volume * len(batch)",
        "                extra_volume = total_dispense_volume * row.get('multi_dispense_extra_percent', 0.0) / 100.0",
        "                aspirate_volume = total_dispense_volume + extra_volume",
        "                pre_wet_tip(pipette, src_location, aspirate_volume, row)",
        "                mix_before_aspirating(pipette, src, row)",
        "                pipette.aspirate(aspirate_volume, src_location)",
        "                timed_delay(row.get('post_aspirate_delay_seconds'))",
        "                add_air_gap(pipette, row)",
        "                release_air_gap_above_destination(pipette, batch[0], row)",
        "                for target in batch:",
        "                    target_location = well_location(target, row.get('dispense_depth_mm'), row.get('dispense_depth_reference', 'from top'))",
        "                    pipette.dispense(dispense_volume, target_location)",
        "                    timed_delay(row.get('post_dispense_delay_seconds'))",
        "                    mix_after_dispensing(pipette, target, row)",
        "                    after_dispense(pipette, target, row)",
        "                blow_out_at_selected_location(pipette, src, batch[-1], row)",
        "        else:",
        "            for target in targets:",
        "                aspirate_volume = dispense_volume",
        "                target_location = well_location(target, row.get('dispense_depth_mm'), row.get('dispense_depth_reference', 'from top'))",
        "                pre_wet_tip(pipette, src_location, aspirate_volume, row)",
        "                mix_before_aspirating(pipette, src, row)",
        "                pipette.aspirate(aspirate_volume, src_location)",
        "                timed_delay(row.get('post_aspirate_delay_seconds'))",
        "                add_air_gap(pipette, row)",
        "                release_air_gap_above_destination(pipette, target, row)",
        "                pipette.dispense(dispense_volume, target_location)",
        "                timed_delay(row.get('post_dispense_delay_seconds'))",
        "                mix_after_dispensing(pipette, target, row)",
        "                after_dispense(pipette, target, row)",
        "                blow_out_at_selected_location(pipette, src, target, row)",
        "        finish_tip_for_row(pipette, row)",
        "        if row.get('move_plate'):",
        "            timed_delay(row.get('pre_move_delay_seconds'))",
        "            from_module_key = row.get('move_from_module_key') or ''",
        "            to_module_key = row.get('move_target_key') or ''",
        "            uses_heater_shaker = 'heater_shaker' in (from_module_key, to_module_key)",
        "            if uses_heater_shaker:",
        "                module_contexts['heater_shaker'].open_labware_latch()",
        "            if row.get('move_target_kind') == 'module':",
        "                new_location = module_adapters[to_module_key]",
        "            else:",
        "                new_location = row['move_to_slot']",
        "            protocol.move_labware(labware[row['move_labware_alias']], new_location=new_location, use_gripper=bool(row.get('move_use_gripper')))",
        "            if uses_heater_shaker:",
        "                module_contexts['heater_shaker'].close_labware_latch()",
        "            if to_module_key == 'heater_shaker':",
        "                heater_shaker_config = next(cfg for cfg in MODULE_CONFIGS if cfg['key'] == 'heater_shaker')",
        "                if heater_shaker_config.get('shake_speed') is not None:",
        "                    heater_shaker = module_contexts['heater_shaker']",
        "                    if heater_shaker_config.get('wait_until_ready'):",
        "                        heater_shaker.set_and_wait_for_shake_speed(heater_shaker_config['shake_speed'])",
        "                    else:",
        "                        heater_shaker.set_shake_speed(heater_shaker_config['shake_speed'])",
        "                    protocol.delay(minutes=heater_shaker_config['shake_duration_minutes'])",
        "                    heater_shaker.deactivate_shaker()",
    ]
    for module_config in module_configs:
        if not module_config.get("deactivate_after_run"):
            continue
        module_ref = f"module_contexts[{module_config['key']!r}]"
        if module_config["key"] == "temperature":
            lines.append(f"    {module_ref}.deactivate()")
        elif module_config.get("target_temperature") is not None:
            lines.append(f"    {module_ref}.deactivate_heater()")
    return "\n".join(lines) + "\n"
