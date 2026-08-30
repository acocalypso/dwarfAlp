# Hardware platform

| Component | Finding | Confidence |
|---|---|---|
| Application SoC | Rockchip RV1106G, board model `RV1106G EVB1 V10` | VERIFIED live DT |
| CPU/RAM | single ARM Cortex-A7-class core; 185,916 KiB RAM; no swap | VERIFIED live |
| Camera sensors | Sony IMX662 and OmniVision OS02K10, 12-bit drivers | VERIFIED |
| Wi-Fi/Bluetooth | Broadcom 43456C5/AP6256-family firmware/NVRAM and BSA BLE | HIGH |
| Storage | ten-partition eMMC; p7 rootfs, p8 oem, p9 userdata, p10 exFAT media | VERIFIED live |
| Boot chain | signed Rockchip FIT with ATF, OP-TEE, U-Boot, kernel/DTB/resource and recovery ramdisk; SHA-256/RSA-2048 metadata | VERIFIED live image |
| USB | Rockchip VID `0x2207`; mass storage and RNDIS active | VERIFIED |
| IR-cut | GPIO 70, 71, 2, 3 initialization | VERIFIED |
| BLE reset | GPIO 48 | VERIFIED |
| Serial | ttyS1, ttyS3 configured; ttyS4 BLE at 921600 | VERIFIED |
| Motor MCU payload | 45,080-byte near-random/high-entropy payload | VERIFIED; container/architecture UNKNOWN |
| RGB MCU payload | instruction stream begins with repeated 8051-family `LJMP`/bit/SFR patterns | HIGH that target is 8051-compatible |

The live device tree confirms `sony,imx662` at I²C address `0x1a` on
`i2c@ff470000` and `ovti,os02k10` at `0x21` on `i2c@ff320000`, with two active
Rockchip ISP virtual pipelines and MIPI CSI blocks. The update ZIP has no DTB,
but the authorized runtime view resolves the sensor/bus attachment. CSI lane
counts, lens/filter mechanics, and exact motor wiring remain unresolved.

`motor.bin` has entropy 7.9767 bits/byte and no stable header or meaningful
strings, consistent with an encrypted/compressed/obfuscated update container;
that interpretation is not distinguishable statically. `rgb.bin` has entropy
6.5526 and code-like 8051 opcodes from offset zero. Neither payload was executed
or disassembled as though its load address were known.
