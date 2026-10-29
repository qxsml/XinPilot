# XinPilot

**An open-source desktop application connecting compound records, synthesis planning and LC–MS review for high-throughput chemistry.**

XinPilot helps chemists keep experimental information together across the synthesis workflow. It links compound identities and stock solutions with liquid-handling plans, expected product structures, reaction conditions and analytical results within a portable project.

XinPilot runs locally on Windows and provides a TypeScript interface with Python-based chemistry and workflow functions. It supports manual additions, Tecan and Opentrons planning, and the import of transfer records from other liquid-handling platforms.

## Connected experimental workflows

### Compound and stock records

Compound Notes stores Chemical IDs, structures, chemical names, stock concentrations, quantities and reference information. Compound information can be retrieved using supported CAS-number or SMILES lookup, and stock-solution calculations help determine the solvent volume required for preparation.

### Synthesis planning

Manual, Tecan and Opentrons additions can be combined within the same experiment.

- **Tecan:** Prepare GWL worklists and accompanying chemical maps. Horizontal and vertical dispensing formats are linked to a common reaction plate map.
- **Opentrons:** Generate Python protocols from selected labware, pipettes, tip policies and transfer settings.
- **Manual:** Record additions alongside automated transfers.
- **External Import:** Import supported transfer tables or structured files, map their fields, and associate source stocks with Chemical IDs.

XinPilot generates worklists and protocols. Instrument control and execution remain in the corresponding instrument software. Generated instructions should be reviewed against the actual instrument and labware configuration before use.

### Expected product structures

XinPilot uses RDKit and reaction SMARTS to generate expected products from selected building blocks. Catalysts, bases and other additives can remain part of the reaction composition without serving as structural inputs.

Predefined transformations, custom reaction templates and manual product-SMILES correction support different experimental needs. Expected products represent the intended transformations; they are not predictions of reaction success or yield.

### LC–MS preparation and analytical review

Reaction wells can be mapped to LC–MS sample positions, with target structures and masses prepared for analysis. Supported charge and counterion adjustments for LC–MS matching are maintained separately from the stored product structures.

XinPilot includes the bundled PyParse workflow and modified workflows for product and impurity analysis. For supported Waters reports, Product Summary brings together structures, analytical values and traces. Interactive peak inspection provides access to available UV chromatograms, integrated peaks and positive- and negative-ion mass spectra.

Chemists can manually assign an existing integrated peak as the product while retaining the automatic result for restoration. UV area percentages are analytical area fractions and should not be interpreted as isolated yields or quantitative conversion.

AutoLynx CSV export is available from **Cheminformatics → LCMS Input**. See the [AutoLynx export guide](docs/autolynx-export.md) for configuration and use.

### Subsequent synthesis planning

Reviewed products can be carried into a subsequent experiment as new stock records after the user supplies the relevant material and stock information. This supports multistep planning while retaining the preceding synthesis records.

### Supplementary tools

The toolkit provides utilities for stock-solution preparation, molecular-property calculation and structural-alert screening. Optional solubility prediction uses a separately installed FASTSOLV environment.

## Portable projects

Experiments can be exported as `.xinpilot.zip` projects for reopening, review and handover.

A project can contain structured compound and planning records, product structures, analytical associations, supported generated files, trace images and extracted numerical data used for interactive inspection.

These analytical data are reduced representations of the imported reports, not complete instrument raw-data archives. Retain the original reports, analysis platemaps and other processing inputs when full reprocessing is required.

## Getting started

1. Download the Windows executable from [Releases](https://github.com/qxsml/XinPilot/releases), when available.
2. Open XinPilot and enter or import compound records in **Compound Notes**.
3. Prepare additions in **Synthesis Plan**, or import supported external transfer records.
4. Push the planning inputs to **Cheminformatics**, select structural building blocks and generate expected products.
5. Configure LC–MS well mapping and process supported analytical reports.
6. Review results in **Reaction Summary** and **Product Summary**.
7. Export a `.xinpilot.zip` project to preserve and share the experiment.

Detailed documentation is available in the [docs folder](docs).

## Scope and interpretation

XinPilot supports experimental planning, record keeping and analytical review. It does not directly operate laboratory instruments or establish that a planned transfer was executed.

Chemical structures, generated protocols, analytical assignments and calculated properties require scientific review. Available analytical detail depends on the information contained in the imported files.

## For developers

XinPilot combines a TypeScript user interface with a Python backend. RDKit provides molecular parsing, depiction and reaction transformations, while Ketcher provides graphical structure and reaction-template input.

See the [developer documentation](docs) for implementation and build information. Contributions that improve usability, interoperability, supported import formats and workflow reliability are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

## Citation and reproducibility

When reporting work performed with XinPilot, identify the software version used and cite the associated publication when available. Retain the project archive and relevant original experimental and analytical inputs alongside the reported results.

## License and acknowledgements

XinPilot is distributed under the [Apache License 2.0](LICENSE).

XinPilot incorporates and depends on third-party software, including RDKit, Ketcher and PyParse. Third-party components retain their respective licenses and attribution requirements. See [NOTICE](NOTICE) and the [third-party materials](third_party).
