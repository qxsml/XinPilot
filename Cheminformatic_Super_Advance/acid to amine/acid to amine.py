"""
Convert carboxylic acid SMILES (R-C(=O)OH) to hydrolyzed Curtius product SMILES.

Hydrolyzed Curtius product is modeled as the amine (R-NH2).
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from rdkit import Chem
except ImportError:  # pragma: no cover - depends on local environment
    Chem = None  # type: ignore[assignment]


if Chem is not None:
    CARBOXYLIC_ACID_QUERY = Chem.MolFromSmarts("[CX3](=O)[OX2H1,OX1-]")
    AMINE_PRODUCT = Chem.MolFromSmiles("N")
else:  # pragma: no cover - depends on local environment
    CARBOXYLIC_ACID_QUERY = None
    AMINE_PRODUCT = None

if CARBOXYLIC_ACID_QUERY is None or AMINE_PRODUCT is None:  # pragma: no cover
    _PATTERN_ERROR = "Failed to build RDKit SMARTS/SMILES patterns."
else:
    _PATTERN_ERROR = ""

DEFAULT_INPUT_PATH = Path(__file__).resolve().parent / "input" / "acid.csv"


@dataclass
class InputRow:
    input_id: str
    input_smiles: str


@dataclass
class ConversionResult:
    input_id: str
    input_smiles: str
    output_smiles: str
    acid_sites: int
    status: str


def hydrolyze_acid_smiles(smiles: str) -> ConversionResult:
    if Chem is None:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "RDKit is required. Install it first, e.g. with "
            "`conda install -c conda-forge rdkit`."
        )
    if _PATTERN_ERROR:
        raise RuntimeError(_PATTERN_ERROR)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ConversionResult("", smiles, "", 0, "invalid_input_smiles")

    site_count = len(mol.GetSubstructMatches(CARBOXYLIC_ACID_QUERY))
    if site_count == 0:
        return ConversionResult(
            "", smiles, Chem.MolToSmiles(mol, canonical=True), 0, "no_carboxylic_acid"
        )

    replaced = Chem.ReplaceSubstructs(
        mol,
        CARBOXYLIC_ACID_QUERY,
        AMINE_PRODUCT,
        replaceAll=True,
    )
    if not replaced:
        return ConversionResult("", smiles, "", site_count, "replacement_failed")

    product_mol = replaced[0]
    try:
        Chem.SanitizeMol(product_mol)
    except Exception:
        return ConversionResult("", smiles, "", site_count, "invalid_product")

    return ConversionResult(
        "",
        smiles,
        Chem.MolToSmiles(product_mol, canonical=True),
        site_count,
        "ok",
    )


def _read_text_smiles(path: Path) -> list[InputRow]:
    rows: list[InputRow] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            rows.append(InputRow("", stripped.split()[0]))
    return rows


def _find_column(fieldnames: list[str], preferred: str, fallback_contains: str) -> str | None:
    lower_to_name = {name.strip().lower(): name for name in fieldnames}
    if preferred.lower() in lower_to_name:
        return lower_to_name[preferred.lower()]
    for name in fieldnames:
        if fallback_contains in name.lower():
            return name
    return None


def _read_csv_smiles(path: Path, smiles_column: str, id_column: str) -> list[InputRow]:
    rows: list[InputRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path} has no header row.")

        smiles_key = _find_column(reader.fieldnames, smiles_column, "smiles")
        if smiles_key is None:
            raise ValueError(
                f"Could not find a SMILES column in {path}. "
                f"Expected '{smiles_column}' or any header containing 'smiles'."
            )
        id_key = _find_column(reader.fieldnames, id_column, "id")

        for row in reader:
            smiles = (row.get(smiles_key) or "").strip()
            if not smiles:
                continue
            input_id = (row.get(id_key) or "").strip() if id_key else ""
            rows.append(InputRow(input_id, smiles))
    return rows


def _read_smiles_from_path(path: Path, smiles_column: str, id_column: str) -> list[InputRow]:
    if path.suffix.lower() == ".csv":
        return _read_csv_smiles(path, smiles_column, id_column)
    return _read_text_smiles(path)


def _read_input_rows(args: argparse.Namespace) -> list[InputRow]:
    rows: list[InputRow] = []

    if args.smiles:
        rows.extend(InputRow("", smi) for smi in args.smiles)

    if args.input:
        rows.extend(_read_smiles_from_path(args.input, args.smiles_column, args.id_column))

    if not rows and not sys.stdin.isatty():
        for line in sys.stdin:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            rows.append(InputRow("", stripped.split()[0]))

    if not rows and DEFAULT_INPUT_PATH.exists():
        rows.extend(
            _read_smiles_from_path(DEFAULT_INPUT_PATH, args.smiles_column, args.id_column)
        )

    if not rows:
        raise ValueError(
            "No SMILES provided. Use positional SMILES, --input, stdin, "
            "or create input/acid.csv."
        )

    return rows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert acid SMILES to hydrolyzed Curtius amine product SMILES."
    )
    parser.add_argument("smiles", nargs="*", help="One or more acid SMILES strings to convert.")
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        help="Input file. Supports CSV (uses --smiles-column) or text (one SMILES per line).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional CSV output path. If omitted, prints TSV to stdout.",
    )
    parser.add_argument(
        "--smiles-column",
        default="SMILES",
        help="CSV SMILES column name (default: SMILES).",
    )
    parser.add_argument(
        "--id-column",
        default="ID",
        help="CSV ID column name (default: ID).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if Chem is None:
        parser.error(
            "RDKit is not installed. Install it first, e.g. "
            "`conda install -c conda-forge rdkit`."
        )
    if _PATTERN_ERROR:
        parser.error(_PATTERN_ERROR)

    try:
        input_rows = _read_input_rows(args)
    except ValueError as exc:
        parser.error(str(exc))

    results: list[ConversionResult] = []
    for row in input_rows:
        result = hydrolyze_acid_smiles(row.input_smiles)
        result.input_id = row.input_id
        results.append(result)

    fieldnames = ["input_id", "input_smiles", "output_smiles", "acid_sites", "status"]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.__dict__ for result in results)
        return 0

    print("\t".join(fieldnames))
    for result in results:
        print(
            f"{result.input_id}\t{result.input_smiles}\t"
            f"{result.output_smiles}\t{result.acid_sites}\t{result.status}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
