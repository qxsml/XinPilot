import csv
import os
import re
from typing import Dict, Tuple, List

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

PROTON = 1.00727646688
SODIUM = 22.989218
WELL_RE = re.compile(r"^[A-Z][0-9]+$")


def _pick_name_field(fieldnames: List[str]) -> str | None:
    keys = {f.lower().strip(): f for f in fieldnames}
    for cand in ["name", "compound name", "compound", "id name", "label", "title"]:
        if cand in keys:
            return keys[cand]
    return None


def load_details(path: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            raise ValueError(f"No header found in {path}")

        field_map = {fn.lower().strip(): fn for fn in r.fieldnames if fn}
        id_key = field_map.get("id")
        smiles_key = field_map.get("smiles")
        if not id_key or not smiles_key:
            raise ValueError(f"{path} must contain ID and SMILES columns (case-insensitive)")

        name_key = _pick_name_field(r.fieldnames)
        for i, row in enumerate(r, start=2):
            cid = (row.get(id_key) or "").strip()
            smi = (row.get(smiles_key) or "").strip()
            if not cid or not smi:
                continue
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                raise ValueError(f"Invalid SMILES in {path} line {i}: {smi}")
            out[cid] = {
                "id": cid,
                "smiles": Chem.MolToSmiles(mol, canonical=True),
                "mol": mol,
                "name": (row.get(name_key) or "").strip() if name_key else "",
            }
    return out


def read_map(path: str) -> Tuple[List[str], List[str], Dict[Tuple[int, int], str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        raw = list(csv.reader(f))

    # Find first real map header row: Row\Col,1,2,... (or similar)
    hidx = None
    for i, row in enumerate(raw):
        if len(row) < 2:
            continue
        first = (row[0] or "").strip().lower()
        if first in {"row\\col", "row/col"} and any((c or "").strip() for c in row[1:]):
            hidx = i
            break
    if hidx is None:
        # Fallback to first row for legacy single-table files
        hidx = 0

    header = raw[hidx] if hidx < len(raw) else []
    cols = [x.strip() for x in header[1:]]
    rows: List[str] = []
    m: Dict[Tuple[int, int], str] = {}

    data_i = 0
    for row in raw[hidx + 1 :]:
        if not any((c or "").strip() for c in row):
            break
        row_label = (row[0] if row else "").strip().upper()
        if not row_label:
            continue
        rows.append(row_label)
        vals = row[1:] if len(row) > 1 else []
        vals += [""] * (len(cols) - len(vals))
        for j, v in enumerate(vals[: len(cols)]):
            v = v.strip()
            if v:
                m[(data_i, j)] = v
        data_i += 1
    return cols, rows, m


def well(rows: List[str], cols: List[str], r: int, c: int) -> str:
    rr = rows[r] if r < len(rows) else ""
    cc = cols[c] if c < len(cols) else ""
    cand = f"{rr}{cc}".strip()
    if WELL_RE.match(cand):
        return cand
    return f"R{r+1}C{c+1}"


def _unique_products(rxn, el_mol, nu_mol) -> List[str]:
    out = []
    for pset in rxn.RunReactants((el_mol, nu_mol)):
        if not pset:
            continue
        p = pset[0]
        try:
            Chem.SanitizeMol(p)
        except Exception:
            continue
        out.append(Chem.MolToSmiles(p, canonical=True))
    return sorted(set(out))


def _run_unimolecular(smarts: str, mol) -> List[str]:
    rxn = AllChem.ReactionFromSmarts(smarts)
    out = []
    for pset in rxn.RunReactants((mol,)):
        if not pset:
            continue
        p = pset[0]
        try:
            Chem.SanitizeMol(p)
        except Exception:
            continue
        out.append(Chem.MolToSmiles(p, canonical=True))
    return sorted(set(out))


def _run_pair(smarts: str, first_mol, second_mol) -> List[str]:
    rxn = AllChem.ReactionFromSmarts(smarts)
    return _unique_products(rxn, first_mol, second_mol)


def _run_homodimer(smarts: str, mol) -> List[str]:
    rxn = AllChem.ReactionFromSmarts(smarts)
    out = []
    for pset in rxn.RunReactants((mol, mol)):
        if not pset:
            continue
        p = pset[0]
        try:
            Chem.SanitizeMol(p)
        except Exception:
            continue
        out.append(Chem.MolToSmiles(p, canonical=True))
    return sorted(set(out))


def _mass_triplet(smiles: str) -> Tuple[str, str, str]:
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        return smiles, "", ""
    ex = rdMolDescriptors.CalcExactMolWt(m)
    return Chem.MolToSmiles(m, canonical=True), f"{ex:.6f}", f"{ex + PROTON:.6f}"


def _predict_side_products(label: str, el_mol, nu_mol) -> List[dict]:
    # Chemistry-informed heuristics: conservative and reaction-aware where possible.
    # tuple: (type, mode, smarts, source)
    # mode: uni (single-reactant transform), homo (homodimerization)
    rules = [
        # broadly applicable transforms when motifs exist
        ("electrophile_dehalogenation", "uni", "[*:1][Br,Cl,I:2]>>[*:1][H]", "el"),
        ("sulfonyl_chloride_hydrolysis", "uni", "[*:1]S(=O)(=O)[Cl:2]>>[*:1]S(=O)(=O)O", "el"),
        ("acyl_chloride_hydrolysis", "uni", "[*:1]C(=O)[Cl:2]>>[*:1]C(=O)O", "el"),
        ("boronic_acid_protodeboronation", "uni", "[*:1]B([O])[O]>>[*:1][H]", "nu"),
    ]

    # cross-coupling families
    if label in {"suzuki", "sonogashira", "heck", "buchwald_hartwig", "snar"}:
        rules.append(("aryl_halide_homocoupling_dimer", "homo", "[*:1][Br,Cl,I,F:2].[*:3][Br,Cl,I,F:4]>>[*:1][*:3]", "el"))

    if label == "suzuki":
        rules.extend([
            ("boronic_acid_homocoupling_dimer", "homo", "[*:1]B([O])[O].[*:3]B([O])[O]>>[*:1][*:3]", "nu"),
        ])

    if label in {"sonogashira", "click_triazole"}:
        # terminal alkyne oxidative homocoupling (Glaser-type)
        rules.append(("terminal_alkyne_homocoupling_diyne", "homo", "[*:1]C#[CH:2].[*:3]C#[CH:4]>>[*:1]C#[C:2][C:3]#[C:4]", "nu"))

    if label in {"sulfonamide_formation"}:
        rules.append(("sulfonyl_chloride_hydrolysis", "uni", "[*:1]S(=O)(=O)[Cl:2]>>[*:1]S(=O)(=O)O", "el"))

    # Force acyl-halide hydrolysis prediction for acyl-halide coupling workflows.
    # Keep a dedicated broad rule here so side-product reporting is consistent.
    if label in {"acyl_halide_amine_coupling", "acyl_halide_alcohol_coupling"}:
        rules.append(("acyl_halide_hydrolysis", "uni", "[*:1]C(=O)[Cl,Br,I:2]>>[*:1]C(=O)O", "el"))

    if label in {"amide_coupling", "esterification"}:
        # dehydrative dimerization of acids to anhydrides
        rules.append(("carboxylic_acid_anhydride_dimer", "homo", "[*:1]C(=O)O.[*:3]C(=O)O>>[*:1]C(=O)OC(=O)[*:3]", "el"))

    if label in {"reductive_amination"}:
        # imine / iminium precursor from carbonyl + amine
        rules.append((
            "imine_intermediate",
            "pair",
            "[C;H0,H1:2](=O).[N;H1,H2:4]>>[C:2]=[N:4]",
            "el_nu",
        ))

    seen = set()
    side_products: List[dict] = []

    for rule_name, kind, smarts, source in rules:
        mol = el_mol if source == "el" else nu_mol
        try:
            if kind == "uni":
                smis = _run_unimolecular(smarts, mol)
            elif kind == "pair":
                smis = _run_pair(smarts, el_mol, nu_mol)
            else:
                smis = _run_homodimer(smarts, mol)
        except Exception:
            smis = []

        for smi in smis:
            can_smi, ex, mh = _mass_triplet(smi)
            if not can_smi or can_smi in seen:
                continue
            seen.add(can_smi)
            side_products.append(
                {
                    "type": rule_name,
                    "smiles": can_smi,
                    "exact_mass": ex,
                    "mass_plus_H": mh,
                }
            )

    return side_products


def run(smarts: str, outname: str, label: str) -> int:
    required = ["input/nu.csv", "input/el.csv", "input/nu_map.csv", "input/el_map.csv", "input/prod_map.csv"]
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        print("Missing input files:")
        for m in missing:
            print(" -", m)
        return 1

    nu = load_details("input/nu.csv")
    el = load_details("input/el.csv")

    pc, pr, pm = read_map("input/prod_map.csv")
    _, _, nm = read_map("input/nu_map.csv")
    _, _, em = read_map("input/el_map.csv")

    rxn = AllChem.ReactionFromSmarts(smarts)
    os.makedirs("output", exist_ok=True)

    skipped_path = os.path.join("output", f"{label}_skipped_rows.csv")
    skipped_rows = []
    output_rows = []

    for (r, c), pid in sorted(pm.items()):
        nid = (nm.get((r, c), "") or "").strip()
        eid = (em.get((r, c), "") or "").strip()
        ww = well(pr, pc, r, c)

        if not nid or not eid:
            skipped_rows.append([ww, pid, nid, eid, "missing_map_id"])
            continue
        if nid not in nu:
            skipped_rows.append([ww, pid, nid, eid, "nucleophile_not_found_in_nu_csv"])
            continue
        if eid not in el:
            skipped_rows.append([ww, pid, nid, eid, "electrophile_not_found_in_el_csv"])
            continue

        prod_smiles = _unique_products(rxn, el[eid]["mol"], nu[nid]["mol"])
        if not prod_smiles:
            skipped_rows.append([ww, pid, nid, eid, "no_product_generated"])
            continue

        smi = prod_smiles[0]
        m = Chem.MolFromSmiles(smi)
        ex = rdMolDescriptors.CalcExactMolWt(m)
        mw = Descriptors.MolWt(m)
        mf = rdMolDescriptors.CalcMolFormula(m)

        side_products = _predict_side_products(label, el[eid]["mol"], nu[nid]["mol"])

        output_rows.append(
            {
                "base": [
                    label,
                    nid,
                    nu[nid]["name"],
                    nu[nid]["smiles"],
                    eid,
                    el[eid]["name"],
                    el[eid]["smiles"],
                    pid,
                    smi,
                    ww,
                    f"{ex:.6f}",
                    f"{mw:.3f}",
                    mf,
                    f"{ex + PROTON:.6f}",
                    f"{ex + SODIUM:.6f}",
                    f"{ex - PROTON:.6f}",
                ],
                "side_products": side_products,
            }
        )

    max_side = max((len(r["side_products"]) for r in output_rows), default=0)

    with open(outname, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = [
            "reaction",
            "nucleophile ID",
            "nucleophile name",
            "nucleophile SMILES",
            "electrophile ID",
            "electrophile name",
            "electrophile SMILES",
            "Product ID",
            "product SMILES",
            "well",
            "exact mass",
            "molecular weight",
            "molecular formula",
            "positive ion m/z: [M+H]+",
            "positive ion m/z: [M+Na]+",
            "negative ion m/z: [M-H]-",
        ]
        for i in range(1, max_side + 1):
            header.extend(
                [
                    f"side product {i} type",
                    f"side product {i} SMILES",
                    f"side product {i} exact mass",
                    f"side product {i} [M+H]+",
                ]
            )
        w.writerow(header)

        for row in output_rows:
            out = list(row["base"])
            for sp in row["side_products"]:
                out.extend([sp["type"], sp["smiles"], sp["exact_mass"], sp["mass_plus_H"]])
            missing_blocks = max_side - len(row["side_products"])
            for _ in range(missing_blocks):
                out.extend(["", "", "", ""])
            w.writerow(out)

    with open(skipped_path, "w", newline="", encoding="utf-8") as sf:
        sw = csv.writer(sf)
        sw.writerow(["well", "product_id", "nucleophile_id", "electrophile_id", "reason"])
        sw.writerows(skipped_rows)

    print(f"Wrote: {outname}")
    print(f"Skipped rows report: {skipped_path} ({len(skipped_rows)} rows)")
    return 0
