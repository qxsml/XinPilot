"""Compile all distributed Python files in memory; do not import or execute them."""
from pathlib import Path
from verify_source_manifest import inventory, ROOT


def syntax_errors(paths):
    errors = []
    for path in paths:
        path = Path(path)
        try:
            compile(path.read_bytes(), str(path), 'exec')
        except (SyntaxError, UnicodeError, OSError) as exc:
            errors.append(f'{path}: {exc}')
    return errors


if __name__ == '__main__':
    paths = [ROOT / name for name in inventory() if name.endswith('.py')]
    errors = syntax_errors(paths)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(paths)} distributed Python files compile')
