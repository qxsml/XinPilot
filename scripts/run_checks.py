"""Run bounded desktop regression checks; native GUI checks are opt-in."""

import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--gui", action="store_true", help="Also open WebView2 test windows")
args = parser.parse_args()
names = [
    "test_protocol_transport.py",
    "test_combo_transport.py",
    "test_uv_peak_selection.py",
    "test_live_transfer_events.py",
    "test_live_project.py",
    "test_opentrons_blowout_controls.py",
]
if args.gui:
    names += [
        "test_clear_pushed_window.py",
        "test_new_gwl_dialog_window.py",
        "test_editable_dropdown_window.py",
        "test_live_window.py",
        "test_external_import_window.py",
        "test_display_audit.py",
        "test_live_scientific_window.py",
    ]
for name in names:
    print(f"Running {name}", flush=True)
    subprocess.run(
        [sys.executable, "-B", str(ROOT / "tests/desktop" / name)],
        cwd=ROOT,
        check=True,
        timeout=240,
    )
if args.gui:
    for case in ("clean", "no", "cancel", "save_cancel", "save"):
        print(f"Running shutdown case: {case}", flush=True)
        subprocess.run(
            [sys.executable, "-B", str(ROOT / "tests/desktop/test_shutdown.py"), case],
            cwd=ROOT,
            check=True,
            timeout=180,
        )
print("PASS: selected desktop regression checks")
