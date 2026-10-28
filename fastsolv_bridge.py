"""External FASTSOLV protocol. No ML dependencies are imported into XinPilot."""
import json
import os
import subprocess
from pathlib import Path

# Executed only by the user's separate FASTSOLV Python interpreter.
RUNNER = r'''
import contextlib, hashlib, importlib.util, json, math, os, sys
from pathlib import Path
request = json.load(sys.stdin)
try:
    spec = importlib.util.find_spec("fastsolv")
    if spec is None:
        raise ValueError("FASTSOLV is not installed in this Python environment.")
    folder = Path(spec.origin).parent / "checkpoints"
    hashes = ["8d0672a025eb0b183f27c238a47c7cfe", "eb34f9898d00ec6eea1d1a33443968d8", "6731ee7f42509ed2bdedcdad415940f4", "e418b389f68d5004508315028f665df6"]
    expected = {f"fastsolv_1701_{i}.ckpt" for i in range(1, 5)}
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != expected:
        raise ValueError("Install all four official FASTSOLV checkpoints in " + str(folder))
    for i, digest in enumerate(hashes, 1):
        with (folder / f"fastsolv_1701_{i}.ckpt").open("rb") as stream:
            if hashlib.file_digest(stream, "md5").hexdigest() != digest:
                raise ValueError("Model integrity check failed; reinstall the official checkpoints.")
    # Older official checkpoints require legacy loading in recent PyTorch.
    # Only allow this after verifying the four published checkpoint digests.
    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["MORDRED_NUM_PROC"] = "1"
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        import pandas as pd
        from fastsolv import fastsolv
        from importlib.metadata import version
        if request["mode"] == "check":
            response = {"version": version("fastsolv"), "models": 4}
        else:
            from rdkit import Chem
            requests = request["items"] if request["mode"] == "batch" else [request]
            if not requests:
                raise ValueError("Select at least one compound.")
            inputs = []
            for item in requests:
                for smiles in (item["solute"], item["solvent"]):
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None or not mol.GetNumAtoms():
                        raise ValueError("Invalid molecular structure.")
                temperature = float(item["temperature_c"]) + 273.15
                if not math.isfinite(temperature) or temperature <= 0:
                    raise ValueError("Temperature must be above absolute zero.")
                inputs.append({"solute_smiles": item["solute"], "solvent_smiles": item["solvent"], "temperature": temperature})
            predictions = fastsolv(pd.DataFrame(inputs))
            results = []
            for _, result in predictions.iterrows():
                log_s, spread = float(result["predicted_logS"]), float(result["predicted_logS_stdev"])
                if not all(math.isfinite(x) for x in (log_s, spread)) or spread < 0:
                    raise ValueError("Model returned an invalid prediction.")
                results.append({"log_s": log_s, "spread": spread, "version": version("fastsolv")})
            if len(results) != len(requests):
                raise ValueError("Model returned an unexpected number of results.")
            response = {"results": results} if request["mode"] == "batch" else results[0]
    print(json.dumps(response, allow_nan=False))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    sys.exit(1)
'''


def run_external(python_path, request):
    executable = Path(python_path).expanduser()
    if not executable.is_file():
        raise ValueError("Select the python.exe in your FASTSOLV environment.")
    env = os.environ.copy()
    # Avoid inherited frozen-app/Python configuration affecting the external interpreter.
    for key in ("PYTHONHOME", "PYTHONPATH", "_MEIPASS2"):
        env.pop(key, None)
    try:
        completed = subprocess.run(
            [str(executable), "-I", "-c", RUNNER], input=json.dumps(request),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("FASTSOLV did not finish within five minutes. The prediction process was stopped; check the selected environment before retrying.") from None
    try:
        result = json.loads(completed.stdout)
    except ValueError:
        raise RuntimeError("FASTSOLV did not return a result. " + completed.stderr[-1200:])
    if completed.returncode or "error" in result:
        raise RuntimeError(result.get("error", "FASTSOLV failed."))
    return result
