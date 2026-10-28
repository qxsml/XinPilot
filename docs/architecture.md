# Architecture and maintenance boundaries

Read the [current engineering overview](ENGINEERING_OVERVIEW.md) for the diagram,
code map, state ownership and developer checks.

The TypeScript renderer communicates with a Python WebView host over pywebview.
The host exchanges validated JSON lines with a separate controller process over
local pipes. Event dispatch, prompts and widget projection are explicit Tk
adapters. Project and robot services in `xinpilot/application` have no dependency
on the interface, controller modules or scientific UI libraries.

Root Python controllers remain compatibility entry points for the established
page interactions and resource paths. They delegate extracted operations to the
application services. Chemistry engines, both PyParse engines and native toolkit
interfaces retain their established numerical and file-processing behavior.

Renderer source is split into ES modules in `desktop/live_ui/src`. TypeScript
checks the types; esbuild bundles the entry point into `dist/app.js` for offline
runtime use. Existing diagnostic globals are exposed in one compatibility file.
Node and development tools are not required to launch the checked-in interface.

Tk still owns layout and some interactive state. This is a modularized hybrid
application, not a complete Tk-free backend or a newly exposed public API.
