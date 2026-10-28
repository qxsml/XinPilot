"""Packaged desktop entry point and explicit bundled subprocess dispatch."""

import os, sys
from pathlib import Path


def pipe_stream(identifier, mode):
    import ctypes, msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    handle = kernel.GetStdHandle(identifier & 0xFFFFFFFF)
    if not handle or handle == ctypes.c_void_p(-1).value:
        return open(os.devnull, mode, encoding="utf-8")
    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY if "r" in mode else os.O_WRONLY)
    return os.fdopen(fd, mode, encoding="utf-8", buffering=1)


def main():
    import multiprocessing

    multiprocessing.freeze_support()
    child = len(sys.argv) > 1 and sys.argv[1] in (
        "--xinpilot-controller",
        "--rxnpilot-controller",
        "--syntrack-controller",
        "--oneclick-run-pyparse",
    )
    if child and os.name == "nt":
        sys.stdin = pipe_stream(-10, "r")
        sys.stdout = pipe_stream(-11, "w")
        sys.stderr = pipe_stream(-12, "w")
    else:
        folder = Path(sys.executable).resolve().parent / "desktop-workspace"
        folder.mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(folder / "desktop.log", "a", encoding="utf-8", buffering=1)
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode in ("--xinpilot-controller", "--rxnpilot-controller", "--syntrack-controller"):
            from desktop.live_engine import main as run

            return run()
        if mode == "--oneclick-run-pyparse":
            from integrated_full_software import _run_bundled_pyparse

            return _run_bundled_pyparse(sys.argv[2], sys.argv[3:])
        if mode in ("--xinpilot-run-tool", "--rxnpilot-run-tool", "--syntrack-run-tool"):
            from integrated_full_software import _run_bundled_tool

            return _run_bundled_tool(sys.argv[2], sys.argv[3:])
        if mode == "--desktop-check":
            from desktop.packaged_check import main as check

            return check(Path(sys.argv[2]))
    from desktop.live_app import main as run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
