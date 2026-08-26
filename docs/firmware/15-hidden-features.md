# Diagnostic, factory, and latent functionality

The recovered `factoryTest.proto` contains roughly 60 message types for MCU
reset, dark/bias/flat capture across cameras, motor backlash, VCM ROM, gyro,
USB mode, PE switches, and level-position tests. Debug/test class names are also
present in `bilbo`. **VERIFIED**

The USB gadget script contains inactive implementations for ADB, MTP, UVC,
NTB, serial, audio, and HID functions. Only RNDIS and mass storage are enabled by
the supplied startup flow. **VERIFIED latent code, not verified capabilities**

Voice-assistant schemas cover status, imaging, astro, sentry, movement, goto,
calibration, focus, tracking, schedules, and panorama. Schedule schemas include
persistence, lock/password, and task states. These are protocol capabilities,
not proof that every UI or model exposes each feature.

Factory, direct-motor, USB-mode, reset, and flashing operations are classified
**Do Not Implement** in DwarfAlp because their safe state requirements and
recovery behavior are not established.
