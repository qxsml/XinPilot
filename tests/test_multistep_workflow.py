import unittest
import tkinter as tk
from tkinter import ttk

from integrated_full_software import IntegratedFullApp
from multistep_workflow import (
    build_product_candidate,
    candidate_to_compound_values,
    parse_percent,
    select_candidates_by_threshold,
)


class MultistepWorkflowTests(unittest.TestCase):
    def test_parse_percent(self):
        self.assertEqual(parse_percent("30%"), 30.0)
        self.assertEqual(parse_percent("30.5"), 30.5)
        self.assertIsNone(parse_percent(""))
        self.assertIsNone(parse_percent("101"))

    def test_threshold_is_inclusive(self):
        candidates = [
            {"reaction_well": "A1", "purity_percent": 29.99},
            {"reaction_well": "A2", "purity_percent": 30.0},
            {"reaction_well": "A3", "purity_percent": 81.2},
            {"reaction_well": "A4", "purity_percent": None},
        ]
        self.assertEqual(
            [row["reaction_well"] for row in select_candidates_by_threshold(candidates, 30)],
            ["A2", "A3"],
        )

    def test_candidate_and_compound_record(self):
        row = {
            "reaction_well": "a01",
            "pyparse_well": "b02",
            "product_id": "P-001",
            "desired product name": "Step-one product",
            "desired product smiles": "CCO",
            "desired product mw": "46.07",
        }
        candidate = build_product_candidate(row, "42.5%", "UV254 purity from Modified PyParse")
        values = candidate_to_compound_values(
            candidate,
            source_step=1,
            data_headers=("ID", "MW", "SMILES", "Name", "Nature"),
            existing_ids={"P-001"},
        )
        self.assertEqual(candidate["reaction_well"], "A1")
        self.assertEqual(candidate["lcms_well"], "B2")
        self.assertEqual(values["ID"], "P-001_2")
        self.assertEqual(values["SMILES"], "CCO")
        self.assertIn("RXN well A1", values["Nature"])
        self.assertIn("42.5%", values["Nature"])

    def test_manual_selection_footer_is_visible_at_initial_size(self):
        class DialogProbe(tk.Tk):
            _manual_next_step_product_selection = IntegratedFullApp._manual_next_step_product_selection

            def __init__(self):
                super().__init__()
                self.geometry("200x100+0+0")
                self.update()
                self.current_synthesis_step = 2
                self.measurement = None

            def wait_window(self, win):
                win.update()
                action_button = None

                def find_action_button(widget):
                    nonlocal action_button
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Button) and child.cget("text") == "Use Selected Products":
                            action_button = child
                        find_action_button(child)

                find_action_button(win)
                self.assert_action_button(action_button, win)
                win.destroy()

            def assert_action_button(self, action_button, win):
                if action_button is None:
                    raise AssertionError("Use Selected Products button was not created")
                button_y = action_button.winfo_rooty() - win.winfo_rooty()
                self.measurement = (button_y, action_button.winfo_height(), win.winfo_height())

        try:
            root = DialogProbe()
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")
        try:
            root._manual_next_step_product_selection([
                {
                    "reaction_well": "A1",
                    "lcms_well": "A1",
                    "product_id": "P1",
                    "product_name": "Product",
                    "purity": "95%",
                    "purity_source": "UV254 purity from Modified PyParse",
                }
            ])
            button_y, button_height, window_height = root.measurement
            self.assertGreaterEqual(button_y, 0)
            self.assertLessEqual(button_y + button_height, window_height)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
