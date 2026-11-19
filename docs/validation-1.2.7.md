# XinPilot v1.2.7 validation

The local Windows build passed 583 source regression tests. Controlled Waters
peak data exercised both adducts disabled, sodium only, ammonium only and both
enabled. Tests covered competing integrations, one observed ion matching two
mass windows, and persistence of options and evidence through project export.

With both adduct options disabled, the packaged application reproduced the previous
release's automatic results and peak-inspection data. Both analysis workflows
completed through the packaged analysis entry point.

The packaged WebView2 diagnostic displayed +H, +Na and +NH4 (subscript 4)
on a single line with the UV254 value at 850 x 600 and maximized. It checked
peak reassignment, disappearance of the indicators and restoration of the
automatic assignment. Synthetic evidence was used for this layout check.

The embedded modified engine matched the local source. The five original
engine files matched the pinned upstream hashes in source and in the EXE.
Validation used the development laptop. Independent clean-PC testing and
experimental confirmation of individual adduct identities remain outside
these checks.

A Waters report containing a sample without a UV254 chromatogram was compared
with a reference run on the same report with that sample omitted. All usable
wells had identical peak bundles and target assignments. An input containing
only the skipped sample failed analysis. Project export and reopening
preserved the unavailable UV254 result.
