"""Thread-safe request correlation over the controller's JSON-line pipes."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, TextIO

from desktop.protocol import Request, Response, decode_response, encode_message


class ControllerClosed(RuntimeError):
    pass


@dataclass
class PendingReply:
    event: threading.Event = field(default_factory=threading.Event)
    response: Response | None = None


class PendingRequests:
    """Own request ids and wake every waiter exactly once on reply or EOF."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = 0
        self._pending: dict[int, PendingReply] = {}
        self.closed = threading.Event()

    def register(self) -> tuple[int, PendingReply]:
        with self._lock:
            if self.closed.is_set():
                raise ControllerClosed("The XinPilot controller has closed.")
            self._counter += 1
            reply = PendingReply()
            self._pending[self._counter] = reply
            return self._counter, reply

    def resolve(self, response: Response) -> bool:
        with self._lock:
            reply = self._pending.get(response["id"])
            if reply is None or reply.event.is_set():
                return False
            reply.response = response
            reply.event.set()
            return True

    def discard(self, identifier: int) -> None:
        with self._lock:
            self._pending.pop(identifier, None)

    def close(self, expected: bool) -> None:
        with self._lock:
            self.closed.set()
            for identifier, reply in self._pending.items():
                if reply.event.is_set():
                    continue
                reply.response = (
                    {"id": identifier, "result": {"closed": True}}
                    if expected
                    else {"id": identifier, "error": "Controller closed unexpectedly."}
                )
                reply.event.set()


class ControllerTransport:
    """Keep pipe IO independent of native windows and the hidden Tk adapter.

    The writer lock protects complete lines; the registry uses a separate lock
    so EOF and responses can release waiters while another thread is writing.
    """

    def __init__(
        self,
        reader: TextIO,
        writer: TextIO,
        *,
        expected_close: Callable[[], bool],
        on_close: Callable[[], None],
    ) -> None:
        self._input = reader
        self._output = writer
        self._expected_close = expected_close
        self._on_close = on_close
        self._write_lock = threading.Lock()
        self.pending = PendingRequests()
        self.closed = self.pending.closed
        self.reader = threading.Thread(
            target=self._read, name="xinpilot-controller-replies", daemon=True
        )

    def start(self) -> None:
        self.reader.start()

    def _read(self) -> None:
        try:
            for line in self._input:
                try:
                    response = decode_response(line)
                except ValueError:
                    # A third-party library may emit non-protocol stdout.
                    continue
                self.pending.resolve(response)
        finally:
            self.pending.close(expected=self._expected_close())
            self._on_close()

    def write(self, request: Request) -> None:
        encoded = encode_message(request.as_dict())
        with self._write_lock:
            self._output.write(encoded)
            self._output.flush()

    def call(self, method: str, data: Any = None, timeout: float = 1800) -> Any:
        # Validate before registering: invalid calls must never leak waiters.
        validated = Request.parse({"id": 0, "method": method, "data": data})
        try:
            identifier, reply = self.pending.register()
        except ControllerClosed:
            if self._expected_close():
                return {"closed": True}
            raise
        try:
            try:
                self.write(Request(identifier, validated.method, validated.data))
            except (BrokenPipeError, OSError):
                if self._expected_close():
                    return {"closed": True}
                raise
            if not reply.event.wait(timeout):
                raise TimeoutError("XinPilot is still waiting for a response.")
            response = reply.response
            assert response is not None  # Event is published only after response.
            if "error" in response:
                raise RuntimeError(response["error"])
            return response.get("result")
        finally:
            self.pending.discard(identifier)
