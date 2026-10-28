# Optional local FASTSOLV

FASTSOLV, PyTorch and model weights are not included. Install FASTSOLV in a
separate Python environment using the [authors' repository](https://github.com/JacksonBurns/fastsolv).
This integration was used with FASTSOLV 1.0.1. It expects four official
fastsolv_1701_1.ckpt through fastsolv_1701_4.ckpt files under the installed package's
checkpoints directory, and checks their integrity before loading. The exact
interface and checkpoint digests are in fastsolv_bridge.py. Arbitrary replacement
models are not supported by this bridge.

In Compound Notes, open Optional Input / Reference and the FASTSOLV prediction
window. Select the separate environment's python.exe and check the environment.
Select compound rows, solvent and temperature, then use Predict All selected.
Distinct solvent/temperature results are retained.

Predictions execute locally. Setup/model downloads require internet access;
inference does not require uploading structures to a prediction service.
Predictions are estimates; model spread is not a confidence interval.

The separate FASTSOLV installer executable is not included in this source snapshot.
If distributed later, attach its matching source/instructions and binary to the
corresponding public release.
