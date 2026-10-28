"""Package completed synthesis steps without depending on the active controllers.

Only supported worklists, chemical maps, trace images and result tables are
included. This is not a raw-data or arbitrary-folder archiver.
"""

from __future__ import annotations

import copy
import re
import zipfile
from collections.abc import Callable
from typing import Any
from pathlib import Path


RESULT_DIRS = (
    "pyparse_result_dir",
    "modified_pyparse_result_dir",
    "modified_pyparse_impurity_result_dir",
)
RESULT_TABLES = {"compoundtable.csv", "outputtable.csv", "atable.csv"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _existing_file(value: object) -> Path | None:
    path = Path(str(value)) if value else None
    return path if path is not None and path.is_file() else None


def _token(value: object, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or fallback


def package_archived_steps(zf: zipfile.ZipFile, payload: dict[str, Any]) -> list[str]:
    """Rewrite a private copy of archived state with archive-relative assets."""
    workflow = copy.deepcopy(payload.get("multistep_workflow") or {})
    payload["multistep_workflow"] = workflow
    warnings = []

    def package(state, prefix):
        from .external_import import package_originals
        package_originals(zf, state.get("external_import", {}) or {}, prefix + "/external-import")
        manifest = {"version": 1}
        tecan = state.get("tecan") or {}
        for index, entry in enumerate(tecan.get("exported_gwl_files") or [], 1):
            name = _token(Path(str(entry.get("name") or "worklist.gwl")).name, "worklist.gwl")
            if not name.lower().endswith(".gwl"):
                name += ".gwl"
            rel = f"{prefix}/gwl/{index:03d}_{name}"
            # Use the saved snapshot first, never a newer external GWL instead.
            content = entry.get("content")
            if not content:
                source = _existing_file(entry.get("portable_source_path")) or _existing_file(
                    entry.get("path")
                )
                if source:
                    content = source.read_text(encoding="utf-8-sig")
            if content:
                zf.writestr(rel, str(content))
                entry["portable_path"] = rel
            else:
                entry.pop("portable_path", None)
                warnings.append(f"{prefix}: missing saved worklist {name}")
            source_map = _existing_file(entry.get("portable_chemical_map_source_path"))
            original = str(entry.get("path") or "")
            if source_map is None and original:
                p = Path(original)
                source_map = _existing_file(p.with_name(p.stem + "_chemical_map.csv"))
            entry.pop("portable_chemical_map_path", None)
            if source_map:
                map_rel = f"{prefix}/gwl/{index:03d}_{Path(name).stem}_chemical_map.csv"
                zf.write(source_map, map_rel)
                entry["portable_chemical_map_path"] = map_rel
            entry["path"] = ""
            entry["requires_save_as"] = True
            entry.pop("portable_source_path", None)
            entry.pop("portable_chemical_map_source_path", None)

        chem = state.get("cheminformatics") or {}
        traces = {}
        for index, (well, paths) in enumerate((chem.get("portable_trace_paths") or {}).items(), 1):
            if not isinstance(paths, dict):
                continue
            packed = {}
            for key, value in paths.items():
                source = _existing_file(value)
                if source:
                    rel = f"{prefix}/traces/{index:03d}_{_token(well, 'well')}_{_token(key, 'trace')}{source.suffix.lower()}"
                    zf.write(source, rel)
                    packed[key] = rel
                elif value:
                    warnings.append(f"{prefix}: missing {key} image for {well}")
            if packed:
                traces[well] = packed
        chem["portable_trace_paths"] = traces
        manifest["trace_manifest"] = traces

        # Older archived steps hold result directories rather than trace paths.
        # Preserve graphs and identity tables, retaining relative subdirectories
        # so the normal target-aware trace resolver still works after import.
        for key in RESULT_DIRS:
            directory_text = str(chem.get(key) or "")
            directory = Path(directory_text) if directory_text else None
            files = []
            if directory is not None and directory.is_dir():
                candidates = list(directory.iterdir())
                for child in list(candidates):
                    if child.is_dir() and not child.is_symlink():
                        candidates.extend(child.iterdir())
                        graphs = child / "graphs"
                        if graphs.is_dir():
                            candidates.extend(graphs.iterdir())
                for source in sorted(set(candidates)):
                    if not source.is_file() or source.is_symlink():
                        continue
                    if (
                        source.suffix.lower() not in IMAGE_SUFFIXES
                        and source.name.lower() not in RESULT_TABLES
                    ):
                        continue
                    try:
                        source.resolve().relative_to(directory.resolve())
                    except ValueError:
                        continue
                    rel = f"{prefix}/analysis/{key}/{source.relative_to(directory).as_posix()}"
                    zf.write(source, rel)
                    files.append(rel)
            if files:
                manifest[key] = f"{prefix}/analysis/{key}"
            elif directory_text and not traces:
                warnings.append(f"{prefix}: no available images/tables for {key}")
            chem[key] = ""
        state["cheminformatics"] = chem
        state["portable_assets"] = manifest
        # Runner output paths describe this archived analysis, not a new run.
        for key in ("pyparse_runner", "modified_pyparse_runner", "modified_impurity_runner"):
            if isinstance(state.get(key), dict):
                state[key]["output_dir"] = ""

    def visit(steps, prefix):
        for index, step in enumerate(steps or [], 1):
            if not isinstance(step, dict) or not isinstance(step.get("state"), dict):
                continue
            step_prefix = f"{prefix}/{index:03d}"
            state = step["state"]
            package(state, step_prefix)
            visit(
                (state.get("multistep_workflow") or {}).get("completed_steps"),
                step_prefix + "/steps",
            )

    visit(workflow.get("completed_steps"), "assets/steps")
    return warnings


def resolve_archived_steps(
    data: dict[str, Any],
    extract_root: Path,
    prepare_gwl: Callable[[dict[str, Any], Path | None], None],
) -> None:
    """Resolve each archived step only inside the extracted project directory."""
    root = Path(extract_root).resolve()

    def resolve(value, directory=False):
        if not value:
            return ""
        candidate = (root / str(value).replace("\\", "/")).resolve()
        if not candidate.is_relative_to(root):
            return ""
        return str(candidate) if (candidate.is_dir() if directory else candidate.is_file()) else ""

    def visit(steps):
        for step in steps or []:
            if not isinstance(step, dict) or not isinstance(step.get("state"), dict):
                continue
            state = step["state"]
            assets = state.get("portable_assets") or {}
            chem = state.get("cheminformatics") or {}
            if assets:
                traces = {}
                for well, paths in (assets.get("trace_manifest") or {}).items():
                    if isinstance(paths, dict):
                        found = {
                            key: path for key, value in paths.items() if (path := resolve(value))
                        }
                        if found:
                            traces[well] = found
                chem["portable_trace_paths"] = traces
                for key in RESULT_DIRS:
                    chem[key] = resolve(assets.get(key), directory=True)
                state["cheminformatics"] = chem
                prepare_gwl(state, root)
            visit((state.get("multistep_workflow") or {}).get("completed_steps"))

    visit((data.get("multistep_workflow") or {}).get("completed_steps"))
