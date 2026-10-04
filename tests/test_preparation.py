"""Preflight failures must stop before outputs, build tools or device writes."""
import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from pairbridge import cli, firmware, probe
from pairbridge.profile import checked_bytes


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.stock = b'\0' * probe.ENTRY + probe.PREFIX + probe.ORIGINAL
        self.old = {'messages': [{'opcode': 123, 'direction': 'host_to_earbuds',
                                'pdu_hex': 'f60a1f010000'}] * 2}
        self.new = {'messages': [{'opcode': 123, 'direction': 'host_to_earbuds',
                                'pdu_hex': 'f60af6760080'}] * 2}

    def test_recorded_requests_and_parameter_sweep(self):
        result = probe.verify(self.stock, self.old, self.new)
        self.assertEqual(result['additional_checks_passed'], 1538)
        self.assertEqual(len(result['observed_requests']), 4)
        self.assertFalse(result['full_firmware_emulated'])

    def test_unsupported_machine_instruction(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported instruction'):
            probe.execute(b'\xff' * 36, bytes.fromhex('f60a1f010000'))

    def test_wrong_pdu_length_and_opcode(self):
        for pdu in [b'', bytes.fromhex('f60a1f0100'), bytes.fromhex('f40a1f010000')]:
            with self.subTest(pdu=pdu), self.assertRaises(ValueError):
                probe.execute(probe.PREFIX + probe.PATCHED, pdu)

    def test_changed_stock_block(self):
        with self.assertRaisesRegex(ValueError, 'Stock code'):
            probe.verify(self.stock[:-1] + b'\0', self.old, self.new)

    def test_failed_probe_cannot_pass_silently(self):
        with patch.object(probe, 'execute', return_value={'decision': 'fallback_path'}):
            with self.assertRaisesRegex(ValueError, 'original branch'):
                probe.verify(self.stock, self.old, self.new)


class PreflightTests(unittest.TestCase):
    def test_wrong_size_hash_and_swapped_file(self):
        reference = b'left-side fixture'
        entry = {'source_bytes': len(reference), 'source_sha256': hashlib.sha256(reference).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'left.bin'
            for data in [b'', reference + b'x', b'rightside fixture']:
                path.write_bytes(data)
                with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'supported input'):
                    checked_bytes(path, entry)
            path.write_bytes(reference)
            self.assertEqual(checked_bytes(path, entry), reference)

    def test_bad_right_input_never_builds_either_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'candidate'
            with patch.object(firmware, 'checked_bytes', side_effect=[b'validated-left', ValueError('wrong right')]), \
                 patch.object(firmware, 'Package') as package:
                with self.assertRaisesRegex(ValueError, 'wrong right'):
                    firmware.prepare('left.bin', 'right.bin', out)
                package.assert_not_called()
                self.assertFalse(out.exists())

    def test_bad_apk_stops_before_output_or_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'dist'
            args = argparse.Namespace(left=Path('left.bin'), right=Path('right.bin'),
                                      apk=Path('upstream.apk'), out=out, firmware_only=False)
            with patch.object(cli, 'checked_bytes', side_effect=[b'left', b'right', ValueError('wrong APK')]), \
                 patch.object(cli.firmware, 'prepare') as build, \
                 patch.object(cli.android, 'prepare') as app:
                with self.assertRaisesRegex(ValueError, 'wrong APK'):
                    cli.prepare(args)
                build.assert_not_called()
                app.assert_not_called()
                self.assertFalse(out.exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'dist'
            out.mkdir()
            existing = out / 'keep.txt'
            existing.write_text('original')
            args = argparse.Namespace(left=Path('left.bin'), right=Path('right.bin'),
                                      apk=Path('upstream.apk'), out=out, firmware_only=False)
            with patch.object(cli, 'checked_bytes', return_value=b'valid'), \
                 patch.object(cli.firmware, 'prepare') as build:
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    cli.prepare(args)
                build.assert_not_called()
            self.assertEqual(existing.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
