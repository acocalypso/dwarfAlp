# Camera and imaging system

| Area | Evidence-backed finding | Confidence |
|---|---|---|
| Sensors | Sony IMX662 and OmniVision OS02K10 12-bit kernel modules and IQ files | VERIFIED |
| Driver modes | 1920×1080 and 1280×720 register sets appear in modules | VERIFIED |
| Still formats | FITS and TIFF stack-format choices; JPEG products and previews | VERIFIED |
| Video | FFmpeg, x264, Rockchip MPP/muxer, RTSP handlers | HIGH |
| RAW processing | `librtprocess`, dark-frame read/check/calibration functions | VERIFIED |
| Camera state | resolution, FOV, temperature and exclusive operation in protobuf | VERIFIED |
| Filters | configuration exposes Astro/Duo-band choices; hardware Dark position is not described by the public setting | HIGH / mapping unresolved |

The default configuration defines exposure as an indexed/special parameter with
index range 0–168. The physical duration lookup is firmware-owned and was not
recovered from this bundle. Gain is defined as 0–120 with default 60. DSO tele
defaults are 15 seconds and gain 60. **VERIFIED**

The imaging pipeline has separate live-stacking, Sun/Moon, maximum/star-trail,
dark-frame calibration, FITS/WCS writing, and stacked-JPEG paths. A captured
FITS should be retrieved through the media volume or album/static-file API; the
WebSocket carries control and progress, not the FITS body. **HIGH**

Configuration comments enumerate `VIS, ASTRO, DUOBAND` while the value list has
only two entries. The Mini also has an internal dark position. The exact numeric
filter-to-position mapping remains unresolved and is not changed here.
