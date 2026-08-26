# Unresolved protocol elements

- The embedded `base.proto` advertises WebSocket 2.3, while captured working
  device/app traffic uses profile-specific 1.2 or 1.20. Profile values remain
  authoritative until same-firmware packet captures resolve the discrepancy.
- Command 15255 has an APK name but no linked APK protobuf handler. Its current
  elapsed/total interpretation is capture-derived, not descriptor-verified.
- During verified single-frame Mini captures, notification 15209 reported
  `total_count=226` while `current_count` correctly advanced from zero to one.
  The descriptor field name is exact, but the meaning of 226 is not assumed to
  be the requested Alpaca frame count. Completion continues to use
  `current_count` and the explicitly requested frame boundary.
- Firmware-only factory, update, voice-assistant and engineering messages are
  inventoried but intentionally not exposed.
- Command availability may differ by model and firmware even when all current
  DWARF models share the V3 envelope. Registry presence alone is not capability
  proof.
- The meaning/range of preview-quality `level` values is app-path evidence; the
  optional firmware `quality` field is not set because the official wrapper
  omits it.
- IDs present only in legacy DwarfAlp material (notably motor 14001/14003-14005
  and panorama 15502) remain compatibility definitions, not current-firmware
  claims.

Unknown notification IDs and payloads must be logged without payload invention
and must not drive camera, mount or focuser state until independently verified.
