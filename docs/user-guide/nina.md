# Connect NINA

Start dwarfAlp before NINA. Both applications must remain running, and the PC firewall
must allow Alpaca HTTP and UDP discovery on the private network.

```text
Start dwarfAlp -> confirm server -> open NINA -> scan Alpaca devices
                -> add equipment -> connect -> run an attended test
```

## Discover the devices

1. In the Control Center, select the correct model and start the server.
2. Confirm that <http://127.0.0.1:11111/management/apiversions> returns JSON.
3. Open NINA and the equipment options for the profile you want to use.
4. Scan for ASCOM Alpaca devices. Select the entries named for your DWARF model and
   server address.
5. If discovery is blocked, add the devices using the Windows PC address and port
   `11111`, not the telescope's own IP. See [troubleshooting](troubleshooting.md).

## Add equipment

Add and connect the devices in this order:

1. **Camera** — choose `<model> Camera` as device number `0`.
2. **Telescope** — choose `<model> Telescope` as device number `0`.
3. **Focuser** — choose `<model> Focuser` as device number `0`.
4. **Filter wheel** — add it for DWARF 3 or DWARF mini only. DWARF 2 correctly
   advertises no filter wheel.

![NINA camera connection](../../images/Setup/4.jpg)

![NINA filter wheel connection](../../images/Setup/5.jpg)

![NINA focuser connection](../../images/Setup/6.jpg)

![NINA telescope connection](../../images/Setup/7.jpg)

Save the NINA equipment profile after every required device connects. Select **No
Guider** unless a separate guider is actually present; dwarfAlp does not expose a
guider.

## First safe test

1. Close the official DWARFLAB app so it cannot retain the master lock.
2. Query the filter list and choose a valid filter where applicable.
3. In daylight, DWARF 2/3 require a millisecond exposure and low gain to avoid a
   constant saturated frame. At night, begin with a short attended astronomy exposure.
4. Wait for NINA to report that the image is ready and display the downloaded FITS.
5. Take a second exposure to verify that capture state returns to idle between frames.

![A captured image in NINA](../../images/Setup/8.png)

## Slewing and calibration

The first uncalibrated deep-sky slew can trigger autofocus, plate-solving calibration,
and then GoTo on the DWARF. Accurate observing coordinates are required. The process
can take several attempts and can move the telescope; keep it attended. Later slews
use ordinary GoTo while calibration remains valid.

NINA's Alpaca coordinate-slew method does not include a target name. When the local
NINA sky-atlas database can be matched, dwarfAlp sends its catalogue name; otherwise
the DWARF receives `Custom` without affecting the coordinates.
