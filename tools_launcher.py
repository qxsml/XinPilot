from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox
from typing import Iterable, Optional, Sequence


TOOLKIT_DIRECTORY = Path("toolkit")
COMPOUND_LIBRARY_BUILDER_DIRECTORY = TOOLKIT_DIRECTORY / "compound_library_builder"
COMPOUND_LIBRARY_BUILDER_LAUNCHER = "Launch_Bulk_Cheminformatics.bat"
AROMATIC_SMILES_CONVERTER_DIRECTORY = TOOLKIT_DIRECTORY / "aromatic_smiles_converter"
AROMATIC_SMILES_CONVERTER_LAUNCHER = "Launch_Aromatic_SMILES_Converter.bat"
OPENTRONS_SIMULATOR_DIRECTORY = TOOLKIT_DIRECTORY / "opentrons_protocol_simulator"
OPENTRONS_SIMULATOR_LAUNCHER = "OpentronsProtocolSimulator.exe"
SOLUTION_CALCULATOR_DIRECTORY = TOOLKIT_DIRECTORY / "solution_calculator"
SOLUTION_CALCULATOR_SCRIPT = "solution_calculator.py"


def _launch_bundled_python_tool(
    tool_name: str,
    tool_key: str,
    parent=None,
    extra_args: Optional[Sequence[str]] = None,
) -> bool:
    try:
        command = [sys.executable, "--xinpilot-run-tool", tool_key]
        command.extend(str(value) for value in (extra_args or ()))
        subprocess.Popen(command)
    except OSError as exc:
        messagebox.showerror(
            f"Could not open {tool_name}",
            f"The bundled tool could not be started.\n\n{exc}",
            parent=parent,
        )
        return False
    return True


def _default_search_roots() -> list[Path]:
    source_dir = Path(__file__).resolve().parent
    roots = [source_dir, source_dir.parent]
    executable_dir = Path(sys.executable).resolve().parent
    roots.extend((executable_dir, executable_dir.parent))

    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def _find_tool_launcher(
    relative_directory: Path,
    launcher_name: str,
    search_roots: Optional[Iterable[Path]] = None,
) -> Optional[Path]:
    for root in search_roots or _default_search_roots():
        root = Path(root)
        candidates = (
            root / relative_directory / launcher_name,
            root / launcher_name,
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return None


def _launch_tool(tool_name: str, relative_directory: Path, launcher_name: str, parent=None) -> bool:
    launcher = _find_tool_launcher(relative_directory, launcher_name)
    if launcher is None:
        messagebox.showerror(
            f"{tool_name} unavailable",
            f"XinPilot could not find the {tool_name} launcher.\n\n"
            f"Expected file: {relative_directory}\\{launcher_name}",
            parent=parent,
        )
        return False

    try:
        os.startfile(str(launcher))
    except OSError as exc:
        messagebox.showerror(
            f"Could not open {tool_name}",
            f"The standalone tool could not be started.\n\n{exc}",
            parent=parent,
        )
        return False
    return True


def find_compound_library_builder_launcher(search_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    return _find_tool_launcher(
        COMPOUND_LIBRARY_BUILDER_DIRECTORY,
        COMPOUND_LIBRARY_BUILDER_LAUNCHER,
        search_roots,
    )


def find_aromatic_smiles_converter_launcher(search_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    return _find_tool_launcher(
        AROMATIC_SMILES_CONVERTER_DIRECTORY,
        AROMATIC_SMILES_CONVERTER_LAUNCHER,
        search_roots,
    )


def find_opentrons_simulator_launcher(search_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    return _find_tool_launcher(
        OPENTRONS_SIMULATOR_DIRECTORY,
        OPENTRONS_SIMULATOR_LAUNCHER,
        search_roots,
    )


def find_solution_calculator_script(search_roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
    return _find_tool_launcher(
        SOLUTION_CALCULATOR_DIRECTORY,
        SOLUTION_CALCULATOR_SCRIPT,
        search_roots,
    )


def launch_compound_library_builder(parent=None) -> bool:
    if getattr(sys, "frozen", False):
        return _launch_bundled_python_tool(
            "Compound Library Builder",
            "compound-library-builder",
            parent,
        )
    return _launch_tool(
        "Compound Library Builder",
        COMPOUND_LIBRARY_BUILDER_DIRECTORY,
        COMPOUND_LIBRARY_BUILDER_LAUNCHER,
        parent,
    )


def launch_aromatic_smiles_converter(parent=None) -> bool:
    if getattr(sys, "frozen", False):
        return _launch_bundled_python_tool(
            "Aromatic SMILES Converter",
            "aromatic-smiles-converter",
            parent,
        )
    return _launch_tool(
        "Aromatic SMILES Converter",
        AROMATIC_SMILES_CONVERTER_DIRECTORY,
        AROMATIC_SMILES_CONVERTER_LAUNCHER,
        parent,
    )


def launch_opentrons_simulator(parent=None) -> bool:
    if getattr(sys, "frozen", False):
        return _launch_bundled_python_tool(
            "Opentrons Protocol Simulator", "opentrons-protocol-simulator", parent,
        )
    if find_opentrons_simulator_launcher() is not None:
        return _launch_tool("Opentrons Protocol Simulator", OPENTRONS_SIMULATOR_DIRECTORY,
                            OPENTRONS_SIMULATOR_LAUNCHER, parent)
    script = _find_tool_launcher(OPENTRONS_SIMULATOR_DIRECTORY, "opentrons_protocol_simulator_gui.py")
    if script is None:
        messagebox.showerror("Opentrons Protocol Simulator unavailable",
                             "The simulator source is missing from toolkit/opentrons_protocol_simulator.", parent=parent)
        return False
    import importlib.util
    if importlib.util.find_spec("opentrons") is None:
        messagebox.showerror("Opentrons dependency unavailable",
                             "Run Setup_TypeScript.bat to install the simulator dependency.", parent=parent)
        return False
    try:
        subprocess.Popen([sys.executable, str(script)])
    except OSError as exc:
        messagebox.showerror("Could not open Opentrons Protocol Simulator", str(exc), parent=parent)
        return False
    return True


def launch_solution_calculator(payload_path: Optional[object] = None, parent=None) -> bool:
    extra_args = ["--input", str(payload_path)] if payload_path else []
    if getattr(sys, "frozen", False):
        return _launch_bundled_python_tool(
            "Solution & Stock Calculator",
            "solution-calculator",
            parent,
            extra_args,
        )

    script = find_solution_calculator_script()
    if script is None:
        messagebox.showerror(
            "Solution & Stock Calculator unavailable",
            f"XinPilot could not find the Solution & Stock Calculator.\n\n"
            f"Expected file: {SOLUTION_CALCULATOR_DIRECTORY}\\{SOLUTION_CALCULATOR_SCRIPT}",
            parent=parent,
        )
        return False
    try:
        subprocess.Popen([sys.executable, str(script), *extra_args])
    except OSError as exc:
        messagebox.showerror(
            "Could not open Solution & Stock Calculator",
            f"The standalone tool could not be started.\n\n{exc}",
            parent=parent,
        )
        return False
    return True


def launch_clogp_calculator(payload_path: Optional[object] = None, parent=None) -> bool:
    extra_args = ["--input", str(payload_path)] if payload_path else []
    if getattr(sys, "frozen", False):
        return _launch_bundled_python_tool("Molecular Properties & Alerts Calculator", "clogp-calculator", parent, extra_args)
    script = _find_tool_launcher(TOOLKIT_DIRECTORY / "clogp_calculator", "clogp_calculator.py")
    if script is None:
        messagebox.showerror("Molecular Properties & Alerts Calculator unavailable", "The molecular properties calculator script could not be found.", parent=parent)
        return False
    try:
        subprocess.Popen([sys.executable, str(script), *extra_args])
    except OSError as exc:
        messagebox.showerror("Could not open Molecular Properties & Alerts Calculator", str(exc), parent=parent)
        return False
    return True
