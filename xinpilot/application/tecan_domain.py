"""Tecan transfer models, well geometry and GWL primitives.

This module has no UI, filesystem or chemistry dependency. The historic
``tecan_frame`` names remain compatibility imports of these canonical definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import math
import re


def validate_gwl_names(entries):
    """Worklist filenames are unique within a project, ignoring Windows case."""
    seen = set()
    for entry in entries:
        name = str(entry.get('name') or entry.get('path') or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            raise ValueError(f"Duplicate GWL filename '{name}'. Each GWL in this project must have a different filename, even when stored in different folders. Rename the file before adding or saving it.")
        seen.add(key)


def validate_gwl_snapshots(rows):
    """Reject ambiguous legacy pushed blocks even if archive filenames changed."""
    seen = {}
    for row in rows:
        payload = row.get('summary_block')
        if not isinstance(payload, dict):
            continue
        key = (str(row.get('source', '')).casefold(), str(row.get('gwl', '')).casefold(), row.get('block'))
        snapshot = (row.get('dest_mode'), payload)
        if key in seen and seen[key] != snapshot:
            raise ValueError(f"Ambiguous pushed GWL '{row.get('gwl', '')}': different blocks share the same filename and block number. Give the worklists unique filenames and push them again before exporting the project.")
        seen[key] = snapshot

SOURCE_LABWARE_OPTIONS = [
    "Vial8Rack_1",
    "Vial8Rack_2",
    "Vial20",
    "Vial1.5_Rack1",
    "Vial1.5_Rack2",
    "DeepPlate1",
    "Green Plate",
]

LIQUID_CLASS_OPTIONS = [
    "XQ_Common_no_gas",
    "XQ_Common_no_cLLD_no_gas",
    "XQ_Gas_involved",
    "XQ_Gas_involved_no_cLLD",
]

PLATE_MODES = [
    "96-well horizontal",
    "96-well vertical",
    "HPLC vials horizontal",
    "HPLC vials vertical",
]

DEST_LABWARE_OPTIONS_96 = ["DeepPlate1", "Green Plate"]

DEST_LABWARE_OPTIONS_HPLC = ["Vial1.5_Rack1"]

WELL_LABEL_RE = re.compile(r"^([A-Za-z]+)([0-9]+)$")


def classify_source_well_usage(
    usages: List[Tuple[object, object]],
    chemical_id: object,
) -> Tuple[Set[str], Set[str]]:
    """Split used source wells into blocked and same-chemical reusable sets."""
    desired = str(chemical_id or "").strip().casefold()
    chemicals_by_label: Dict[str, Set[str]] = {}
    for label, used_chemical_id in usages:
        normalized_label = str(label or "").strip().upper()
        if not normalized_label:
            continue
        chemicals_by_label.setdefault(normalized_label, set()).add(
            str(used_chemical_id or "").strip().casefold()
        )

    blocked: Set[str] = set()
    reusable: Set[str] = set()
    for label, used_chemicals in chemicals_by_label.items():
        if desired and used_chemicals == {desired}:
            reusable.add(label)
        else:
            blocked.add(label)
    return blocked, reusable


SOURCE_LAYOUTS = {
    "Vial20": {"rows": 2, "cols": 4, "style": "rowcol"},
    "Vial8Rack_1": {"rows": 4, "cols": 6, "style": "rowcol"},
    "Vial8Rack_2": {"rows": 6, "cols": 4, "style": "colrow"},
    "Vial1.5_Rack1": {"rows": 6, "cols": 8, "style": "rowcol"},
    "Vial1.5_Rack2": {"rows": 8, "cols": 6, "style": "colrow"},
    # Added plate-style source maps to match destination-style well labeling.
    "DeepPlate1": {"rows": 8, "cols": 12, "style": "rowcol"},
    "Green Plate": {"rows": 8, "cols": 12, "style": "rowcol"},
}

KNOWN_LABWARE_OPTIONS = list(
    dict.fromkeys(SOURCE_LABWARE_OPTIONS + DEST_LABWARE_OPTIONS_96 + DEST_LABWARE_OPTIONS_HPLC)
)


def normalize_liquid_class_names(values) -> List[str]:
    if not isinstance(values, (list, tuple)):
        return []
    names: List[str] = []
    seen: Set[str] = set()
    for value in values:
        name = str(value or "").strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def default_labware_aliases() -> Dict[str, str]:
    return {name: name for name in KNOWN_LABWARE_OPTIONS}


def mode_dims_order(mode: str) -> Tuple[int, int, str]:
    if mode in {"384-well horizontal", "384 well horizontal"}:
        return 16, 24, "column-major"
    if mode == "96-well horizontal":
        return 8, 12, "column-major"
    if mode == "96-well vertical":
        return 8, 12, "row-major-reverse-columns"
    if mode == "HPLC vials horizontal":
        return 6, 8, "column-major"
    if mode == "HPLC vials vertical":
        return 6, 8, "row-major-reverse-columns"
    if mode in {"48-well horizontal", "48 well horizontal"}:
        return 6, 8, "column-major"
    if mode in {"24-well horizontal", "24 well horizontal"}:
        return 4, 6, "column-major"
    return 8, 12, "column-major"


def row_label_to_number(label: str) -> int:
    n = 0
    for c in label.upper():
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n


def row_number_to_label(n: int) -> str:
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def index_to_label(index: int, rows: int, cols: int, order: str) -> str:
    if not (1 <= index <= rows * cols):
        raise ValueError(f"Well index {index} out of range 1..{rows * cols}")
    if order == "column-major":
        col = (index - 1) // rows + 1
        row = (index - 1) % rows + 1
    elif order == "row-major":
        row = (index - 1) // cols + 1
        col = (index - 1) % cols + 1
    elif order == "row-major-reverse-columns":
        row = (index - 1) // cols + 1
        visual_col = (index - 1) % cols + 1
        col = cols - visual_col + 1
    else:
        raise ValueError(f"Unknown order {order}")
    return f"{row_number_to_label(row)}{col}"


def label_to_index(label: str, rows: int, cols: int, order: str) -> int:
    m = WELL_LABEL_RE.match((label or "").strip())
    if not m:
        raise ValueError(f"Invalid well label: {label}")
    row = row_label_to_number(m.group(1))
    col = int(m.group(2))
    if not (1 <= row <= rows):
        raise ValueError(f"Row out of range in {label} (1..{rows})")
    if not (1 <= col <= cols):
        raise ValueError(f"Column out of range in {label} (1..{cols})")

    if order == "column-major":
        return (col - 1) * rows + row
    if order == "row-major":
        return (row - 1) * cols + col
    if order == "row-major-reverse-columns":
        visual_col = cols - col + 1
        return (row - 1) * cols + visual_col
    raise ValueError(f"Unknown order {order}")


def parse_well_expr(expr: str, rows: int, cols: int, order: str) -> List[int]:
    expr = (expr or "").strip()
    if not expr:
        return []
    out: List[int] = []
    for part in [p.strip() for p in expr.split(",") if p.strip()]:
        if WELL_LABEL_RE.match(part):
            out.append(label_to_index(part, rows=rows, cols=cols, order=order))
            continue
        if "-" in part and part[0].isdigit():
            if ":" in part:
                range_part, step_part = part.split(":", 1)
                step = int(step_part)
            else:
                range_part = part
                step = 1
            a, b = range_part.split("-", 1)
            start, end = int(a), int(b)
            if step <= 0:
                raise ValueError(f"Invalid step in '{part}'")
            if start <= end:
                out.extend(list(range(start, end + 1, step)))
            else:
                out.extend(list(range(start, end - 1, -step)))
            continue
        out.append(int(part))

    seen = set()
    unique = []
    max_idx = rows * cols
    for x in out:
        if x <= 0 or x > max_idx:
            raise ValueError(f"Well index {x} out of range 1..{max_idx}")
        if x in seen:
            continue
        unique.append(x)
        seen.add(x)
    return unique


def parse_dest_well_expr(expr: str, mode: str, dest_labware: str) -> List[int]:
    rows, cols, order = mode_dims_order(mode)
    return parse_well_expr(expr, rows, cols, order)


def index_to_dest_label(index: int, mode: str, dest_labware: str) -> str:
    rows, cols, order = mode_dims_order(mode)
    return index_to_label(index, rows, cols, order)


def source_label_to_index(label: str, labware: str) -> int:
    cfg = SOURCE_LAYOUTS.get(labware)
    if not cfg:
        raise ValueError(f"Unsupported source labware: {labware}")
    m = WELL_LABEL_RE.match((label or "").strip())
    if not m:
        raise ValueError(f"Invalid well label: {label}")
    letters, num_text = m.groups()
    n = int(num_text)
    style, rows, cols = cfg["style"], cfg["rows"], cfg["cols"]

    if style == "rowcol":
        visual_row = row_label_to_number(letters)
        visual_col = n
        if not (1 <= visual_row <= rows and 1 <= visual_col <= cols):
            raise ValueError(f"Label {label} out of range for {labware}")
        return (visual_col - 1) * rows + visual_row

    visual_col = row_label_to_number(letters)
    visual_row = rows - n + 1
    if not (1 <= visual_row <= rows and 1 <= visual_col <= cols):
        raise ValueError(f"Label {label} out of range for {labware}")
    return (visual_col - 1) * rows + visual_row


def source_index_to_label(index: int, labware: str) -> str:
    cfg = SOURCE_LAYOUTS.get(labware)
    if not cfg:
        return ""
    rows, cols, style = cfg["rows"], cfg["cols"], cfg["style"]
    if index <= 0 or index > rows * cols:
        return ""
    visual_col = (index - 1) // rows + 1
    visual_row = (index - 1) % rows + 1
    if style == "rowcol":
        return f"{row_number_to_label(visual_row)}{visual_col}"
    return f"{row_number_to_label(visual_col)}{rows - visual_row + 1}"


def rounded_gwl_volume(volume: float) -> float:
    """The numeric value represented by a GWL command's 0.1 uL precision."""
    return float(f"{float(volume):.1f}")


def _validate_gwl_volume(volume: float):
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("GWL transfer volume must be a finite number greater than zero.")
    if rounded_gwl_volume(volume) <= 0:
        raise ValueError("GWL transfer volume rounds to zero at the supported 0.1 uL precision.")


def gwl_a_line(labware: str, well: int, volume: float, liquid_class: str) -> str:
    _validate_gwl_volume(volume)
    return f"A;{labware};;;{well};;{volume:.1f};{liquid_class};;;"


def gwl_d_line(labware: str, well: int, volume: float, liquid_class: str) -> str:
    _validate_gwl_volume(volume)
    return f"D;{labware};;;{well};;{volume:.1f};{liquid_class};;;"


@dataclass
class DispenseGroup:
    volume: float = 20.0
    wells_expr: str = ""


@dataclass
class TransferBlock:
    source_labware: str = "Vial8Rack_1"
    source_well: int = 1
    source_volume: float = 20.0
    dest_labware: str = "DeepPlate1"
    dest_wells_expr: str = ""
    dest_volume: float = 20.0
    liquid_class: str = "XQ_Common_no_gas"
    chemical_name: str = ""
    add_wash: bool = True
    disp_different_vol: bool = False
    dispense_groups: List[DispenseGroup] = field(default_factory=list)
    is_building_block: bool = False
    reaction_umol: str = ""
    extra_aspirate_percent: str = ""
