# Complete a pending commit

This path is for firmware that has already transferred and passed storage integrity on **both** earbuds. It is not a workaround for rejected input, failed integrity or an unknown device state.

The observed failure happened after both WriteFlash and CheckIntegrityStorage stages completed. The old SDK started another transfer cycle, the partner returned status `0x41`, and cleanup raised an exception. That response is not interpreted as success. A fresh query showed both sides in state `0x0311`, ready for the SDK's commit flow.

For the same verified situation:

1. Preserve the transfer result. Keep both earbuds outside the case and charged above 20%. Close the app, reopen it and reconnect to your earbuds.
2. Open **TWS FLASH → Request Firmware Information**. This is a fresh device query and also performs the upstream SDK's normal update preparation.
3. Scroll to **PairBridge Commit (checked)**. It is enabled only when the controller, both firmware versions, flash size and both current pending states match the reviewed profile. A version match alone does not establish that the patch is staged.
4. Confirm that the original transfer imported the generated files with matching hashes and completed storage integrity on both sides. Then tap the checked commit once, keeping the battery threshold at 20.
5. Keep the app open while the SDK runs battery checks, storage integrity checks, **CommitRelay**, **Commit**, reconnects and queries the final state. Wait for **FOTA Succeed**.

The guard runs after the query, at the click and immediately before the SDK API. It does not set device states, rewrite responses, skip battery/integrity checks or repeat a payload write. If the checked button is disabled, or either integrity check fails, stop and retain the local result.

A commit response alone is not the final success criterion. The verified successful run included commit on both sides, reconnect after reboot, both states returned to `0x0101`, and the SDK reboot callback. Pairing and audio were then confirmed by the device owner.

If the APK displays a pending-state error that differs from this sequence, collect the minimal local stage information before deciding what to do next. Repeated transfers or forced commits are not part of the documented path.
