# Contributing

Keep private experimental data and machine configuration out of changes. See
[architecture](docs/architecture.md) for the Python/controller boundaries and
[testing](docs/testing.md) for supported validation commands.

```bat
python scripts/validate_python.py
Run_Checks.bat
Run_Checks.bat --gui
```

Rebuild the renderer after TypeScript changes. Use tests/fixtures for synthetic
examples. Add meaningful regressions for behavior changes; chemistry templates
require chemical review. Robot changes also require instrument-specific review,
simulation and an appropriate physical check. Report the exact tested source and
known limitations. XinPilot's original code is licensed under Apache-2.0;
see LICENSE and NOTICE. Retain the applicable third-party licenses and notices.
# Additional liquid-handling formats

External Import uses the existing normalized transfer and Chemical ID model.
Keep new readers or format adapters in `xinpilot/application/`, with UI wiring
in `external_import_frame.py`. Include redistributable examples and tests for
units, source identities, destination geometry, missing fields and project
round trips. Document whether a format is a native vendor export or a converted
table. Do not infer physical positions or claim robot execution from an import
test alone. Existing robot exporters and chemistry engines should remain
independent of additional readers.
