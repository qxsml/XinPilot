# Version 1.2.4 validation

Validated locally on Windows on 30 October 2026.

- All 542 Python regression tests passed in an isolated source copy.
- The full suite used a shorter temporary root after the deeply nested build folder caused one long-filename fixture to exceed Windows path limits before application code ran. Initial sandbox access failures were resolved by rerunning with native filesystem access.
- Bundled application modules and selected resources match the distributed source, including both PyParse entry scripts, reaction scripts, renderer bundle, LICENSE, NOTICE and VERSION.
- Windows file/product version and executable filename are 1.2.4.
- Standard and modified PyParse startup passed using an isolated runtime PATH.
- Packaged WebView2 scientific inspection diagnostic passed using synthetic project data.
- Packaged AutoLynx export popup opened and closed with the expected controls.
- The source inventory verified successfully. Both PyParse source trees are unchanged.

Application logic is unchanged from the source that passed GitHub Python and renderer workflows at commit 1e11d55. This build updates version metadata and embedded licensing materials. Existing v1.2.3 functional acceptance evidence is documented separately; those full chemistry and robot GUI campaigns were not rerun for this maintenance build.

The executable is unsigned. No independent clean-PC or physical robot test was performed. Private build logs, test projects and caches are outside the upload source folder.
