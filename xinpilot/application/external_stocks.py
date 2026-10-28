"""Source-stock templates and staged compound additions for external imports."""
from __future__ import annotations

from .external_import import positive_number, source_key

HEADERS = ("Source labware", "Source well", "Chemical ID", "SMILES", "CAS", "Chemical name",
           "Concentration", "Concentration unit", "Building block")
CONCENTRATION_UNITS = {"M": 1.0, "mM": .001, "uM": .000001, "µM": .000001}


def write_template(path, sources):
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation
    book = Workbook()
    sheet = book.active
    sheet.title = "Source stocks"
    sheet.append(HEADERS)
    for source in sources.values():
        sheet.append([source["source_labware"], source["source_well"], source.get("chemical_id", ""),
                      "", "", "", "", "M", "yes" if source.get("is_building_block") else "no"])
    # Treat user identifiers as literal text, including leading '=' characters.
    for row in sheet:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in "ABCDEFGHI":
        sheet.column_dimensions[column].width = 24
    for column, formula in (("H", '"M,mM,uM"'), ("I", '"yes,no"')):
        validation = DataValidation(type="list", formula1=formula)
        validation.errorTitle = "Choose a listed value"
        validation.showErrorMessage = True
        sheet.add_data_validation(validation)
        validation.add(f"{column}2:{column}{max(2, sheet.max_row)}")
    book.save(path)


def stage_stocks(rows, sources, compounds):
    """Validate the entire template before changing any compounds or mappings.

    Existing records are never overwritten. Populated template fields must
    agree with existing records; corrections belong in Compound Notes.
    """
    from .stock_update import structure_key
    index = {}
    for record in compounds:
        cid = str(record.get("ID", "")).strip()
        if cid:
            if cid in index:
                raise ValueError(f"Duplicate Chemical ID in Compound Notes: {cid}")
            index[cid] = record
    updated = {k: dict(v) for k, v in sources.items()}
    additions, seen = {}, set()
    for number, row in enumerate(rows, 2):
        text = lambda field: str(row.get(field) or "").strip()
        key = source_key(text("Source labware"), text("Source well"))
        if key not in sources or key in seen:
            raise ValueError(f"Row {number}: unknown or duplicate source location.")
        seen.add(key)
        cid = text("Chemical ID")
        if not cid:
            raise ValueError(f"Row {number}: Chemical ID is required.")
        flag = text("Building block").lower()
        if flag not in {"", "yes", "no", "true", "false", "1", "0"}:
            raise ValueError(f"Row {number}: Building block must be yes or no.")
        conc = text("Concentration")
        if conc:
            unit = text("Concentration unit")
            if unit not in CONCENTRATION_UNITS:
                raise ValueError(f"Row {number}: concentration unit must be M, mM or uM.")
            conc = format(positive_number(conc, f"Row {number} concentration") * CONCENTRATION_UNITS[unit], ".12g")
        record = {"ID": cid, "SMILES": text("SMILES"), "CAS": text("CAS"), "Name": text("Chemical name"), "Conc.": conc}
        if record["SMILES"]:
            structure_key(record["SMILES"])
        existing = index.get(cid, additions.get(cid))
        if existing is not None:
            for field in ("SMILES", "Conc.", "CAS"):
                incoming = record[field]
                if not incoming:
                    continue
                previous = str(existing.get(field, "") or "").strip()
                equal = previous == incoming
                if previous and field == "SMILES":
                    equal = structure_key(previous) == structure_key(incoming)
                if previous and field == "Conc.":
                    equal = abs(float(previous) - float(incoming)) <= max(1e-12, abs(float(incoming)) * 1e-9)
                if not equal:
                    raise ValueError(f"{cid}: {field} differs from its existing record. Review Compound Notes first; no records were changed.")
        else:
            additions[cid] = record
        updated[key].update(chemical_id=cid, is_building_block=flag in {"yes", "true", "1"})
    return updated, list(additions.values())
