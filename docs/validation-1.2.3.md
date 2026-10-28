# Version 1.2.3 validation

Validated on Windows on 25 October 2026. Application code is identical to the corrected source that passed all 542 regression tests. Packaging changed version metadata, release documentation and the executable-check default path only.

## Source workflow checks

All 43 menu-reaction examples and six boundary cases passed GUI import, Manual push, reaction selection, generation and export; all 49 exports reopened with matching products. OT-2 rack preservation and Flex blocked/clear deck cases passed GUI checks. Corrected H1/A1 Flex and OT-2 protocols passed the official Opentrons simulator. These checks used isolated synthetic projects, not live hardware.

## Packaged v1.2.3 checks

- Bundled application code and chemistry resource files match the distributed source; Windows file/product version is 1.2.3.
- Standard and modified PyParse startup and the packaged scientific inspector pass with an isolated runtime PATH.
- AutoLynx export popup opens with expected controls and closes normally.
- Six corrected chemistry boundary cases were regenerated through the TypeScript GUI connected to the packaged controller, exported and reopened. Displayed products match the corrected source results.
- Packaged GUI preserves the selected OT-2 rack and rejects the occupied Flex overhang slot. Rearranging the deck permits export. The GUI-exported OT-2 and Flex protocols pass simulation (14 and 34 commands).
- Source SHA256 inventory and clean upload-folder inventory pass. Both PyParse source trees are unchanged.

Private test projects, logs and build caches are outside the distribution. No independent clean-PC, physical robot or Waters acquisition test was performed. The executable is unsigned. Template results are expected structures, not proof of experimental outcome; Flex clearance is a conservative adjacent-slot check, not a complete collision model.
