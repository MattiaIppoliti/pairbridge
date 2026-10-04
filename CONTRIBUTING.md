# Contributing

Run `python3 -m unittest discover -s tests -v` before proposing a change.

Use synthetic fixtures for parsing tests. For an additional compatibility profile, provide exact input identities, a reviewed code change, container/section/NVKEY validation and explicit hardware outcomes. A matching chipset or version string alone is not enough.

Keep source publication separate from downloaded or generated third-party files. Issues should contain a minimal sanitized stage/result summary, not full diagnostics, device addresses, pairing keys, APKs or signing files.

Document whether evidence came from a device response, a build check or an owner report. Preserve the SDK integrity/battery checks and fail on unknown input or state. Use descriptive code-level identifiers; keep the project title neutral.
