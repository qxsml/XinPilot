import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools_launcher

from tools_launcher import (
    AROMATIC_SMILES_CONVERTER_DIRECTORY,
    AROMATIC_SMILES_CONVERTER_LAUNCHER,
    COMPOUND_LIBRARY_BUILDER_DIRECTORY,
    COMPOUND_LIBRARY_BUILDER_LAUNCHER,
    OPENTRONS_SIMULATOR_DIRECTORY,
    OPENTRONS_SIMULATOR_LAUNCHER,
    SOLUTION_CALCULATOR_DIRECTORY,
    SOLUTION_CALCULATOR_SCRIPT,
    find_aromatic_smiles_converter_launcher,
    find_compound_library_builder_launcher,
    find_opentrons_simulator_launcher,
    find_solution_calculator_script,
    launch_aromatic_smiles_converter,
    launch_compound_library_builder,
    launch_opentrons_simulator,
    launch_solution_calculator,
)


class ToolsLauncherTests(unittest.TestCase):
    def test_finds_each_launcher_in_its_xinpilot_toolkit_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases = (
                (
                    COMPOUND_LIBRARY_BUILDER_DIRECTORY,
                    COMPOUND_LIBRARY_BUILDER_LAUNCHER,
                    find_compound_library_builder_launcher,
                ),
                (
                    AROMATIC_SMILES_CONVERTER_DIRECTORY,
                    AROMATIC_SMILES_CONVERTER_LAUNCHER,
                    find_aromatic_smiles_converter_launcher,
                ),
                (
                    OPENTRONS_SIMULATOR_DIRECTORY,
                    OPENTRONS_SIMULATOR_LAUNCHER,
                    find_opentrons_simulator_launcher,
                ),
                (
                    SOLUTION_CALCULATOR_DIRECTORY,
                    SOLUTION_CALCULATOR_SCRIPT,
                    find_solution_calculator_script,
                ),
            )
            for relative_directory, launcher_name, finder in cases:
                with self.subTest(launcher=launcher_name):
                    launcher = root / relative_directory / launcher_name
                    launcher.parent.mkdir(parents=True, exist_ok=True)
                    launcher.touch()
                    self.assertEqual(launcher, finder([root]))

    @patch("tools_launcher.os.startfile")
    @patch("tools_launcher._find_tool_launcher")
    def test_launches_each_existing_standalone_application(self, find_launcher, startfile):
        launcher = Path(r"C:\tools\Launch_Bulk_Cheminformatics.bat")
        find_launcher.return_value = launcher

        for launch in (
            launch_compound_library_builder,
            launch_aromatic_smiles_converter,
            launch_opentrons_simulator,
        ):
            with self.subTest(launch=launch.__name__):
                self.assertTrue(launch())

        self.assertEqual(3, startfile.call_count)
        startfile.assert_called_with(str(launcher))

    @patch("tools_launcher.subprocess.Popen")
    def test_frozen_build_relaunches_itself_for_python_toolkit_apps(self, popen):
        with patch.object(tools_launcher.sys, "frozen", True, create=True):
            self.assertTrue(launch_compound_library_builder())
            self.assertTrue(launch_aromatic_smiles_converter())
            self.assertTrue(launch_solution_calculator(r"C:\Temp\products.json"))

        executable = tools_launcher.sys.executable
        self.assertEqual(
            [
                (([executable, "--xinpilot-run-tool", "compound-library-builder"],), {}),
                (([executable, "--xinpilot-run-tool", "aromatic-smiles-converter"],), {}),
                (([executable, "--xinpilot-run-tool", "solution-calculator", "--input", r"C:\Temp\products.json"],), {}),
            ],
            [(call.args, call.kwargs) for call in popen.call_args_list],
        )

    @patch("tools_launcher.subprocess.Popen")
    @patch("tools_launcher.find_solution_calculator_script")
    def test_source_solution_calculator_receives_transfer_path(self, find_script, popen):
        script = Path(r"C:\XinPilot\toolkit\solution_calculator\solution_calculator.py")
        find_script.return_value = script
        self.assertTrue(launch_solution_calculator(r"C:\Temp\products.json"))
        popen.assert_called_once_with([
            tools_launcher.sys.executable,
            str(script),
            "--input",
            r"C:\Temp\products.json",
        ])

    def test_desktop_spec_bundles_toolkit_and_simulator_dependencies(self):
        spec_text = (Path(__file__).resolve().parents[1] / "packaging" / "TypeScript.spec").read_text(encoding="utf-8")
        self.assertIn("'toolkit'", spec_text)
        self.assertIn("collect_data_files('opentrons_shared_data')", spec_text)

    @patch("tools_launcher.subprocess.Popen")
    def test_source_simulator_uses_current_python_without_binary(self, popen):
        with patch("tools_launcher.find_opentrons_simulator_launcher", return_value=None), patch("importlib.util.find_spec", return_value=object()):
            self.assertTrue(launch_opentrons_simulator())
        command = popen.call_args.args[0]
        self.assertEqual(command[0], tools_launcher.sys.executable)
        self.assertEqual(Path(command[1]).name, "opentrons_protocol_simulator_gui.py")

    @patch("tools_launcher.subprocess.Popen")
    def test_frozen_simulator_dispatch(self, popen):
        with patch.object(tools_launcher.sys, "frozen", True, create=True):
            self.assertTrue(launch_opentrons_simulator())
        popen.assert_called_once_with([tools_launcher.sys.executable, "--xinpilot-run-tool", "opentrons-protocol-simulator"])

    def test_simulator_dispatch_resolves_a_bundled_script(self):
        import integrated_full_software as app
        script = Path(__file__).resolve().parents[1] / "toolkit/opentrons_protocol_simulator/opentrons_protocol_simulator_gui.py"
        self.assertTrue(script.is_file())
        with patch.object(app, "resource_path", return_value=script), patch.object(app.runpy, "run_path") as run, patch.object(app.sys, "argv", []), patch.object(app.sys, "path", list(app.sys.path)):
            self.assertEqual(app._run_bundled_tool("opentrons-protocol-simulator"), 0)
        run.assert_called_once_with(str(script), run_name="__main__")

    @patch("tools_launcher.messagebox.showerror")
    @patch("tools_launcher._find_tool_launcher", return_value=None)
    def test_missing_launcher_is_reported_without_crashing_xinpilot(self, _find_launcher, showerror):
        for launch in (
            launch_compound_library_builder,
            launch_aromatic_smiles_converter,
            launch_opentrons_simulator,
        ):
            with self.subTest(launch=launch.__name__):
                self.assertFalse(launch())
        self.assertEqual(3, showerror.call_count)


if __name__ == "__main__":
    unittest.main()
