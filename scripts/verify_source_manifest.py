"""Check or regenerate the distributed source inventory (not a release signature)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SOURCE_SHA256.json"
GENERATED = {
    ".git", ".venv", ".desktop-deps", ".desktop-tooling", ".ruff_cache",
    ".pytest_cache", "__pycache__", "node_modules", "artifacts", "outputs",
    "desktop-workspace", "build", ".build", "release",
}
LOCAL = {"xinpilot.local.bat", "rxnpilot.local.bat", "syntrack.local.bat",
         "fastsolv_local.json", "Compound_Stock_GUI_settings.json"}


def inventory():
    result = {}
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path == MANIFEST or set(rel.parts) & GENERATED:
            continue
        if path.name in LOCAL or path.name.startswith("BB Stock list"):
            continue
        content = path.read_bytes()
        result[rel.as_posix()] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Record the current approved source")
    args = parser.parse_args()
    actual = inventory()
    if args.write:
        MANIFEST.write_text(json.dumps({"version": (ROOT / "VERSION").read_text().strip(), "files": actual}, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded {len(actual)} files")
    else:
        expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
        changed = sorted(name for name in expected.keys() | actual.keys() if expected.get(name) != actual.get(name))
        if changed:
            raise SystemExit("Source inventory differs:\n" + "\n".join(changed))
        print(f"PASS: {len(actual)} source files match")
