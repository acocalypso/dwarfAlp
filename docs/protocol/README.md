# DWARF protocol reference

The maintained protocol sources are the `.proto` files under
`src/dwarf_alpaca/proto`. Generated Python bindings are checked in because the
runtime imports them directly. Regenerate and validate with:

```text
uv run python scripts/generate_protos.py
uv run python scripts/generate_protos.py --check
```

Evidence and confidence for reverse-engineered V3 additions are recorded in
[the APK analysis](../apk-analysis/README.md), with the full application
registry in [api-inventory.json](../apk-analysis/api-inventory.json).

Important Mini values:

| Definition | Value | Applicability | Confidence |
|---|---:|---|---|
| WS major/minor | 1/20 | Mini firmware 1.1.3 build 2 | app code and hardware traffic |
| WS device ID | 4 | Mini | app code and hardware traffic |
| Astro / Duo-Band / Dark | 1 / 2 / 3 | newer filter enum; Dark calibration-only | app code, normal filters hardware-confirmed |
| Get/set V3 capture params | 11040 / 11041 | Mini verified; other models unknown | hardware traffic |
| Calibration list | 11043 | registered newer workflow | app code; response unresolved |
| Start/stop calibration capture | 11045 / 11046 | newer/Mini | app code |
| Calibration state/progress | 15290 / 15291 | newer/Mini | app code |

Do not turn a registry entry into a production capability without model and
firmware evidence. Preserve unknown protobuf fields and use placeholder names
when semantics are not established.
