"""Integrity checks for the observed S305 31.6.305.162 NVKEY layout only.

The additive checksum rule matches all 363 records in both hash-pinned archival
inputs. This module does not identify an iOS fix or prove bootloader acceptance.
"""
from dataclasses import dataclass
import struct


class NVKeyError(ValueError):
    pass


START = 0x14C000
END = 0x157000
PAYLOAD_LENGTH = 2043904


@dataclass(frozen=True)
class Record:
    key: int
    start: int
    data: int
    size: int
    checksum: int


def records(payload: bytes) -> list[Record]:
    if len(payload) != PAYLOAD_LENGTH:
        raise NVKeyError("Unsupported S305 payload length")
    result, keys = [], set()
    for page in range(START, END, 4096):
        limit = page + 4096
        if payload[page] == 0xFF and payload[page:limit] == b"\xff" * 4096:
            continue
        if payload[page] != 0x3F:
            raise NVKeyError(f"Unsupported NVKEY page state at 0x{page:x}")
        cursor = page + 1
        while cursor < limit and payload[cursor] != 0xFF:
            if payload[cursor] != 0x0F or cursor + 5 > limit:
                raise NVKeyError(f"Unsupported NVKEY record at 0x{cursor:x}")
            size, key = struct.unpack_from("<HH", payload, cursor + 1)
            data = (cursor + 8) & ~3
            checksum = data + size
            if not size or checksum >= limit or key in keys:
                raise NVKeyError("Invalid NVKEY length, boundary or duplicate key")
            if payload[cursor + 5:data] != b"\xff" * (data - cursor - 5):
                raise NVKeyError("Unsupported NVKEY alignment padding")
            expected = ((key & 255) + (key >> 8) + sum(payload[data:checksum])) & 255
            if payload[checksum] != expected:
                raise NVKeyError(f"NVKEY 0x{key:04x} additive checksum mismatch")
            result.append(Record(key, cursor, data, size, checksum))
            keys.add(key)
            cursor = checksum + 1
        if payload[cursor:limit] != b"\xff" * (limit - cursor):
            raise NVKeyError("Unsupported trailing NVKEY data")
    if len(result) != 363:
        raise NVKeyError("Unsupported S305 NVKEY record count")
    return result


def repair_data_edits(original: bytes, edited: bytes, edits: list[tuple[int, int]]) -> bytes:
    """Repair checksums after explicit, fixed-length edits inside record data.

Page states, keys, lengths, padding, trailing space and checksum bytes cannot be
edited by a manifest. The caller must first verify the exact archival input hash.
"""
    source_records = records(original)
    if len(edited) != len(original):
        raise NVKeyError("Length-changing NVKEY edits refused")
    for start, end in edits:
        if start < END and START < end:
            if not any(r.data <= start < end <= r.checksum for r in source_records):
                raise NVKeyError("NVKEY edits must stay within one record's data; metadata/checksums refused")
    result = bytearray(edited)
    for r in source_records:
        if original[r.data:r.checksum] != edited[r.data:r.checksum]:
            result[r.checksum] = ((r.key & 255) + (r.key >> 8) + sum(result[r.data:r.checksum])) & 255
    # Parsing the complete section again rejects invalid checksum/structure.
    if records(bytes(result)) != source_records:
        raise NVKeyError("NVKEY record structure changed")
    return bytes(result)


def checksum_changes(original: bytes, edited: bytes) -> list[dict]:
    before, after = records(original), records(edited)
    if before != after:
        raise NVKeyError("NVKEY record structure changed")
    return [{"key": f"0x{r.key:04x}", "offset": r.checksum,
             "before": original[r.checksum], "after": edited[r.checksum],
             "reason": "Automatic additive checksum for an explicitly edited NVKEY data record"}
            for r in before if original[r.checksum] != edited[r.checksum]]
