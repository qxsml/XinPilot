"""Inventory user-facing GPT6 controls; this is not a claim of behavioral parity."""
import ast,csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT
OUT=ROOT/'artifacts/control-inventory'
OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for path in sorted(SOURCE.glob('*.py')):
    if path.stem.startswith(('render_','validate_')):
        continue
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        name=ast.unparse(node.func)
        if name.split('.')[-1] not in ('Button','Checkbutton','Radiobutton','Combobox','add_command','add_checkbutton','add_radiobutton'):
            continue
        attrs={kw.arg:kw.value for kw in node.keywords if kw.arg}
        label=attrs.get('text',attrs.get('label'))
        callback=attrs.get('command')
        rows.append({'file':path.name,'line':node.lineno,'control':name,
                     'label':ast.literal_eval(label) if isinstance(label,ast.Constant) else ast.unparse(label) if label else '',
                     'callback':ast.unparse(callback) if callback else '',
                     'parity':'not individually verified'})
with (OUT/'gpt6_control_inventory.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
counts={name:sum(r['file']==name for r in rows) for name in sorted({r['file'] for r in rows})}
(OUT/'inventory_summary.json').write_text(json.dumps({'control_count':len(rows),'by_file':counts},indent=2))
print(json.dumps(counts,indent=2));print('Total controls:',len(rows))
