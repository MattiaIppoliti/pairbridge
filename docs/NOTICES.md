# Sources and notices

The MIT license in this repository covers its original code, tests, guard templates and documentation. It does not relicense downloaded device firmware, the upstream Android APK, its SDK, or third-party trademarks.

## Container format

[ramikg/airoha-firmware-parser](https://github.com/ramikg/airoha-firmware-parser) is the format reference. Its published code uses the Unlicense. PairBridge's bounded parser and validation checks were implemented independently and adapted from the locally supplied workbench; its original MIT attribution is retained.

## Archived firmware inputs

[Gostrdr1337/AirFirmwareDL](https://github.com/Gostrdr1337/AirFirmwareDL), pinned to commit `bd4405ed3ed0739075987de37f6d6e0110508f8c`, provides the reviewed archival paths. That repository publishes an MIT license, copyright 2024 Simon. Its archive license does not establish the underlying device vendor's authorship or redistribution permissions. PairBridge obtains these files locally and validates their exact hashes; it publishes no firmware images.

## Upstream Android APK

The reviewed input is the public APK reached through [the community updater link](https://airreps.link/updateapk). Its package, hash, size and SDK identity are specified in `profiles/p1.json`. No application-wide license or original source release was established for that executable, so it is not included in this repository or offered as a binary release. The build adds our UI guard locally; unchanged vendor SDK code remains third-party software.

## Build tools

[Apktool](https://github.com/iBotPeaches/Apktool) performs local decode/rebuild. Java tools provide local signing. PairBridge does not redistribute these tools.

## Rights and publication

The public repository contains original tooling and minimal patch templates. Private diagnostics, Bluetooth addresses or keys, downloaded inputs, generated APKs/firmware, and signing identities are excluded. A publicly downloadable file and an archive hash are not a grant of rights to relicense its vendor code. See [GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) for the distinction between public visibility and an open-source license.
