# XinPilot v1.2.7

Modified PyParse product analysis can search for sodium and ammonium adducts.
Under Run options, select Sodium, Ammonium or both. Both default to off.
Use the same input platemap as before.

Product Details shows observed ion matches beside the selected product's UV254
area percentage. Assigning another integrated peak or restoring the automatic
assignment updates the displayed ions. Older projects without ion evidence
open with their original results. Ion labels indicate agreement within the
configured mass tolerance. UV254 area percentages retain their original meaning.

The original PyParse engine remains byte-identical to its upstream snapshot.
Its separate XinPilot launcher handles missing values in numeric platemap
columns and leaves empty pie charts blank.

For reaction names, use hyphens or underscores in place of spaces to avoid
the existing lookup issue in Product Details.

When a Waters report lacks a 254 nm chromatogram for an individual sample, Modified PyParse analyzes the usable wells. The LC-MS run status identifies skipped wells, and Product Details marks their UV254 value as unavailable. Analysis fails if every sample lacks the channel.
