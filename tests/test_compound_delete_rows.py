import sys
import tkinter as tk
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compound_notes_frame import (  # noqa: E402
    CompoundNotesFrame,
    CompoundRecord,
    DATA_HEADERS,
)


class CompoundDeleteRowsTests(unittest.TestCase):
    def test_delete_row_removes_every_selected_record_and_tracks_excel_rows(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        try:
            frame = CompoundNotesFrame(root)
            records = []
            for index, compound_id in enumerate(("A", "B", "C", "D"), start=2):
                values = {header: "" for header in DATA_HEADERS}
                values.update({"ID": compound_id, "Solvent": "DMA"})
                records.append(CompoundRecord(values, source_row=index))
            frame.records = records
            frame._refresh_tree()
            frame.tree.selection_set(("1", "3"))

            frame._delete_row()

            self.assertEqual(["A", "C"], [record.values["ID"] for record in frame.records])
            self.assertEqual({3, 5}, frame._deleted_source_rows)
            self.assertEqual("Deleted 2 selected rows.", frame.status_var.get())
            self.assertEqual((), frame.tree.selection())
        finally:
            for after_id in root.tk.call("after", "info"):
                try:
                    root.tk.call("after", "cancel", after_id)
                except tk.TclError:
                    pass
            root.destroy()


if __name__ == "__main__":
    unittest.main()
