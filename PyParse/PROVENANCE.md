# Bundled PyParse provenance

The bundled PyParse baseline traces to `thatchemistryguy/PyParse`, branch
`v1_archive`, commit `9d08f0803e68e385ec4e5d7d5179fb89b104b5cb`
(`Add conda-environment yml`, 2026-08-04).

After newline normalization, local `__init__.py`, `getShimadzuData.py`,
`getWatersData.py`, and `templates/html_template.html` match that commit. The
local `PyParse.py` differs by two XinPilot integration changes: PyInstaller-aware
template lookup through Jinja2 `FileSystemLoader`, and defensive
string-preserving CSV import. These changes support embedding without altering
the intended analytical workflow.

The original bundled file is protected by the XinPilot regression test
`tests/test_original_pyparse_integrity.py` and must not be edited casually.
Additional XinPilot analytical changes are isolated in `../Modified PyParse/`
and documented in `../Modified PyParse/MODIFICATIONS.md`.
