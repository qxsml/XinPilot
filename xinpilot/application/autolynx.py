"""MassLynx sample-list CSV export, independent of GUI and chemistry engines."""
import csv
import io
from decimal import Decimal, InvalidOperation
import re
from pathlib import Path

HEADERS = 'FILE_NAME FILE_TEXT MS_FILE MS_TUNE_FILE INLET_FILE SAMPLE_LOCATION SAMPLE_GROUP TYPE PROCESS PROCESS_PARAMS ID CONC_A CONC_B CONC_C CONC_D CONC_E CONC_F INJ_VOL QUAN_REF METH_DB Index'.split()
METHOD_FIELDS = ('MS_FILE', 'MS_TUNE_FILE', 'INLET_FILE', 'PROCESS', 'PROCESS_PARAMS')


def load_methods(path):
    """Read uniform method settings only; never reuse volume or sample metadata."""
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('The example needs unique MassLynx column headings.')
        if not {'MS_FILE', 'INLET_FILE'} <= set(reader.fieldnames):
            raise ValueError('The example must contain MS_FILE and INLET_FILE.')
        rows = list(reader)
    if not rows:
        raise ValueError('The example contains no samples.')
    result = {}
    for field in METHOD_FIELDS:
        values = {str(row.get(field) or '').strip() for row in rows}
        if len(values) != 1:
            raise ValueError(f'The example contains different {field} values. Choose a uniform example or enter methods manually.')
        result[field] = values.pop()
    return result


def sample_csv(samples, settings):
    """Validate all samples before returning any output. Wells are LCMS wells."""
    plate = str(settings.get('plate', '')).strip()
    if not re.fullmatch(r'[1-9][0-9]*', plate):
        raise ValueError('Enter a positive Waters plate position, for example 1 or 2.')
    try:
        volume = Decimal(str(settings.get('INJ_VOL', '')).strip())
    except (InvalidOperation, TypeError, ValueError):
        volume = Decimal(0)
    if not volume.is_finite() or volume <= 0:
        raise ValueError('Enter a positive injection volume in uL for this export.')
    # Protect decimal expansion while leaving physical limits to the instrument setting.
    if volume < Decimal('0.000000001') or volume > Decimal('1000000'):
        raise ValueError('Injection volume is outside the supported CSV range (0.000000001 to 1000000 uL).')
    maximum = str(settings.get('max_injection_ul', '')).strip()
    if maximum:
        try:
            maximum_value = Decimal(maximum)
        except InvalidOperation:
            raise ValueError('Enter a positive instrument maximum injection volume.') from None
        if not maximum_value.is_finite() or maximum_value <= 0:
            raise ValueError('Enter a positive instrument maximum injection volume.')
        if volume > maximum_value:
            raise ValueError('Injection volume exceeds the configured instrument maximum.')
    for field in ('MS_FILE', 'INLET_FILE'):
        if not str(settings.get(field, '')).strip():
            raise ValueError(f'Enter {field}.')
    if settings.get('PROCESS', '').strip() and not settings.get('PROCESS_PARAMS', '').strip():
        raise ValueError('Enter the processing method, or leave processing blank.')
    limits = {'48-well': (6, 8), '96-well': (8, 12)}
    if settings.get('format') not in limits:
        raise ValueError('Choose the LCMS plate format.')
    max_row, max_col = limits[settings['format']]
    names, wells, output = set(), set(), []
    for sample in samples:
        name = str(sample.get('reaction_name') or '').strip()
        if not name or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith('.'):
            raise ValueError('Each reaction needs a valid sample filename (no path characters).')
        base = name.split('.', 1)[0].rstrip(' ').upper()
        if base in {'CON', 'PRN', 'AUX', 'NUL'} or re.fullmatch(r'(COM|LPT)[1-9\u00b9\u00b2\u00b3]', base):
            raise ValueError(f'{name}: Windows reserved names cannot be used as sample filenames.')
        if len(name.encode('utf-16-le')) // 2 > 200:
            raise ValueError('Sample filenames must be at most 200 characters, leaving room for the data extension.')
        if name.casefold() in names:
            raise ValueError(f'Duplicate reaction name: {name}. Rename it in LCMS Input first.')
        names.add(name.casefold())
        well = str(sample.get('pyparse_well') or '').strip().upper()
        match = re.fullmatch(r'([A-Z])([1-9][0-9]*)', well)
        if not match or not (1 <= ord(match[1])-64 <= max_row and 1 <= int(match[2]) <= max_col):
            raise ValueError(f'{name}: assign a valid LCMS well for {settings["format"]} (currently {well or "blank"}).')
        if well in wells:
            raise ValueError(f'Duplicate LCMS well: {well}.')
        wells.add(well)
        row = {field: str(settings.get(field, '')).strip() for field in METHOD_FIELDS}
        row.update(FILE_NAME=name, SAMPLE_LOCATION=f'{plate}:{match[1]},{int(match[2])}', TYPE='ANALYTE', INJ_VOL=format(volume, 'f'))
        output.append((ord(match[1]), int(match[2]), row))
    if not output:
        raise ValueError('No LCMS Input samples are available.')
    order = settings.get('order', 'Across rows')
    if order not in ('Across rows', 'Down columns'):
        raise ValueError('Choose an injection order.')
    output.sort(key=lambda item: (item[0], item[1]) if order == 'Across rows' else (item[1], item[0]))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(item[2] for item in output)
    return stream.getvalue()
