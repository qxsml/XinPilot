"""Failure and concurrency contracts for the desktop process boundary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
import queue
import threading
from types import SimpleNamespace
import unittest

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from desktop.controller_server import ControllerServer
from desktop.protocol import ProtocolError, Request, decode_response, validate_event
from desktop.transport import ControllerTransport


class PipeInput:
    def __init__(self):
        self.lines = queue.Queue()

    def __iter__(self):
        while (line := self.lines.get()) is not None:
            yield line


class PipeOutput:
    def __init__(self):
        self.requests = queue.Queue()

    def write(self, line):
        self.requests.put(json.loads(line))

    def flush(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_invalid_messages_are_rejected_before_dispatch(self):
        for request in (
            [],
            {"id": True, "method": "snapshot"},
            {"id": 1, "method": "execute"},
            {"id": 1, "method": "event", "data": {"action": "eval", "id": "."}},
        ):
            with self.subTest(request=request), self.assertRaises(ProtocolError):
                Request.parse(request)
        for event in (
            {"action": "resize", "width": float("nan"), "height": 400},
            {"action": "pointer", "id": ".", "sequence": "arbitrary Tcl"},
            {"action": "selection", "id": ".tree", "items": [True]},
        ):
            with self.subTest(event=event), self.assertRaises(ProtocolError):
                validate_event(event)

    def test_existing_dialog_and_widget_payloads_are_preserved(self):
        for event in (
            {"action": "answer", "id": "dialog-token", "value": None},
            {"action": "selection", "id": ".tree", "items": ["row1", 2]},
            {
                "action": "pointer",
                "id": ".canvas",
                "sequence": "<B1-Motion>",
                "x": 12,
                "y": 14,
                "rootx": 99,
                "rooty": 100,
                "state": 256,
            },
            {"action": "value", "id": ".combo", "value": "same choice", "selection": True},
        ):
            self.assertEqual(event, Request.parse({"id": 4, "method": "event", "data": event}).data)
        self.assertEqual({"id": 1, "result": None}, decode_response('{"id":1,"result":null}'))
        with self.assertRaises(ProtocolError):
            decode_response('{"id":1,"result":null,"error":"ambiguous"}')


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.input = PipeInput()
        self.output = PipeOutput()
        self.expected_close = False
        self.closed_callback = threading.Event()
        self.transport = ControllerTransport(
            self.input,
            self.output,
            expected_close=lambda: self.expected_close,
            on_close=self.closed_callback.set,
        )
        self.transport.start()

    def tearDown(self):
        self.input.lines.put(None)
        self.transport.reader.join(timeout=2)
        self.assertFalse(self.transport.reader.is_alive())

    def test_concurrent_replies_are_correlated_even_in_reverse_order(self):
        with ThreadPoolExecutor(max_workers=8) as workers:
            futures = [
                workers.submit(
                    self.transport.call,
                    "event",
                    {"action": "value", "id": ".entry", "value": index},
                    2,
                )
                for index in range(8)
            ]
            requests = [self.output.requests.get(timeout=2) for _ in futures]
            for request in reversed(requests):
                self.input.lines.put(
                    json.dumps({"id": request["id"], "result": request["data"]["value"]})
                )
            self.assertEqual(list(range(8)), [future.result(timeout=2) for future in futures])

    def test_noise_and_duplicate_replies_do_not_cross_requests(self):
        with ThreadPoolExecutor(max_workers=1) as worker:
            reply = worker.submit(self.transport.call, "snapshot", timeout=2)
            request = self.output.requests.get(timeout=2)
            for line in (
                "library diagnostic",
                "[]",
                '{"id":true,"result":1}',
                json.dumps({"id": request["id"], "result": "first"}),
                json.dumps({"id": request["id"], "result": "duplicate"}),
            ):
                self.input.lines.put(line)
            self.assertEqual("first", reply.result(timeout=2))

    def test_timeout_does_not_leave_a_pending_request(self):
        with self.assertRaises(TimeoutError):
            self.transport.call("snapshot", timeout=0.01)
        self.assertEqual({}, self.transport.pending._pending)

    def test_eof_releases_waiters_as_an_error_for_unexpected_exit(self):
        with ThreadPoolExecutor(max_workers=1) as worker:
            reply = worker.submit(self.transport.call, "snapshot", timeout=2)
            self.output.requests.get(timeout=2)
            self.input.lines.put(None)
            with self.assertRaisesRegex(RuntimeError, "unexpectedly"):
                reply.result(timeout=2)
        self.assertTrue(self.closed_callback.wait(1))

    def test_eof_during_normal_close_returns_closed_state(self):
        self.expected_close = True
        with ThreadPoolExecutor(max_workers=1) as worker:
            reply = worker.submit(self.transport.call, "snapshot", timeout=2)
            self.output.requests.get(timeout=2)
            self.input.lines.put(None)
            self.assertEqual({"closed": True}, reply.result(timeout=2))
        self.assertEqual({"closed": True}, self.transport.call("snapshot"))

    def test_invalid_request_never_reaches_pipe_or_registry(self):
        with self.assertRaises(ProtocolError):
            self.transport.call("run_python")
        self.assertTrue(self.output.requests.empty())
        self.assertEqual({}, self.transport.pending._pending)


class ControllerServerTests(unittest.TestCase):
    def test_host_eof_stops_hidden_controller(self):
        controller = SimpleNamespace(stopped=False, app=SimpleNamespace(after=lambda *args: None))
        controller.stop = lambda: setattr(controller, "stopped", True)
        output = io.StringIO()
        server = ControllerServer(controller, io.StringIO(""), output)
        server.read_requests()
        server.pump()
        self.assertTrue(controller.stopped)
        self.assertEqual("", output.getvalue())


if __name__ == "__main__":
    unittest.main()
