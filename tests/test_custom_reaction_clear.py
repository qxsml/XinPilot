from __future__ import annotations

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cheminformatics_frame import CheminformaticsFrame  # noqa: E402


class _FakeText:
    def __init__(self, value=""):
        self.value = value

    def get(self, _start, _end):
        return self.value

    def delete(self, _start, _end):
        self.value = ""


class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class CustomReactionClearTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(CheminformaticsFrame)
        self.frame.custom_template_text = _FakeText("$RXN\nold template")
        self.frame.custom_products = {"A1": {"smiles": "CCO", "source": "custom_template"}}
        self.frame.custom_failures = {"A2": "Failed: no product"}
        self.frame.product_details_generated = True
        self.frame.lcms_target_smiles_by_well = {"A1": "CCO"}
        self.frame.lcms_target_summaries_by_well = {"A1": "Used Product Details exactly"}
        self.frame._last_product_identity_rows = {
            "A1": {"reaction_well": "A1", "pyparse_well": "C1", "desired product smiles": "CCO"}
        }
        self.frame._ketcher_template_queue = queue.Queue()
        self.frame._ketcher_template_queue.put("$RXN\npending template")
        self.frame.reaction_var = _FakeVar("Amide coupling")
        self.frame._refresh_product_details_preview = MagicMock()
        self.frame.logw = MagicMock()

    def test_confirmed_clear_removes_custom_state_and_preserves_reaction_type(self):
        with tempfile.TemporaryDirectory() as directory:
            stored_template = Path(directory) / "custom_reaction_template_from_ketcher.rxn"
            stored_template.write_text("$RXN\nstored template\n", encoding="utf-8")
            with (
                patch("cheminformatics_frame.KETCHER_TEMPLATE_PATH", stored_template),
                patch("cheminformatics_frame.messagebox.askyesno", return_value=True),
            ):
                self.frame._clear_custom_input_reaction()
            self.assertFalse(stored_template.exists())

        self.assertEqual("", self.frame.custom_template_text.value)
        self.assertEqual({}, self.frame.custom_products)
        self.assertEqual({}, self.frame.custom_failures)
        self.assertFalse(self.frame.product_details_generated)
        # Keep the prior target until regeneration can compare actual products.
        # This preserves reviewed settings if the built-in product is identical.
        self.assertEqual({"A1": "CCO"}, self.frame.lcms_target_smiles_by_well)
        self.assertEqual({"A1": "Used Product Details exactly"}, self.frame.lcms_target_summaries_by_well)
        self.assertEqual(self.frame._last_product_identity_rows, self.frame.pending_product_identity_rows)
        self.assertTrue(self.frame._ketcher_template_queue.empty())
        self.assertEqual("Amide coupling", self.frame.reaction_var.get())
        self.frame._refresh_product_details_preview.assert_called_once_with(show_products=False)

    def test_cancel_leaves_custom_state_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            stored_template = Path(directory) / "custom_reaction_template_from_ketcher.rxn"
            stored_template.write_text("$RXN\nstored template\n", encoding="utf-8")
            with (
                patch("cheminformatics_frame.KETCHER_TEMPLATE_PATH", stored_template),
                patch("cheminformatics_frame.messagebox.askyesno", return_value=False),
            ):
                self.frame._clear_custom_input_reaction()

            self.assertTrue(stored_template.exists())

        self.assertTrue(self.frame.custom_template_text.value)
        self.assertIn("A1", self.frame.custom_products)
        self.assertTrue(self.frame.product_details_generated)
        self.assertFalse(self.frame._ketcher_template_queue.empty())
        self.frame._refresh_product_details_preview.assert_not_called()


if __name__ == "__main__":
    unittest.main()
