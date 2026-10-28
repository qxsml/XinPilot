"""Guard the service layer against dependencies on interface implementation."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def test_application_services_import_without_gui_or_site_packages(self):
        code = """
import importlib, pkgutil, sys
import xinpilot.application
for item in pkgutil.iter_modules(xinpilot.application.__path__):
    importlib.import_module('xinpilot.application.' + item.name)
for forbidden in ('tkinter', 'webview', 'rdkit', 'openpyxl', 'xinpilot_shared', 'desktop.live_engine'):
    assert forbidden not in sys.modules, forbidden
"""
        result = subprocess.run(
            [sys.executable, "-B", "-S", "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_service_imports_do_not_point_back_to_controllers(self):
        forbidden = {path.stem for path in ROOT.glob("*_frame.py")}
        forbidden.update(
            {"xinpilot_shared", "integrated_full_software", "tkinter", "desktop", "webview"}
        )
        for path in (ROOT / "xinpilot/application").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [item.name.split(".")[0] for item in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imports = [(node.module or "").split(".")[0]]
                with self.subTest(module=path.name, line=getattr(node, "lineno", 0)):
                    self.assertTrue(forbidden.isdisjoint(imports), imports)

    def test_analysis_frame_keeps_legacy_import_names(self):
        from pyparse_runner_frame import _AnalysisJob, _pyparse_platemap_signature
        from xinpilot.application.analysis_jobs import AnalysisJob, platemap_signature

        self.assertIs(_AnalysisJob, AnalysisJob)
        self.assertIs(_pyparse_platemap_signature, platemap_signature)


if __name__ == "__main__":
    unittest.main()
