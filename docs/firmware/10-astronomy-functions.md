# Astronomy functions

The firmware contains an integrated astronomy pipeline:

- astrometry.net WCS utilities and a configuration using indexes 4109/4110,
  CPU limit 10, and search depths 10–50;
- plate-solve progress and timing strings in `bilbo`;
- calibration with attempt counters and an azimuth/altitude result;
- target goto, tracking, focus/autofocus, raw live stacking, mosaic, star-trail,
  Sun/Moon, and schedule messages;
- OpenCV processing, PHD-derived star-source clues, RKNN sky segmentation,
  CFITSIO, WCS insertion, and dark-frame calibration.

These components are directly present; their precise algorithmic composition is
only partly inferable from a stripped binary. **VERIFIED components / HIGH flow**

## Modes

| ID | Mode | Techniques present |
|---:|---|---|
| 1 | Normal | single, burst, video, timelapse |
| 2 | DSO | stacking |
| 3 | Sun/Moon parent | stacking, burst, video, timelapse |
| 4 | Milky Way | stacking, timelapse |
| 5 | Star Trail | stacking |
| 8 | Sun | stacking, burst, video, timelapse |
| 9 | Moon | stacking, burst, video, timelapse |
| 10 | Planet | stacking, burst, video, timelapse |

`auto_calibration` defaults true for DSO, Milky Way, Sun, Moon, and Planet in
the supplied parameter configuration. That setting does not prove every model
or firmware performs the same workflow. **VERIFIED for this bundle**
