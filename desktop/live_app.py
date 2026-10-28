"""Local desktop host for the feature-preserving TypeScript renderer."""

from __future__ import annotations
from desktop.protocol import Request
from desktop.transport import ControllerTransport
import json, os, subprocess, sys, threading, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".desktop-deps"))
if os.name == "nt":
    os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")


class LiveBridge:
    """Native WebView host; pipe correlation belongs to ControllerTransport."""

    def __init__(self):
        self._window = None
        self._dialog = None
        self._lock = threading.Lock()
        self._shutdown_lock = threading.Lock()
        self._closing = False
        self._destroy_requested = False
        self._allow_native_close = False
        self._shutting_down = False
        self._title = "XinPilot"
        self._file_dialog_lock = threading.Lock()
        self._file_dialog_tokens = set()
        frozen = getattr(sys, "frozen", False)
        app_dir = Path(sys.executable).resolve().parent if frozen else ROOT
        logdir = app_dir / "desktop-workspace"
        logdir.mkdir(exist_ok=True)
        self._log = (logdir / ("live-" + uuid.uuid4().hex + ".log")).open("w", encoding="utf-8")
        command = (
            [sys.executable, "--xinpilot-controller"]
            if frozen
            else [sys.executable, "-B", "-m", "desktop.live_engine"]
        )
        try:
            self._process = subprocess.Popen(
                command,
                cwd=app_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                text=True,
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                bufsize=1,
            )
        except Exception:
            self._log.close()
            raise
        self._transport = ControllerTransport(
            self._process.stdout,
            self._process.stdin,
            expected_close=lambda: self._closing or self._shutting_down,
            on_close=self._on_controller_closed,
        )
        self._controller_closed = self._transport.closed
        self._reader = self._transport.reader
        self._transport.start()

    def _call(self, method, data=None, timeout=1800):
        return self._transport.call(method, data, timeout)

    def snapshot(self):
        result = self._call("snapshot")
        self._dialog = result.get("dialog")
        windows = result.get("windows", [])
        if windows and self._window:
            title = windows[0].get("title") or "XinPilot"
            if title != self._title:
                self._window.set_title(title)
                self._title = title
        return result

    def event(self, data):
        if not isinstance(data, dict):
            raise ValueError("Invalid event.")
        return self._call("event", data)

    def file_dialog(self, token):
        with self._file_dialog_lock:
            if token in self._file_dialog_tokens:
                return
            if not self._dialog or self._dialog.get("id") != token:
                return
            self._file_dialog_tokens.add(token)
        return self._show_file_dialog(token)

    def _show_file_dialog(self, token):
        import webview

        data = self._dialog
        if not data or data.get("id") != token:
            return
        kind = data["kind"]
        kwargs = {}
        if kind not in ("askopenfilename", "askopenfilenames", "asksaveasfilename", "askdirectory"):
            return
        if data.get("initialdir") and Path(data["initialdir"]).is_dir():
            kwargs["directory"] = data["initialdir"]
        if data.get("initialfile"):
            kwargs["save_filename"] = data["initialfile"]
        filters = []
        for label, patterns in data.get("filetypes", []):
            if isinstance(patterns, (tuple, list)):
                patterns = ";".join(patterns)
            patterns = str(patterns).replace(" ", ";")
            if patterns == "*":
                patterns = "*.*"
            filters.append(f"{label} ({patterns})")
        if filters:
            kwargs["file_types"] = tuple(filters)
        mode = (
            webview.FileDialog.SAVE
            if kind == "asksaveasfilename"
            else webview.FileDialog.FOLDER
            if kind == "askdirectory"
            else webview.FileDialog.OPEN
        )
        if kind == "askopenfilenames":
            kwargs["allow_multiple"] = True
        try:
            value = self._window.create_file_dialog(mode, **kwargs)
            if kind == "askopenfilenames":
                value = list(value or [])
            elif isinstance(value, (tuple, list)):
                value = value[0] if value else ""
            if kind == "asksaveasfilename" and value and (not Path(value).is_absolute()):
                raise ValueError(
                    "No full save location was selected. Please choose a folder and filename again."
                )
            if (
                kind == "asksaveasfilename"
                and value
                and (not Path(value).suffix)
                and data.get("defaultextension")
            ):
                value += data["defaultextension"]
        except Exception:
            self.event({"action": "answer", "id": token, "value": None})
            raise
        return self.event({"action": "answer", "id": token, "value": value})

    def _request_close(self):
        if self._controller_closed.is_set() or self._process.poll() is not None:
            return not self._destroy_requested or self._allow_native_close
        with self._lock:
            if self._closing:
                return False
            self._closing = True

        def close():
            try:
                result = self.event({"action": "close", "id": "."})
                if not (result or {}).get("closed"):
                    with self._lock:
                        self._closing = False
            except Exception as exc:
                if not self._controller_closed.is_set():
                    with self._lock:
                        self._closing = False
                    if not self._log.closed:
                        print(f"Close request failed: {exc}", file=self._log, flush=True)

        threading.Thread(target=close, name="xinpilot-close-request", daemon=True).start()
        return False

    def _shutdown(self):
        with self._shutdown_lock:
            if self._log.closed:
                return
            self._shutting_down = True
            try:
                if self._process.poll() is None:
                    try:
                        self._transport.write(Request(-1, "stop"))
                        self._process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        self._process.terminate()
                        try:
                            self._process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self._process.kill()
                            self._process.wait(timeout=5)
                self._reader.join(timeout=5)
            finally:
                for stream in (self._process.stdin, self._process.stdout):
                    if stream:
                        stream.close()
                self._log.close()

    def _on_controller_closed(self):
        with self._lock:
            destroy = self._closing and (not self._shutting_down) and (not self._destroy_requested)
            if destroy:
                self._destroy_requested = True
        if not destroy or self._window is None:
            return
        deadline = time.monotonic() + 3
        while not self._shutting_down and time.monotonic() < deadline:
            try:
                if self._window.evaluate_js("finished && !polling && inFlight === 0"):
                    break
            except Exception:
                break
            time.sleep(0.03)
        if not self._shutting_down:
            self._allow_native_close = True
            self._window.destroy()


def html():
    ui = ROOT / "desktop/live_ui"
    return (
        (ui / "index.html")
        .read_text(encoding="utf-8")
        .replace("/* CSS */", (ui / "style.css").read_text(encoding="utf-8"))
        .replace("/* JS */", (ui / "dist/app.js").read_text(encoding="utf-8"))
    )


def main():
    import webview

    bridge = LiveBridge()
    window = webview.create_window(
        "XinPilot",
        html=html(),
        js_api=bridge,
        width=1280,
        height=850,
        min_size=(850, 600),
        background_color="#edf2f6",
    )
    bridge._window = window
    window.events.closing += bridge._request_close
    try:
        webview.start(gui="edgechromium" if os.name == "nt" else None)
    finally:
        bridge._shutdown()


if __name__ == "__main__":
    main()
