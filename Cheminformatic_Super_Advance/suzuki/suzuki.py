from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from reaction_template_engine import run

# Broader Suzuki template: aryl/vinyl halide + boronic acid/boronate
SMARTS = "[*:1][Br,Cl,I:2].[*:3]B([O])[O]>>[*:1][*:3]"

raise SystemExit(run(SMARTS, "output/suzuki_products.csv", "suzuki"))
