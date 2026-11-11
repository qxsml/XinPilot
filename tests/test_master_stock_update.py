import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compound_notes_frame import CompoundNotesFrame, CompoundRecord, DATA_HEADERS, DISPLAY_HEADER_LABELS
from xinpilot.application.stock_update import stock_corrections, stock_updates, structure_key


class MasterStockTests(unittest.TestCase):
    def test_correction_comparisons(self):
        existing = {'Solvent': 'DMSO', 'Conc.': '0.1'}
        self.assertEqual(stock_corrections(existing, {'Solvent': ' dmso ', 'Conc.': '0.100'}), {})
        self.assertEqual(stock_corrections(existing, {'Conc.': '1e-1'}), {})
        self.assertEqual(stock_corrections(existing, {}), {})
        self.assertEqual(stock_corrections(existing, {'Solvent': 'water', 'Conc.': 0}),
                         {'Solvent': ('DMSO', 'water'), 'Conc.': ('0.1', 0)})
        self.assertIn('Conc.', stock_corrections({}, {'Conc.': '0.1'}))
        for invalid in ['nan', 'Infinity', '-0.1', '100 mM', 'bad']:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                stock_corrections(existing, {'Conc.': invalid})

    def test_workbook_correction_approval_and_cancellation(self):
        cases = [({'Solvent': 'water'}, True, True),
                 ({'Solvent': 'water'}, False, True),
                 ({'Conc.': '0.2'}, True, True),
                 ({'Conc.': '0.2'}, False, True),
                 ({'Conc.': '0.10000000001'}, True, True),
                 ({'Solvent': 'water', 'Conc.': '0.2'}, True, True),
                 ({'Conc.': '0.100', 'Solvent': ' dmso '}, True, False),
                 ({'Solvent': '', 'Conc.': ''}, True, False),
                 ({'SMILES': 'CO', 'Solvent': 'water'}, True, False),
                 ({'Conc.': 'NaN'}, True, False)]
        for changes, approve, expect_prompt in cases:
            with self.subTest(changes=changes, approve=approve), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'master.xlsx'
                original = {'ID': 'BB1', 'SMILES': 'CCO', 'Name': 'ethanol',
                            'Nature': 'old', 'Volume': '10', 'Solvent': 'DMSO', 'Conc.': '0.1'}
                incoming = dict(original, Name='corrected', Nature='new', Volume='5', **changes)
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.append(DATA_HEADERS)
                ws.append([original.get(h, '') for h in DATA_HEADERS])
                wb.save(path)
                wb.close()
                frame = object.__new__(CompoundNotesFrame)
                frame._commit_current_form_to_record = Mock()
                frame.master_stock_excel_var = SimpleNamespace(get=lambda: str(path))
                frame.status_var = Mock()
                # A separate physical stock may have identical contents and name.
                frame.records = [CompoundRecord(incoming), CompoundRecord(dict(original, ID='BB2'))]
                with patch('compound_notes_frame.messagebox.askokcancel', return_value=approve) as confirm, \
                        patch('compound_notes_frame.messagebox.showinfo'), \
                        patch('compound_notes_frame.messagebox.showwarning'), \
                        patch('compound_notes_frame.messagebox.showerror') as error:
                    frame._append_to_master_stock_list()
                    error.assert_not_called()
                    self.assertEqual(confirm.call_count, int(expect_prompt))
                    if expect_prompt:
                        self.assertEqual(confirm.call_args.kwargs['default'], 'cancel')
                        self.assertIn('BB1', confirm.call_args.args[1])
                        for field in ('Solvent', 'Conc.'):
                            if field in changes:
                                self.assertIn(str(original[field]), confirm.call_args.args[1])
                                self.assertIn(str(changes[field]), confirm.call_args.args[1])
                wb = openpyxl.load_workbook(path)
                ws = wb.active
                row = {h: ws.cell(2, c + 1).value for c, h in enumerate(DATA_HEADERS)}
                self.assertEqual(ws.max_row, 3)
                self.assertEqual(ws.cell(3, DATA_HEADERS.index('ID') + 1).value, 'BB2')
                blocked = 'SMILES' in changes or changes.get('Conc.') == 'NaN'
                if blocked or (expect_prompt and not approve):
                    for field, value in original.items():
                        self.assertEqual(row[field], value)
                else:
                    self.assertEqual(row['Name'], 'corrected')
                    self.assertEqual(row['Nature'], 'new')
                    self.assertEqual(row['Volume'], '5')
                    for field in ('Solvent', 'Conc.'):
                        expected = incoming[field] or original[field]
                        if field == 'Conc.':
                            self.assertEqual(float(row[field]), float(expected))
                        else:
                            self.assertEqual(row[field], expected)
                wb.close()

    def test_name_nature_and_numeric_zero_updates(self):
        existing = {'SMILES': 'CCO', 'Name': 'old', 'Nature': 'old nature'}
        self.assertEqual(stock_updates(existing, {
            'SMILES': 'OCC', 'Name': 'new', 'Nature': 'new nature', 'Volume': 0,
        }), {'Name': 'new', 'Nature': 'new nature', 'Volume': 0})
        for blank in ['', '  ', None]:
            self.assertEqual(stock_updates(existing, {
                'SMILES': 'CCO', 'Name': blank, 'Nature': blank,
            }), {})

    def test_batch_identity_checks_before_workbook_writes(self):
        for second_smiles in ['CO', '', 'not-smiles', 'OCC']:
            with self.subTest(second_smiles=second_smiles), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'master.xlsx'
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.append(DATA_HEADERS)
                original = {'ID': 'BB1', 'SMILES': 'CCO', 'Name': 'old',
                            'Nature': 'old nature', 'Volume': '10'}
                ws.append([original.get(h, '') for h in DATA_HEADERS])
                wb.save(path)
                wb.close()
                incoming = [
                    {'ID': 'BB1', 'SMILES': 'CCO', 'Name': 'updated', 'Nature': 'new nature', 'Volume': 0},
                    {'ID': 'NEW', 'SMILES': 'CCO', 'Name': 'new compound', 'Nature': 'new nature'},
                    {'ID': ' bb1 ', 'SMILES': second_smiles, 'Volume': '999'},
                    {'ID': 'new', 'SMILES': second_smiles},
                    {'ID': 'OTHER', 'SMILES': 'CCC', 'Name': 'unaffected'},
                ]
                frame = object.__new__(CompoundNotesFrame)
                frame._commit_current_form_to_record = Mock()
                frame.master_stock_excel_var = SimpleNamespace(get=lambda: str(path))
                frame.status_var = Mock()
                frame.records = [CompoundRecord(r) for r in incoming]
                with patch('compound_notes_frame.messagebox.showinfo'), \
                        patch('compound_notes_frame.messagebox.showwarning') as warning, \
                        patch('compound_notes_frame.messagebox.showerror') as error:
                    frame._append_to_master_stock_list()
                    error.assert_not_called()
                wb = openpyxl.load_workbook(path)
                ws = wb.active
                rows = [{h: ws.cell(r, c + 1).value for c, h in enumerate(DATA_HEADERS)}
                        for r in range(2, ws.max_row + 1)]
                wb.close()
                self.assertEqual([r['ID'] for r in rows], ['BB1', 'OTHER'])
                for field, value in original.items():
                    self.assertEqual(rows[0][field], value)
                self.assertIn('rows 1, 3', warning.call_args.args[1])
                self.assertIn('rows 2, 4', warning.call_args.args[1])

    def test_equivalent_smiles_and_preserve_blank_fields(self):
        result = stock_updates({'SMILES': 'CCO', 'Name': 'Ethanol', 'Solvent': 'water'},
                               {'SMILES': 'OCC', 'Name': 'new', 'Volume': '0', 'Solvent': '', 'Conc.': '0.2'})
        self.assertEqual(result, {'Volume': '0', 'Conc.': '0.2', 'Name': 'new'})
        self.assertEqual(structure_key('[CH3:1][OH:2]'), structure_key('CO'))

    def test_different_structures_rejected(self):
        for left, right in [('CCO', 'CO'), ('F[C@H](Cl)Br', 'F[C@@H](Cl)Br'),
                            ('[13CH3]O', 'CO'), ('CN', 'C[NH3+]'), ('CC(=O)[O-].[Na+]', 'CC(=O)O')]:
            with self.subTest(left=left), self.assertRaises(ValueError):
                stock_updates({'SMILES': left}, {'SMILES': right, 'Volume': '50'})

    def test_unverifiable_identity_rejected(self):
        for smiles in ['', 'not-smiles']:
            for left, right in [(smiles, 'CCO'), ('CCO', smiles)]:
                with self.assertRaises(ValueError):
                    stock_updates({'SMILES': left}, {'SMILES': right})

    def test_cas_name_populates_only_blank_legacy_name(self):
        from test_compound_cas_lookup import CompoundCasLookupTests
        frame = CompoundCasLookupTests().make_frame()
        frame.cas_smiles_var.set('CCO'); frame.cas_name_var.set('ethanol')
        frame._apply_cas_to_form()
        self.assertEqual(frame.vars['Name'].get(), 'ethanol')
        frame.vars['Name'].set('My ethanol'); frame._apply_cas_to_form()
        self.assertEqual(frame.vars['Name'].get(), 'My ethanol')
        self.assertIn('Name', DATA_HEADERS)
        self.assertEqual(DISPLAY_HEADER_LABELS['Name'], 'Chemical name')

    def test_real_workbook_update_block_and_duplicate_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'master.xlsx'
            wb = openpyxl.Workbook(); ws = wb.active; ws.append(DATA_HEADERS)
            original = {'ID': 'BB1', 'Name': 'ethanol', 'SMILES': 'CCO', 'Volume': '10', 'Solvent': 'water'}
            conflict = {'ID': 'BB2', 'Name': 'methanol', 'SMILES': 'CO', 'Volume': '20'}
            for row in [original, conflict]: ws.append([row.get(h, '') for h in DATA_HEADERS])
            ws.cell(2, len(DATA_HEADERS) + 1, '=1+2')
            wb.save(path); wb.close()
            incoming = [dict(original, SMILES='OCC', **{'Volume': '100', 'Conc.': '0.2', 'Quantity (mg)': '9.2', 'Quantity(umol)': '200', 'Solvent added (uL)': '1000', 'Solvent': ''}),
                        dict(conflict, SMILES='CC', Volume='999'),
                        {'ID': 'BB3', 'Name': 'ethanol', 'SMILES': 'CCO'},
                        {'ID': 'BB4', 'Name': 'new', 'SMILES': 'CCC'},
                        {'ID': 'BB4', 'Name': 'new', 'SMILES': 'CCC'}]
            frame = object.__new__(CompoundNotesFrame)
            frame._commit_current_form_to_record = Mock()
            frame.master_stock_excel_var = SimpleNamespace(get=lambda: str(path))
            frame.status_var = Mock()
            frame.records = [CompoundRecord(r) for r in incoming]
            with patch('compound_notes_frame.messagebox.askokcancel', return_value=True), patch('compound_notes_frame.messagebox.showinfo'), patch('compound_notes_frame.messagebox.showwarning') as warning:
                frame._append_to_master_stock_list()
                self.assertIn('BB2', warning.call_args.args[1])
            wb = openpyxl.load_workbook(path); ws = wb.active
            rows = [{h: ws.cell(r, c + 1).value for c, h in enumerate(DATA_HEADERS)} for r in range(2, ws.max_row + 1)]
            self.assertEqual([r['ID'] for r in rows], ['BB1', 'BB2', 'BB3'])
            for key in ['Volume', 'Conc.', 'Quantity (mg)', 'Quantity(umol)', 'Solvent added (uL)']:
                self.assertEqual(rows[0][key], incoming[0][key])
            self.assertEqual(rows[0]['Solvent'], 'water')
            self.assertEqual(rows[1]['Volume'], '20')
            self.assertEqual(ws.cell(2, len(DATA_HEADERS) + 1).value, '=1+2')
            self.assertEqual(ws.cell(1, DATA_HEADERS.index('Name') + 1).value, 'Name')
            wb.close()
            # Load the saved workbook through the existing header-based importer.
            frame._deleted_source_rows = set()
            frame._refresh_tree = Mock()
            frame._set_associated_workbook_name = Mock()
            frame._mark_saved_snapshot = Mock()
            frame._load_excel(path)
            self.assertEqual(frame.records[0].values['Name'], 'ethanol')
