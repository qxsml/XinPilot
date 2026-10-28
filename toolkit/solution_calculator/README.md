# Solution & Stock Calculator

This standalone XinPilot Toolkit utility calculates:

- final stock-solution volume from available mg or µmol and a target concentration;
- concentration from available amount and final solution volume; and
- required µmol/mg from target concentration and final volume.

XinPilot can send selected Product Details rows into the batch table through a temporary JSON transfer. The utility does not modify the active project, Compound Notes, or any stock list. Product Details SMILES and molecular weight are the weighing identity. An LCMS target and UV254 purity may be shown as references, but UV254 area purity is never automatically used as mass/assay purity.

The XinPilot batch table has an optional structure-preview checkbox. It is off by default; while enabled, its separate preview window stays open and follows the selected row using that row's calculation SMILES.

The Import Batch tab accepts SDF, Excel, and CSV files. The user maps one ID column and explicitly chooses exactly one calculation source/column: SMILES, molecular formula, or molecular weight. SMILES is parsed to calculate formula/MW and supports structure preview. Formula is used only to calculate average molecular weight, and an imported molecular weight is used directly. Formula/MW imports do not compare against, select, or fall back to a SMILES column. Solvent, target concentration, recovered-amount unit, and recovered amounts are entered in the calculator GUI rather than mapped from the file.

Preparation notes intentionally say **make up to the final solution volume**; the calculated volume is not necessarily the literal solvent volume to add to a solid.
