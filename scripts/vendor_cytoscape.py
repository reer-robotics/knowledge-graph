"""Fetch a pinned official npm release, verify integrity, and copy only browser JS/license."""
import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
lock = root / 'vendor-lock.json'
if lock.exists():
    version = json.loads(lock.read_text())['version']
else:
    with urlopen('https://registry.npmjs.org/cytoscape/latest') as response:
        version = json.load(response)['version']
with urlopen('https://registry.npmjs.org/cytoscape/' + version) as response:
    metadata = json.load(response)
with urlopen(metadata['dist']['tarball']) as response:
    blob = response.read()
algorithm, expected = metadata['dist']['integrity'].split('-', 1)
assert algorithm == 'sha512'
assert base64.b64encode(hashlib.sha512(blob).digest()).decode() == expected
out = root / 'src/knowledge_graph/web/vendor'
with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
    for member, target in [('package/dist/cytoscape.min.js','cytoscape.min.js'), ('package/LICENSE','CYTOSCAPE-LICENSE')]:
        content = archive.extractfile(member).read()
        (out / target).write_bytes(content)
record = {'package':'cytoscape','version':version,'integrity':metadata['dist']['integrity'],
          'url':metadata['dist']['tarball'], 'browser_sha256':hashlib.sha256((out/'cytoscape.min.js').read_bytes()).hexdigest()}
lock.write_text(json.dumps(record, indent=2)+'\n')
print('Vendored Cytoscape.js', version, 'with verified npm integrity.')
