"""LC-MS job identity and input-file checks, independent of interface widgets.

Compatibility names remain re-exported by pyparse_runner_frame. The original
and modified PyParse processing engines are not changed by this extraction.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysisJob:
    token: int
    project_generation: int
    output_dir: Path
    analysis_kind: str
    context_signature: object
    platemap_signature: tuple
    started_at: float
    input_signature: tuple = ()


def input_signature(value):
    path = Path(str(value or "")).expanduser().resolve()
    try:
        stat = path.stat()
        return (str(path), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return (str(path), "missing")


def platemap_kind(path: Path) -> str:
    """Classify a Modified PyParse platemap without relying on its filename."""
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            byproduct_fields = [
                field
                for field in (reader.fieldnames or [])
                if re.fullmatch(r"byproduct\d+ smiles", str(field or "").strip().lower())
            ]
            if byproduct_fields:
                for row in reader:
                    if any(str(row.get(field, "") or "").strip() for field in byproduct_fields):
                        return "impurity"
    except Exception:
        pass
    return "product"


def has_analysis_results(output_dir: Path) -> bool:
    """Detect prior/partial analysis artifacts that could contaminate a new run."""
    output_dir = Path(output_dir)
    known_files = {
        "atable.csv",
        "compoundtable.csv",
        "outputtable.csv",
        "logfile.txt",
        "html_output.html",
        "output.zip",
        "xinpilot_pyparse_run.json",
        "rxnpilot_pyparse_run.json",
        "syntrack_pyparse_run.json",
    }
    try:
        if any(
            path.is_file() and path.name.lower() in known_files for path in output_dir.iterdir()
        ):
            return True
        graphs = output_dir / "graphs"
        return graphs.is_dir() and any(path.is_file() for path in graphs.iterdir())
    except Exception:
        return False


def platemap_signature(path_text: str) -> tuple:
    """Return a stable identity for a platemap, including in-place edits."""
    raw_path = str(path_text or "").strip()
    if not raw_path:
        return ("", "missing")
    path = Path(raw_path)
    try:
        resolved = str(path.resolve())
    except Exception:
        resolved = str(path)
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        stat = path.stat()
        return (resolved, stat.st_size, digest.hexdigest())
    except Exception:
        return (resolved, "missing")
