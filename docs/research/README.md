# Protocol and firmware research

This section is for readers investigating DWARFLAB internals and the evidence behind
dwarfAlp. It is deliberately separate from installation and NINA guidance.

## Evidence levels

- **Hardware-observed:** captured from a named model/firmware or confirmed in a live
  test. It may still be version-specific.
- **APK-derived:** registered or used by the analyzed DWARFLAB Android application.
- **Firmware-derived:** present in extracted firmware, descriptors, binaries, or
  configuration.
- **Implemented/tested:** represented in dwarfAlp and exercised by automated tests;
  this does not by itself mean physically certified.
- **Inferred/unresolved:** a conclusion or candidate whose runtime semantics still
  require evidence. Research documents should label it accordingly.

## Navigation

- [Protocol reference](../protocol/README.md) — transport framing, command/schema
  comparisons, response codes, and unresolved protocol elements
- [APK analysis](../apk-analysis/README.md) — Android architecture, complete API
  inventory, reconstructed workflows, transport use, and evidence index
- [Firmware analysis](../firmware/README.md) — platform, boot, services, camera,
  motors, astronomy, security, hardware, and reproducibility
- [Engineering audit](engineering-audit.md) — historical implementation and evidence
  review
- [Integration plan](integration-plan.md) — historical bridge design retained for
  context; current code and architecture take precedence
- [Raw references](references/README.md) — preserved vendor/historical artifacts
- [Generated API Observatory](../site/index.html) — browsable Alpaca, local HTTP,
  WebSocket, BLE, and firmware inventories

## Reproducibility and safety

`scripts/` rebuilds repository inventories/site data. `tools/protocol/` and
`tools/firmware/` contain standalone audit/extraction utilities. Only curated metadata
under `firmware-analysis/metadata/` is tracked; original vendor archives, extracted
filesystems, APKs, decompiler output, and Ghidra projects remain local and ignored.

Some documented device operations can move hardware, delete media, reset state, or
update firmware. Documentation is not authorization to invoke them. Live probes must
remain read-only unless the operator explicitly approves a bounded state change.
