"""Portable project persistence without GUI or chemistry-engine dependencies.

Controllers resolve scientific trace identity and provide TraceAsset descriptors.
This service owns package paths, supported asset serialization, archive validation,
legacy loading, and atomic writes. The version-one JSON contract is unchanged.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .project_history import package_archived_steps, resolve_archived_steps
from .project_state import ProjectPayload, timestamp, validate_project_data


@dataclass(frozen=True)
class TraceAsset:
    """One already-resolved scientific image to include in a portable package."""

    well: str
    kind: str
    source: Path | None
    archive_stem: str
    include_empty_well: bool = False


def package_project_assets(
    zf: zipfile.ZipFile,
    payload: ProjectPayload,
    trace_assets: Sequence[TraceAsset] | None = None,
) -> ProjectPayload:
    """Write supported assets and rewrite only the supplied private payload."""
    assets: Dict[str, object] = {}
    from .external_import import package_originals
    package_originals(zf, payload.get("external_import", {}) or {})
    assets["archived_step_warnings"] = package_archived_steps(zf, payload)
    tecan = payload.get("tecan", {}) or {}
    gwl_manifest: List[Dict[str, str]] = []
    if isinstance(tecan, dict):
        portable_entries: List[Dict[str, object]] = []
        used_names = set()
        for index, raw_entry in enumerate(tecan.get("exported_gwl_files", []) or [], start=1):
            if not isinstance(raw_entry, dict):
                continue
            entry: Dict[str, object] = dict(raw_entry)
            entry["blocks"] = [
                dict(block)
                for block in (raw_entry.get("blocks", []) or [])
                if isinstance(block, dict)
            ]
            raw_name = str(entry.get("name", "") or "").strip()
            if not raw_name:
                raw_path = str(entry.get("path", "") or "").strip()
                raw_name = Path(raw_path).name if raw_path else f"GWL_{index}.gwl"
            safe_name = (
                re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(raw_name).name).strip("._")
                or f"GWL_{index}.gwl"
            )
            if not safe_name.lower().endswith(".gwl"):
                safe_name += ".gwl"
            base_stem = Path(safe_name).stem
            candidate_name = safe_name
            duplicate = 2
            while candidate_name.casefold() in used_names:
                candidate_name = f"{base_stem}_{duplicate}.gwl"
                duplicate += 1
            used_names.add(candidate_name.casefold())
            archive_path = f"assets/gwl/{candidate_name}"
            content = str(entry.get("content", "") or "")
            if not content:
                portable_source_text = str(raw_entry.get("portable_source_path", "") or "").strip()
                portable_source = Path(portable_source_text) if portable_source_text else None
                if portable_source is not None and portable_source.is_file():
                    try:
                        content = portable_source.read_text(encoding="utf-8")
                    except Exception:
                        content = ""
            zf.writestr(archive_path, content)

            chemical_map_archive = ""
            original_path_text = str(raw_entry.get("path", "") or "").strip()
            original_path = Path(original_path_text) if original_path_text else None
            chemical_map_path = (
                original_path.with_name(original_path.stem + "_chemical_map.csv")
                if original_path is not None
                else None
            )
            if chemical_map_path is None or not chemical_map_path.is_file():
                portable_map_text = str(
                    raw_entry.get("portable_chemical_map_source_path", "") or ""
                ).strip()
                portable_map = Path(portable_map_text) if portable_map_text else None
                chemical_map_path = (
                    portable_map if portable_map is not None and portable_map.is_file() else None
                )
            if chemical_map_path is not None and chemical_map_path.is_file():
                chemical_map_archive = f"assets/gwl/{Path(candidate_name).stem}_chemical_map.csv"
                zf.write(chemical_map_path, chemical_map_archive)

            entry["name"] = candidate_name
            entry["path"] = ""
            entry["portable_path"] = archive_path
            entry["requires_save_as"] = True
            entry.pop("portable_source_path", None)
            entry.pop("portable_chemical_map_source_path", None)
            if chemical_map_archive:
                entry["portable_chemical_map_path"] = chemical_map_archive
            else:
                entry.pop("portable_chemical_map_path", None)
            portable_entries.append(entry)
            manifest_item = {"name": candidate_name, "path": archive_path}
            if chemical_map_archive:
                manifest_item["chemical_map_path"] = chemical_map_archive
            gwl_manifest.append(manifest_item)
        tecan = dict(tecan)
        tecan["exported_gwl_files"] = portable_entries
        payload["tecan"] = tecan
    assets["gwl_manifest"] = gwl_manifest

    if trace_assets is None:
        return assets
    written: Dict[str, Path] = {}
    portable_trace_paths: Dict[str, Dict[str, str]] = {}

    def add_trace(source: Optional[Path], archive_dir: str, archive_name: str) -> str:
        if source is None or not source.is_file():
            return ""
        archive_path = f"{archive_dir.rstrip('/')}/{archive_name}{source.suffix.lower()}"
        existing = written.get(archive_path)
        if existing is not None:
            return archive_path if existing == source else ""
        try:
            zf.write(source, archive_path)
            written[archive_path] = source
            return archive_path
        except Exception:
            return ""

    for trace in trace_assets:
        path = add_trace(trace.source, "assets/traces", trace.archive_stem)
        if path or trace.include_empty_well:
            row_traces = portable_trace_paths.setdefault(trace.well, {})
            if path:
                row_traces[trace.kind] = path
    assets["trace_manifest"] = portable_trace_paths
    chem = payload.get("cheminformatics", {}) or {}
    if isinstance(chem, dict):
        chem["portable_trace_paths"] = portable_trace_paths
        if any(
            ("pyparse_uv" in traces or "impurity_pyparse" in traces)
            for traces in portable_trace_paths.values()
        ):
            chem["pyparse_result_dir"] = ""
        if any(
            ("modified_uv" in traces or "modified_es" in traces or "impurity_modified" in traces)
            for traces in portable_trace_paths.values()
        ):
            chem["modified_pyparse_result_dir"] = ""
            chem["modified_pyparse_impurity_result_dir"] = ""
        payload["cheminformatics"] = chem
    runner_clear_flags = {
        "modified_impurity_runner": any(
            "impurity_modified" in traces for traces in portable_trace_paths.values()
        ),
        "pyparse_runner": any(
            ("pyparse_uv" in traces or "impurity_pyparse" in traces)
            for traces in portable_trace_paths.values()
        ),
        "modified_pyparse_runner": any(
            ("modified_uv" in traces or "modified_es" in traces or "impurity_modified" in traces)
            for traces in portable_trace_paths.values()
        ),
    }
    for runner_key, should_clear in runner_clear_flags.items():
        runner = payload.get(runner_key, {}) or {}
        if should_clear and isinstance(runner, dict):
            runner["output_dir"] = ""
            payload[runner_key] = runner
    return assets


def safe_extract_project_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract members only beneath the caller's project directory."""
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve()
    for member in zf.infolist():
        member_name = member.filename.replace("\\", "/")
        target = (dest / member_name).resolve()
        if target != dest_root and dest_root not in target.parents:
            raise ValueError(f"Unsafe path in project package: {member.filename}")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def prepare_imported_gwl_entries(data: ProjectPayload, extract_root: Path | None) -> None:
    """Resolve packaged worklists while requiring a local Save As destination."""
    tecan = data.get("tecan", {}) or {}
    if not isinstance(tecan, dict):
        return
    root = extract_root.resolve() if extract_root is not None else None
    prepared: List[Dict[str, object]] = []
    for raw_entry in tecan.get("exported_gwl_files", []) or []:
        if not isinstance(raw_entry, dict):
            continue
        entry: Dict[str, object] = dict(raw_entry)
        portable_path = str(entry.get("portable_path", "") or "").strip().replace("\\", "/")
        portable_source: Optional[Path] = None
        if root is not None and portable_path:
            candidate = (root / portable_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                candidate = None
            if candidate is not None and candidate.is_file():
                portable_source = candidate
                entry["portable_source_path"] = str(candidate)
                if not str(entry.get("content", "") or ""):
                    entry["content"] = candidate.read_text(encoding="utf-8")
        chemical_map_rel = (
            str(entry.get("portable_chemical_map_path", "") or "").strip().replace("\\", "/")
        )
        if root is not None and chemical_map_rel:
            chemical_map_candidate = (root / chemical_map_rel).resolve()
            try:
                chemical_map_candidate.relative_to(root)
            except ValueError:
                chemical_map_candidate = None
            if chemical_map_candidate is not None and chemical_map_candidate.is_file():
                entry["portable_chemical_map_source_path"] = str(chemical_map_candidate)

        raw_path = str(entry.get("path", "") or "").strip()
        existing_path = Path(raw_path) if raw_path else None
        if portable_source is not None:
            # The packaged copy is readable, but the recipient must choose
            # where their editable working GWL should live.
            entry["path"] = ""
            entry["requires_save_as"] = True
        elif existing_path is None or not existing_path.is_file():
            # Legacy projects retained the sender's absolute path. Embedded
            # content/blocks remain usable; saving must choose a local path.
            entry["path"] = ""
            entry["requires_save_as"] = True
        else:
            entry["requires_save_as"] = bool(entry.get("requires_save_as", False))
        prepared.append(entry)
    tecan = dict(tecan)
    tecan["exported_gwl_files"] = prepared
    data["tecan"] = tecan


def load_project_package(
    path: Path,
    output_dir: Path,
    *,
    normalize_well: Callable[[object], str],
) -> tuple[ProjectPayload, Path | None]:
    """Load JSON or a portable package and resolve supported local assets.

    The caller supplies well-label normalization to retain its scientific naming
    convention without importing its controllers or chemistry dependencies.
    """
    if not zipfile.is_zipfile(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_project_data(data)
        prepare_imported_gwl_entries(data, None)
        return data, None
    # Repeating the full project name and a timestamp can push otherwise valid
    # packaged asset paths over Windows MAX_PATH. The UUID provides uniqueness;
    # a short recognizable prefix is sufficient for this internal directory.
    safe_name = (re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("._") or "project")[:24]
    extract_root = output_dir / "imported_projects" / f"{safe_name}_{uuid.uuid4().hex[:12]}"
    try:
        with zipfile.ZipFile(path, "r") as zf:
            project_member = "project.json"
            if project_member not in zf.namelist():
                raise ValueError("This zip does not contain a XinPilot project.json file.")
            total_size = sum(member.file_size for member in zf.infolist())
            if len(zf.infolist()) > 10000 or total_size > 2 * 1024 * 1024 * 1024:
                raise ValueError("Project package is unreasonably large and was not extracted.")
            data = json.loads(zf.read(project_member).decode("utf-8"))
            validate_project_data(data)
            safe_extract_project_zip(zf, extract_root)
        data = json.loads((extract_root / "project.json").read_text(encoding="utf-8"))
    except Exception:
        if extract_root.exists():
            shutil.rmtree(extract_root, ignore_errors=True)
        raise
    assets = data.get("portable_assets", {}) or {}
    chem = data.get("cheminformatics", {}) or {}
    if isinstance(assets, dict) and isinstance(chem, dict):
        portable_trace_paths = (
            chem.get("portable_trace_paths", {}) or assets.get("trace_manifest", {}) or {}
        )
        has_resolved_portable_traces = False
        if isinstance(portable_trace_paths, dict):
            resolved_traces: Dict[str, Dict[str, str]] = {}
            for well, traces in portable_trace_paths.items():
                if not isinstance(traces, dict):
                    continue
                resolved: Dict[str, str] = {}
                for trace_key, rel_path in traces.items():
                    rel = str(rel_path or "").strip().replace("\\", "/")
                    if not rel:
                        continue
                    candidate = (extract_root / rel).resolve()
                    try:
                        candidate.relative_to(extract_root.resolve())
                    except ValueError:
                        continue
                    if candidate.is_file():
                        resolved[str(trace_key)] = str(candidate)
                if resolved:
                    resolved_traces[normalize_well(well)] = resolved
            chem["portable_trace_paths"] = resolved_traces
            has_resolved_portable_traces = bool(resolved_traces)
        if has_resolved_portable_traces:
            has_pyparse_traces = any(
                ("pyparse_uv" in traces or "impurity_pyparse" in traces)
                for traces in resolved_traces.values()
            )
            has_modified_traces = any(
                (
                    "modified_uv" in traces
                    or "modified_es" in traces
                    or "impurity_modified" in traces
                )
                for traces in resolved_traces.values()
            )
            if has_pyparse_traces:
                chem["pyparse_result_dir"] = ""
                runner = data.get("pyparse_runner", {}) or {}
                if isinstance(runner, dict):
                    runner["output_dir"] = ""
                    data["pyparse_runner"] = runner
            if has_modified_traces:
                chem["modified_pyparse_result_dir"] = ""
                chem["modified_pyparse_impurity_result_dir"] = ""
                runner = data.get("modified_pyparse_runner", {}) or {}
                if isinstance(runner, dict):
                    runner["output_dir"] = ""
                    data["modified_pyparse_runner"] = runner
                impurity_runner = data.get("modified_impurity_runner", {}) or {}
                if isinstance(impurity_runner, dict):
                    impurity_runner["output_dir"] = ""
                    data["modified_impurity_runner"] = impurity_runner
        else:
            for state_key in (
                "pyparse_result_dir",
                "modified_pyparse_result_dir",
                "modified_pyparse_impurity_result_dir",
            ):
                rel = str(assets.get(state_key, "") or "").strip().replace("\\", "/")
                if rel:
                    bundled_dir = (extract_root / rel).resolve()
                    try:
                        bundled_dir.relative_to(extract_root.resolve())
                    except ValueError:
                        continue
                    if bundled_dir.is_dir():
                        chem[state_key] = str(bundled_dir)
                        runner_key = (
                            "modified_impurity_runner"
                            if state_key == "modified_pyparse_impurity_result_dir"
                            else (
                                "modified_pyparse_runner"
                                if state_key.startswith("modified_")
                                else "pyparse_runner"
                            )
                        )
                        runner = data.get(runner_key, {}) or {}
                        if isinstance(runner, dict):
                            runner["output_dir"] = str(bundled_dir)
                            data[runner_key] = runner
        data["cheminformatics"] = chem
    prepare_imported_gwl_entries(data, extract_root)
    resolve_archived_steps(data, extract_root, prepare_imported_gwl_entries)
    return data, extract_root


def save_project_package(
    path: Path,
    payload: ProjectPayload,
    *,
    package_assets: Callable[
        [zipfile.ZipFile, ProjectPayload], ProjectPayload
    ] = package_project_assets,
) -> ProjectPayload:
    """Verify a temporary package before atomically replacing its destination.

    Payloads are deeply detached before asset paths are rewritten. On failure an
    existing destination remains intact, and the incomplete temporary file is
    removed. The returned asset manifest includes archived-step warnings.
    """
    payload = copy.deepcopy(payload)
    validate_project_data(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            assets = package_assets(archive, payload)
            payload["portable_assets"] = {"version": 1, "created_at": timestamp(), **assets}
            archive.writestr("project.json", json.dumps(payload, indent=2))
        with zipfile.ZipFile(temporary, "r") as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ValueError(f"Export verification failed at archive member: {corrupt_member}")
            validate_project_data(json.loads(archive.read("project.json").decode("utf-8")))
        os.replace(temporary, path)
        return assets
    finally:
        if temporary.exists():
            temporary.unlink()
