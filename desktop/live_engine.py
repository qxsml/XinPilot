"""Controller process composition and Tk event-loop lifetime.

The established application owns validation and scientific/project state.
Its invisible Tk widgets are a compatibility adapter for the TypeScript UI;
projection, event translation, prompts and pipe transport live separately.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop.controller_server import ControllerServer
from desktop.protocol import validate_event
from desktop.tk_dialogs import TkDialogAdapter, prompt
from desktop.tk_events import dispatch_event
from desktop.tk_snapshot import TkSnapshotProjector


class Controller:
    """Own one application and its adapters, all on the Tk main thread."""

    def __init__(self, width=1280, height=850):
        self.pending = {}
        self.menu = None
        self.pointer = (20, 20)
        self.dialog = None
        self.errors = []
        self.viewport = (width, height)
        self.stopped = False
        self._dialogs = TkDialogAdapter(self)
        try:
            self._dialogs.install()
            import integrated_full_software as integrated

            # The native host owns sizing; the hidden layout root must not
            # maximize itself or appear briefly while it is constructed.
            original_maximize = integrated.IntegratedFullApp._maximize_on_open
            integrated.IntegratedFullApp._maximize_on_open = lambda app: None
            try:
                self.app = integrated.IntegratedFullApp()
            finally:
                integrated.IntegratedFullApp._maximize_on_open = original_maximize
            self._destroy_app = self.app.destroy
            self.app.destroy = self.stop
            self._projection = TkSnapshotProjector(self)
            self.app.overrideredirect(True)
            self.app.geometry(f"{width}x{height}-32000-32000")
            self.app.deiconify()
            self.app.report_callback_exception = self._callback_error
            self.app.update()
        except Exception:
            self._dialogs.restore()
            raise

    def _callback_error(self, *exception_info):
        self.errors.append("".join(traceback.format_exception(*exception_info)))

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        try:
            # Cancel callbacks before their widget commands disappear.
            for token in self.app.tk.splitlist(self.app.tk.call("after", "info")):
                self.app.tk.call("after", "cancel", token)
            self._destroy_app()
        finally:
            self._dialogs.restore()

    def prompt(self, data):
        return prompt(self, data)

    def snapshot(self):
        return self._projection.snapshot()

    def serialize(self, widget):
        """Expose individual projections for existing desktop diagnostics."""
        return self._projection.serialize(widget)

    def event(self, request):
        return dispatch_event(self, validate_event(request))


def main():
    output = sys.stdout
    sys.stdout = sys.stderr  # Library diagnostics must not corrupt JSON replies.
    controller = Controller()
    server = ControllerServer(controller, sys.stdin, output)
    try:
        server.run()
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
