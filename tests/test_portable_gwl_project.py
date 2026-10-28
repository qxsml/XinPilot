import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from integrated_full_software import IntegratedFullApp


class _EmptyCheminformatics:
    pyparse_result_dir = None
    modified_pyparse_result_dir = None
    modified_pyparse_impurity_result_dir = None

    def _cheminformatics_result_export_rows(self):
        return []

    def _impurity_reaction_rows(self):
        return []


class PortableGwlProjectTests(unittest.TestCase):
    def test_export_packages_gwl_without_mutating_live_path(self):
        live_entry = {
            "path": r"C:\sender\experiment\plate1.gwl",
            "name": "plate1.gwl",
            "content": "A;Source;;1;;10.0;;;Water free dispense;;\nW;\n",
            "mode": "96 Well Microplate",
            "blocks": [],
        }
        payload = {
            "tecan": {"exported_gwl_files": [live_entry]},
            "cheminformatics": {},
            "pyparse_runner": {},
            "modified_pyparse_runner": {},
        }
        fake_app = SimpleNamespace(cheminformatics_tab=_EmptyCheminformatics())
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "project.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                assets = IntegratedFullApp._add_portable_project_assets(fake_app, zf, payload)
            with zipfile.ZipFile(archive, "r") as zf:
                self.assertIn("assets/gwl/plate1.gwl", zf.namelist())
                self.assertIn("A;Source", zf.read("assets/gwl/plate1.gwl").decode("utf-8"))
        exported_entry = payload["tecan"]["exported_gwl_files"][0]
        self.assertEqual(live_entry["path"], r"C:\sender\experiment\plate1.gwl")
        self.assertEqual(exported_entry["path"], "")
        self.assertEqual(exported_entry["portable_path"], "assets/gwl/plate1.gwl")
        self.assertTrue(exported_entry["requires_save_as"])
        self.assertNotIn("portable_source_path", exported_entry)
        self.assertEqual(assets["gwl_manifest"][0]["path"], "assets/gwl/plate1.gwl")

    def test_import_resolves_portable_copy_and_requires_local_save_as(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gwl = root / "assets" / "gwl" / "plate1.gwl"
            gwl.parent.mkdir(parents=True)
            gwl.write_text("W;\n", encoding="utf-8")
            data = {
                "tecan": {
                    "exported_gwl_files": [{
                        "path": "",
                        "name": "plate1.gwl",
                        "content": "",
                        "portable_path": "assets/gwl/plate1.gwl",
                    }]
                }
            }
            IntegratedFullApp._prepare_imported_gwl_entries(data, root)
            entry = data["tecan"]["exported_gwl_files"][0]
            self.assertEqual(entry["path"], "")
            self.assertEqual(entry["content"], "W;\n")
            self.assertEqual(Path(entry["portable_source_path"]), gwl)
            self.assertTrue(entry["requires_save_as"])

    def test_legacy_missing_absolute_path_falls_back_to_snapshot(self):
        data = {
            "tecan": {
                "exported_gwl_files": [{
                    "path": r"Z:\missing\sender\plate2.gwl",
                    "name": "plate2.gwl",
                    "content": "W;\n",
                    "blocks": [],
                }]
            }
        }
        IntegratedFullApp._prepare_imported_gwl_entries(data, None)
        entry = data["tecan"]["exported_gwl_files"][0]
        self.assertEqual(entry["path"], "")
        self.assertEqual(entry["content"], "W;\n")
        self.assertTrue(entry["requires_save_as"])


if __name__ == "__main__":
    unittest.main()
