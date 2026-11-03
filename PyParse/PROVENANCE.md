# Bundled original PyParse provenance

The original engine is copied byte-for-byte from `thatchemistryguy/PyParse`,
`v1_archive`, commit `9d08f0803e68e385ec4e5d7d5179fb89b104b5cb`
(`Add conda-environment yml`, 4 August 2026).

The unchanged upstream files are `PyParse.py`, `__init__.py`, `getWatersData.py`,
`getShimadzuData.py` and `templates/html_template.html`. Their SHA-256 hashes are
recorded in `UPSTREAM_SHA256.json` and checked by
`tests/test_original_pyparse_integrity.py`. Comparison includes original newline
bytes; it is not only a comparison of executable statements.

Source: https://github.com/thatchemistryguy/PyParse/tree/9d08f0803e68e385ec4e5d7d5179fb89b104b5cb

XinPilot's runner provides process launching and failure reporting outside the
engine. Upstream parsing, molecular-weight handling, plotting and exit behavior
remain unchanged. The bundled runtime can still expose upstream compatibility
errors, including the empty-pie error; XinPilot reports detected analysis failures.
The source template loader works without changes. A rebuilt executable still
requires its own packaging validation.

The local documentation and checksum manifest are XinPilot metadata, not upstream
engine files. Analytical modifications remain separately in `../Modified PyParse/`.
