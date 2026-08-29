# First run

Use simulation first to verify the Control Center and Alpaca client independently of
the telescope. Then switch to the physical device.

## 1. Verify with simulation

1. Start `DwarfAlpacaGUI.exe`.
2. Open **Settings** and enable **Force simulation mode**.
3. Leave the HTTP port at `11111` and select **Start server**.
4. Open <http://127.0.0.1:11111/management/apiversions>. A JSON response confirms
   that the HTTP service is running.
5. Optionally follow the [NINA guide](../user-guide/nina.md) and connect the simulated
   devices.
6. Stop the server before changing to physical hardware.

See [simulation mode](simulation.md) for the equivalent command-line setup.

## 2. Put the DWARF on a reachable network

Choose one network mode:

- **AP mode:** connect the PC directly to the DWARF Wi-Fi network. The usual device
  address is `192.168.88.1`.
- **STA mode:** connect the DWARF and PC to the same home network. Discover/provision
  the unit in the Control Center and use the reported STA address.

The official DWARFLAB app must be closed before dwarfAlp connects because only one
client can hold the device master lock.

## 3. Configure the physical device

1. Disable **Force simulation mode**.
2. Select **DWARF 2**, **DWARF 3**, or **DWARF mini**. The selection controls device
   identity, camera geometry, filters, and the WebSocket client ID.
3. Enter the reachable DWARF IP address.
4. For mount calibration and slewing, enter accurate latitude and longitude in decimal
   degrees. **Fetch current position** is only a public-IP estimate; verify it.
5. Leave **Skip connectivity preflight** disabled for the first connection.
6. Select **Start server** and watch the log panel. A successful preflight acquires
   the master lock and the server begins listening.

Enabling startup calibration preparation performs autofocus after server start, but
the target-based calibration waits for the first NINA slew. The telescope can move;
keep it attended and clear of obstructions.

## 4. Verify NINA and capture

Follow [NINA setup](../user-guide/nina.md), connect each applicable device, and run one
attended test exposure. Confirm that NINA receives an image, not merely that the FITS
file appears on the telescope. Review [capture behavior](../user-guide/capture.md)
before an unattended sequence.

If startup or discovery fails, use the symptom-led
[troubleshooting guide](../user-guide/troubleshooting.md).
