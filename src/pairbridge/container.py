"""Validated firmware containers; never connects to a device."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import lzma
from pathlib import Path
import re
import struct
from . import nvkeys as nvkey_integrity

MAX_FILE = 16 * 1024 * 1024
MAX_PAYLOAD = 32 * 1024 * 1024
MAX_DICT = 16 * 1024 * 1024
# These are published archival hashes, NOT manufacturer signatures.
STOCK = {
    "left": "4781193dd399278df583d220c5804e5985961370425eed3d339c5c613ba4546f",
    "right": "7cdeff75c420316646c67fe9fad6f5f3e365a1791a55241e351924f411d78bda",
}
TLV_NAMES = {0x11: "basic", 0x12: "mover", 0x13: "version",
             0x14: "integrity", 0x20: "device_name", 0x21: "device_type",
             0xF0: "nvdm_incompatible"}

class FirmwareError(ValueError):
    """Malformed, unsupported, or unsafe-to-process firmware input."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_limited(path: Path, maximum: int = MAX_FILE) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise FirmwareError(f"File exceeds the {maximum}-byte limit")
    return data


def write_new(path: Path, data: bytes) -> None:
    """Never overwrite an original, symlink, or existing report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write_json(path: Path, value: object) -> None:
    write_new(path, (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode())


@dataclass(frozen=True)
class TLV:
    kind: int
    value: bytes
    value_offset: int


class Package:
    def __init__(self, data: bytes, name: str = "firmware"):
        if not 270 <= len(data) <= MAX_FILE:
            raise FirmwareError("Not a supported-size Airoha package")
        if data[32:256] != b"\xff" * 224:
            raise FirmwareError("Unsupported outer header/padding")
        if hashlib.sha256(data[256:]).digest() != data[:32]:
            raise FirmwareError("Outer SHA-256 mismatch; input was not changed")
        self.data, self.name = data, name
        self.tlvs: dict[int, TLV] = {}
        cursor, declared_offset = 256, None
        while cursor + 2 <= (declared_offset or len(data)):
            kind = struct.unpack_from("<H", data, cursor)[0]
            if kind == 0xFFFF:
                break
            if cursor + 4 > (declared_offset or len(data)):
                raise FirmwareError("Truncated TLV header")
            kind, length = struct.unpack_from("<HH", data, cursor)
            end = cursor + 4 + length
            if length == 0 or end > (declared_offset or len(data)):
                raise FirmwareError("TLV length crosses header boundary")
            if kind in self.tlvs:
                raise FirmwareError(f"Duplicate TLV 0x{kind:04x}")
            self.tlvs[kind] = TLV(kind, data[cursor + 4:end], cursor + 4)
            if kind == 0x11:
                if length != 10:
                    raise FirmwareError("Unsupported BASIC_INFO length")
                _, _, declared_offset, _ = struct.unpack("<BBII", self.tlvs[kind].value)
                if not end <= declared_offset <= len(data):
                    raise FirmwareError("Invalid payload offset")
            cursor = end
            if len(self.tlvs) > 128:
                raise FirmwareError("Too many header entries")
        for required in (0x11, 0x12, 0x14):
            if required not in self.tlvs:
                raise FirmwareError(f"Missing TLV 0x{required:04x}")
        self.compression, self.integrity, self.offset, self.size = struct.unpack(
            "<BBII", self.tlvs[0x11].value)
        if self.offset + self.size != len(data) or cursor > self.offset:
            raise FirmwareError("Payload bounds do not match file size")
        if data[cursor:self.offset] != b"\xff" * (self.offset - cursor):
            raise FirmwareError("Unsupported padding before payload")
        if self.compression not in (0, 1, 2):
            raise FirmwareError("Unknown compression mode")
        if self.integrity != 1:
            raise FirmwareError("Only SHA-256 packages supported; signed/CRC variants refused")
        table = self.tlvs[0x12].value
        if len(table) < 4:
            raise FirmwareError("Truncated section count")
        count = struct.unpack_from("<I", table)[0]
        if not 1 <= count <= 128 or len(table) != 4 + 12 * count:
            raise FirmwareError("Invalid section table")
        self.sections = [struct.unpack_from("<III", table, 4 + i * 12) for i in range(count)]
        # Airoha mover source offsets include the FOTA header length. They are
        # NOT direct offsets in the decompressed payload. Verified on S305/S505.
        expected = self.offset
        destinations: list[tuple[int, int]] = []
        for src, length, dest in self.sections:
            if src != expected or length == 0 or length > MAX_PAYLOAD:
                raise FirmwareError("Non-contiguous or invalid mover section")
            expected += length
            if dest + length > 0x100000000:
                raise FirmwareError("Destination address overflow")
            if any(dest < hi and lo < dest + length for lo, hi in destinations):
                raise FirmwareError("Overlapping destination sections")
            destinations.append((dest, dest + length))
        self.payload_length = expected - self.offset
        if self.payload_length > MAX_PAYLOAD:
            raise FirmwareError("Decompressed image exceeds limit")
        verification = self.tlvs[0x14].value
        if len(verification) != 4 + 32 * count or struct.unpack_from("<I", verification)[0] != count:
            raise FirmwareError("Section checksum table mismatch")
        self.checksums = [verification[4 + i * 32:4 + (i + 1) * 32] for i in range(count)]

    @property
    def stock_side(self) -> str | None:
        digest = sha(self.data)
        return next((side for side, value in STOCK.items() if digest == value), None)

    def unpack(self) -> bytes:
        compressed = self.data[self.offset:]
        if self.compression == 2:
            raise FirmwareError("AES-encrypted package: no key is assumed or guessed")
        if self.compression == 0:
            payload = compressed
        else:
            if len(compressed) < 13:
                raise FirmwareError("Truncated LZMA header")
            dictionary = struct.unpack_from("<I", compressed, 1)[0]
            if dictionary > MAX_DICT:
                raise FirmwareError("LZMA dictionary exceeds limit")
            # Vendor uses an initialized size field. Decode as an unknown-size
            # LZMA-Alone stream and enforce the mover-table size independently.
            fixed = compressed[:5] + b"\xff" * 8 + compressed[13:]
            try:
                dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=64 * 1024 * 1024)
                payload = dec.decompress(fixed, max_length=self.payload_length + 1)
            except lzma.LZMAError as exc:
                raise FirmwareError(f"LZMA decoding failed: {exc}") from exc
            if not dec.eof:
                raise FirmwareError("Truncated LZMA stream or decompressed-size overflow")
            if dec.unused_data and set(dec.unused_data) != {255}:
                raise FirmwareError("Unexpected data after the LZMA stream")
        if len(payload) != self.payload_length:
            raise FirmwareError("Decompressed length does not match mover table")
        for number, ((src, length, _), digest) in enumerate(zip(self.sections, self.checksums)):
            begin = src - self.offset
            if hashlib.sha256(payload[begin:begin + length]).digest() != digest:
                raise FirmwareError(f"Section {number} SHA-256 mismatch")
        return payload

    def info(self) -> dict:
        result = {
            "file": self.name, "size": len(self.data), "sha256": sha(self.data),
            "archival_s305_side": self.stock_side,
            "identity_note": "Stock identity is hash-based, not inferred from filename/version text",
            "compression": {0: "none", 1: "LZMA", 2: "LZMA+AES"}[self.compression],
            "package_integrity": "SHA-256; this is not a digital signature or a bootloader audit",
            "payload_offset": self.offset, "compressed_length": self.size,
            "expected_payload_length": self.payload_length,
            "outer_sha256_valid": True,
            "header_tlvs": [{"type": hex(t.kind), "name": TLV_NAMES.get(t.kind, "unknown"),
                              "length": len(t.value)} for t in self.tlvs.values()],
            "text_header_values": {TLV_NAMES[k]: t.value.rstrip(b"\xff\x00").decode("ascii", "replace")
                                   for k, t in self.tlvs.items() if k in (0x13, 0x20, 0x21)},
            "sections": [{"source": src, "payload_offset": src - self.offset,
                          "length": length, "destination": dest, "sha256": h.hex()}
                         for (src, length, dest), h in zip(self.sections, self.checksums)],
            "hardware_tested": False, "iphone_compatibility": "not established",
        }
        if self.compression != 2:
            payload = self.unpack()
            result.update(payload_sha256=sha(payload), payload_length=len(payload),
                          all_section_hashes_valid=True)
            if self.stock_side:
                result["s305_nvkey_records_validated"] = len(nvkey_integrity.records(payload))
                result["s305_nvkey_checksum_rule"] = "sum(key low byte, key high byte, data bytes) modulo 256"
        else:
            result["all_section_hashes_valid"] = None
        return result

    def rebuild(self, payload: bytes) -> bytes:
        """Build an OFFLINE research candidate; does not authorize flashing."""
        self.unpack()  # validates original, and refuses encrypted input
        if set(self.tlvs) - set(TLV_NAMES):
            raise FirmwareError("Rebuild refused: unknown TLVs might contain integrity metadata")
        if len(payload) != self.payload_length:
            raise FirmwareError("Length-changing edits are not supported")
        if self.stock_side:
            nvkey_integrity.records(payload)
        if self.compression == 0:
            encoded = payload
        else:
            old = self.data[self.offset:]
            prop, dictionary = old[0], struct.unpack_from("<I", old, 1)[0]
            lc = prop % 9
            rem = prop // 9
            lp, pb = rem % 5, rem // 5
            if pb > 4 or lc + lp > 4:
                raise FirmwareError("Unsupported LZMA properties for recompression")
            try:
                encoded = lzma.compress(payload, format=lzma.FORMAT_ALONE, filters=[{
                    "id": lzma.FILTER_LZMA1, "dict_size": dictionary, "lc": lc,
                    "lp": lp, "pb": pb, "mode": lzma.MODE_FAST,
                    "nice_len": 25, "mf": lzma.MF_BT4}])
            except (lzma.LZMAError, ValueError) as exc:
                raise FirmwareError(f"LZMA recompression failed: {exc}") from exc
            encoded = encoded[:5] + struct.pack("<Q", len(payload)) + encoded[13:]
        header = bytearray(self.data[:self.offset])
        struct.pack_into("<I", header, self.tlvs[0x11].value_offset + 6, len(encoded))
        for i, (src, length, _) in enumerate(self.sections):
            start = src - self.offset
            position = self.tlvs[0x14].value_offset + 4 + i * 32
            header[position:position + 32] = hashlib.sha256(payload[start:start + length]).digest()
        rebuilt = header + encoded
        rebuilt[:32] = hashlib.sha256(rebuilt[256:]).digest()
        verified = Package(bytes(rebuilt), "OFFLINE_CANDIDATE")
        if verified.unpack() != payload or verified.sections != self.sections:
            raise FirmwareError("Internal rebuild round-trip check failed")
        return bytes(rebuilt)


def changed_ranges(first: bytes, second: bytes, limit: int = 128) -> dict:
    ranges, start, changes = [], None, 0
    length = max(len(first), len(second))
    for i in range(length):
        different = i >= len(first) or i >= len(second) or first[i] != second[i]
        if different:
            changes += 1
            if start is None:
                start = i
        elif start is not None:
            if len(ranges) < limit:
                ranges.append({"start": start, "length": i - start})
            start = None
    if start is not None and len(ranges) < limit:
        ranges.append({"start": start, "length": length - start})
    return {"changed_byte_positions": changes, "first_changed_ranges": ranges,
            "range_list_may_be_truncated": len(ranges) >= limit,
            "alignment": "same offsets only; not function-level equivalence or a transplantable patch"}


def compare_packages(a: Package, b: Package) -> dict:
    first, second = a.unpack(), b.unpack()
    return {"first": a.info(), "second": b.info(),
            "same_mover_layout": a.sections == b.sections,
            "same_decompressed_length": len(first) == len(second),
            "difference": changed_ranges(first, second),
            "safe_to_cross_flash": False,
            "warning": "A newer filename or shared chipset does not prove compatibility or identify a fix"}


def apply_manifest(package: Package, manifest: dict) -> bytes:
    """Apply a researched, exact-input, fixed-length manifest."""
    source_hash = manifest.get("source_sha256")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source_hash):
        raise FirmwareError("Manifest source SHA-256 must be a 64-digit hexadecimal string")
    if source_hash.lower() != sha(package.data):
        raise FirmwareError("Manifest source SHA-256 does not match this exact file")
    if manifest.get("requires_hardware_validation") is not True:
        raise FirmwareError("Manifest must explicitly require hardware validation")
    edits = manifest.get("patches")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 128:
        raise FirmwareError("A nonempty, explicitly researched patch list is required")
    original = package.unpack()
    result, used = bytearray(original), []
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("reason"), str) or not edit["reason"].strip():
            raise FirmwareError("Every edit needs a reason")
        try:
            value = edit["offset"]
            offset = int(value, 0) if isinstance(value, str) else value
            if type(offset) is not int:
                raise ValueError("offset must be an integer")
            before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FirmwareError(f"Invalid patch entry: {exc}") from exc
        if not before or len(before) != len(after) or before == after:
            raise FirmwareError("Each edit must change bytes without changing length")
        end = offset + len(before)
        if offset < 0 or end > len(original):
            raise FirmwareError("Patch is outside decompressed payload")
        if any(offset < hi and lo < end for lo, hi in used):
            raise FirmwareError("Overlapping patches refused")
        if package.stock_side and offset <= 0x82B < end:
            raise FirmwareError("Refusing to modify the verified S305 left/right marker")
        if original[offset:end] != before:
            raise FirmwareError(f"Expected bytes do not match at 0x{offset:x}")
        result[offset:end] = after
        used.append((offset, end))
    if package.stock_side:
        result = bytearray(nvkey_integrity.repair_data_edits(original, bytes(result), used))
    return package.rebuild(bytes(result))



def load_package(path: Path) -> Package:
    return Package(read_limited(path), path.name)
