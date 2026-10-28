# XinPilot Toolkit

This directory contains standalone utilities launched from XinPilot's **Toolkit** menu.

## Compound Library Builder

`compound_library_builder/` contains the independent, path-in/path-out compound-library enumeration application. XinPilot launches its existing batch entry point in a separate process; the utility does not read or modify the active XinPilot project.

## Aromatic SMILES Converter

`aromatic_smiles_converter/` converts aromatic SMILES to explicit alternating bonds and converts explicit aromatic bond patterns back to aromatic notation.

## Opentrons Protocol Simulator

`opentrons_protocol_simulator/` contains a self-contained simulator for Opentrons protocol and custom-labware files. It does not require a local Opentrons environment.

## Solution & Stock Calculator

`solution_calculator/` calculates stock preparation volumes, resulting concentrations, and required mass/amount. It can open independently or receive a temporary, read-only set of Product Details rows from XinPilot's Next Step tab. It does not archive or advance the synthesis, clear project data, or write to Compound Notes or stock lists.
