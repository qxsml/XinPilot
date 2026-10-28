from __future__ import annotations

import csv
import ast
import http.server
import json
import queue
import re
import runpy
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import openpyxl
from PIL import Image, ImageDraw, ImageTk
from rdkit import Chem
from rdkit.Chem import Draw

import compound_notes_frame
import integrated_tecan_compound_cheminformatics as core
import tecan_frame


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PRODUCT_REACTANT_MASS_CONFLICT = "PRODUCT_REACTANT_MASS_CONFLICT"
ROOT = APP_DIR.parent if APP_DIR.name.lower().startswith("dist") else APP_DIR
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") else ROOT
OUTPUT_DIR = ROOT / "outputs"
PYPARSE_INPUT_DIR = OUTPUT_DIR / "pyparse_inputs"
DEFAULT_PYPARSE_PLATEMAP = PYPARSE_INPUT_DIR / "oneclick_pyparse_platemap.csv"
KETCHER_TEMPLATE_PATH = OUTPUT_DIR / "custom_reaction_template_from_ketcher.rxn"
PYPARSE_DIR = RESOURCE_ROOT / "PyParse"
MODIFIED_PYPARSE_DIR = RESOURCE_ROOT / "Modified PyParse"


from xinpilot.application.values import coerce_bool


def _normalize_well(value: object) -> str:
    text = str(value or "").strip().upper()
    m = re.match(r"^([A-H])\s*0*([1-9]|1[0-2])$", text)
    if m:
        return f"{m.group(1)}{int(m.group(2))}"
    return text


def _format_percent_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return f"{float(text):.2f}%"
    except ValueError:
        return text if text.endswith("%") else f"{text}%"


def _blank_or_zero(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    try:
        return float(text.rstrip("%")) == 0
    except ValueError:
        return False


def _numeric_percent_value(value: object) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.rstrip("%").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _store_purity_value(result: Dict[str, str], well: str, purity: object, *, overwrite: bool = False):
    well = _normalize_well(well)
    if not well or well == "NONE FOUND." or purity in (None, ""):
        return
    formatted = _format_percent_value(purity)
    if not formatted:
        return
    existing = result.get(well, "")
    if overwrite or not existing or _blank_or_zero(existing):
        result[well] = formatted


def _canonical_smiles_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        mol = Chem.MolFromSmiles(text)
        if mol is not None:
            return Chem.MolToSmiles(mol)
    except Exception:
        pass
    return text


def _nearby_named_files(folder: Path, filename: str) -> List[Path]:
    paths: List[Path] = []
    direct = folder / filename
    if direct.is_file():
        paths.append(direct)
    try:
        for child in folder.iterdir():
            if child.is_dir():
                candidate = child / filename
                if candidate.is_file():
                    paths.append(candidate)
    except Exception:
        pass
    return sorted(set(paths), key=lambda p: p.stat().st_mtime)


def _read_modified_pyparse_uv254_purity_by_product(output_dir: Path) -> Dict[str, Dict[str, str]]:
    """Read true UV254 purity without losing the compound identity.

    ``compoundtable.csv`` contains one purity map per compound.  Flattening all
    of those maps to ``{well: purity}`` lets a starting material or impurity
    overwrite the desired product in the same well.  ``aTable.csv`` is used as
    the per-well assignment gate: a submitted product with no accepted hit is
    explicitly recorded as 0%, even when an unassigned UV peak is present.
    """
    if not output_dir.exists():
        return {}

    desired_smiles = set()
    submitted_product_wells = set()
    detected_product_wells = set()
    for path in _nearby_named_files(output_dir, "aTable.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    if str(row.get("analyte_class", "") or "").strip().casefold() != "desired product":
                        continue
                    smiles_key = _canonical_smiles_key(row.get("analyte_smiles", ""))
                    well = _normalize_well(row.get("well_ID") or row.get("well") or row.get("Well"))
                    if not smiles_key or not well:
                        continue
                    desired_smiles.add(smiles_key)
                    submitted_product_wells.add((smiles_key, well))
                    data_type = str(row.get("data_type", "") or "").strip().casefold()
                    if data_type not in {"retention time", "percentage area"}:
                        continue
                    try:
                        detected = float(str(row.get("data_entry", "") or "0").strip()) > 0
                    except ValueError:
                        detected = False
                    if detected:
                        detected_product_wells.add((smiles_key, well))
        except Exception:
            continue

    result: Dict[str, Dict[str, str]] = {}
    for path in _nearby_named_files(output_dir, "compoundtable.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    smiles_key = _canonical_smiles_key(row.get("g_smiles", ""))
                    if not smiles_key or (desired_smiles and smiles_key not in desired_smiles):
                        continue
                    purity_map = {}
                    purity_by_well = str(row.get("purity_by_well", "") or "").strip()
                    if purity_by_well:
                        try:
                            parsed = ast.literal_eval(purity_by_well)
                        except Exception:
                            parsed = {}
                        if isinstance(parsed, dict):
                            purity_map.update(parsed)

                    best_well = _normalize_well(row.get("best_well") or row.get("well") or row.get("Well"))
                    if best_well and best_well != "NONE FOUND.":
                        best_purity = row.get("best_purity254")
                        if _blank_or_zero(best_purity) and not _blank_or_zero(row.get("best_purity")):
                            best_purity = row.get("best_purity")
                        if best_purity not in (None, ""):
                            purity_map.setdefault(best_well, best_purity)

                    values = result.setdefault(smiles_key, {})
                    not_found = str(row.get("qc_flag", "") or "").strip().upper() == "NOT_FOUND"
                    for map_well, map_purity in purity_map.items():
                        well = _normalize_well(map_well)
                        if not well:
                            continue
                        product_well = (smiles_key, well)
                        if submitted_product_wells:
                            purity = map_purity if product_well in detected_product_wells else "0"
                        else:
                            purity = "0" if not_found else map_purity
                        formatted = _format_percent_value(str(purity))
                        if formatted and (well not in values or _blank_or_zero(values[well])):
                            values[well] = formatted
        except Exception:
            continue
    return {smiles: values for smiles, values in result.items() if values}


def _read_modified_pyparse_conflicts_by_product(output_dir: Path) -> Dict[str, Dict[str, str]]:
    """Read structured product-assignment conflict reasons by SMILES and well."""
    if not output_dir.exists():
        return {}

    result: Dict[str, Dict[str, str]] = {}
    for path in _nearby_named_files(output_dir, "compoundtable.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    smiles_key = _canonical_smiles_key(row.get("g_smiles", ""))
                    raw_conflicts = str(row.get("assignment_conflicts", "") or "").strip()
                    if not smiles_key or not raw_conflicts:
                        continue
                    try:
                        parsed = ast.literal_eval(raw_conflicts)
                    except Exception:
                        parsed = {}
                    if not isinstance(parsed, dict):
                        continue
                    values = result.setdefault(smiles_key, {})
                    for map_well, reason in parsed.items():
                        well = _normalize_well(map_well)
                        reason = str(reason or "").strip()
                        if well and reason == PRODUCT_REACTANT_MASS_CONFLICT:
                            values[well] = reason
        except Exception:
            continue
    return {smiles: values for smiles, values in result.items() if values}


def _read_pyparse_uv254_purity_by_well(output_dir: Path, modified: bool = False) -> Dict[str, str]:
    if not output_dir.exists():
        return {}
    result: Dict[str, str] = {}

    if modified:
        for path in _nearby_named_files(output_dir, "compoundtable.csv"):
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as fh:
                    for row in csv.DictReader(fh):
                        purity_by_well = str(row.get("purity_by_well", "") or "").strip()
                        if purity_by_well:
                            try:
                                parsed = ast.literal_eval(purity_by_well)
                            except Exception:
                                parsed = {}
                            if isinstance(parsed, dict):
                                for map_well, map_purity in parsed.items():
                                    _store_purity_value(result, str(map_well), map_purity)
                        well = _normalize_well(row.get("best_well") or row.get("well") or row.get("Well"))
                        purity = row.get("best_purity254")
                        if _blank_or_zero(purity) and not _blank_or_zero(row.get("best_purity")):
                            purity = row.get("best_purity")
                        if _blank_or_zero(purity):
                            purity = row.get("UV254 purity") or row.get("uv254_purity")
                        _store_purity_value(result, well, purity)
            except Exception:
                continue
        return result

    for path in _nearby_named_files(output_dir, "aTable.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    if str(row.get("analyte_class", "")).strip().lower() != "desired product":
                        continue
                    if str(row.get("data_type", "")).strip().lower() != "percentage area":
                        continue
                    well = _normalize_well(row.get("well_ID") or row.get("well") or row.get("Well"))
                    value = row.get("data_entry")
                    if well and value not in (None, ""):
                        result[well] = _format_percent_value(value)
        except Exception:
            continue

    for path in _nearby_named_files(output_dir, "outputTable.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    well = _normalize_well(row.get("Well") or row.get("well"))
                    purity = row.get("Purity254") or row.get("UV254 purity") or row.get("uv254_purity") or row.get("Parea")
                    if well and purity not in (None, "") and well not in result:
                        result[well] = _format_percent_value(purity)
        except Exception:
            continue
    return result


def _safe_pyparse_graph_token(value: object) -> str:
    return str(value or "").replace(" ", "_").replace("/", "_").replace("\\", "_")


from xinpilot_theme import COLORS, configure_controls, configure_table_tags, stripe_tag


PRODUCT_SUMMARY_ROW_COLORS = {
    "green": "#d8f0d2",
    "yellow": "#fff2b8",
    "red": "#f7c9c9",
    "blue": "#cfe3ff",
}


def _is_hex_color(value: object) -> bool:
    return bool(re.match(r"^#[0-9a-fA-F]{6}$", str(value or "").strip()))


def _make_tab_icon(master, kind: str, size: int = 22):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    ink = (47, 50, 54, 255)
    soft = (93, 97, 102, 255)
    w = max(2, size // 9)

    if kind == "compound":
        pts = [(size * 0.50, size * 0.12), (size * 0.82, size * 0.30), (size * 0.82, size * 0.68),
               (size * 0.50, size * 0.86), (size * 0.18, size * 0.68), (size * 0.18, size * 0.30)]
        draw.line(pts + [pts[0]], fill=ink, width=w)
        draw.ellipse((size * 0.42, size * 0.42, size * 0.58, size * 0.58), fill=soft)
    elif kind == "tecan":
        draw.rounded_rectangle((size * 0.14, size * 0.18, size * 0.86, size * 0.78), radius=3, outline=ink, width=w)
        for r in range(3):
            for c in range(4):
                x = size * (0.30 + c * 0.14)
                y = size * (0.34 + r * 0.14)
                draw.ellipse((x - 1.4, y - 1.4, x + 1.4, y + 1.4), fill=soft)
    elif kind == "chem":
        nodes = [(0.28, 0.34), (0.58, 0.26), (0.72, 0.58), (0.40, 0.70)]
        px = [(size * x, size * y) for x, y in nodes]
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            draw.line((px[a], px[b]), fill=soft, width=w)
        for x, y in px:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=ink)
    elif kind == "pyparse":
        draw.rounded_rectangle((size * 0.24, size * 0.12, size * 0.76, size * 0.86), radius=2, outline=ink, width=w)
        for y in (0.34, 0.48, 0.62):
            draw.line((size * 0.34, size * y, size * 0.66, size * y), fill=soft, width=w)
    elif kind == "modified":
        draw.rounded_rectangle((size * 0.18, size * 0.14, size * 0.62, size * 0.82), radius=2, outline=ink, width=w)
        cx, cy, rr = size * 0.70, size * 0.67, size * 0.16
        draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=ink, width=w)
        draw.ellipse((cx - rr * 0.35, cy - rr * 0.35, cx + rr * 0.35, cy + rr * 0.35), fill=soft)
    elif kind == "template":
        draw.line((size * 0.20, size * 0.30, size * 0.80, size * 0.30), fill=ink, width=w)
        draw.line((size * 0.25, size * 0.58, size * 0.75, size * 0.58), fill=ink, width=w)
        draw.polygon([(size * 0.76, size * 0.22), (size * 0.88, size * 0.30), (size * 0.76, size * 0.38)], fill=ink)
        draw.polygon([(size * 0.24, size * 0.50), (size * 0.12, size * 0.58), (size * 0.24, size * 0.66)], fill=ink)
    elif kind == "pipette":
        draw.rounded_rectangle((size * 0.26, size * 0.10, size * 0.46, size * 0.26), radius=2, outline=ink, width=w)
        draw.line((size * 0.40, size * 0.26, size * 0.72, size * 0.58), fill=ink, width=w + 1)
        draw.line((size * 0.53, size * 0.39, size * 0.66, size * 0.26), fill=soft, width=w)
        draw.line((size * 0.70, size * 0.60, size * 0.84, size * 0.74), fill=ink, width=w)
        draw.polygon(
            [(size * 0.82, size * 0.72), (size * 0.90, size * 0.82), (size * 0.78, size * 0.78)],
            fill=soft,
        )
        draw.ellipse((size * 0.30, size * 0.68, size * 0.40, size * 0.78), fill=soft)
    elif kind == "map":
        for r in range(3):
            for c in range(3):
                x = size * (0.28 + c * 0.22)
                y = size * (0.28 + r * 0.22)
                draw.rectangle((x - 3, y - 3, x + 3, y + 3), outline=ink, width=1)
    else:
        draw.ellipse((size * 0.18, size * 0.18, size * 0.82, size * 0.82), outline=ink, width=w)

    return ImageTk.PhotoImage(img, master=master)


def make_tab_icons(master):
    return {
        "compound": _make_tab_icon(master, "compound"),
        "tecan": _make_tab_icon(master, "tecan"),
        "chem": _make_tab_icon(master, "chem"),
        "pyparse": _make_tab_icon(master, "pyparse"),
        "modified": _make_tab_icon(master, "modified"),
        "template": _make_tab_icon(master, "template"),
        "pipette": _make_tab_icon(master, "pipette"),
        "map": _make_tab_icon(master, "map"),
    }


def _rounded_notebook_tab_image(master, fill: str, outline: str, size: int = 24, radius: int = 6):
    scale = 4
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (scale, scale, (size - 2) * scale, (size - 2) * scale),
        radius=radius * scale,
        fill=fill,
        outline=outline,
        width=scale,
    )
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image, master=master)


def _configure_rounded_notebook_tabs(root, style):
    image_sets = getattr(root, "_xinpilot_rounded_tab_images", None)
    if image_sets is None:
        image_sets = {}
        element_name = "XinPilotRounded.tab"
        normal = _rounded_notebook_tab_image(root, COLORS["panel_alt"], COLORS["line"], size=24, radius=6)
        selected = _rounded_notebook_tab_image(root, COLORS["select"], COLORS["line"], size=24, radius=6)
        active = _rounded_notebook_tab_image(root, COLORS["button_active"], COLORS["line"], size=24, radius=6)
        image_sets[element_name] = (normal, selected, active)
        try:
            style.element_create(
                element_name,
                "image",
                normal,
                ("selected", selected),
                ("active", active),
                border=(7, 7, 7, 7),
                sticky="nsew",
            )
        except tk.TclError:
            pass
        root._xinpilot_rounded_tab_images = image_sets

    try:
        style.layout(
            "Main.TNotebook.Tab",
            [
                (
                    element_name,
                    {
                        "sticky": "nswe",
                        "children": [
                            (
                                "Notebook.padding",
                                {
                                    "side": "top",
                                    "sticky": "nswe",
                                    "children": [("Notebook.label", {"side": "top", "sticky": ""})],
                                },
                            )
                        ],
                    },
                )
            ],
        )
    except tk.TclError:
        pass


def resource_path(relative_path: str) -> Path:
    candidates = [ROOT / relative_path]
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        candidates.append(Path(bundle_dir) / relative_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def configure_modern_theme(root):
    configure_controls(root)
    style = ttk.Style(root)
    style.layout("Main.TNotebook.Tab", style.layout("TNotebook.Tab"))


def style_plain_widgets(widget):
    for child in widget.winfo_children():
        # Labels should blend into their actual parent surface. Preserve explicit
        # backgrounds, which may communicate a scientific or warning state.
        if isinstance(child, ttk.Label) and not str(child.cget("background") or ""):
            try:
                if isinstance(widget, ttk.Widget):
                    parent_style = widget.cget("style") or widget.winfo_class()
                    surface = ttk.Style(widget).lookup(parent_style, "background")
                else:
                    surface = widget.cget("background")
                if surface:
                    child.configure(background=surface)
            except tk.TclError:
                pass
        if isinstance(child, tk.Text):
            child.configure(
                bg=COLORS["panel"],
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                relief="solid",
                bd=1,
                highlightthickness=1,
                highlightbackground=COLORS["line"],
                highlightcolor=COLORS["accent"],
                padx=8,
                pady=6,
                font=("Segoe UI", 10),
            )
        elif isinstance(child, tk.Listbox):
            child.configure(
                bg=COLORS["panel"],
                fg=COLORS["text"],
                selectbackground=COLORS["select"],
                selectforeground=COLORS["text"],
                relief="solid",
                bd=1,
                highlightthickness=1,
                highlightbackground=COLORS["line"],
                highlightcolor=COLORS["accent"],
                font=("Segoe UI", 10),
            )
        elif isinstance(child, ttk.Button):
            current_style = child.cget("style")
            preserve_styles = {
                "Accent.TButton",
                "DrawReaction.TButton",
                "Blue.TButton",
                "Violet.TButton",
                "FileAction.TButton",
                "ChemAction.TButton",
                "ChemAction.TCheckbutton",
                "RowAction.TButton",
                "Danger.TButton",
                "SynthesisSelector.TButton",
                "SynthesisSelectorSelected.TButton",
            }
            if current_style not in preserve_styles:
                child.configure(style="CompoundToolbar.TButton")
        style_plain_widgets(child)


def style_region_widgets(widget, region_prefix: str):
    frame_style = f"{region_prefix}.TFrame"
    label_style = f"{region_prefix}.TLabel"
    muted_style = f"{region_prefix}.Muted.TLabel"
    check_style = f"{region_prefix}.TCheckbutton"
    radio_style = f"{region_prefix}.TRadiobutton"
    for child in widget.winfo_children():
        if isinstance(child, ttk.Frame):
            current = child.cget("style")
            if not current:
                child.configure(style=frame_style)
        elif isinstance(child, ttk.Label):
            current = child.cget("style")
            explicit_bg = str(child.cget("background") or "")
            if explicit_bg:
                style_region_widgets(child, region_prefix)
                continue
            if current == "Muted.TLabel":
                child.configure(style=muted_style)
            elif not current:
                child.configure(style=label_style)
        elif isinstance(child, ttk.Checkbutton):
            current = child.cget("style")
            if not current:
                child.configure(style=check_style)
        elif isinstance(child, ttk.Radiobutton):
            current = child.cget("style")
            if not current:
                child.configure(style=radio_style)
        style_region_widgets(child, region_prefix)


def install_notebook_tab_feedback(root):
    if getattr(root, "_oneclick_tab_feedback_installed", False):
        return
    root._oneclick_tab_feedback_installed = True

    def on_button_release(event):
        widget = event.widget
        if not isinstance(widget, ttk.Button):
            return
        try:
            if "disabled" in widget.state():
                return
            widget.state(["pressed"])
            widget.after(170, lambda w=widget: w.winfo_exists() and w.state(["!pressed"]))
        except Exception:
            pass

    root.bind_class("TButton", "<ButtonRelease-1>", on_button_release, add="+")


ROLE_PATTERNS = {
    "suzuki": {
        "Nucleophile": ["[B]([O])[O]", "[B;X3]", "[#6][B;X3]"],
        "Electrophile": ["[c][Cl,Br,I]", "[c]-[Cl,Br,I]", "[$([C;X3]([#6])=[#6])][Cl,Br,I]"],
    },
    "buchwald_hartwig": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[c][Cl,Br,I]"],
    },
    "ullmann_cn": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[c][Cl,Br,I]"],
    },
    "snar": {
        "Nucleophile": ["[N;H1,H2]", "[O;H1]", "[S;H1]"],
        "Electrophile": ["[c][F,Cl]"],
    },
    "amide_coupling": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[C](=O)[O;H1]"],
    },
    "sulfonamide_formation": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["S(=O)(=O)Cl"],
    },
    "sonogashira": {
        "Nucleophile": ["[C]#[CH]"],
        "Electrophile": ["[c,C][Cl,Br,I]"],
    },
    "heck": {
        "Nucleophile": ["C=C"],
        "Electrophile": ["[c,C][Cl,Br,I]"],
    },
    "sn2_alkylation": {
        "Nucleophile": ["[N;H1,H2]", "[O;H1]", "[S;H1]"],
        "Electrophile": ["[#6][Cl,Br,I]"],
    },
    "click_triazole": {
        "Nucleophile": ["[C]#C"],
        "Electrophile": ["N=[N+]=[N-]"],
    },
    "acyl_halide_amine_coupling": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[C](=O)[Cl,Br,I]"],
    },
    "acyl_halide_alcohol_coupling": {
        "Nucleophile": ["[O;H1]"],
        "Electrophile": ["[C](=O)[Cl,Br,I]"],
    },
    "esterification": {
        "Nucleophile": ["[O;H1]"],
        "Electrophile": ["[C](=O)[O;H1]"],
    },
    "mitsunobu": {
        "Nucleophile": ["[O,N,S;H1]"],
        "Electrophile": ["[O;H1]"],
    },
    "williamson_ether": {
        "Nucleophile": ["[O;H1]"],
        "Electrophile": ["[#6][Cl,Br,I]"],
    },
    "boc_protection": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["C(=O)OC(=O)"],
    },
    "chan_lam": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[c][B]([O])[O]", "[#6][B]([O])[O]"],
    },
    "anhydride_amine_coupling": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["C(=O)OC(=O)"],
    },
    "activated_ester_amide": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["C(=O)O[#6]"],
    },
    "reductive_amination": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[C](=O)"],
    },
    "reductive_amination_aldehyde": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[CH](=O)"],
    },
    "reductive_amination_ketone": {
        "Nucleophile": ["[N;H1,H2]"],
        "Electrophile": ["[#6][C](=O)[#6]"],
    },
    "nitro_reduction": {"Electrophile": ["[N+](=O)[O-]"]},
    "alcohol_oxidation": {"Electrophile": ["[C;H1,H2][O;H1]"]},
    "carbonyl_reduction": {"Electrophile": ["[C]=[O]"]},
    "alkene_hydrogenation": {"Electrophile": ["[C]=[C]"]},
    "ester_hydrolysis": {"Electrophile": ["C(=O)O[#6]"]},
    "amide_hydrolysis": {"Electrophile": ["C(=O)N"]},
    "cbz_deprotection": {"Electrophile": ["NC(=O)OCc1ccccc1"]},
    "silyl_ether_deprotection": {"Electrophile": ["O[Si]([#6])([#6])[#6]"]},
    "carbamate_isocyanate": {
        "Electrophile": ["N=C=O"],
        "Nucleophile": ["[O;H1]"],
    },
    "thiourea_isothiocyanate": {
        "Electrophile": ["N=C=S"],
        "Nucleophile": ["[N;H1,H2]"],
    },
    "alcohol_sulfonylation": {
        "Electrophile": ["S(=O)(=O)Cl"],
        "Nucleophile": ["[O;H1]"],
    },
    "n_alkylation": {
        "Electrophile": ["[#6][Cl,Br,I]"],
        "Nucleophile": ["[N;H1,H2]"],
    },
    "o_alkylation": {
        "Electrophile": ["[#6][Cl,Br,I]"],
        "Nucleophile": ["[O;H1]"],
    },
    "oxime_formation": {
        "Electrophile": ["[C]=[O]"],
        "Nucleophile": ["[N;H2][O;H1]"],
    },
    "amine_epoxide_opening": {
        "Electrophile": ["C1OC1"],
        "Nucleophile": ["[N;H1,H2]"],
    },
}


SUZUKI_HALIDE_QUERY = Chem.MolFromSmarts("[#6][Cl,Br,I]") if Chem is not None else None
SUZUKI_BORON_QUERY = Chem.MolFromSmarts("[#6][B]([O])[O]") if Chem is not None else None
SUZUKI_GENERIC_SMARTS = "[*:1][Br,Cl,I:2].[*:3]B([O])[O]>>[*:1][*:3]"


def _compile_patterns(patterns: List[str]):
    out = []
    for patt in patterns:
        mol = Chem.MolFromSmarts(patt)
        if mol is not None:
            out.append(mol)
    return out


def _record_values(record) -> Dict[str, str]:
    return getattr(record, "values", {}) or {}


__all__ = [name for name in globals() if not name.startswith("__")]


