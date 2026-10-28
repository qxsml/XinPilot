"""Serve JSON-line requests on the controller's Tk thread.

Reading pipes never touches Tk. Scheduling the next pump before dispatch lets
nested Tk prompt loops keep servicing snapshots and answers while an earlier
request is waiting for its dialog to finish.
"""

from __future__ import annotations

import json
import queue
import threading
import traceback
from typing import Any, TextIO

from desktop.protocol import Request, encode_message

_END_OF_INPUT = object()


class ControllerServer:
    POLL_INTERVAL_MS = 20
    REQUESTS_PER_TICK = 25

    def __init__(self, controller, input_stream: TextIO, output_stream: TextIO):
        self.controller = controller
        self.input = input_stream
        self.output = output_stream
        self.requests: queue.Queue[Any] = queue.Queue()

    def read_requests(self):
        try:
            for line in self.input:
                try:
                    self.requests.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            # The host has exited. Release the hidden Tk process even if the
            # host could not send its final stop request.
            self.requests.put(_END_OF_INPUT)

    def pump(self):
        controller = self.controller
        if controller.stopped:
            return
        controller.app.after(self.POLL_INTERVAL_MS, self.pump)
        for _ in range(self.REQUESTS_PER_TICK):
            try:
                raw = self.requests.get_nowait()
            except queue.Empty:
                break
            if raw is _END_OF_INPUT:
                controller.stop()
                return
            identifier = raw.get("id") if isinstance(raw, dict) else None
            try:
                request = Request.parse(raw)
                if request.method == "snapshot":
                    result = controller.snapshot()
                elif request.method == "event":
                    result = controller.event(request.data)
                else:
                    controller.stop()
                    return
                response = {"id": request.id, "result": result}
            except Exception:
                # Without a correlatable id, there is no caller to answer.
                if isinstance(identifier, bool) or not isinstance(identifier, int):
                    continue
                response = {"id": identifier, "error": traceback.format_exc()}
            self.output.write(encode_message(response))
            self.output.flush()
            if controller.stopped:
                return

    def run(self):
        reader = threading.Thread(
            target=self.read_requests, name="xinpilot-controller-requests", daemon=True
        )
        reader.start()
        self.controller.app.after(self.POLL_INTERVAL_MS, self.pump)
        self.controller.app.mainloop()
