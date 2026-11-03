"""Compatibility entry point: use the canonical source-manifest writer."""
from pathlib import Path
import runpy
import sys


def main():
    verifier = Path(__file__).with_name("verify_source_manifest.py")
    sys.argv = [str(verifier), "--write"]
    runpy.run_path(str(verifier), run_name="__main__")


if __name__ == "__main__":
    main()
