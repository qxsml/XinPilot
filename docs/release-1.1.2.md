# XinPilot v1.1.2

Bug-fix release, 12 October 2026. Matching Windows executable:
`XinPilot-v1.1.2-Windows-x64.exe`.

This release addresses the nine cases reproduced in the broader v1.1.1 review:

- Track building-block structural identity, including edits that retain the same
  Chemical ID, and invalidate affected automatic products and analytical links.
- Compare replacement Product Details with existing structures before retaining
  analytical results; preserve unaffected results and general notes.
- Resolve conflicts between imported LC-MS wells and prior explicit mappings.
- Ask whether to export, discard or cancel before replacing an unsaved project.
- Respect selected tip capacity when validating Opentrons operations and batches.
- Balance Tecan aspiration against the actual rounded dispense commands.
- Track physical source wells for ordinary all-channel Opentrons transfers.
- Correct the terminal-alkyne homocoupling impurity transformation.
- Match Excel quantity updates by Chemical ID and reject inconsistent identities.

Original and Modified PyParse engines are unchanged. Existing project extensions
and the version-one project schema remain supported. See the accompanying
validation report for the completed checks and their limits.
