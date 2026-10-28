import csv
import os
import re
import sys
from typing import Dict, List, Tuple

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

INPUT_DIR = "input"
OUTPUT_DIR = "output"
NU_CSV = os.path.join(INPUT_DIR, "nu.csv")
EL_CSV = os.path.join(INPUT_DIR, "el.csv")
NU_MAP_CSV = os.path.join(INPUT_DIR, "nu_map.csv")
EL_MAP_CSV = os.path.join(INPUT_DIR, "el_map.csv")
PROD_MAP_CSV = os.path.join(INPUT_DIR, "prod_map.csv")
OUT_CSV = os.path.join(OUTPUT_DIR, "curtius_products.csv")
SKIP_CSV = os.path.join(OUTPUT_DIR, "curtius_skipped_rows.csv")

PROTON_MASS = 1.00727646688
SODIUM_MASS = 22.989218
CURTIUS_RXN = AllChem.ReactionFromSmarts("[*:2]-[C:1](=O)[O;H1].[N;H1,H2:4]>>[*:2]-[N]-[C:1](=O)-[N:4]")
WELL_REF_RE = re.compile(r"^[A-Z][0-9]+$")


def pick_name_field(fields: List[str]) -> str | None:
    m = {f.lower().strip(): f for f in fields}
    for k in ["name", "compound name", "compound", "label", "title"]:
        if k in m:
            return m[k]
    return None


def load_details_csv(path: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            raise ValueError(f"No header in {path}")
        name_key = pick_name_field(r.fieldnames)
        for i, row in enumerate(r, start=2):
            cid = (row.get("ID") or "").strip()
            smi = (row.get("SMILES") or "").strip()
            if not cid or not smi:
                continue
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                raise ValueError(f"Invalid SMILES in {path} line {i}: {smi}")
            out[cid] = {
                "id": cid,
                "name": (row.get(name_key) or "").strip() if name_key else "",
                "mol": mol,
                "smiles": Chem.MolToSmiles(mol, canonical=True),
            }
    return out


def read_map_csv(path: str) -> Tuple[List[str], List[str], Dict[Tuple[int, int], str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        col_labels = [cell.strip() for cell in header[1:]]
        row_labels: List[str] = []
        cells: Dict[Tuple[int, int], str] = {}
        for row_idx, row in enumerate(reader):
            row_label = row[0].strip().upper() if row else ""
            row_labels.append(row_label)
            values = row[1:] if len(row) > 1 else []
            if len(values) < len(col_labels):
                values.extend([""] * (len(col_labels) - len(values)))
            for col_idx, value in enumerate(values[: len(col_labels)]):
                value = value.strip()
                if value:
                    cells[(row_idx, col_idx)] = value
    return col_labels, row_labels, cells


def make_well(row_label: str, col_label: str, row_idx: int, col_idx: int) -> str:
    row_label = row_label.strip().upper()
    col_label = col_label.strip()
    if row_label and col_label:
        candidate = f"{row_label}{col_label}"
        if WELL_REF_RE.match(candidate):
            return candidate
    return f"R{row_idx + 1}C{col_idx + 1}"


def product_smiles(electrophile: Chem.Mol, nucleophile: Chem.Mol) -> List[str]:
    products = CURTIUS_RXN.RunReactants((electrophile, nucleophile))
    smiles_list: List[str] = []
    for product_set in products:
        if not product_set:
            continue
        product = product_set[0]
        try:
            Chem.SanitizeMol(product)
        except Exception:
            continue
        smiles_list.append(Chem.MolToSmiles(product, canonical=True))
    return sorted(set(smiles_list))


def main() -> int:
    required_paths = [NU_CSV, EL_CSV, NU_MAP_CSV, EL_MAP_CSV, PROD_MAP_CSV]
    missing = [path for path in required_paths if not os.path.exists(path)]
    if missing:
        print("Missing required input file(s):", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 1

    nucleophiles = load_details_csv(NU_CSV)
    electrophiles = load_details_csv(EL_CSV)

    prod_cols, prod_rows, prod_cells = read_map_csv(PROD_MAP_CSV)
    _, _, nu_cells = read_map_csv(NU_MAP_CSV)
    _, _, el_cells = read_map_csv(EL_MAP_CSV)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    skipped = []

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "nucleophile ID", "nucleophile name", "nucleophile SMILES",
            "electrophile ID", "electrophile name", "electrophile SMILES",
            "Product ID", "product SMILES", "well",
            "exact mass", "molecular weight", "molecular formula",
            "positive ion m/z: [M+H]+", "positive ion m/z: [M+Na]+", "negative ion m/z: [M-H]-",
        ])

        for (row_idx, col_idx), product_id in sorted(prod_cells.items()):
            nucleophile_id = (nu_cells.get((row_idx, col_idx)) or "").strip()
            electrophile_id = (el_cells.get((row_idx, col_idx)) or "").strip()
            well = make_well(prod_rows[row_idx] if row_idx < len(prod_rows) else "", prod_cols[col_idx] if col_idx < len(prod_cols) else "", row_idx, col_idx)

            if not nucleophile_id or not electrophile_id:
                skipped.append([well, product_id, nucleophile_id, electrophile_id, "missing_map_id"])
                continue
            if nucleophile_id not in nucleophiles:
                skipped.append([well, product_id, nucleophile_id, electrophile_id, "nucleophile_not_found_in_nu_csv"])
                continue
            if electrophile_id not in electrophiles:
                skipped.append([well, product_id, nucleophile_id, electrophile_id, "electrophile_not_found_in_el_csv"])
                continue

            products = product_smiles(electrophiles[electrophile_id]["mol"], nucleophiles[nucleophile_id]["mol"])
            if not products:
                skipped.append([well, product_id, nucleophile_id, electrophile_id, "no_product_generated"])
                continue

            product_smiles_value = products[0]
            product_mol = Chem.MolFromSmiles(product_smiles_value)
            exact_mass = rdMolDescriptors.CalcExactMolWt(product_mol)
            molecular_weight = Descriptors.MolWt(product_mol)
            molecular_formula = rdMolDescriptors.CalcMolFormula(product_mol)

            writer.writerow([
                nucleophile_id,
                nucleophiles[nucleophile_id]["name"],
                nucleophiles[nucleophile_id]["smiles"],
                electrophile_id,
                electrophiles[electrophile_id]["name"],
                electrophiles[electrophile_id]["smiles"],
                product_id,
                product_smiles_value,
                well,
                f"{exact_mass:.6f}",
                f"{molecular_weight:.3f}",
                molecular_formula,
                f"{exact_mass + PROTON_MASS:.6f}",
                f"{exact_mass + SODIUM_MASS:.6f}",
                f"{exact_mass - PROTON_MASS:.6f}",
            ])

    with open(SKIP_CSV, "w", newline="", encoding="utf-8") as sf:
        sw = csv.writer(sf)
        sw.writerow(["well", "product_id", "nucleophile_id", "electrophile_id", "reason"])
        sw.writerows(skipped)

    print(f"Wrote: {OUT_CSV}")
    print(f"Skipped rows report: {SKIP_CSV} ({len(skipped)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
