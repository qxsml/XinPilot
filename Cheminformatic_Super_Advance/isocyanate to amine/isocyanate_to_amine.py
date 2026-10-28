#!/usr/bin/env python3
"""
Convert isocyanate SMILES (R-N=C=O) to hydrolyzed product SMILES.

Default product is the amine (R-NH2), which is the usual final product of
isocyanate hydrolysis. You can switch to carbamic acid output if needed.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from rdkit import Chem
except ModuleNotFoundError as exc:
    raise SystemExit(
        "RDKit is required. Install with conda (recommended) or pip before running this script."
    ) from exc


ISOCYANATE_QUERY = Chem.MolFromSmarts("[N]=[C]=[O]")
PRODUCT_SMILES = {
    "amine": "N",
    "carbamic_acid": "NC(=O)O",
}
PRODUCT_MOLS = {name: Chem.MolFromSmiles(smi) for name, smi in PRODUCT_SMILES.items()}

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = SCRIPT_DIR / "input"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_SMILES_COLUMN_CANDIDATES = (
    "SMILES",
    "smiles",
    "Smiles",
    "canonical_smiles",
    "CanonicalSMILES",
)

if ISOCYANATE_QUERY is None or any(mol is None for mol in PRODUCT_MOLS.values()):
    raise RuntimeError("Failed to build RDKit SMARTS/SMILES patterns.")


@dataclass
class ConversionResult:
    input_smiles: str
    output_smiles: str
    isocyanate_sites: int
    status: str


@dataclass
class CsvProcessSummary:
    input_path: Path
    output_path: Path
    rows_total: int
    rows_with_isocyanate: int
    rows_ok: int


def hydrolyze_isocyanate_smiles(smiles: str, product: str = "amine") -> ConversionResult:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ConversionResult(smiles, "", 0, "invalid_input_smiles")

    site_count = len(mol.GetSubstructMatches(ISOCYANATE_QUERY))
    if site_count == 0:
        return ConversionResult(smiles, Chem.MolToSmiles(mol, canonical=True), 0, "no_isocyanate")

    replacement = PRODUCT_MOLS[product]
    replaced = Chem.ReplaceSubstructs(
        mol,
        ISOCYANATE_QUERY,
        replacement,
        replaceAll=True,
    )
    if not replaced:
        return ConversionResult(smiles, "", site_count, "replacement_failed")

    product_mol = replaced[0]
    try:
        Chem.SanitizeMol(product_mol)
    except Exception:
        return ConversionResult(smiles, "", site_count, "invalid_product")

    return ConversionResult(
        input_smiles=smiles,
        output_smiles=Chem.MolToSmiles(product_mol, canonical=True),
        isocyanate_sites=site_count,
        status="ok",
    )


def _read_smiles_from_path(path: Path) -> list[str]:
    smiles = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            smiles.append(stripped.split()[0])
    return smiles


def _read_input_smiles(args: argparse.Namespace) -> list[str]:
    smiles: list[str] = []

    if args.smiles:
        smiles.extend(args.smiles)

    if args.input:
        smiles.extend(_read_smiles_from_path(args.input))

    if not smiles and not sys.stdin.isatty():
        for line in sys.stdin:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            smiles.append(stripped.split()[0])

    if not smiles:
        raise ValueError("No SMILES provided. Use positional SMILES, --input, or stdin.")

    return smiles


def _should_use_csv_mode(args: argparse.Namespace) -> bool:
    if args.smiles:
        return False
    if not sys.stdin.isatty():
        return False
    if args.input is None:
        return True
    return args.input.suffix.lower() == ".csv" or args.input.is_dir()


def _get_csv_inputs(input_arg: Path | None) -> list[Path]:
    input_path = input_arg if input_arg is not None else DEFAULT_INPUT_DIR

    if not input_path.exists():
        raise ValueError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() != ".csv":
            raise ValueError(f"CSV mode expects a .csv file or directory, got: {input_path}")
        return [input_path]

    csv_files = sorted(path for path in input_path.glob("*.csv") if path.is_file())
    if not csv_files:
        raise ValueError(f"No CSV files found in: {input_path}")
    return csv_files


def _resolve_csv_outputs(csv_inputs: list[Path], output_arg: Path | None) -> dict[Path, Path]:
    if output_arg is None:
        output_dir = DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        return {path: output_dir / f"{path.stem}_hydrolyzed.csv" for path in csv_inputs}

    if len(csv_inputs) == 1 and output_arg.suffix.lower() == ".csv":
        output_arg.parent.mkdir(parents=True, exist_ok=True)
        return {csv_inputs[0]: output_arg}

    if output_arg.suffix.lower() == ".csv" and len(csv_inputs) > 1:
        raise ValueError("When processing multiple CSV files, --output must be a directory.")

    output_arg.mkdir(parents=True, exist_ok=True)
    return {path: output_arg / f"{path.stem}_hydrolyzed.csv" for path in csv_inputs}


def _pick_smiles_column(fieldnames: list[str], smiles_column: str | None) -> str:
    if smiles_column:
        if smiles_column in fieldnames:
            return smiles_column
        for name in fieldnames:
            if name.lower() == smiles_column.lower():
                return name
        raise ValueError(f"SMILES column '{smiles_column}' not found. Columns: {fieldnames}")

    fieldname_map = {name.lower(): name for name in fieldnames}
    for candidate in DEFAULT_SMILES_COLUMN_CANDIDATES:
        found = fieldname_map.get(candidate.lower())
        if found:
            return found

    raise ValueError(
        "Could not auto-detect SMILES column. "
        f"Use --smiles-column. Available columns: {fieldnames}"
    )


def _convert_csv(
    input_path: Path,
    output_path: Path,
    product: str,
    smiles_column: str | None,
    output_column: str,
    sites_column: str,
    status_column: str,
) -> CsvProcessSummary:
    rows_total = 0
    rows_with_isocyanate = 0
    rows_ok = 0

    with input_path.open("r", encoding="utf-8", newline="") as in_handle:
        reader = csv.DictReader(in_handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {input_path}")

        smiles_col = _pick_smiles_column(reader.fieldnames, smiles_column)
        output_fields = list(reader.fieldnames)
        for field in (output_column, sites_column, status_column):
            if field not in output_fields:
                output_fields.append(field)

        with output_path.open("w", encoding="utf-8", newline="") as out_handle:
            writer = csv.DictWriter(out_handle, fieldnames=output_fields)
            writer.writeheader()

            for row in reader:
                rows_total += 1
                source_smiles = (row.get(smiles_col) or "").strip()
                result = hydrolyze_isocyanate_smiles(source_smiles, product=product)
                if result.isocyanate_sites > 0:
                    rows_with_isocyanate += 1
                if result.status == "ok":
                    rows_ok += 1

                row[output_column] = result.output_smiles
                row[sites_column] = str(result.isocyanate_sites)
                row[status_column] = result.status
                writer.writerow(row)

    return CsvProcessSummary(
        input_path=input_path,
        output_path=output_path,
        rows_total=rows_total,
        rows_with_isocyanate=rows_with_isocyanate,
        rows_ok=rows_ok,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert isocyanate SMILES to hydrolyzed products. "
            "If no SMILES/stdin are provided, all CSV files in ./input are processed."
        )
    )
    parser.add_argument(
        "smiles",
        nargs="*",
        help="One or more SMILES strings to convert.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        help=(
            "Input source. For text mode: file with one SMILES per line. "
            "For CSV mode: .csv file or directory containing .csv files. "
            "Default CSV directory is ./input."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Output destination. For text mode: CSV file path. "
            "For CSV mode: output CSV file path (single input) or output directory. "
            "Default CSV output directory is ./output."
        ),
    )
    parser.add_argument(
        "--product",
        choices=sorted(PRODUCT_SMILES.keys()),
        default="amine",
        help="Hydrolysis product type to generate.",
    )
    parser.add_argument(
        "--smiles-column",
        help="CSV column name containing input SMILES. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--output-column",
        default="hydrolyzed_smiles",
        help="CSV column name for converted product SMILES.",
    )
    parser.add_argument(
        "--sites-column",
        default="isocyanate_sites",
        help="CSV column name for number of isocyanate groups found.",
    )
    parser.add_argument(
        "--status-column",
        default="conversion_status",
        help="CSV column name for conversion status code.",
    )
    return parser


def _run_text_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        input_smiles = _read_input_smiles(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    results = [hydrolyze_isocyanate_smiles(smi, product=args.product) for smi in input_smiles]
    fieldnames = ["input_smiles", "output_smiles", "isocyanate_sites", "status"]

    if args.output:
        if args.output.exists() and args.output.is_dir():
            parser.error("Text mode output must be a file path, not a directory.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(result.__dict__ for result in results)
        return 0

    print("\t".join(fieldnames))
    for result in results:
        print(
            f"{result.input_smiles}\t"
            f"{result.output_smiles}\t"
            f"{result.isocyanate_sites}\t"
            f"{result.status}"
        )
    return 0


def _run_csv_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        csv_inputs = _get_csv_inputs(args.input)
        output_map = _resolve_csv_outputs(csv_inputs, args.output)
    except ValueError as exc:
        parser.error(str(exc))

    summaries: list[CsvProcessSummary] = []
    for csv_input in csv_inputs:
        try:
            summary = _convert_csv(
                input_path=csv_input,
                output_path=output_map[csv_input],
                product=args.product,
                smiles_column=args.smiles_column,
                output_column=args.output_column,
                sites_column=args.sites_column,
                status_column=args.status_column,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        summaries.append(summary)

    for summary in summaries:
        print(
            f"{summary.input_path} -> {summary.output_path} "
            f"(rows={summary.rows_total}, with_isocyanate={summary.rows_with_isocyanate}, ok={summary.rows_ok})"
        )
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if _should_use_csv_mode(args):
        return _run_csv_mode(args, parser)
    return _run_text_mode(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
