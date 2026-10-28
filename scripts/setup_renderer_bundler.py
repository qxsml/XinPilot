"""Install the pinned offline renderer bundler; no npm or global installation.

The native distribution is published by esbuild at the npm registry. Downloads
are checked against the registry's SHA-512 integrity before extraction.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.25.12"


def main() -> None:
    with urlopen(
        f"https://registry.npmjs.org/@esbuild/win32-x64/{VERSION}", timeout=90
    ) as response:
        metadata = json.load(response)
    with urlopen(metadata["dist"]["tarball"], timeout=90) as response:
        content = response.read()
    algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
    if (
        algorithm != "sha512"
        or base64.b64encode(hashlib.sha512(content).digest()).decode() != expected
    ):
        raise ValueError("The esbuild download failed its integrity check.")
    destination = ROOT / ".desktop-tooling" / "esbuild"
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
        # Extract explicit regular files only, never paths or links from the tarball.
        for name in ("esbuild.exe", "README.md", "package.json"):
            member = archive.getmember("package/" + name)
            if not member.isfile():
                raise ValueError(f"Unexpected archive entry: {name}")
            with archive.extractfile(member) as stream:
                (destination / name).write_bytes(stream.read())
    record = {
        "package": "@esbuild/win32-x64",
        "version": VERSION,
        "integrity": metadata["dist"]["integrity"],
        "executable_sha256": hashlib.sha256((destination / "esbuild.exe").read_bytes()).hexdigest(),
    }
    (destination / "installation.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Installed isolated esbuild {VERSION}.")


if __name__ == "__main__":
    main()
