"""Regression contracts for GUI-independent project state and persistence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from xinpilot.application.project_archive import (
    TraceAsset,
    load_project_package,
    package_project_assets,
    save_project_package,
)
from xinpilot.application.project_state import (
    build_project_payload,
    create_synthesis_step_snapshot,
    project_name_from_path,
    synthesis_progress,
    validate_project_data,
)

ROOT = Path(__file__).resolve().parents[1]


class ProjectStateTests(unittest.TestCase):
    def test_payload_and_restored_history_do_not_alias_live_state(self):
        sections = {"tecan": {"rows": [{"volume": "20"}]}}
        history = [{"state": {"cheminformatics": {"nested": ["saved"]}}}]
        payload = build_project_payload(sections, current_step=2, completed_steps=history, saved_at="saved-time")
        payload["tecan"]["rows"][0]["volume"] = "99"
        step, restored = synthesis_progress(payload)
        restored[0]["state"]["cheminformatics"]["nested"].append("new")
        self.assertEqual(2, step)
        self.assertEqual("20", sections["tecan"]["rows"][0]["volume"])
        self.assertEqual(["saved"], history[0]["state"]["cheminformatics"]["nested"])
        self.assertEqual(history, payload["multistep_workflow"]["completed_steps"])
        self.assertEqual("saved-time", payload["saved_at"])

    def test_step_snapshot_excludes_recursive_history_and_detaches_selected_products(self):
        payload = {"tecan": {"rows": [1]}, "multistep_workflow": {"completed_steps": [{"step_number": 1}]}}
        selected = [{"product_id": "P1", "carried_impurities": [{"smiles": "CCO"}]}]
        snapshot = create_synthesis_step_snapshot(
            payload, step_number=2, selected_products=selected, selection_method="manual", completed_at="finished",
        )
        selected[0]["carried_impurities"][0]["smiles"] = "CCN"
        payload["tecan"]["rows"].append(2)
        self.assertNotIn("multistep_workflow", snapshot["state"])
        self.assertEqual([1], snapshot["state"]["tecan"]["rows"])
        self.assertEqual("CCO", snapshot["selected_products"][0]["carried_impurities"][0]["smiles"])
        self.assertEqual("finished", snapshot["completed_at"])

    def test_validation_preserves_legacy_optional_sections_and_unknown_fields(self):
        data = {"tecan": None, "future_extension": {"keep": "value"}}
        validate_project_data(data)
        self.assertEqual((1, []), synthesis_progress(data))
        self.assertEqual({"keep": "value"}, data["future_extension"])
        for invalid in (
            [], {"version": True}, {"version": 2}, {"compound_notes": {"records": ["bad"]}},
            {"multistep_workflow": {"current_step": 0}},
            {"multistep_workflow": {"completed_steps": ["bad"]}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_project_data(invalid)

    def test_project_names_preserve_all_supported_historical_extensions(self):
        for extension in (".xinpilot.zip", ".rxnpilot.zip", ".syntrack.zip", ".oneclick.zip", ".oneclick.json", ".zip", ".json"):
            with self.subTest(extension=extension):
                self.assertEqual("Campaign", project_name_from_path("Campaign" + extension.upper()))

    def test_application_imports_without_site_packages_or_gui_modules(self):
        code = (
            "import sys; "
            "from xinpilot.application import project_state, project_archive, project_history; "
            "assert not any(name in sys.modules for name in "
            "('tkinter', 'rdkit', 'webview', 'integrated_full_software', 'xinpilot_shared'))"
        )
        result = subprocess.run([sys.executable, "-B", "-S", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)


class ProjectArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def load(self, package):
        return load_project_package(package, self.root / "outputs", normalize_well=lambda value: str(value).upper())

    def test_atomic_export_failure_keeps_existing_file_and_live_payload(self):
        destination = self.root / "campaign.zip"
        destination.write_bytes(b"existing project")
        payload = {"tecan": {"rows": [1]}}

        def failing_assets(archive, private_payload):
            private_payload["tecan"]["rows"].append(2)
            archive.writestr("partial.txt", "partial")
            raise OSError("simulated asset failure")

        with self.assertRaisesRegex(OSError, "simulated asset failure"):
            save_project_package(destination, payload, package_assets=failing_assets)
        self.assertEqual(b"existing project", destination.read_bytes())
        self.assertEqual({"tecan": {"rows": [1]}}, payload)
        self.assertEqual([destination], list(self.root.iterdir()))

    def test_verification_failure_does_not_replace_existing_package(self):
        destination = self.root / "campaign.zip"
        destination.write_bytes(b"existing project")

        def invalid_assets(archive, payload):
            payload["version"] = 99
            return {}

        with self.assertRaisesRegex(ValueError, "Unsupported"):
            save_project_package(destination, {}, package_assets=invalid_assets)
        self.assertEqual(b"existing project", destination.read_bytes())
        self.assertEqual([destination], list(self.root.iterdir()))

    def test_worklist_trace_and_step_history_survive_import_and_reexport(self):
        source = self.root / "sender"
        source.mkdir()
        worklist = source / "plate.gwl"
        worklist.write_text("new external content", encoding="utf-8")
        (source / "plate_chemical_map.csv").write_text("well,id\nA1,P1\n", encoding="utf-8")
        trace = source / "trace.png"
        trace.write_bytes(b"saved trace image")
        (source / "original.rpt").write_text("not a portable analysis asset", encoding="utf-8")
        payload = {
            "version": 1,
            "tecan": {"exported_gwl_files": [{"name": "plate.gwl", "path": str(worklist), "content": "saved GWL snapshot"}]},
            "cheminformatics": {"modified_pyparse_result_dir": str(source), "target_data": {"A1": "CCO"}},
            "modified_pyparse_runner": {"output_dir": str(source)},
            "multistep_workflow": {"current_step": 2, "completed_steps": [{"step_number": 1, "state": {
                "tecan": {"exported_gwl_files": [{"name": "plate.gwl", "content": "archived snapshot"}]},
                "cheminformatics": {"portable_trace_paths": {"A1": {"modified_uv": str(trace)}}},
            }}]},
        }
        before = copy.deepcopy(payload)
        destination = self.root / "campaign.xinpilot.zip"
        descriptor = TraceAsset("A1", "modified_uv", trace, "A1_modified_uv254")
        save_project_package(destination, payload, package_assets=lambda archive, state: package_project_assets(archive, state, [descriptor]))
        self.assertEqual(before, payload)
        source.rename(self.root / "sender_moved")
        imported, extracted = self.load(destination)
        chem = imported["cheminformatics"]
        self.assertEqual("", chem["modified_pyparse_result_dir"])
        self.assertEqual("", imported["modified_pyparse_runner"]["output_dir"])
        self.assertEqual({"A1": "CCO"}, chem["target_data"])
        self.assertEqual(b"saved trace image", Path(chem["portable_trace_paths"]["A1"]["modified_uv"]).read_bytes())
        entry = imported["tecan"]["exported_gwl_files"][0]
        self.assertEqual("", entry["path"])
        self.assertTrue(entry["requires_save_as"])
        self.assertEqual("saved GWL snapshot", Path(entry["portable_source_path"]).read_text(encoding="utf-8"))
        self.assertTrue(Path(entry["portable_chemical_map_source_path"]).is_relative_to(extracted))
        archived = imported["multistep_workflow"]["completed_steps"][0]["state"]
        self.assertTrue(Path(archived["cheminformatics"]["portable_trace_paths"]["A1"]["modified_uv"]).is_file())
        second = self.root / "recipient.zip"
        local_trace = Path(chem["portable_trace_paths"]["A1"]["modified_uv"])
        save_project_package(second, imported, package_assets=lambda archive, state: package_project_assets(
            archive, state, [TraceAsset("A1", "modified_uv", local_trace, "A1_modified_uv254")],
        ))
        with zipfile.ZipFile(second) as archive:
            self.assertFalse(any(name.endswith(".rpt") for name in archive.namelist()))
            self.assertEqual("saved GWL snapshot", archive.read("assets/gwl/plate.gwl").decode("utf-8"))
            self.assertEqual(b"saved trace image", archive.read("assets/traces/A1_modified_uv254.png"))
            self.assertTrue(any(name.startswith("assets/steps/001/") and name.endswith(".png") for name in archive.namelist()))

    def test_duplicate_worklist_names_rejected_before_export(self):
        payload = {"tecan": {"exported_gwl_files": [
            {"name": "plate.gwl", "content": "first"}, {"name": "PLATE.GWL", "content": "second"},
        ]}}
        destination = self.root / "duplicate.zip"
        with self.assertRaisesRegex(ValueError, "Duplicate GWL filename"):
            save_project_package(destination, payload)
        self.assertFalse(destination.exists())

    def test_long_project_name_imports_assets_in_nested_installation(self):
        destination = self.root / ("Suzuki-study-with-a-long-descriptive-project-name" * 2 + ".xinpilot.zip")
        relative = "assets/gwl/Aryl_chloride_2_tips_chemical_map.csv"
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("project.json", "{}")
            archive.writestr(relative, "well,id\nA1,BB1\n")
        output = self.root / ("nested-" + "x" * max(1, 139 - len(str(self.root)) - 8))
        _, extracted = load_project_package(destination, output, normalize_well=str)
        self.assertEqual("well,id\nA1,BB1\n", (extracted / relative).read_text())
        self.assertLess(len(str(extracted / relative)), 260)
        _, second = load_project_package(destination, output, normalize_well=str)
        self.assertNotEqual(extracted, second)
        self.assertEqual((extracted / relative).read_bytes(), (second / relative).read_bytes())

    def test_legacy_json_load_keeps_embedded_worklist_and_unknown_sections(self):
        destination = self.root / "old.oneclick.json"
        data = {"tecan": {"exported_gwl_files": [{"path": str(self.root / "missing.gwl"), "content": "W;\n"}]}, "extension": {"keep": 7}}
        destination.write_text(json.dumps(data), encoding="utf-8")
        before = destination.read_bytes()
        imported, extracted = self.load(destination)
        self.assertIsNone(extracted)
        self.assertEqual(before, destination.read_bytes())
        self.assertEqual({"keep": 7}, imported["extension"])
        self.assertEqual("W;\n", imported["tecan"]["exported_gwl_files"][0]["content"])
        self.assertTrue(imported["tecan"]["exported_gwl_files"][0]["requires_save_as"])

    def test_unsafe_archive_member_is_rejected_and_partial_extraction_removed(self):
        for member in ("../escape.txt", "..\\escape.txt"):
            with self.subTest(member=member):
                destination = self.root / "unsafe.zip"
                with zipfile.ZipFile(destination, "w") as archive:
                    archive.writestr("project.json", "{}")
                    archive.writestr("safe.txt", "safe")
                    archive.writestr(member, "escape")
                with self.assertRaisesRegex(ValueError, "Unsafe path"):
                    self.load(destination)
                output = self.root / "outputs"
                self.assertFalse(any(output.rglob("*.txt")))
                self.assertEqual([], list((output / "imported_projects").iterdir()))

    def test_invalid_json_schema_is_rejected_before_creating_extraction_directory(self):
        destination = self.root / "invalid.zip"
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("project.json", "[]")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            self.load(destination)
        self.assertFalse((self.root / "outputs").exists())


if __name__ == "__main__":
    unittest.main()
