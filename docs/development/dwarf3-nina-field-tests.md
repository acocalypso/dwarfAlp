# DWARF 3 + NINA field tests

Record of the environment and results used to validate the DWARF 3 changes on
branch `dwarf3-nina-fixes` (continuous sessions, full-resolution FITS, GOTO from
NINA, Activity log). DWARFLAB publishes no API and changes the protocol between
releases, so results only hold for the versions listed here.

## Test environment

| Component | Version |
| --- | --- |
| DWARF 3 firmware | V1.5.4.1 |
| DWARFLAB app (used for calibration and to check files) | V3.4.5 (build 794) |
| N.I.N.A. | 3.2.0.9001 |
| Plate solver | ASTAP with D50 database |
| Windows | 11 (build 22631), x64 |
| Python (build machine) | 3.14 |
| dwarfAlp | fork `tomansi/dwarfAlp`, branch `dwarf3-nina-fixes` |

Mount mode: alt-az (`AZI_MODE`). NINA connects to dwarfAlp natively over
Alpaca (no ASCOM Platform installed).

Firmware and app updates are on hold until these changes are tested; repeat the
checks below after updating.

## Results

| Date | Test | Result |
| --- | --- | --- |
| 2026-11-13 | Full-resolution capture (3856×2180, ~16 MB FITS) in DSO mode 2 | OK (indoors) |
| 2026-11-13 | Continuous session at 5, 10, 30 and 60 s; ImageBytes transfer | OK (indoors) |
| 2026-11-13 | Delete the DWARF session after download | OK (needs dwarfAlp open 1–2 min after the sequence) |
| 2026-11-15 | Captures under the sky (4 s VIS, 10 s Astro) | OK |
| 2026-11-15 | First GOTO from NINA (NGC 7000, NGC 2281): one-click GOTO, plate solve, tracking | OK in ~20–25 s |
| 2026-11-15 | 10 × 10 s sequence after GOTO (HFR ≈ 1.7, ~450 stars) | OK |
| 2026-11-15 | Second GOTO after a capture session | Fails: DWARF answers -11501 (busy) until power cycled; fix pending test |
| 2026-11-15 (2nd session) | GOTO → sequence → GOTO to another target (M31, then Caldwell 20) with return to live view after each session | OK, no power cycle needed; GOTO in 19–31 s |
| 2026-11-15 (2nd session) | Abort from NINA during a 30 s exposure | OK: session ended, DWARF ready after 31 s |
| 2026-11-15 (2nd session) | In-order delivery, frames left on the DWARF reported | OK (3–8 extra frames while the idle timeout ran) |
| 2026-11-16 | GOTO without autofocus (new default) | OK in ~18 s (was ~40 s with the 20 s autofocus wait) |
| 2026-11-16 | Legacy sequencer, three targets with "Slew to target" (Caldwell 19 → custom → Caldwell 20): session ends on slew, GOTO waits for the close, next sequence starts | OK, 5–7 frames per target; 0–1 extra frames with a 30 s idle timeout |
| 2026-11-16 | Frames saved by NINA after the ASCOM [x, y] fix | OK: 3856×2180, same orientation as the DWARF (before: 2180×3856, transposed) |
| 2026-11-16 | Stop pressed in the middle of a NINA sequence | OK: session ended, the next sequence started normally |
| 2026-11-17 | DWARF 3 in EQ mode (polar aligned in the app): GOTO (Tr 37, M44), tracking, 30 s and 120 s sequences | OK: GOTO in 24–35 s, frames delivered in order, session closes in 51–57 s |
| 2026-11-17 | DWARF 2: connection, model detection and basic moves from NINA | OK; capture and GOTO not tested (clouds) |
| 2026-11-19 | "Prepare calibration after start" (EQ mode) | OK: the DWARF calibrated during the first GOTO (3 plate solves, 42 s); nothing visible because it happens inside the GOTO |
| 2026-11-19 | Second GOTO after dwarfAlp calibrated | Failed: the plain GOTO (11002) was accepted but the DWARF did not move. Fixed: one-click GOTO always |
| 2026-11-19 | StartExposure sent by NINA right after Stop | Failed: the new exposure never started. Fixed |
| 2026-11-19 | Abort slew while the DWARF was closing a session | Failed: 500 error and the aborted GOTO still ran. Fixed |
| 2026-11-19 | Tracking off from NINA | OK: "Tracking stopped by NINA" |
| 2026-11-19 | Sequence M81 → M31 with slews | OK, frames saved in NINA |
| 2026-11-19 (2nd run) | "Prepare calibration after start", GOTO M31 (calibrates, 64 s) → M81 → M31 → M81 with the one-click GOTO fix | OK: every GOTO moved, 23–30 s after the first |
| 2026-11-19 (2nd run) | Slew + Center to M81 | GOTO OK; ASTAP plate solve failed ("Large FOV"): NINA/ASTAP settings to be checked |
| 2026-11-19 (daytime) | Firmware updated to V1.5.5.1 (app unchanged, V3.4.5): connection, NINA camera/mount, GOTO request | OK; the GOTO failed with -11504 (calibration failed), as expected in daylight. Night tests pending |
| 2026-11-20 | NINA test plan (advanced sequencer) on firmware V1.5.5.1, many clouds | GOTO to M31 failed (calibration -11504, clouds). M81: calibration and GOTO OK; frames 15 s OK; tracking off OK; GOTO after tracking off OK; Stop OK |
| 2026-11-20 | 10 s exposures (gain 60 and 90) on V1.5.5.1 | Failed: quick set 11041 answered -3; V1.5.5.1 only accepts its preset pairs (V1.5.4.1 accepted any). Fixed: nearest preset, then live exposure/gain. Slew + Center failed for the same reason |
| 2026-11-20 | 30 s frames after Stop | NINA aborted three times at its 60 s camera timeout (first frame of a session ~90 s). Raise NINA camera timeout to 180 s |
| 2026-11-22 | Test plan 2 (filters, gains), firmware V1.5.5.1 | 10 s gain 60 OK with the preset fallback (also 45 s gain 60); filter changes end the session as expected; 20 s refused with the list of exposures; tracking off and GOTO OK |
| 2026-11-22 | Exposures without a matching dark frame after the first one | Failed: the DWARF did not answer "continue without dark" (11050) and the request stayed pending, so 13 s gain 100, the 10 s plate-solve frame and all 45 s frames never started. Fixed: stale request released |
| 2026-11-22 | NINA Camera Timeout still 60 s | NINA aborted 13 s and 15 s frames at 73–75 s. Set Options → Equipment → Camera → Camera Timeout to 180 s |
| 2026-11-23 | Test plan 2 repeated with the 11050 fix, firmware V1.5.5.1 | OK: Slew and Center (10 s gain 90 plate solve) on M81 twice, VIS 10 s gain 60, Astro 13 s gain 100, Duo-Band 30 s, VIS 15 s gain 130, Astro 45 s, filter changes, 20 s refused, tracking off, GOTO after tracking off. Every exposure started |
| 2026-11-23 | NINA Camera Timeout | Still 60 s: the first frame after a filter change was aborted once or twice at exposure + 60 s before it arrived |
| 2026-11-16 | Slew + Center (NINA plate solve) | First attempt failed and it was slow; aborted. To be retried |
| 2026-11-15 | Astro autofocus before calibration | DWARF acknowledges but never starts it; GOTO now continues without it |
| 2026-11-15 | Folder names created by one-click GOTO (`Caldwell20`, `NGC2281`) | Differ from the app (`C 20`, `NGC 2281`); the app still recognises them |

## Pending checks

- Slew + Center from NINA (repeated GOTOs, no Sync).
