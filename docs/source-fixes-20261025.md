# Chemistry and Opentrons source corrections

These source changes follow review of v1.2.2. They are included in the v1.2.3 source and matching executable.

## Reaction templates

- Heck coupling now limits this template to terminal, monosubstituted alkenes. The internal and 1,1-disubstituted alkene cases are rejected rather than losing a substituent. Use a suitable custom template for other alkene scopes.
- CuAAC requires a terminal alkyne. Internal alkynes no longer generate a product with a missing substituent.
- Mitsunobu encodes inversion at the alcohol-bearing carbon. Unspecified starting stereochemistry remains unspecified.
- Oxime formation and generic reductive amination accept aldehydes as well as ketones.
- The carbonyl-reduction, oxime and generic reductive-amination patterns exclude acyl derivatives such as esters, acids and amides. They are not general reductions or conversions of every C=O group.

Reaction IDs and saved project keys are unchanged. Templates construct expected products; they do not establish experimental feasibility or yield. Existing projects are not rewritten automatically. Regenerate and review affected products explicitly; existing product-regeneration safeguards apply to associated analytical results.

## Opentrons

Changing one pipette no longer resets the other mount's tip-rack selection. Reselecting a pipette preserves a compatible rack; changing to an incompatible pipette selects its default compatible rack.

Flex eight-channel single-tip export checks the adjacent slot into which the unused nozzles overhang. H1 checks towards deck row A; A1 checks towards row D. Source, destination, liquid waste and tip-rack access are included, with plate locations captured before each row's optional move. Only racks of mounts used by the generated protocol enter this clearance check.

This is deliberately conservative: the overhang slot must be empty, even where a specific well height might permit movement. The check is not a complete three-dimensional collision simulator. The error names the transfer row and conflicting slots. Rearrange the deck, use a one-channel pipette, or use a compatible full eight-channel transfer, and simulate the revised protocol. Full eight-channel and one-channel transfers are unaffected by this additional restriction.

Reference: [Opentrons partial tip pickup](https://docs.opentrons.com/python-api/pipettes/partial-tip-pickup/).

## Architecture and validation

Chemistry changes stay in the existing SMARTS definitions. UI callbacks handle rack selection; the existing headless Opentrons validation/compiler services handle clearance. No new runtime dependency or project schema was introduced. Both PyParse engines are unchanged.

Regression coverage includes independently specified products for all 43 menu reactions, stereochemical inversion, unsupported-substrate rejection, aldehyde transformations, rack preservation and clearance in both nozzle directions. The full 542-test suite passed; corrected H1/A1 Flex protocols and an OT-2 rack-preservation protocol passed the official simulator. GUI validation evidence is maintained separately from this upload folder.

All 43 simple product examples and six corrected boundary cases passed through automated GUI import, Manual push, reaction selection, generation and export. All 49 exported projects reopened with the expected displayed products. The exact GUI-exported OT-2 and Flex protocols passed simulation (14 and 34 commands respectively). Packaged validation is recorded separately in validation-1.2.3.md. No physical robot validation was performed.
