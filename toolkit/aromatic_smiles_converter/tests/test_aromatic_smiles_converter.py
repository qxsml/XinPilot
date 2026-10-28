import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aromatic_smiles_converter import (  # noqa: E402
    AROMATIC_TO_BONDS,
    BONDS_TO_AROMATIC,
    Chem,
    convert_smiles_line,
    convert_smiles_lines,
)


@unittest.skipIf(Chem is None, "RDKit is unavailable")
class AromaticSmilesConverterTests(unittest.TestCase):
    def assert_same_molecule(self, first: str, second: str):
        first_mol = Chem.MolFromSmiles(first)
        second_mol = Chem.MolFromSmiles(second)
        self.assertIsNotNone(first_mol)
        self.assertIsNotNone(second_mol)
        self.assertEqual(Chem.MolToSmiles(first_mol), Chem.MolToSmiles(second_mol))

    def test_benzene_converts_in_both_directions(self):
        self.assertEqual("C1=CC=CC=C1", convert_smiles_line("c1ccccc1", AROMATIC_TO_BONDS))
        self.assertEqual("c1ccccc1", convert_smiles_line("C1=CC=CC=C1", BONDS_TO_AROMATIC))

    def test_heteroaromatic_and_fused_rings_preserve_molecular_identity(self):
        for value in ("n1ccccc1", "c1ccc2ccccc2c1", "[nH]1cccc1"):
            with self.subTest(value=value):
                explicit = convert_smiles_line(value, AROMATIC_TO_BONDS)
                aromatic = convert_smiles_line(explicit, BONDS_TO_AROMATIC)
                self.assert_same_molecule(value, explicit)
                self.assert_same_molecule(value, aromatic)

    def test_nonaromatic_stereochemistry_is_preserved(self):
        value = "F[C@H](Cl)Br"
        converted = convert_smiles_line(value, BONDS_TO_AROMATIC)
        self.assertIn("@", converted)
        self.assert_same_molecule(value, converted)

    def test_invalid_smiles_and_direction_are_reported_per_line(self):
        self.assertTrue(convert_smiles_line("not-a-smiles", AROMATIC_TO_BONDS).startswith("[ERROR] Invalid SMILES"))
        self.assertTrue(convert_smiles_line("c1ccccc1", "unsupported").startswith("[ERROR] Unknown conversion direction"))

    def test_multiline_conversion_keeps_one_output_per_input_line(self):
        self.assertEqual(
            "C1=CC=CC=C1\nC1=CC=NC=C1",
            convert_smiles_lines("c1ccccc1\nn1ccccc1", AROMATIC_TO_BONDS),
        )


if __name__ == "__main__":
    unittest.main()
