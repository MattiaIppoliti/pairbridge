"""Offline tests only. Synthetic packages are never sent to an earbud."""
from __future__ import annotations
import contextlib
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pairbridge import container as lab

def digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def wrap(payload: bytes | None = None, compression: int = 1, offset: int = 512,
         extra: bool = False, integrity: int = 1) -> bytes:
    """Create a small, independently assembled two-section test container."""
    if payload is None:
        payload = bytes(range(256)) * 16
    n = len(payload) // 2
    sections = [(offset, n, 0x10000), (offset + n, len(payload) - n, 0x20000)]
    encoded = payload if compression == 0 else lzma.compress(payload, format=lzma.FORMAT_ALONE)
    if compression:
        encoded = encoded[:5] + struct.pack('<Q', len(payload)) + encoded[13:]
    values = [
        (0x11, struct.pack('<BBII', compression, integrity, offset, len(encoded))),
        (0x12, struct.pack('<I', 2) + b''.join(struct.pack('<III', *s) for s in sections)),
        (0x13, b'SYNTHETIC_FIXTURE_NOT_FOR_HARDWARE'),
        (0x14, struct.pack('<I', 2) + digest(payload[:n]) + digest(payload[n:])),
    ]
    if extra:
        values.append((0x99, b'unknown'))
    metadata = b''.join(struct.pack('<HH', k, len(v)) + v for k, v in values)
    if 256 + len(metadata) > offset:
        raise ValueError('fixture header too small')
    result = bytearray(b'\x00' * 32 + b'\xff' * 224 + metadata)
    result += b'\xff' * (offset - len(result)) + encoded
    result[:32] = digest(result[256:])
    return bytes(result)


def rehash(data: bytearray) -> bytes:
    data[:32] = digest(data[256:])
    return bytes(data)


def manifest(p: lab.Package) -> dict:
    return {'source_sha256': lab.sha(p.data), 'requires_hardware_validation': True,
            'patches': [{'offset': '0x10', 'before': '10', 'after': 'aa',
                         'reason': 'Synthetic unit test, not a compatibility correction'}]}


class PackageTests(unittest.TestCase):
    def test_plain(self):
        p = lab.Package(wrap(compression=0))
        self.assertEqual(p.unpack(), bytes(range(256)) * 16)
        self.assertTrue(p.info()['all_section_hashes_valid'])

    def test_lzma(self):
        p = lab.Package(wrap())
        self.assertEqual(p.unpack(), bytes(range(256)) * 16)
        self.assertEqual(p.info()['compression'], 'LZMA')

    def test_nondefault_payload_offset(self):
        p = lab.Package(wrap(offset=8192))
        self.assertEqual(p.offset, 8192)
        self.assertEqual(p.unpack(), bytes(range(256)) * 16)

    def test_roundtrip(self):
        p = lab.Package(wrap())
        rebuilt = lab.Package(p.rebuild(p.unpack()))
        self.assertEqual(rebuilt.unpack(), p.unpack())
        self.assertEqual(rebuilt.sections, p.sections)

    def test_plain_roundtrip(self):
        p = lab.Package(wrap(compression=0))
        self.assertEqual(p.rebuild(p.unpack()), p.data)

    def test_filename_does_not_establish_identity(self):
        p = lab.Package(wrap(), 'S305_cc ultra_AB1562AE_V31.6.305.162_left_FotaPackage.bin')
        self.assertIsNone(p.stock_side)

    def test_bad_outer_hash(self):
        data = bytearray(wrap()); data[-1] ^= 1
        with self.assertRaisesRegex(lab.FirmwareError, 'Outer SHA'):
            lab.Package(bytes(data))

    def test_bad_outer_padding(self):
        data = bytearray(wrap()); data[40] = 0
        with self.assertRaisesRegex(lab.FirmwareError, 'padding'):
            lab.Package(bytes(data))

    def test_short_input(self):
        with self.assertRaises(lab.FirmwareError):
            lab.Package(b'')

    def test_tlv_length(self):
        data = bytearray(wrap()); struct.pack_into('<H', data, 258, 65000)
        with self.assertRaises(lab.FirmwareError):
            lab.Package(rehash(data))

    def test_duplicate_tlv(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        struct.pack_into('<H', data, p.tlvs[0x13].value_offset - 4, 0x12)
        with self.assertRaisesRegex(lab.FirmwareError, 'Duplicate'):
            lab.Package(rehash(data))

    def test_missing_mover(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        struct.pack_into('<H', data, p.tlvs[0x12].value_offset - 4, 0x98)
        with self.assertRaisesRegex(lab.FirmwareError, 'Missing'):
            lab.Package(rehash(data))

    def test_bad_payload_bounds(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        struct.pack_into('<I', data, p.tlvs[0x11].value_offset + 6, p.size + 1)
        with self.assertRaisesRegex(lab.FirmwareError, 'bounds'):
            lab.Package(rehash(data))

    def test_noncontiguous_mover(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        struct.pack_into('<I', data, p.tlvs[0x12].value_offset + 4, p.offset + 1)
        with self.assertRaisesRegex(lab.FirmwareError, 'Non-contiguous'):
            lab.Package(rehash(data))

    def test_overlapping_destinations(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        struct.pack_into('<I', data, p.tlvs[0x12].value_offset + 4 + 12 + 8, 0x10000)
        with self.assertRaisesRegex(lab.FirmwareError, 'Overlapping'):
            lab.Package(rehash(data))

    def test_bad_section_digest(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        data[p.tlvs[0x14].value_offset + 4] ^= 1
        with self.assertRaisesRegex(lab.FirmwareError, 'Section 0 SHA'):
            lab.Package(rehash(data)).unpack()

    def test_aes_refused(self):
        p = lab.Package(wrap(compression=2))
        self.assertIsNone(p.info()['all_section_hashes_valid'])
        with self.assertRaisesRegex(lab.FirmwareError, 'AES'):
            p.unpack()

    def test_signed_indicator_refused(self):
        with self.assertRaisesRegex(lab.FirmwareError, 'signed/CRC'):
            lab.Package(wrap(integrity=2))

    def test_crc_indicator_refused(self):
        with self.assertRaises(lab.FirmwareError):
            lab.Package(wrap(integrity=0))

    def test_unknown_compression(self):
        with self.assertRaisesRegex(lab.FirmwareError, 'Unknown compression'):
            lab.Package(wrap(compression=3))

    def test_dictionary_limit(self):
        p = lab.Package(wrap()); data = bytearray(p.data)
        struct.pack_into('<I', data, p.offset + 1, lab.MAX_DICT + 1)
        with self.assertRaisesRegex(lab.FirmwareError, 'dictionary'):
            lab.Package(rehash(data)).unpack()

    def test_truncated_lzma(self):
        p = lab.Package(wrap()); data = bytearray(p.data[:-8])
        struct.pack_into('<I', data, p.tlvs[0x11].value_offset + 6, p.size - 8)
        with self.assertRaises(lab.FirmwareError):
            lab.Package(rehash(data)).unpack()

    def test_unknown_tlv_inspection_only(self):
        p = lab.Package(wrap(extra=True))
        self.assertEqual(len(p.unpack()), 4096)
        with self.assertRaisesRegex(lab.FirmwareError, 'unknown TLVs'):
            p.rebuild(p.unpack())

    def test_rebuild_length_change(self):
        p = lab.Package(wrap())
        with self.assertRaisesRegex(lab.FirmwareError, 'Length-changing'):
            p.rebuild(p.unpack() + b'x')


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.p = lab.Package(wrap())
        self.m = manifest(self.p)

    def test_single_synthetic_edit(self):
        q = lab.Package(lab.apply_manifest(self.p, self.m))
        a, b = self.p.unpack(), q.unpack()
        self.assertEqual(b[16], 0xaa)
        self.assertEqual(sum(x != y for x, y in zip(a, b)), 1)
        self.assertTrue(q.info()['all_section_hashes_valid'])

    def test_wrong_source(self):
        self.m['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(lab.FirmwareError, 'source SHA'):
            lab.apply_manifest(self.p, self.m)

    def test_invalid_source_hash_type(self):
        self.m['source_sha256'] = None
        with self.assertRaisesRegex(lab.FirmwareError, '64-digit'):
            lab.apply_manifest(self.p, self.m)

    def test_invalid_source_hash_format(self):
        self.m['source_sha256'] = 'not-a-hash'
        with self.assertRaisesRegex(lab.FirmwareError, '64-digit'):
            lab.apply_manifest(self.p, self.m)

    def test_no_hardware_acknowledgment(self):
        self.m['requires_hardware_validation'] = False
        with self.assertRaises(lab.FirmwareError):
            lab.apply_manifest(self.p, self.m)

    def test_expected_byte_mismatch(self):
        self.m['patches'][0]['before'] = 'ff'
        with self.assertRaisesRegex(lab.FirmwareError, 'Expected bytes'):
            lab.apply_manifest(self.p, self.m)

    def test_length_changing_patch(self):
        self.m['patches'][0]['after'] = 'aabb'
        with self.assertRaisesRegex(lab.FirmwareError, 'without changing length'):
            lab.apply_manifest(self.p, self.m)

    def test_overlapping_edits(self):
        self.m['patches'].append(dict(self.m['patches'][0]))
        with self.assertRaisesRegex(lab.FirmwareError, 'Overlapping'):
            lab.apply_manifest(self.p, self.m)

    def test_empty_manifest(self):
        self.m['patches'] = []
        with self.assertRaisesRegex(lab.FirmwareError, 'nonempty'):
            lab.apply_manifest(self.p, self.m)

    def test_negative_offset(self):
        self.m['patches'][0]['offset'] = -1
        with self.assertRaisesRegex(lab.FirmwareError, 'outside'):
            lab.apply_manifest(self.p, self.m)

    def test_boolean_offset(self):
        self.m['patches'][0]['offset'] = True
        with self.assertRaisesRegex(lab.FirmwareError, 'integer'):
            lab.apply_manifest(self.p, self.m)

    def test_missing_reason(self):
        self.m['patches'][0]['reason'] = ''
        with self.assertRaisesRegex(lab.FirmwareError, 'reason'):
            lab.apply_manifest(self.p, self.m)

    def test_protected_side_marker(self):
        self.m['patches'][0].update(offset='0x82b', before='2b', after='ff')
        with patch.dict(lab.STOCK, {'left': lab.sha(self.p.data)}):
            with self.assertRaisesRegex(lab.FirmwareError, 'left/right marker'):
                lab.apply_manifest(self.p, self.m)


class UtilityTests(unittest.TestCase):
    def test_changed_ranges(self):
        result = lab.changed_ranges(b'abc123z', b'axc993Z')
        self.assertEqual(result['changed_byte_positions'], 4)
        self.assertEqual(result['first_changed_ranges'],
                         [{'start': 1, 'length': 1}, {'start': 3, 'length': 2}, {'start': 6, 'length': 1}])

    def test_length_difference(self):
        self.assertEqual(lab.changed_ranges(b'a', b'abc')['changed_byte_positions'], 2)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'original'
            lab.write_new(p, b'original')
            with self.assertRaises(FileExistsError):
                lab.write_new(p, b'replacement')
            self.assertEqual(p.read_bytes(), b'original')

    def test_read_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input'; p.write_bytes(b'123456')
            with self.assertRaises(lab.FirmwareError):
                lab.read_limited(p, 5)



if __name__ == "__main__":
    unittest.main()
