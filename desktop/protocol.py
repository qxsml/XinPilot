"""The JSON-line contract between the desktop host and controller process.

This module deliberately has no GUI or application imports. Requests expose a
fixed set of widget operations; renderer input is never executable Python/Tcl.
The existing wire format remains compatible with the TypeScript renderer.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

Method = Literal["snapshot", "event", "stop"]
METHODS = frozenset({"snapshot", "event", "stop"})
POINTER_SEQUENCES = frozenset(
    {
        "<Button-1>",
        "<ButtonRelease-1>",
        "<Button-3>",
        "<Double-Button-1>",
        "<Motion>",
        "<B1-Motion>",
        "<Enter>",
        "<Leave>",
        "<FocusIn>",
        "<FocusOut>",
        "<KeyRelease>",
        "<MouseWheel>",
        "<Return>",
        "<Delete>",
        "<Escape>",
        "<Control-c>",
        "<Control-v>",
    }
)
EVENT_ACTIONS = frozenset(
    {
        "answer",
        "resize",
        "dismiss_menu",
        "close",
        "window_size",
        "column_size",
        "invoke",
        "value",
        "tab",
        "selection",
        "expand",
        "heading",
        "post",
        "sash",
        "menu",
        "scroll",
        "pointer",
    }
)
FILE_DIALOG_KINDS = frozenset(
    {
        "askopenfilename",
        "askopenfilenames",
        "asksaveasfilename",
        "askdirectory",
    }
)


class ProtocolError(ValueError):
    """An invalid envelope or operation received at the process boundary."""


class Response(TypedDict, total=False):
    id: int
    result: Any
    error: str


def _identifier(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("Request id must be an integer.")
    return value


def _text(data: dict[str, Any], key: str) -> None:
    if not isinstance(data.get(key), str) or not data[key]:
        raise ProtocolError(f"Event {key} must be a nonempty string.")


def _number(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"Event {key} must be a finite number.")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ProtocolError(f"Event {key} must be a finite number.")


def validate_event(value: Any) -> dict[str, Any]:
    """Validate operation shape before dispatch, preserving optional fields.

    Widget existence and widget-specific state remain the Tk adapter's concern:
    queued focus/hover messages may legitimately refer to a dismissed window.
    """
    if not isinstance(value, dict):
        raise ProtocolError("Invalid event: expected an object.")
    data = value.copy()
    action = data.get("action")
    if not isinstance(action, str) or action not in EVENT_ACTIONS:
        raise ProtocolError("Unsupported event action.")
    if action not in {"resize", "dismiss_menu"}:
        _text(data, "id")
    if action in {"resize", "window_size"}:
        _number(data, "width")
        _number(data, "height")
    if action in {"column_size", "heading"}:
        _text(data, "column")
    if action == "column_size":
        _number(data, "width")
    if action == "tab":
        _text(data, "tab")
    if action == "selection":
        items = data.get("items", [])
        if not isinstance(items, list) or any(
            isinstance(item, bool) or not isinstance(item, (str, int)) for item in items
        ):
            raise ProtocolError("Selection items must be widget ids or indices.")
    if action == "expand":
        _text(data, "item")
        if not isinstance(data.get("open"), bool):
            raise ProtocolError("Expansion state must be a boolean.")
    if action == "sash":
        _number(data, "index")
        _number(data, "position")
    if action == "scroll":
        _number(data, "position")
        if data.get("axis", "y") not in ("x", "y"):
            raise ProtocolError("Scroll axis must be x or y.")
    if action == "pointer":
        sequence = data.get("sequence")
        if not isinstance(sequence, str) or sequence not in POINTER_SEQUENCES:
            raise ProtocolError("Unsupported pointer event.")
    for key in ("x", "y", "rootx", "rooty", "state", "delta", "rx", "ry"):
        if key in data:
            _number(data, key)
    return data


@dataclass(frozen=True)
class Request:
    id: int
    method: Method
    data: dict[str, Any] | None = None

    @classmethod
    def parse(cls, value: Any) -> "Request":
        if not isinstance(value, dict):
            raise ProtocolError("Request must be an object.")
        identifier = _identifier(value.get("id"))
        method = value.get("method")
        if not isinstance(method, str) or method not in METHODS:
            raise ProtocolError("Unknown request method.")
        data = validate_event(value.get("data")) if method == "event" else None
        return cls(identifier, method, data)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "method": self.method, "data": self.data}


def decode_response(line: str) -> Response:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ProtocolError("Response must be an object.")
    _identifier(value.get("id"))
    if ("result" in value) == ("error" in value):
        raise ProtocolError("Response must contain exactly one result or error.")
    if "error" in value and not isinstance(value["error"], str):
        raise ProtocolError("Response error must be text.")
    return value


def encode_message(value: dict[str, Any]) -> str:
    return json.dumps(value, default=str, separators=(",", ":"), allow_nan=False) + "\n"
