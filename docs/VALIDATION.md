# Validation

The reviewed compatibility profile records the exact input identities and the configuration used in the original local test. This is a record of one successful unit, not a universal compatibility claim.

## Firmware

The patch changes 24 bytes in a fixed 27-byte block. Both generated firmware files must reproduce the reviewed SHA-256 outputs. The builder checks the original input hashes, decompressed payload, outer and section digests, section layout, LZMA properties/dictionary, version field, side marker and unchanged NVKEY region. Only the reviewed block changes.

A bounded interpreter executes the actual parameter-validation instructions with default configuration registers. It checks the recorded requests and 1,538 additional cases per variant. This is not full CPU, radio or bootloader emulation.

## Device workflow

On 2026-10-04 the local device run confirmed:

- Transfer and storage integrity on both earbuds.
- Both sides in pending state `0x0311` after the old app's repeat-transfer failure.
- A guarded call to the existing SDK commit API with battery threshold 20.
- Battery and storage integrity checks, CommitRelay and Commit completed.
- Reconnect after reboot, both states `0x0101`, SDK **FOTA Succeed**.
- The owner confirmed successful pairing and audio from both earbuds on the target phone.

The number returned as firmware version is intentionally unchanged. No active-memory dump or post-patch HCI trace was collected. Long-term behavior and other device/OS configurations are untested.

## Public wrapper

The public source renames the earlier locally tested recovery guard/UI and uses a separate application package. File-provider authorities are adjusted for that package. Its build verifies the same FOTA SDK classes and the rebuilt guard, without reflashing the already working device. Build correctness is recorded separately from the earlier hardware success.

The repository's tests use synthetic containers and code-level probes, so they run without downloaded firmware. Real input preparation is an additional local check; downloaded inputs and generated APKs are kept outside the public source tree.
