"""Deterministic Tecan worklist and companion-map generation.

Callers supply transfer blocks, destination format, optional export aliases and
any conflicts found in their external worklist inventory. No widgets or files
are accessed here; the controller owns that inventory and all user interaction.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence
import math

from .tecan_domain import (
    TransferBlock,
    gwl_a_line,
    gwl_d_line,
    index_to_dest_label,
    parse_dest_well_expr,
    rounded_gwl_volume,
)


def build_gwl_lines(
    blocks: Sequence[TransferBlock],
    mode: str,
    *,
    labware_aliases: Mapping[str, str] | None = None,
    source_conflicts: Mapping[int, str] | None = None,
) -> List[str]:
    """Validate and render ordered A/D/W commands; conflicts use 1-based block numbers."""
    labware_aliases = labware_aliases or {}
    source_conflicts = source_conflicts or {}

    def export_name(logical_name: str) -> str:
        logical_name = str(logical_name or "").strip()
        return (labware_aliases.get(logical_name, logical_name) or logical_name).strip()

    if blocks and not mode:
        raise ValueError("Select a destination format before exporting transfer blocks.")
    lines = []
    for idx, b in enumerate(blocks, start=1):
        if not b.dest_labware.strip():
            raise ValueError(f"Block {idx}: select destination labware before exporting.")
        conflict = source_conflicts.get(idx, "")
        if conflict:
            raise ValueError(
                f"Block {idx}: {conflict} Choose an unused source well or use the same Chemical ID."
            )
        if not math.isfinite(float(b.source_volume)) or float(b.source_volume) <= 0:
            raise ValueError(f"Block {idx}: aspirate volume must be greater than 0 uL")
        if not math.isfinite(float(b.dest_volume)) or float(b.dest_volume) <= 0:
            raise ValueError(f"Block {idx}: dispense volume must be greater than 0 uL")
        for grp in b.dispense_groups:
            if not math.isfinite(float(grp.volume)) or float(grp.volume) <= 0:
                raise ValueError(
                    f"Block {idx}: every extra-group dispense volume must be greater than 0 uL"
                )
        try:
            if b.disp_different_vol and b.dispense_groups:
                for grp in b.dispense_groups:
                    parse_dest_well_expr(grp.wells_expr, mode, b.dest_labware)
            else:
                parse_dest_well_expr(b.dest_wells_expr, mode, b.dest_labware)
        except Exception as exc:
            raise ValueError(f"Block {idx}: invalid destination wells: {exc}") from exc

        source_export_name = export_name(b.source_labware)
        dest_export_name = export_name(b.dest_labware)
        lines.append(gwl_a_line(source_export_name, b.source_well, b.source_volume, b.liquid_class))
        total_dispense = 0.0
        dest_wells = parse_dest_well_expr(b.dest_wells_expr, mode, b.dest_labware)
        total_dispense = rounded_gwl_volume(b.dest_volume) * len(dest_wells)
        for w in dest_wells:
            lines.append(gwl_d_line(dest_export_name, w, b.dest_volume, b.liquid_class))

        if b.disp_different_vol and b.dispense_groups:
            for grp in b.dispense_groups:
                grp_wells = parse_dest_well_expr(grp.wells_expr, mode, b.dest_labware)
                total_dispense += rounded_gwl_volume(grp.volume) * len(grp_wells)
                for w in grp_wells:
                    lines.append(gwl_d_line(dest_export_name, w, grp.volume, b.liquid_class))

        if total_dispense > rounded_gwl_volume(b.source_volume) + 1e-9:
            raise ValueError(
                f"Block {idx}: total dispense volume ({total_dispense:.1f} uL) exceeds aspirate volume ({b.source_volume:.1f} uL)"
            )
        if b.add_wash:
            lines.append("W;")
    return lines


def build_chemical_map(blocks: Sequence[TransferBlock], mode: str) -> Dict[str, List[str]]:
    chem_map: Dict[str, List[str]] = {}
    for i, b in enumerate(blocks, start=1):
        dest_wells = parse_dest_well_expr(b.dest_wells_expr, mode, b.dest_labware)
        if b.disp_different_vol and b.dispense_groups:
            for grp in b.dispense_groups:
                dest_wells.extend(parse_dest_well_expr(grp.wells_expr, mode, b.dest_labware))
        name = b.chemical_name.strip() or f"Block {i}"
        for idx in dest_wells:
            lbl = index_to_dest_label(idx, mode, b.dest_labware)
            chem_map.setdefault(lbl, []).append(name)
    return chem_map


def build_volume_map(blocks: Sequence[TransferBlock], mode: str) -> Dict[str, float]:
    vol_map: Dict[str, float] = {}
    for b in blocks:
        base_wells = parse_dest_well_expr(b.dest_wells_expr, mode, b.dest_labware)
        for idx in base_wells:
            lbl = index_to_dest_label(idx, mode, b.dest_labware)
            vol_map[lbl] = vol_map.get(lbl, 0.0) + rounded_gwl_volume(b.dest_volume)

        if b.disp_different_vol and b.dispense_groups:
            for grp in b.dispense_groups:
                grp_wells = parse_dest_well_expr(grp.wells_expr, mode, b.dest_labware)
                for idx in grp_wells:
                    lbl = index_to_dest_label(idx, mode, b.dest_labware)
                    vol_map[lbl] = vol_map.get(lbl, 0.0) + rounded_gwl_volume(grp.volume)
    return vol_map
