# Build the Windows executable

Use 64-bit Python 3.12 with Tk, the repository runtime dependencies and
`requirements-dev.txt`. Microsoft Edge WebView2 Runtime is required to run it.

```bat
python -m pip install -r requirements-dev.txt
```

When TypeScript source changes, rebuild the renderer first using
[the setup instructions](../docs/setup.md). The unchanged source snapshot already
includes its matching compiled JavaScript; Node is not needed to package that
bundle. `Build_Executable.bat` packages the bundle that is present, so it must
be kept in sync with renderer changes.

Run `Build_Executable.bat`. `TypeScript.spec` uses `desktop/frozen_entry.py` and
writes `release/XinPilot-v1.2.4-Windows-x64.exe`. It includes both PyParse routes,
toolkit/simulator resources, runtime dependencies and third-party notices. It
does not include private stock/settings files or FASTSOLV/model weights.

After building, run the packaged native diagnostic:

```bat
release\XinPilot-v1.2.4-Windows-x64.exe --desktop-check artifacts\packaged-check.json
```

This opens a real WebView2 window with a synthetic project and checks traces,
manual peak assignment and layout. Also test on a clean Windows computer.
Logs and local preferences are written beside the executable. Keep the EXE
out of Git; distribute it as a GitHub Release asset with its SHA-256 checksum.
Freeze source/version metadata before producing a publication release, and
archive that exact release under a persistent identifier.

The matching executable is built from this unified reaction-plate source snapshot.
See `release/BUILD_INFO.json`, `release/SHA256SUMS.txt` and
[validation results](../docs/validation-unified-plate.md) for its provenance and checks.
The local `release/` folder is ignored by Git: upload its contents as GitHub
Release assets, not as source files. Independent clean-PC testing remains
outstanding.
