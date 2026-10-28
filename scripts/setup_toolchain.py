"""Install an isolated, checksum-verified Node LTS/TypeScript build toolchain."""
import hashlib, io, json, tarfile, urllib.request, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'.desktop-tooling'
OUT.mkdir(exist_ok=True)
def fetch(url):
    return urllib.request.urlopen(url, timeout=120).read()
versions = json.loads(fetch('https://nodejs.org/dist/index.json'))
version = next(row['version'] for row in versions if row.get('lts'))
name = f'node-{version}-win-x64.zip'
base = f'https://nodejs.org/dist/{version}/'
checks = fetch(base+'SHASUMS256.txt').decode()
expected = next(line.split()[0] for line in checks.splitlines() if line.endswith('  '+name))
content = fetch(base+name)
assert hashlib.sha256(content).hexdigest() == expected
with zipfile.ZipFile(io.BytesIO(content)) as z:
    (OUT/'node.exe').write_bytes(z.read(f'node-{version}-win-x64/node.exe'))
meta = json.loads(fetch('https://registry.npmjs.org/typescript/6.0.2'))
content = fetch(meta['dist']['tarball'])
assert hashlib.sha1(content).hexdigest() == meta['dist']['shasum']
with tarfile.open(fileobj=io.BytesIO(content),mode='r:gz') as archive:
    for item in archive.getmembers():
        if item.isfile() and item.name.startswith('package/lib/'):
            dest = (OUT/'typescript'/item.name.removeprefix('package/')).resolve()
            dest.relative_to(OUT.resolve())
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(archive.extractfile(item).read())
(OUT/'versions.json').write_text(json.dumps({'node':version,'typescript':meta['version']}))
print('Installed isolated toolchain:',version,meta['version'])
