# Capture behavior

dwarfAlp maps Alpaca exposure, gain, binning, filter, and frame-count requests to the
DWARF astronomy workflow, monitors firmware progress, and retrieves the resulting FITS
through FTP or the app-equivalent HTTP album/FITS-list path.

## Before capture

- Connect the camera and model-dependent filter wheel.
- Select only a gain, duration, binning, and filter the profile reports as supported.
- Complete calibration/tracking when the exposure requires it.
- Keep adequate free storage on the telescope.

The driver verifies requested parameters and does not silently claim success after a
configuration failure. Current firmware can reload saved settings while starting a
capture; dwarfAlp follows the active parameter namespace and reapplies the request.

## Darks

Like the official app's **Continue** action, light exposures proceed by default when
a matching dark is absent or outside its temperature tolerance. The condition is
logged. Set `DWARF_ALPACA_ALLOW_CONTINUE_WITHOUT_DARKS=false` to make that condition
fail instead. dwarfAlp does not automatically start a long dark-library procedure.

The mini's internal dark filter is firmware-controlled and is not presented as an
ordinary NINA filter selection.

## Completion and retrieval

An exposure is complete only when firmware progress identifies the requested raw
frames and the matching FITS has been downloaded. Do not request `imagebytes` before
Alpaca `imageready` becomes true. Retrieval can take longer than the nominal exposure,
especially while the telescope finalizes files or the network is slow.

Before a second exposure, dwarfAlp waits for capture state to return to idle/stopped.
This prevents a stale firmware busy state from being mistaken for a new capture.

## Stop, abort, and saturated frames

`CanStopExposure` is false because a distinct graceful-stop operation is unproven.
`CanAbortExposure` is true for the astronomy workflow. A DWARF 3 FITS containing 4095
in every pixel is saturated at the 12-bit sensor ceiling, not an empty image; some
viewers display a constant frame as black. Use low gain and millisecond durations for
indoor/daylight tests.
