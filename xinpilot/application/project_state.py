"""Version-one project snapshots, independent of widgets and chemistry engines.

The existing JSON shape is the persistence contract. These functions retain
legacy optional sections and unknown fields; front ends gather/apply their own
widget state and pass ordinary dictionaries across this boundary.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ProjectPayload = dict[str, Any]
PROJECT_FORMAT = "oneclick_synthesis_project"
PROJECT_VERSION = 1
STATE_SECTIONS = (
    "compound_notes",
    "tecan",
    "manual_workflow",
    "external_import",
    "opentrons",
    "cheminformatics",
    "reaction_summary",
    "pyparse_runner",
    "modified_pyparse_runner",
    "modified_impurity_runner",
    "multistep_workflow",
)


def timestamp() -> str:
    """Return the local timestamp format used by existing project packages."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def build_project_payload(
    sections: Mapping[str, Any],
    *,
    current_step: int,
    completed_steps: Sequence[Mapping[str, Any]],
    saved_at: str | None = None,
) -> ProjectPayload:
    """Capture detached state so packaging cannot mutate live controller data."""
    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "saved_at": saved_at if saved_at is not None else timestamp(),
        **copy.deepcopy(dict(sections)),
        "multistep_workflow": {
            "current_step": int(current_step),
            "completed_steps": copy.deepcopy(list(completed_steps)),
        },
    }


def validate_project_data(data: object) -> None:
    """Check the established import contract before any state is applied."""
    if not isinstance(data, dict):
        raise ValueError("Project data must be a JSON object.")
    version = data.get("version", PROJECT_VERSION)
    if type(version) is not int or version != PROJECT_VERSION:
        raise ValueError(f"Unsupported XinPilot project version: {version!r}")
    for section in STATE_SECTIONS:
        value = data.get(section, {})
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"Project section {section!r} must be an object.")
    compound = data.get("compound_notes", {}) or {}
    from .tecan_domain import validate_gwl_names, validate_gwl_snapshots
    validate_gwl_names((data.get("tecan") or {}).get("exported_gwl_files", []) or [])
    validate_gwl_snapshots((data.get("cheminformatics") or {}).get("pushed_rows", []) or [])
    from .external_import import validate_state
    validate_state(data.get("external_import", {}) or {})
    records = compound.get("records", []) or []
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ValueError("Compound Notes records must be a list of objects.")
    multistep = data.get("multistep_workflow", {}) or {}
    current_step = multistep.get("current_step", 1)
    completed_steps = multistep.get("completed_steps", []) or []
    if type(current_step) is not int or current_step < 1:
        raise ValueError("Current synthesis step must be a positive whole number.")
    if not isinstance(completed_steps, list) or any(
        not isinstance(item, dict) for item in completed_steps
    ):
        raise ValueError("Completed synthesis steps must be a list of objects.")


def synthesis_progress(data: Mapping[str, Any]) -> tuple[int, list[ProjectPayload]]:
    """Restore detached step history from current or legacy project state."""
    workflow = data.get("multistep_workflow", {}) or {}
    return (
        int(workflow.get("current_step", 1) or 1),
        [
            copy.deepcopy(item)
            for item in (workflow.get("completed_steps", []) or [])
            if isinstance(item, dict)
        ],
    )


def create_synthesis_step_snapshot(
    payload: Mapping[str, Any],
    *,
    step_number: int,
    selected_products: Sequence[Mapping[str, Any]],
    selection_method: str,
    completed_at: str | None = None,
) -> ProjectPayload:
    """Archive one completed workspace without recursively nesting its history."""
    state = copy.deepcopy(dict(payload))
    state.pop("multistep_workflow", None)
    return {
        "step_number": step_number,
        "completed_at": completed_at if completed_at is not None else timestamp(),
        "selection_method": selection_method,
        "selected_products": copy.deepcopy(list(selected_products)),
        "state": state,
    }


def project_name_from_path(path: Path | str) -> str:
    """Strip current and historical package extensions for the window title."""
    filename = Path(path).name
    lower_name = filename.casefold()
    for extension in (
        ".xinpilot.zip",
        ".rxnpilot.zip",
        ".syntrack.zip",
        ".oneclick.zip",
        ".oneclick.json",
        ".zip",
        ".json",
    ):
        if lower_name.endswith(extension):
            return filename[: -len(extension)].strip() or filename
    return Path(filename).stem.strip() or filename
