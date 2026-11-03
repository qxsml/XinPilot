"""CSV and Excel share compound import rules; CSV never becomes a workbook target."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from openpyxl import Workbook, load_workbook
from compound_notes_frame import CompoundNotesFrame, CompoundRecord, DATA_HEADERS
from xinpilot.application.compound_table import read_compound_table


class CompoundCsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / 'stocks.csv'

    def write_csv(self, rows):
        with self.csv.open('w', encoding='utf-8-sig', newline='') as stream:
            csv.writer(stream).writerows(rows)

    def frame(self):
        frame = object.__new__(CompoundNotesFrame)
        frame.records = [CompoundRecord({'ID': 'OLD'})]
        frame._deleted_source_rows = set()
        frame._deleted_source_records = []
        frame.source_excel = self.root / 'previous.xlsx'
        for name in ('_refresh_tree', '_set_associated_workbook_name', '_mark_saved_snapshot',
                     '_commit_current_form_to_record', '_refresh_saved_excel_values',
                     '_commit_quantity_to_current_record'):
            setattr(frame, name, Mock())
        frame.status_var = Mock()
        frame._quantity_input_label = Mock(return_value='Quantity')
        return frame

    def test_same_mapping_duplicates_blanks_and_legacy_filter_as_excel(self):
        rows = [['SMILES', ' ID ', 'Name', 'Conc.', 'unknown'],
                ['CCO', '001', 'name, with "quotes"\nand newline', '0.2', 'ignore'],
                ['CCN', '001', 'duplicate retained', '', ''],
                ['', '', '', '', ''], ['O', 'TEMP2', '', '', ''],
                ['C', '', 'blank ID retained', '', '']]
        self.write_csv(rows)
        book = Workbook()
        for row in rows:
            book.active.append(row)
        xlsx = self.root / 'stocks.xlsx'
        book.save(xlsx)
        book.close()
        csv_rows = read_compound_table(self.csv, DATA_HEADERS)
        excel_rows = read_compound_table(xlsx, DATA_HEADERS)
        self.assertEqual([(n, v) for n, v, _ in csv_rows], [(n, v) for n, v, _ in excel_rows])
        self.assertEqual(['001', '001', ''], [v['ID'] for _, v, _ in csv_rows])

    def test_formula_source_cells_remain_preserved_for_excel(self):
        book = Workbook()
        book.active.append(['ID', 'MW'])
        book.active.append(['A', '=10+2'])
        path = self.root / 'formula.xlsx'
        book.save(path)
        book.close()
        row = read_compound_table(path, DATA_HEADERS)[0]
        self.assertEqual('', row[1]['MW'])
        self.assertEqual('=10+2', row[2]['MW'])

    def test_existing_picker_imports_csv_and_save_current_requests_excel(self):
        self.write_csv([['ID', 'SMILES', 'Conc.'], ['001', 'CCO', '0.2']])
        before = self.csv.read_bytes()
        frame = self.frame()
        with patch('compound_notes_frame.filedialog.askopenfilename', return_value=str(self.csv)) as picker:
            frame._pick_excel()
        self.assertIn('*.csv', str(picker.call_args))
        self.assertIsNone(frame.source_excel)
        frame._auto_save_quantity_column()
        self.assertEqual(before, self.csv.read_bytes())
        saved = self.root / 'saved.xlsx'
        with patch('compound_notes_frame.filedialog.asksaveasfilename', return_value=str(saved)), \
             patch('compound_notes_frame.messagebox.showerror') as error:
            self.assertTrue(frame._save_current_excel(show_message=False))
            error.assert_not_called()
        book = load_workbook(saved)
        self.addCleanup(book.close)
        id_column = next(cell.column for cell in book.active[1] if cell.value == 'ID')
        self.assertEqual('001', book.active.cell(2, id_column).value)
        self.assertEqual(before, self.csv.read_bytes())

    def test_bad_csv_keeps_previous_records_and_workbook(self):
        self.csv.write_text('ID,SMILES\nA,"unterminated', encoding='utf-8')
        frame = self.frame()
        previous = frame.source_excel
        with self.assertRaises(csv.Error):
            frame._load_excel(self.csv)
        self.assertEqual('OLD', frame.records[0].values['ID'])
        self.assertEqual(previous, frame.source_excel)


if __name__ == '__main__':
    unittest.main()
