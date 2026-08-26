# Hardware platform

| Component | Finding | Confidence |
|---|---|---|
| Application SoC | Rockchip RV1106 family | HIGH |
| Camera sensors | Sony IMX662 and OmniVision OS02K10, 12-bit drivers | VERIFIED |
| Wi-Fi/Bluetooth | Broadcom 43456C5/AP6256-family firmware/NVRAM and BSA BLE | HIGH |
| Storage | `/dev/mmcblk0p10` exFAT media partition | VERIFIED |
| USB | Rockchip VID `0x2207`; mass storage and RNDIS active | VERIFIED |
| IR-cut | GPIO 70, 71, 2, 3 initialization | VERIFIED |
| BLE reset | GPIO 48 | VERIFIED |
| Serial | ttyS1, ttyS3 configured; ttyS4 BLE at 921600 | VERIFIED |
| Motor MCU payload | 45,080-byte near-random/high-entropy payload | VERIFIED; container/architecture UNKNOWN |
| RGB MCU payload | instruction stream begins with repeated 8051-family `LJMP`/bit/SFR patterns | HIGH that target is 8051-compatible |

The kernel modules identify OF compatibles `sony,imx662` and `ovti,os02k10`.
No DTB is included, so CSI lane topology, I²C addresses, memory, clocks, PWM,
regulators, and exact board wiring cannot be reconstructed. No kernel config or
bootloader is present.

`motor.bin` has entropy 7.9767 bits/byte and no stable header or meaningful
strings, consistent with an encrypted/compressed/obfuscated update container;
that interpretation is not distinguishable statically. `rgb.bin` has entropy
6.5526 and code-like 8051 opcodes from offset zero. Neither payload was executed
or disassembled as though its load address were known.
