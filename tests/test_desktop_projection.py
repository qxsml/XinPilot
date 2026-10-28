"""Tk projection ownership contract; transport threads run in a separate process."""

from types import SimpleNamespace
import unittest


class ProjectionTests(unittest.TestCase):
    def test_snapshot_projects_the_current_controller_dialog(self):
        import tkinter as tk
        from desktop.tk_snapshot import TkSnapshotProjector

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        controller = SimpleNamespace(
            app=root,
            dialog={"id": "first", "kind": "askstring"},
            menu=None,
            errors=["diagnostic"],
            viewport=(900, 600),
        )
        projector = TkSnapshotProjector(controller)
        self.assertEqual(controller.dialog, projector.snapshot()["dialog"])
        self.assertEqual([], controller.errors)
        controller.dialog = {"id": "second", "kind": "askyesno"}
        self.assertEqual("second", projector.snapshot()["dialog"]["id"])


if __name__ == "__main__":
    unittest.main()
