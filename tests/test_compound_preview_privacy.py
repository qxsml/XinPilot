"""Preview and SMILES actions must not disclose structures without consent."""
import io
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from rdkit import Chem
from rdkit.Chem import Descriptors
from compound_notes_frame import CompoundNotesFrame, DATA_HEADERS


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class PreviewPrivacyTests(unittest.TestCase):
    def frame(self):
        frame = object.__new__(CompoundNotesFrame)
        frame.vars = {key: Value() for key in DATA_HEADERS}
        frame.vars["SMILES"].set("CCO")
        frame.structure_cache = {}
        frame.structure_label = Mock()
        frame.status_var = Value()
        frame.quantity_input_unit_var = Value()
        frame.quantity_input_var = Value()
        frame.cas_lookup_var = Value()
        frame._confirm_pubchem_preview = Mock(return_value=False)
        return frame

    def test_smiles_action_is_local_and_preserves_existing_identity(self):
        frame = self.frame()
        frame.vars["CAS"].set("64-17-5")
        frame.vars["Name"].set("My ethanol stock")
        with patch("compound_notes_frame.urlopen") as network, \
                patch("compound_notes_frame.ImageTk.PhotoImage", return_value="local-image"), \
                patch("compound_notes_frame.messagebox.showinfo"), \
                patch("compound_notes_frame.messagebox.showerror") as error:
            frame._fetch_from_smiles()
        network.assert_not_called()
        error.assert_not_called()
        frame._confirm_pubchem_preview.assert_not_called()
        self.assertAlmostEqual(Descriptors.MolWt(Chem.MolFromSmiles("CCO")), float(frame.vars["MW"].get()), places=4)
        self.assertEqual("64-17-5", frame.vars["CAS"].get())
        self.assertEqual("My ethanol stock", frame.vars["Name"].get())
        self.assertEqual("local-image", frame.structure_img)

    def test_select_existing_record_and_cached_preview_are_local(self):
        frame = self.frame()
        frame.records = [SimpleNamespace(values={"ID": "BB1", "SMILES": "CCO"})]
        frame.tree = Mock()
        frame.tree.selection.return_value = ("0",)
        frame.solubility_panel = None
        frame._commit_pending_form_update = Mock()
        frame._commit_pending_quantity_update = Mock()
        with patch("compound_notes_frame.urlopen") as network, \
                patch("compound_notes_frame.ImageTk.PhotoImage", return_value="local-image") as photo:
            frame._on_tree_select(None)
            frame._on_tree_select(None)
        network.assert_not_called()
        photo.assert_called_once()
        frame._confirm_pubchem_preview.assert_not_called()

    def test_failed_preview_cancel_never_contacts_network(self):
        frame = self.frame()
        with patch("compound_notes_frame.Draw.MolToImage", side_effect=ValueError("drawing failed")), \
                patch("compound_notes_frame.urlopen") as network:
            frame._load_record_into_form({"ID": "BB1", "SMILES": "CCO"}, 0)
        frame._confirm_pubchem_preview.assert_called_once()
        network.assert_not_called()
        self.assertEqual("Structure preview unavailable", frame.structure_label.configure.call_args.kwargs["text"])

    def test_approved_fallback_only_fetches_image_and_caches_it(self):
        frame = self.frame()
        raw = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(raw, format="PNG")
        events = []
        frame._confirm_pubchem_preview.side_effect = lambda: events.append("consent") or True

        def request(url, timeout):
            self.assertIn("/compound/smiles/CCO/PNG?", url)
            events.append("request")
            return io.BytesIO(raw.getvalue())

        with patch("compound_notes_frame.Draw.MolToImage", side_effect=ValueError("drawing failed")), \
                patch("compound_notes_frame.urlopen", side_effect=request) as network, \
                patch("compound_notes_frame.ImageTk.PhotoImage", return_value="online-image"):
            frame._update_structure_preview("CCO")
            frame._update_structure_preview("CCO")
        self.assertEqual(["consent", "request"], events)
        network.assert_called_once()
        self.assertEqual("online-image", frame.structure_img)

    def test_invalid_smiles_action_does_not_lookup_or_overwrite_mw(self):
        frame = self.frame()
        frame.vars["SMILES"].set("not-a-smiles")
        frame.vars["MW"].set("123")
        with patch("compound_notes_frame.urlopen") as network, \
                patch("compound_notes_frame.messagebox.showerror") as error:
            frame._fetch_from_smiles()
        network.assert_not_called()
        error.assert_called_once()
        self.assertEqual("123", frame.vars["MW"].get())

    def test_popup_cancel_close_and_explicit_fetch(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        host = tk.Frame(root)
        for action, expected in (("Cancel", False), ("close", False), ("Fetch preview from PubChem", True)):
            def respond(action=action):
                dialog = next(w for w in host.winfo_children() if isinstance(w, tk.Toplevel))
                # A duplicate selection event must not open another consent window.
                self.assertFalse(CompoundNotesFrame._confirm_pubchem_preview(host))
                if action == "close":
                    dialog.destroy()
                else:
                    buttons = [b for w in dialog.winfo_children() for b in w.winfo_children()
                               if b.winfo_class() == "TButton"]
                    next(b for b in buttons if b.cget("text") == action).invoke()
            root.after(30, respond)
            self.assertEqual(expected, CompoundNotesFrame._confirm_pubchem_preview(host))


if __name__ == "__main__":
    unittest.main()
