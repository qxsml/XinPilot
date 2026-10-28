import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import integrated_full_software
from integrated_full_software import IntegratedFullApp


class _StatusVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _SendProbe:
    _send_products_to_solution_calculator = IntegratedFullApp._send_products_to_solution_calculator
    _solution_calculator_payload = IntegratedFullApp._solution_calculator_payload
    _write_solution_calculator_payload = IntegratedFullApp._write_solution_calculator_payload

    def __init__(self, mode="all"):
        self._solution_calculator_dialog_active = False
        self.current_project_name = "Project X"
        self.current_synthesis_step = 3
        self.completed_synthesis_steps = [{"step_number": 2}]
        self.compound_records = ["unchanged"]
        self.project_status_var = _StatusVar()
        self.mode = mode
        self.manual_selection = []
        self.threshold = None
        self.candidates = [
            {"reaction_well": "A1", "product_smiles": "CCO", "purity_percent": 20.0},
            {"reaction_well": "A2", "product_smiles": "CCN", "purity_percent": 80.0},
        ]

    def _next_step_product_candidates(self):
        return [dict(item) for item in self.candidates]

    def _choose_solution_calculator_selection_mode(self):
        return self.mode

    def _manual_solution_calculator_product_selection(self, candidates):
        return [dict(candidates[index]) for index in self.manual_selection]

    def _ask_solution_calculator_uv254_threshold(self):
        return self.threshold


class SolutionCalculatorIntegrationTests(unittest.TestCase):
    def test_candidates_use_product_details_identity_with_optional_lcms_reference(self):
        class CheminformaticsProbe:
            lcms_target_smiles_by_well = {"A1": "CCN"}

            @staticmethod
            def _pyparse_rows():
                return [{
                    "reaction_well": "A1",
                    "pyparse_well": "B1",
                    "reaction_name": "RXN-9",
                    "product_id": "P9",
                    "desired product name": "Charged product",
                    "desired product smiles": "CC[NH3+].[Cl-]",
                    "desired product formula": "C2H8ClN",
                    "desired product exact mass": "81.0345",
                    "desired product mw": "81.54",
                }]

            @staticmethod
            def _product_structure_uv_source_for_row(_row):
                return "modified"

            @staticmethod
            def _product_structure_purity_for_row(_row, _source):
                return "75%"

            @staticmethod
            def _product_structure_uv_source_label(_source):
                return "Modified PyParse UV254"

        class CandidateProbe:
            cheminformatics_tab = CheminformaticsProbe()
            _next_step_product_candidates = IntegratedFullApp._next_step_product_candidates

        candidate = CandidateProbe()._next_step_product_candidates()[0]
        self.assertEqual("CC[NH3+].[Cl-]", candidate["product_smiles"])
        self.assertEqual("C2H8ClN", candidate["product_formula"])
        self.assertEqual("81.0345", candidate["product_exact_mass"])
        self.assertEqual("81.54", candidate["product_mw"])
        self.assertEqual("CCN", candidate["lcms_reference_smiles"])

    def test_send_all_launches_transfer_without_mutating_xinpilot_state(self):
        probe = _SendProbe("all")
        before = (
            probe.current_synthesis_step,
            list(probe.completed_synthesis_steps),
            list(probe.compound_records),
        )
        captured = {}

        def capture(selected):
            captured["selected"] = selected
            return os.path.join(tempfile.gettempdir(), "synthetic-transfer.json")

        probe._write_solution_calculator_payload = capture
        with patch.object(integrated_full_software, "launch_solution_calculator", return_value=True) as launch:
            self.assertTrue(probe._send_products_to_solution_calculator())

        self.assertEqual(["A1", "A2"], [item["reaction_well"] for item in captured["selected"]])
        launch.assert_called_once()
        self.assertEqual(before, (
            probe.current_synthesis_step,
            probe.completed_synthesis_steps,
            probe.compound_records,
        ))
        self.assertIn("XinPilot data was unchanged", probe.project_status_var.value)

    def test_manual_and_auto_modes_use_independent_selection(self):
        manual = _SendProbe("manual")
        manual.manual_selection = [1]
        automatic = _SendProbe("auto")
        automatic.threshold = 50
        sent = []

        def capture(self, selected):
            sent.append([item["reaction_well"] for item in selected])
            return os.path.join(tempfile.gettempdir(), "synthetic-transfer.json")

        with patch.object(_SendProbe, "_write_solution_calculator_payload", capture), patch.object(
            integrated_full_software, "launch_solution_calculator", return_value=True
        ):
            self.assertTrue(manual._send_products_to_solution_calculator())
            self.assertTrue(automatic._send_products_to_solution_calculator())
        self.assertEqual([["A2"], ["A2"]], sent)

    def test_transfer_payload_contains_product_details_and_deletes_after_load_flag(self):
        probe = _SendProbe("all")
        probe.candidates = [{
            "reaction_well": "B3",
            "reaction_name": "RXN-17",
            "product_smiles": "CC[NH3+].[Cl-]",
            "product_formula": "C2H8ClN",
            "product_exact_mass": "81.0345",
            "product_mw": "81.54",
            "lcms_reference_smiles": "CCN",
        }]
        path = probe._write_solution_calculator_payload(probe.candidates)
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual("xinpilot_solution_calculator.v1", data["schema"])
            self.assertTrue(data["delete_after_load"])
            self.assertEqual("CC[NH3+].[Cl-]", data["products"][0]["product_smiles"])
            self.assertEqual("CCN", data["products"][0]["lcms_reference_smiles"])
            self.assertEqual(3, data["source"]["synthesis_step"])
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
