# Supported device models

dwarfAlp selects an explicit capability profile; do not use a different model merely
because it connects. All profiles use the V3 `1.20`, device-ID `4` command family,
but retain model-specific client IDs, sensors, filters, and limits.

| Model | Camera profile | Alpaca devices | Physical verification |
| --- | --- | --- | --- |
| DWARF 2 | IMX415, 3840 x 2160 raw profile | Telescope, Camera, Focuser | Not verified against current hardware in this project audit |
| DWARF 3 | IMX678, 3856 x 2180 astronomy FITS | Telescope, Camera, Focuser, FilterWheel | Camera, focuser, filters, slew, and NINA FITS capture |
| DWARF mini | IMX662, 1920 x 1080 | Telescope, Camera, Focuser, FilterWheel | Camera and Astro/Duo-Band capture |

The DWARF 3 preview stream can report 1920 x 1080; this is not its astronomy FITS
geometry. DWARF 2 has no built-in filter wheel, so dwarfAlp deliberately does not
advertise one. The mini exposes Astro and Duo-Band to Alpaca; its internal dark
position is reserved for the firmware's dark-frame workflow.

Physical verification is evidence from particular devices and firmware versions,
not a compatibility guarantee. Automated tests exercise every profile using mocks
and simulation.
