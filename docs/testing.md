# Testing

Install the runtime/development dependencies on Windows with Tk and WebView2.
Run the root regression suite and desktop checks separately:

```bat
python -B scripts/validate_python.py
python -B scripts/run_checks.py
python -B scripts/run_checks.py --gui
```

The root suite includes project archives, custom reactions, chemistry-target
identity, explicit pushed records, robot compiler contracts and source toolkit
launching. Desktop checks cover bridge transport, dropdowns, maps, protocol
controls, project import, scientific display and all five unchanged/edited
close/save cases. External-import tests cover source-stock mapping, table
validation, mixed-source summaries, product generation and portable archives.
Native checks need an interactive Windows desktop and open test windows.

Reports go to `artifacts/`; host logs go to `desktop-workspace/`. These generated
folders are ignored and must not be included in a manual upload. CI runs the
root suite on Windows and separately checks the renderer build.

`tests/fixtures/peak-inspection-portable.zip` is synthetic, with two wells and
triangular traces. Robot compiler fixtures cover Flex/OT-2, mixing, delays,
modules, air gaps, excess liquid, retained tips and eight-channel mappings.
These are software fixtures, not experimental chemistry evidence.

An optional dataset-specific UV check uses `XINPILOT_PRIVATE_RPT`; it skips when
unset. Private reports are not distributed. Do not point this variable at an
arbitrary RPT and expect the dataset-specific assertions to apply.

Additional checks:

```bat
python -B scripts/verify_source_manifest.py
python -B scripts/build_renderer.py
python -m ruff check xinpilot desktop scripts/build_renderer.py scripts/setup_renderer_bundler.py
```

Rebuilding the renderer requires the isolated toolchain or the npm alternative
in [setup](setup.md). See [validation summary](validation-summary.md) for actual
results and limitations. Tests and simulation do not replace physical robot or
independent clean-computer validation.
