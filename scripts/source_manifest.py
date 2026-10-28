"""Record hashes of distributable files; reject common local-data directories."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OMIT = {'.git', '.venv', '.desktop-deps', '.desktop-tooling', '__pycache__',
        'artifacts', 'outputs', 'desktop-workspace', 'release', '.pytest_cache'}

def main():
    files = {}
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if not path.is_file() or set(relative.parts) & OMIT:
            continue
        if path.name in {'SOURCE_SHA256.json', 'xinpilot.local.bat', 'fastsolv_local.json',
                         'Compound_Stock_GUI_settings.json'}:
            continue
        if path.suffix in {'.pyc', '.exe', '.log'} or path.name.startswith('BB Stock list'):
            continue
        files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    output = {'algorithm': 'SHA-256', 'files': files}
    (ROOT / 'SOURCE_SHA256.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(f'Recorded {len(files)} distributable files')

if __name__ == '__main__':
    main()
