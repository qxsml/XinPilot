"""Read compound Excel/CSV tables through the same header and row rules."""
import csv
import re
from pathlib import Path


def read_compound_table(path, headers):
    """Return (source row, displayed values, original cells), without mutation."""
    path = Path(path)
    if path.suffix.lower() == '.csv':
        # utf-8-sig accepts ordinary UTF-8 and Excel's UTF-8 BOM export.
        # Keep all cells as text (not inferred numbers or executable formulas).
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream, strict=True))
        raw_rows = rows
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        try:
            rows = list(wb.worksheets[0].values)
        finally:
            wb.close()
        wb = openpyxl.load_workbook(path, data_only=False)
        try:
            raw_rows = list(wb.worksheets[0].values)
        finally:
            wb.close()

    columns = {str(value).strip(): index for index, value in enumerate(rows[0] if rows else [])
               if value is not None and str(value).strip()}

    def cell(row, header):
        index = columns.get(header)
        return row[index] if index is not None and index < len(row) else ''

    result = []
    for number, row in enumerate(rows[1:], start=2):
        values = {header: '' if cell(row, header) is None else str(cell(row, header))
                  for header in headers}
        if not any(value.strip() for value in values.values()):
            continue
        if re.match(r'^TEMP\d*$', values.get('ID', '').strip().upper()):
            continue
        raw = raw_rows[number - 1] if number <= len(raw_rows) else ()
        result.append((number, values, {header: cell(raw, header) for header in headers}))
    return result
