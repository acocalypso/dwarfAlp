# Supported device models

dwarfAlp selects an explicit capability profile; do not use a different model merely
because it connects. All profiles use the V3 `1.20`, device-ID `4` command family,
but retain model-specific client IDs, sensors, filters, and limits.

| Model | Camera profile | Alpaca devices | Physical verification |
| --- | --- | --- | --- |
| DWARF 2 | IMX415, 3840 x 2160 raw profile | Telescope, Camera, Focuser | Not verified against current hardware in this project audit |
| DWARF 3 | IMX678, 3856 x 2180 astronomy FITS | Telescope, Camera, Focuser, FilterWheel | Camera, focuser, filters, slew, and NINA FITS capture |
| DWARF mini | IMX662, 1920 x 1080 | Telescope, Camera, Focuser, FilterWheel | Camera and Astro/HO capture |

The DWARF 3 preview stream can report 1920 x 1080; this is not its astronomy FITS
geometry. DWARF 2 has no built-in filter wheel, so dwarfAlp deliberately does not
advertise one (the DWARFLAB app still lists VIS and Astro for it). The mini exposes
Astro and HO to Alpaca; its internal dark position is reserved for the firmware's
dark-frame workflow.

## Filters, exposures and gain per model

From the DWARFLAB app's astro settings (checked 2026-11-23). The app renamed the
dual-band filter from "Duo-Band" to **HO**. dwarfAlp uses these names and limits;
the exact exposure list comes from the DWARF itself, and an exposure it does not
offer is refused with the list of valid ones. A gain between two steps is rounded to
the nearest step.

| Model | Filters in dwarfAlp | Astro exposures (s) | Gain |
| --- | --- | --- | --- |
| DWARF 2 | none (the app lists VIS, Astro) | 1, 1.3, 1.6, 2, 2.5, 3.2, 4, 5, 6, 8, 10, 13, 15 | 40–240, steps of 10 |
| DWARF 3 | VIS, Astro, HO | 1 … 15, 30, 45, 60, 90, 120 | 40–240, steps of 10 |
| DWARF mini | Astro, HO | 1 … 15, 30, 45, 60, 90, 120, 180 | 40–240, steps of 10 |

Shorter exposures (down to 1/10000 s) exist outside the astro mode.

**Draco Standard and SHO Edition** have no dwarfAlp device profile. The
[Draco research reference](../site/draco.html) records the filters, exposures, and
gain observed in the November app UI alongside the versioned APK evidence and
DWARFLAB specifications. Draco firmware and NINA interoperability remain unverified.

Physical verification is evidence from particular devices and firmware versions,
not a compatibility guarantee. Automated tests exercise every profile using mocks
and simulation.
