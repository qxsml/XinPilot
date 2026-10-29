# XinPilot

**An open-source desktop application connecting compound records, synthesis planning, and LC–MS analysis for high-throughput chemistry.**

XinPilot is a Windows desktop application designed to support experimental planning, data management, and analytical review in high-throughput chemistry. It connects compound identities, stock solutions, liquid-handling instructions, expected product structures, reaction conditions, and analytical results within a unified workflow.

The application combines a TypeScript user interface with Python-based chemistry and workflow functions. It supports manual additions, Tecan and Opentrons liquid-handling workflows, and the import of transfer records from other automation platforms.

## Getting started

### Download and run

XinPilot is available as a standalone Windows executable. **No installation is required.**

1. Download the latest `.exe` file from [GitHub Releases](https://github.com/qxsml/XinPilot/releases).
2. Double-click the downloaded executable to launch XinPilot.
3. Start creating or importing compound records and planning experiments.

### Basic workflow

1. **Compound Notes:** Create or import compound and stock records.
2. **Synthesis Plan:** Prepare manual, Tecan, or Opentrons additions.
3. **Cheminformatics:** Generate expected product structures.
4. **LCMS Analysis:** Process supported analytical reports.
5. **Reaction Summary / Product Summary:** Review experimental and analytical results.
6. **Next Step:** Carry reviewed products into subsequent experiments.
7. **Export Project:** Save your work as a portable `.xinpilot.zip` file.

Additional instructions are available in the [documentation](docs/).

## Connected experimental workflows

### Compound and stock records

Compound Notes provides a centralized workspace for recording Chemical IDs, molecular structures, chemical names, stock concentrations, quantities, and reference information.

Compound information can be retrieved through supported CAS-number and SMILES lookups. Integrated stock-solution calculations assist with determining the solvent volumes required for preparing solutions at specified concentrations.

### Synthesis planning

XinPilot supports manual and automated liquid-handling plans within the same experiment.

- **Tecan:** Generate GWL worklists and associated chemical maps. Horizontal and vertical dispensing formats are mapped to a common reaction plate layout.
- **Opentrons:** Generate Python protocols using selected labware, pipettes, tip-handling policies, and transfer settings.
- **Manual additions:** Record manually dispensed reagents alongside automated transfers.
- **External import:** Import supported transfer tables or structured files, map their fields, and associate source stocks with Chemical IDs.

XinPilot generates worklists and protocols but does not directly control laboratory instruments. Execution remains within the respective instrument software. All generated instructions should be reviewed against the actual instrument and labware configurations before use.

### Expected product structures

XinPilot uses RDKit and reaction SMARTS to generate expected product structures from selected chemical building blocks.

Catalysts, bases, solvents, and other additives can be included in the reaction composition without being treated as structural inputs.

Predefined transformations, customizable reaction templates, and manual product-SMILES correction accommodate different synthetic workflows.

Generated structures represent expected transformations rather than predictions of reaction success, conversion, or isolated yield.

### LC–MS preparation and analytical review

XinPilot supports the preparation of LC–MS sample information and the subsequent analysis of supported analytical reports.

Reaction wells can be mapped to LC–MS sample positions, with expected product structures and masses prepared for analysis. Supported charge-state and counterion adjustments used for mass matching are handled separately from the stored product structures.

#### PyParse integration

XinPilot incorporates the original [PyParse](https://github.com/thatchemistryguy/PyParse) software alongside modified workflows derived from PyParse for product and impurity analysis.

Dedicated graphical user interfaces have been developed for both the original and modified PyParse workflows, allowing their analytical functionality to be accessed within the XinPilot environment.

The original PyParse software is distributed under the Apache License 2.0 license. We acknowledge its original authors and refer users to the associated publication:

> Mason, J.; Wilders, H.; Fallon, D. J.; Thomas, R. P.; Bush, J. T.; Tomkinson, N. C. O.; Rianjongdee, F. **Automated LC-MS Analysis and Data Extraction for High-Throughput Chemistry.** *Digital Discovery* **2023**, *2*, 1894–1899. [https://doi.org/10.1039/D3DD00167A](https://doi.org/10.1039/D3DD00167A).

#### Analytical review

For supported Waters LC–MS reports, XinPilot provides:

- **Product Summary:** Consolidated product structures, analytical results, and chromatographic information.
- **Interactive peak inspection:** Access to available UV chromatograms, integrated peaks, and positive- and negative-ion mass spectra.
- **Manual peak assignment:** Users can reassign an existing integrated peak as the target product while preserving the original automatic assignment for restoration.
- **Modified PyParse workflows:** Customized analytical functionality integrated into the XinPilot environment.

UV area percentages represent chromatographic area fractions and should not be interpreted as isolated yields or quantitative reaction conversions.

#### AutoLynx export

AutoLynx CSV export is available through **Cheminformatics → LCMS Input**.

See the [AutoLynx export guide](docs/autolynx-export.md) for configuration and instructions.

### Subsequent synthesis planning

Reviewed products can be incorporated into subsequent experiments as new stock records once the user provides the relevant material quantities and stock information.

This supports multistep synthesis planning while preserving records of preceding experimental stages.

### Supplementary tools

XinPilot includes additional utilities for stock-solution preparation, molecular-property calculation, and structural-alert screening.

Optional solubility prediction is supported through a separately installed FASTSOLV environment.

## Portable projects

Experiments can be exported as `.xinpilot.zip` project archives for reopening, review, and sharing.

Depending on the workflow, a project archive may include:

- Compound records and stock information.
- Reaction conditions and liquid-handling plans.
- Expected product structures.
- Associated analytical results.
- Supported generated files.
- Chromatographic images and extracted numerical data used for interactive inspection.

The exported analytical data are reduced representations of imported reports rather than complete instrument raw-data archives.

Original analytical reports, analysis platemaps, and other processing inputs should be retained when full reprocessing or independent verification is required.

## Scope and interpretation

XinPilot is intended to support experimental planning, record keeping, and analytical review.

It does not directly operate laboratory instruments or independently verify that planned reagent transfers have been executed.

Generated chemical structures, instrument protocols, analytical assignments, and calculated molecular properties require appropriate scientific review.

The availability and quality of analytical information depend on the original experimental data and supported input formats.

## For developers

XinPilot combines a TypeScript user interface with a Python backend.

RDKit supports molecular parsing, depiction, and reaction transformations, while Ketcher provides graphical molecular-structure and reaction-template editing.

Additional implementation and build information is available in the [developer documentation](docs/).

Contributions improving usability, interoperability, analytical workflows, supported import formats, and software reliability are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

## Citation and reproducibility

When reporting research performed using XinPilot, users are encouraged to identify the software version employed and cite the associated publication when available.

Project archives and relevant original experimental and analytical inputs should be retained alongside reported results to support reproducibility.

Research using the incorporated PyParse software should also cite the original PyParse publication listed above.

## License and acknowledgements

XinPilot is distributed under the [Apache License 2.0](LICENSE).

The application incorporates or depends on third-party software, including RDKit, Ketcher, and PyParse. These components retain their respective licenses, copyright notices, and attribution requirements.

See [NOTICE](NOTICE) and [Third-Party Notices](THIRD_PARTY_NOTICES.md) for additional licensing and attribution information.
