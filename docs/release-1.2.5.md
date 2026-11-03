# XinPilot v1.2.5

Local Windows build incorporating the approved reviewer fixes and Compound Notes
CSV import. See [changes and validation](review-fixes-20261102.md) for scope.

- Original PyParse is restored to the pinned upstream engine, without local
  modifications. XinPilot reports failed analyses as failures; upstream analysis
  bugs are not patched. Modified PyParse is unchanged.
- Corrected Mitsunobu stereochemistry handling and Tecan saved-worklist/summary
  consistency; improved Opentrons tip and Heater-Shaker compatibility checks.
- Improved AutoLynx export validation and precision.
- SMILES processing and normal previews remain local. A failed preview requires
  explicit approval before sending the structure to PubChem. CAS lookup remains
  online.
- Load Excel also accepts UTF-8 CSV using the same column rules. Saving CSV
  imports uses an Excel destination and preserves the original CSV.
- Improved callback cleanup, source syntax checks, manifest tooling and setup
  documentation.

The executable requires Windows x64 and Microsoft Edge WebView2 Runtime. It is
unsigned. Software regression tests and simulation do not replace physical robot
or independent clean-PC validation. This local build does not publish a GitHub
release or create a tag.
