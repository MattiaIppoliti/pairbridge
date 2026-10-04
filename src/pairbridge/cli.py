"""Small user-facing command line: fetch, verify and prepare; never flashes."""
import argparse
from pathlib import Path
import hashlib
import tempfile
import urllib.parse
import urllib.request

from . import android, firmware
from .profile import ROOT, PROFILE, checked_bytes


def fetch(directory):
    directory = Path(directory)
    entries = {'upstream.apk': PROFILE['app']}
    entries.update({entry['input_name']: entry for entry in PROFILE['firmware'].values()})
    results = []
    for name, entry in entries.items():
        target = directory / name
        if target.exists():
            checked_bytes(target, entry)
        else:
            url = entry['source_url']
            request = urllib.request.Request(url, headers={'User-Agent': 'PairBridge/0.1'})
            with urllib.request.urlopen(request, timeout=45) as response:
                final = urllib.parse.urlsplit(response.url)
                hosts = {'raw.githubusercontent.com', 'www.dropbox.com', 'dl.dropboxusercontent.com'}
                host = final.hostname or ''
                if final.scheme != 'https' or (host not in hosts and not host.endswith('.dropboxusercontent.com')):
                    raise ValueError('Input download redirected outside the reviewed hosts')
                data = response.read(entry['source_bytes'] + 1)
            if len(data) != entry['source_bytes'] or hashlib.sha256(data).hexdigest() != entry['source_sha256']:
                raise ValueError(f'{name}: source download changed; no file written')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(data)
        results.append(name)
        print(f'Verified input: {name}', flush=True)
    return results


def prepare(args):
    # Reject incompatible/mislabeled inputs before invoking tools or writing outputs.
    checked_bytes(args.left, PROFILE['firmware']['left'])
    checked_bytes(args.right, PROFILE['firmware']['right'])
    if not args.firmware_only:
        checked_bytes(args.apk, PROFILE['app'])
    out = args.out.resolve()
    if out.exists():
        raise ValueError('Output directory already exists. Choose a new --out directory; existing files are preserved')
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=local) as scratch:
        scratch = Path(scratch)
        print('Preparing verified firmware files...', flush=True)
        firmware.prepare(args.left, args.right, scratch)
        if not args.firmware_only:
            print('Building and verifying the Android app locally...', flush=True)
            android.prepare(args.apk.resolve(), scratch)
        sums = ''.join(hashlib.sha256(f.read_bytes()).hexdigest() + '  ' + f.name + '\n'
                       for f in sorted(scratch.iterdir()) if f.is_file())
        (scratch / 'SHA256SUMS.txt').write_text(sums)
        # Reserve the destination only after ALL verification and build work succeeds.
        out.mkdir(parents=True, exist_ok=False)
        for file in scratch.iterdir():
            if file.is_file():
                with (out / file.name).open('xb') as target:
                    target.write(file.read_bytes())
    print(f'Ready: {out}', flush=True)
    print('Copy the generated files to Android, then follow README.md. This command did not connect to or flash a device.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='PairBridge — verified local preparation and Android commit recovery')
    commands = parser.add_subparsers(dest='command', required=True)
    f = commands.add_parser('fetch', help='Download the exact reviewed third-party inputs locally')
    f.add_argument('--into', type=Path, default=ROOT / 'inputs')
    p = commands.add_parser('prepare', help='Generate verified firmware files and the locally signed Android app')
    p.add_argument('--left', type=Path, default=ROOT / 'inputs/left.bin')
    p.add_argument('--right', type=Path, default=ROOT / 'inputs/right.bin')
    p.add_argument('--apk', type=Path, default=ROOT / 'inputs/upstream.apk')
    p.add_argument('--out', type=Path, default=ROOT / 'dist')
    p.add_argument('--firmware-only', action='store_true', help='Prepare firmware files without rebuilding Android software')
    v = commands.add_parser('verify-inputs', help='Check all local inputs without rebuilding anything')
    v.add_argument('--into', type=Path, default=ROOT / 'inputs')
    args = parser.parse_args(argv)
    try:
        if args.command == 'fetch':
            fetch(args.into)
        elif args.command == 'verify-inputs':
            checked_bytes(args.into / 'upstream.apk', PROFILE['app'])
            for entry in PROFILE['firmware'].values():
                checked_bytes(args.into / entry['input_name'], entry)
            print('All local input files match the reviewed profile.')
        else:
            return prepare(args)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Stopped: {exc}', file=__import__('sys').stderr)
        return 2
