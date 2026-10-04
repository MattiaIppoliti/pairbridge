"""Build the reviewed patch with container, section and NVKEY checks intact."""
from pathlib import Path

from .container import Package, apply_manifest, sha, write_new, write_json
from . import nvkeys, probe
from .profile import PROFILE, checked_bytes


def prepare(left, right, destination):
    # Validate BOTH sides before creating either candidate.
    sources = {side: checked_bytes(path, PROFILE['firmware'][side])
               for side, path in [('left', left), ('right', right)]}
    built = {}
    rows = []
    old = {'messages': [{'opcode': 123, 'direction': 'host_to_earbuds', 'pdu_hex': 'f60a1f010000'}] * 2}
    new = {'messages': [{'opcode': 123, 'direction': 'host_to_earbuds', 'pdu_hex': 'f60af6760080'}] * 2}
    for side, data in sources.items():
        package = Package(data, side)
        original = package.unpack()
        probe_result = probe.verify(original, old, new)
        patch = dict(PROFILE['patch'])
        patch['reason'] = 'Keep the existing command/reply path; relax byte3 and only bit7 of byte5. Validated on the profile unit; other units remain untested.'
        manifest = {'source_sha256': PROFILE['firmware'][side]['source_sha256'],
                    'requires_hardware_validation': True, 'patches': [patch]}
        image = apply_manifest(package, manifest)
        checked = Package(image)
        edited = checked.unpack()
        expected = PROFILE['firmware'][side]
        if len(image) != expected['candidate_bytes'] or sha(image) != expected['candidate_sha256']:
            raise ValueError('Reconstructed candidate does not match the reviewed output hash')
        offset, after = int(patch['offset'], 0), bytes.fromhex(patch['after'])
        if edited[:offset] != original[:offset] or edited[offset+len(after):] != original[offset+len(after):]:
            raise ValueError('Unexpected change outside the reviewed patch')
        if edited[offset:offset+len(after)] != after or checked.sections != package.sections:
            raise ValueError('Patch bytes or mover layout changed')
        if edited[nvkeys.START:nvkeys.END] != original[nvkeys.START:nvkeys.END]:
            raise ValueError('NVKEY region changed')
        if nvkeys.records(edited) != nvkeys.records(original):
            raise ValueError('NVKEY records changed')
        if checked.tlvs[0x13].value != package.tlvs[0x13].value or edited[0x82b] != original[0x82b]:
            raise ValueError('Version or side marker changed')
        if image[package.offset:package.offset+5] != data[package.offset:package.offset+5]:
            raise ValueError('LZMA properties/dictionary changed')
        unchanged_sections = [i for i, (src, count, _) in enumerate(package.sections)
                              if original[src-package.offset:src-package.offset+count] == edited[src-package.offset:src-package.offset+count]]
        if unchanged_sections != [0, 2, 3]:
            raise ValueError('Unexpected firmware section changed')
        built[side] = image
        rows.append({'side': side, 'file': expected['output_name'], 'source_sha256': sha(data),
                     'output_sha256': sha(image), 'bytes': len(image), 'changed_payload_bytes': sum(a != b for a, b in zip(original, edited)),
                     'nvkeys_unchanged': True, 'section_hashes_verified': True,
                     'lzma_properties_preserved': True, 'version_and_side_preserved': True,
                     'unchanged_sections': unchanged_sections, 'probe': probe_result})
    destination = Path(destination)
    for side, image in built.items():
        write_new(destination / PROFILE['firmware'][side]['output_name'], image)
    report = {'profile': PROFILE['id'], 'variants': rows, 'flashed_by_this_command': False,
              'historical_validation': PROFILE['validation']}
    write_json(destination / 'firmware-verification.json', report)
    return report
