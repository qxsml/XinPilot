# Publish this source snapshot

Use this folder's **contents as the repository root**. GitHub Desktop or Git
preserves all subfolders and dotfiles, including `.github` and `.gitignore`.
Browser upload can be inconvenient for a multi-file source tree; do not flatten
the directories or omit the compiled UI/Ketcher assets.

The repository source excludes experimental ZIP/RPT files, workbooks, manuscripts,
private settings, model weights, environments and build logs. The local release
folder contains the matching executable and metadata; .gitignore excludes it
from commits. Attach those files separately to a GitHub Release.
Synthetic fixtures and necessary offline browser resources are included.
If you run the app here, do not manually upload the generated `.venv`,
`outputs`, `artifacts` or `desktop-workspace` directories afterward.

## Items the owner still needs to supply

XinPilot's original code is licensed under Apache-2.0, copyright 2026 Xin Qiu.
The root LICENSE and NOTICE record this decision. Retain all third-party terms.

1. **License materials with binary distribution.** Include LICENSE, NOTICE and
   applicable third-party notices with the executable distribution. The existing
   v1.2.3 EXE predates the root license decision and was not rebuilt for this
   documentation update; supply these notices alongside it.
2. **Approved authors and citation details.** Add CITATION.cff with the real
   author list, release date/version and repository URL; add the archive DOI
   when assigned. No author list or DOI is guessed in this snapshot.
3. **Repository and archived release.** Create the repository, freeze/tag the
   chosen publication version and deposit the matching release in a persistent
   archive such as Zenodo. Update the manuscript with the final identifiers.
4. **Matching public binary, if distributing one.** Build from this frozen
   source and attach the EXE/checksum to GitHub Releases, rather than committing
   it. Test installation/startup on another clean Windows computer.
5. **Experimental examples/SI, if desired.** Supply only the datasets authorized
   for publication. Private validation inputs were deliberately not included.

This release is version 1.2.3, combining horizontal and vertical Tecan additions
on one reaction plate, AutoLynx CSV export and the documented chemistry/robot fixes.
Use the matching v1.2.3 tag and executable for publication. Keep VERSION,
release documentation and Windows version metadata consistent in future releases.

`SOURCE_SHA256.json` identifies distributed source files (excluding itself and
the separate release directory). Verify it
with `python -B scripts/verify_source_manifest.py`; regenerate it after approved
edits using `--write`. Keep `.gitattributes`: it prevents line-ending conversion
from changing the protected PyParse source or invalidating the file inventory.
Preparing this folder does not upload it,
mint a DOI or create a release. See [validation](validation-summary.md).
