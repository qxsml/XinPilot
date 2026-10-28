"""Product connectivity, template scope, and reacting-centre stereochemistry."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import integrated_tecan_compound_cheminformatics as core


class ReactionTemplateScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reactions = {r['id']: r for r in core.load_reactions()}

    def products(self, reaction, *inputs):
        return core.run_reaction(self.reactions[reaction]['smarts'],
                                 *[core.canonical_smiles(s)[0] for s in inputs])

    def test_all_menu_reactions_have_a_known_product_example(self):
        cases = json.loads((ROOT / 'tests/fixtures/reaction_examples.json').read_text())
        self.assertEqual(set(self.reactions), {c['reaction'] for c in cases})
        for case in cases:
            with self.subTest(reaction=case['reaction']):
                expected = [core.canonical_smiles(case['expected'])[1]]
                self.assertEqual(expected, self.products(case['reaction'], *case['inputs']))
                self.assertEqual(expected, self.products(case['reaction'], *reversed(case['inputs'])))

    def test_heck_rejects_unsupported_alkenes_without_discarding_substituents(self):
        for alkene in ('CC=CC', 'C=C(C)C'):
            self.assertEqual([], self.products('heck', 'Brc1ccccc1', alkene))

    def test_click_requires_terminal_alkyne(self):
        self.assertEqual([], self.products('click_triazole', 'CN=[N+]=[N-]', 'CC#CC'))
        self.assertEqual(['Cc1cn(C)nn1'], self.products('click_triazole', 'CN=[N+]=[N-]', 'CC#C'))

    def test_mitsunobu_inverts_both_enantiomers_without_inventing_chirality(self):
        for alcohol, expected in [('C[C@H](O)CC', 'R'), ('C[C@@H](O)CC', 'S')]:
            product, = self.products('mitsunobu', alcohol, 'Oc1ccccc1')
            centers = core.Chem.FindMolChiralCenters(core.Chem.MolFromSmiles(product))
            self.assertEqual([expected], [label for _, label in centers])
        product, = self.products('mitsunobu', 'CC(O)CC', 'Oc1ccccc1')
        self.assertNotIn('@', product)

    def test_aldehydes_and_ketones_form_oximes_and_reductive_amination_products(self):
        self.assertEqual(['CC=NO'], self.products('oxime_formation', 'CC=O', 'NO'))
        self.assertEqual(['CCNC'], self.products('reductive_amination', 'CC=O', 'CN'))
        self.assertEqual(['CCN(C)C'], self.products('reductive_amination', 'CC=O', 'CNC'))
        self.assertEqual(['CCO'], self.products('carbonyl_reduction', 'CC=O'))

    def test_carbonyl_templates_exclude_acyl_derivatives(self):
        for substrate in ('CC(=O)OC', 'CC(=O)O', 'CC(=O)N', 'CC(=O)Cl'):
            for rid, others in [('carbonyl_reduction', ()), ('oxime_formation', ('NO',)),
                                ('reductive_amination', ('CN',))]:
                with self.subTest(reaction=rid, substrate=substrate):
                    self.assertEqual([], self.products(rid, substrate, *others))


if __name__ == '__main__':
    unittest.main()
