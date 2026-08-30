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

## Calibration control flow

Targeted Ghidra analysis of the live Mini's alternate `bilbo_s` service adds
function-level evidence for the equatorial calibration state machine:

1. Attempt plate solving until the configured number of successful solves is
   reached or the remaining attempts can no longer satisfy that requirement.
2. If the first solve cannot start, reinitialize the camera path and retry.
3. For selected solve or motor-limit failures, reverse the sky-search direction,
   move yaw, wait for the motor to stop, pause two seconds, and try again.
4. On success, calculate the calibration result and emit `15256`, followed by
   body/state latch `15262`.
5. Return `-11504` if solving ultimately fails or yaw cannot stop correctly.

The implementation distinguishes first-pass, camera-recovery, and
opposite-direction success. It remembers the last search direction for about
601 seconds to choose the next initial direction. Motor limit codes `-14518`
and `-14519` can therefore be intermediate search outcomes rather than the
terminal calibration result. **HIGH (stripped decompilation)**

Direct DSO goto command `11002` does not perform this calibration. It requires
an existing non-zero solved position and returns `-11511` when calibration is
needed. One-click DSO command `11013` is the combined calibration-plus-goto
workflow and is the appropriate recovery path. **HIGH**
