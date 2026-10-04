"""The reviewed compatibility profile is data, never a guessed hardware match."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
PROFILE = json.loads((ROOT / 'profiles/p1.json').read_text())


def checked_bytes(path, entry):
    path = Path(path)
    with path.open('rb') as source:
        data = source.read(entry['source_bytes'] + 1)
    if len(data) != entry['source_bytes'] or hashlib.sha256(data).hexdigest() != entry['source_sha256']:
        raise ValueError(f'{path.name}: file does not match the supported input; nothing patched')
    return data
