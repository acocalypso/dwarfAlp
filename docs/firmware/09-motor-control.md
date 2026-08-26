# Mount, focus, and motor control

The exact `motor_control.proto` descriptor exposes joystick movement, fixed-angle
movement, stop, run, run-to, pulse, position, speed/direction, level calibration,
dual-camera linkage, and device-attitude notifications. Focus has its own schema,
including astronomy autofocus. **VERIFIED**

The `ReqMotorRunTo` payload carries motor id, end position, speed, ramp, and
resolution. These fields are transport facts, not safe operating limits. The
bundle does not establish per-axis ranges, collision limits, homing rules, or
current limits. Direct motor primitives are therefore documented but excluded
from public DwarfAlp features. **VERIFIED / safety limits UNKNOWN**

UART1 and UART3 are configured during startup and are probably associated with
motor controllers; the axis-to-UART mapping is not proven. `motor.bin` has very
high entropy and no reliably identifiable container/architecture, so no MCU
instruction-set claim is made.

Application-level goto is preferable because its request contains RA, Dec,
target name, goto-only, and optional rotation and can retain firmware safety
checks. Calibration yields azimuth/altitude alignment results used by motion.
