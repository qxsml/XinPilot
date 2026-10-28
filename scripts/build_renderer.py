"""Type-check ES modules, then produce the offline single-file renderer bundle."""

from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    toolchain = ROOT / ".desktop-tooling"
    node = toolchain / "node.exe"
    compiler = toolchain / "typescript/lib/tsc.js"
    bundler = toolchain / "esbuild/esbuild.exe"
    missing = [
        str(path.relative_to(ROOT)) for path in (node, compiler, bundler) if not path.is_file()
    ]
    if missing:
        raise SystemExit(
            "Missing build tools: "
            + ", ".join(missing)
            + ". See docs/setup.md; compiled assets are already included for running the app."
        )
    subprocess.run([str(node), str(compiler), "-p", "desktop/live_ui"], cwd=ROOT, check=True)
    subprocess.run(
        [
            str(bundler),
            "desktop/live_ui/app.ts",
            "--bundle",
            "--format=iife",
            "--target=es2021",
            "--charset=utf8",
            "--legal-comments=inline",
            "--outfile=desktop/live_ui/dist/app.js",
        ],
        cwd=ROOT,
        check=True,
    )
    print("PASS: renderer type checking and offline bundle")


if __name__ == "__main__":
    main()
