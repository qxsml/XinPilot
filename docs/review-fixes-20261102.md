# Reviewer fixes and Compound Notes privacy

These local source changes prepare the next release after v1.2.4. They do not
update the existing executable, published tag or GitHub Release. The version
and packaging metadata will be updated when the next release is authorized.

## Four priority findings

- **F-06, Mitsunobu:** the alcohol-side carbon must be sp3 (`X4`). This prevents
  a carboxylic acid from also matching as the alcohol and producing an extra
  retained-stereochemistry ester. The acid/alcohol case is regression-tested in
  both enantiomeric directions. Other reaction-template scopes are unchanged.
- **F-29, Tecan:** pushing listed worklists checks saved commands against the
  editable blocks. Unsaved current edits require save confirmation; declining
  cancels the push. External file edits, missing previously saved files and
  inconsistent snapshots block the push without replacing summary records.
  Consistent portable-project worklists remain usable without saving separate
  local files. New worklists can be saved through the confirmation. A failed
  listed worklist no longer causes a partial summary update.
- **F-39, original PyParse:** the original engine is now byte-identical to the
  pinned upstream commit. XinPilot's runner detects nonzero exits, fatal console
  errors and legacy failure reports even when the engine exits zero. It reports
  failure and does not attach failed results. The upstream empty-pie bug remains;
  no local plotting, parsing or exit-status changes are retained in this engine.
  See [restoration record](../PyParse/MODIFICATIONS.md).
- **F-23, Opentrons:** one compatibility table covers all eleven known pipettes
  and is used by the interface and compiler to validate tip-rack capacities.

## Additional agreed changes

- Unsupported 96-channel pipettes are hidden from new selections and rejected
  by the compiler. Protocol export reminds users to simulate and check module,
  adapter and plate compatibility. A generated-code comment distinguishes nozzle
  reference wells from the complete physical destination list; it changes no
  executable protocol statements.
- AutoLynx writes injection volumes as plain decimals without six-significant-
  figure rounding, rejects reserved/overlong Windows sample names, and supports
  an optional user-specified instrument injection limit. The default processing
  program spelling is `OpenLynx`; loaded method names are preserved. See the
  [export guide](autolynx-export.md) for numeric bounds and installation limits.
- `CITATION.cff` identifies Xin Qiu as the software author. The existing copyright
  notice is retained; manuscript authorship is a separate matter.

## Compound Notes privacy

**From SMILES** parses the structure and calculates molecular weight locally
with RDKit. It does not query PubChem for properties or synonyms and does not
replace existing chemical names or CAS numbers. Selecting existing records
uses cached images or local rendering.

If rendering fails, a popup explains that fetching a preview sends the SMILES
to PubChem. Only **Fetch preview from PubChem** authorizes the image request.
**Cancel**, Escape or closing the popup declines. The button appears only in
the popup. Duplicate selection events cannot open nested consent windows.
An approved image is cached for that structure; approval does not authorize
requests for other structures. **From CAS** remains an explicit online lookup.

## Deliberately unchanged

No new Tecan empty/duplicate-well restrictions, aspiration limits, rounding
checks or concentration-unit rules are included. No product-generation logging,
broader reaction-scope changes or repository reorganization are included.
Modified PyParse is unchanged. The separately approved follow-up below adds
callback cleanup and source-checking improvements.

## Separately approved follow-up

- **F-14:** Heater-Shaker plate/adapter combinations are checked against the
  installed Opentrons definitions and stacking rules for the selected protocol
  API. This covers plates initially on the adapter and plates moved there later.
  Unsupported combinations are rejected before protocol generation. Legacy
  combined labware definitions retain their direct module-loading path.
- **F-20:** scheduled Tk work is cancelled when its owning widget is destroyed.
  The shared helper cancels only that widget's callbacks, preserving timers in
  other windows. Existing explicit cancellation remains supported.
- **F-18:** the README states Windows x64/WebView2 requirements and unsigned
  executable status, and links setup/testing instructions.
- **F-01 follow-up:** CI compiles all distributed Python sources in memory,
  including reaction templates, to detect syntax and encoding errors without
  executing them or creating bytecode caches.
- **F-17:** the older `source_manifest.py` command delegates to the canonical
  manifest writer so both commands use the same schema and exclusion rules.

These are local source changes; they do not constitute a rebuilt release.

## Validation and limits

Regression tests cover local-only SMILES processing and selection, failed-preview
cancellation, explicit approval with a mocked image response, popup close behavior,
Tecan save-before-push and external-edit rejection, PyParse upstream integrity/failure
handling, pipette capacities and AutoLynx formatting. The TypeScript/WebView test
`tests/desktop/test_compound_privacy_window.py` exercises the local action and
popup cancellation through the actual renderer.

Network tests use mocked responses and do not transmit experimental structures.
Software tests do not establish robot execution, Waters import compatibility or
an independent clean-PC installation. Callback checks cover application-owned
timers; they do not imply that every internal Tcl/Tk diagnostic is suppressed.

Validation completed on 2 November 2026 after upstream restoration: all 561 root regression tests passed
(0 failures, 0 errors). The six existing desktop-check scripts passed; their
optional private-RPT check was skipped because that dataset was not supplied.
The native TypeScript privacy-window test passed separately. All 186 distributed
Python files compiled in memory. Nine Opentrons protocol fixtures retained
identical executable ASTs; only the explanatory comment changed their hashes.
No physical robot, live PubChem lookup, Waters import or new executable was tested.

All five original PyParse engine files match the pinned upstream bytes. The original template loader was exercised without modification. A real failed upstream run and mocked zero-exit failures were correctly classified by XinPilot; 13 analytical lifecycle tests also passed after the final failure-message wording change. The existing executable has not been rebuilt or validated with this restoration.

After the separately approved follow-up, all 570 root tests passed (no failures,
errors or skips), and all 190 distributed Python files compiled. Targeted tests
cover module definitions at API 2.15, 2.24 and 2.27, initial and moved plates,
widget-owned callback cancellation and compatibility of both manifest commands.
The installed Opentrons simulator independently accepted the NEST deep-well/deep
adapter and Corning flat/universal adapter pairs and rejected the mismatched
NEST deep-well/flat-bottom adapter pair at API 2.24. This is software simulation,
not physical validation. The nine existing protocol contract fixtures are
unchanged from the prior approved fixes.

All thirteen desktop-check scripts and all five shutdown cases passed, with one
optional private-RPT check skipped. Shutdown controller logs were empty. The
external-import UI test now waits for the table to render before asserting its
row count; its initial immediate assertion raced the asynchronous renderer.
No external-import application logic was changed.

## Compound Notes CSV import

The existing Load Excel action also accepts comma-separated UTF-8 CSV files
(with or without a BOM). Both formats now use the same table-reading service
for header mapping, empty cells, legacy TEMP-row filtering and record creation.
Duplicate IDs retain the existing Excel import behavior. Invalid CSV parsing
leaves the previous records and Excel association intact. CSV imports detach
Excel writeback; Save Current requests an Excel destination and quantity edits
remain in the table until saved. The original CSV is preserved. No new tab or
renderer change is involved.
