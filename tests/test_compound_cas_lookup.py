"""Offline CAS lookup regression tests, without a Tk window or HTTP requests."""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compound_notes_frame import CompoundNotesFrame  # noqa: E402
from rdkit import Chem  # noqa: E402


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class CompoundCasLookupTests(unittest.TestCase):
    CAS = "56-41-7"

    def make_frame(self):
        frame = object.__new__(CompoundNotesFrame)
        for name in (
            "cas_lookup_var", "cas_smiles_var", "cas_mw_var", "cas_name_var",
            "cas_cid_var", "cas_status_var", "status_var",
        ):
            setattr(frame, name, Value())
        frame.cas_lookup_var.set(self.CAS)
        frame.vars = {name: Value() for name in ("CAS", "SMILES", "MW", "Name")}
        frame._update_structure_preview = Mock()
        return frame

    def run_lookup(self, frame, records):
        """Records deliberately supply mocked property variants, not live data."""
        requested = []

        def respond(url, timeout):
            requested.append(url)
            self.assertEqual(20, timeout)
            if "/xref/RN/" in url:
                payload = {"IdentifierList": {"CID": list(records)}}
            else:
                cid = int(url.split("/cid/", 1)[1].split("/", 1)[0])
                synonyms, properties = records[cid]
                if "/synonyms/" in url:
                    payload = {"InformationList": {"Information": [{"Synonym": synonyms}]}}
                else:
                    self.assertIn("/property/", url)
                    payload = {"PropertyTable": {"Properties": [properties]}}
            return io.BytesIO(json.dumps(payload).encode("utf-8"))

        with patch("compound_notes_frame.urlopen", side_effect=respond), \
                patch("compound_notes_frame.messagebox.showerror") as error, \
                patch("compound_notes_frame.messagebox.showwarning") as warning:
            frame._fetch_from_cas()
        error.assert_not_called()
        return requested, warning

    def test_current_and_legacy_properties_preserve_stereochemistry_and_isotopes(self):
        cases = (
            ("N[C@@H](C)C(=O)O", "NC(C)C(=O)O"),
            ("[13CH3][C@@H](N)C(=O)O", "CC(N)C(=O)O"),
        )
        for full_key, connectivity_key in (
            ("IsomericSMILES", "CanonicalSMILES"),
            ("SMILES", "ConnectivitySMILES"),
        ):
            for full_smiles, connectivity in cases:
                with self.subTest(response=full_key, smiles=full_smiles):
                    frame = self.make_frame()
                    _, warning = self.run_lookup(frame, {
                        1: ([self.CAS], {
                            full_key: full_smiles,
                            connectivity_key: connectivity,
                            "MolecularWeight": "89.09",
                            "IUPACName": "mock compound",
                        }),
                    })
                    warning.assert_not_called()
                    self.assertEqual(full_smiles, frame.cas_smiles_var.get())
                    frame._apply_cas_to_form()
                    self.assertEqual(full_smiles, frame.vars["SMILES"].get())
                    mol = Chem.MolFromSmiles(frame.vars["SMILES"].get())
                    self.assertIsNotNone(mol)
                    self.assertTrue(Chem.FindMolChiralCenters(mol))
                    if "13C" in full_smiles:
                        self.assertIn(13, [atom.GetIsotope() for atom in mol.GetAtoms()])

    def test_full_smiles_wins_over_legacy_connectivity_in_mixed_response(self):
        frame = self.make_frame()
        full = "N[C@@H](C)C(=O)O"
        self.run_lookup(frame, {1: ([self.CAS], {
            "CanonicalSMILES": "NC(C)C(=O)O", "SMILES": full,
        })})
        self.assertEqual(full, frame.cas_smiles_var.get())

    def test_connectivity_only_response_remains_supported(self):
        for key in ("CanonicalSMILES", "ConnectivitySMILES"):
            with self.subTest(property=key):
                frame = self.make_frame()
                self.run_lookup(frame, {1: ([self.CAS], {key: "NC(C)C(=O)O"})})
                self.assertEqual("NC(C)C(=O)O", frame.cas_smiles_var.get())

    def test_exact_cas_verification_skips_nonmatching_candidate(self):
        frame = self.make_frame()
        requests, warning = self.run_lookup(frame, {
            1: (["not " + self.CAS], {"SMILES": "CC"}),
            2: ([self.CAS], {"SMILES": "N[C@@H](C)C(=O)O"}),
        })
        warning.assert_not_called()
        self.assertEqual("2", frame.cas_cid_var.get())
        self.assertFalse(any("/cid/1/property/" in url for url in requests))

    def test_no_exact_cas_match_does_not_apply_a_structure(self):
        frame = self.make_frame()
        frame.vars["SMILES"].set("CCO")
        _, warning = self.run_lookup(frame, {1: (["not " + self.CAS], {"SMILES": "CC"})})
        warning.assert_called_once()
        self.assertEqual("", frame.cas_smiles_var.get())
        self.assertEqual("CCO", frame.vars["SMILES"].get())
        frame._update_structure_preview.assert_not_called()

    def test_applying_lookup_keeps_entered_mw_and_name(self):
        for initial_mw, expected_mw in (("", "89.09"), ("90.1", "90.1")):
            with self.subTest(initial_mw=initial_mw):
                frame = self.make_frame()
                frame.vars["MW"].set(initial_mw)
                frame.vars["Name"].set("user name")
                self.run_lookup(frame, {1: ([self.CAS], {
                    "SMILES": "N[C@@H](C)C(=O)O", "MolecularWeight": "89.09",
                    "IUPACName": "mock compound",
                })})
                frame._apply_cas_to_form()
                self.assertEqual(self.CAS, frame.vars["CAS"].get())
                self.assertEqual(expected_mw, frame.vars["MW"].get())
                self.assertEqual("user name", frame.vars["Name"].get())


if __name__ == "__main__":
    unittest.main()
