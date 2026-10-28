# XinPilot

Includes AutoLynx CSV export in Cheminformatics > LCMS Input. See [export guide](docs/autolynx-export.md).

**Version 1.2.3, 25 October 2026:** the source and matching Windows executable include the chemistry and Opentrons corrections. See [release notes](docs/release-1.2.3.md) and [correction details](docs/source-fixes-20261025.md).

XinPilot is a Windows desktop notebook for connected, plate-based synthetic
chemistry. It links compound stocks, Tecan/Opentrons/manual plans, expected
products, LC-MS review and subsequent synthesis steps in portable projects.

**Unified reaction-plate edition with AutoLynx export.** This edition
uses the modular desktop architecture and TypeScript interface, including
external transfer import and project change tracking.

See [release history](docs/release-1.2.0.md).

This release includes the [13 October controller corrections](docs/source-fixes-20261013.md) and combines horizontal and vertical Tecan additions on one horizontal reaction map.

**Version 1.2.1, 14 October 2026:** standalone GWL import now requires
explicit plate size/orientation, and GWL filenames must be unique within a project.
These two fixes remain included in subsequent releases.

## Start on Windows

1. Install 64-bit Python 3.12 with Tk and the Python launcher, and Microsoft
   Edge WebView2 Runtime.
2. Clone or download this repository into a writable folder.
3. Run **Setup_TypeScript.bat** to install the pinned Python dependencies.
4. Run **Launch_XinPilot.bat**.

Setup needs internet access. Node is not required to run the checked-in
interface. See [setup](docs/setup.md) and [building an executable](packaging/README.md).
Executables are separate GitHub Release assets, not repository files.

## Connected workflows

- **Compound Notes:** Chemical IDs, structures, stocks, quantities and references.
- **Synthesis Plan:** Tecan GWLs and chemical maps, Opentrons Python protocols,
  manual additions, and compatible external transfer tables. Explicitly pushed records combine in Reaction Summary;
  building-block flags select structural inputs for product generation.
- **Cheminformatics:** predefined or custom reaction transformations, editable
  expected products, and separate reviewed LC-MS target representations.
- **LCMS Analysis:** bundled PyParse and modified product/impurity routes.
- **Reaction and Product Summaries:** linked conditions, structures, analytical
  values, traces and notes. Supported numerical data enable peak inspection and
  reversible manual assignment.
- **Next Step:** carry reviewed products into new stock records after assessing
  their available amount, concentration and volume.
- **External Import:** map CSV/TSV/text, Excel or supported JSON transfer tables
  to Chemical IDs; optionally import source-stock details from an Excel template.
  See [formats, mapping and limitations](docs/EXTERNAL_IMPORT_TRIAL.md).
- **Change tracking:** meaningful unsaved project changes are indicated in the
  title. See [what is tracked](docs/CHANGE_TRACKING_TRIAL.md).

The Toolkit includes stock-solution and molecular-property/structural-alert
calculators and an Opentrons simulator. Toolkit utilities retain their native
interfaces. [FASTSOLV](docs/fastsolv.md) is optional and installed separately.
UV area fractions and property predictions are not experimental yields.

## Architecture

| Location | Responsibility |
| --- | --- |
| `desktop/live_ui/src/` | TypeScript controls, dialogs, tables and trace display |
| `desktop/` | WebView host, process transport and explicit Tk adapters |
| `xinpilot/application/` | GUI-independent project and robot services |
| Root Python modules | Established page controllers and scientific integration |
| `PyParse/`, `Modified PyParse/` | Separate analytical implementations |
| `Cheminformatic_Super_Advance/` | Reaction transformations and registry |
| `ketcher_bridge/dist/` | Bundled structure/reaction editor |
| `toolkit/` | Standalone utilities and simulator source |
| `tests/`, `scripts/`, `packaging/` | Regression coverage and development tools |

This is a local hybrid desktop application, not a hosted website. Hidden Tk
controllers retain layout and established interactions. See the
[architecture diagram and code map](docs/ENGINEERING_OVERVIEW.md),
[testing](docs/testing.md), [validation summary](docs/validation-external-import.md),
[known limitations](docs/known-issues.md) and [contributing](CONTRIBUTING.md).

## Publication and licensing

The source folder excludes private projects, experiments, local settings,
environments and build outputs. It includes synthetic tests and retained
[third-party licenses and attribution](THIRD_PARTY_NOTICES.md).

XinPilot's original code is licensed under the [Apache License 2.0](LICENSE).
Copyright 2026 Xin Qiu. See [NOTICE](NOTICE); third-party components retain
their respective licenses and attribution requirements.

Approved author/citation metadata, repository URL and archival DOI remain to
be supplied. See [publication steps](docs/publication.md).
