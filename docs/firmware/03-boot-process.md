# Boot and service startup

The update manifest installs `S50usbdevice` under `/etc/init.d`, establishing a
SysV/BusyBox-style boot hook. The package does not contain `/etc/inittab` or the
parent rc scripts, so the sequence before that hook is unknown. **VERIFIED**

```mermaid
flowchart TD
  B[Bootloader] -->|not supplied| K[Linux kernel]
  K -->|base rootfs not supplied| I[BusyBox/SysV-style init]
  I --> S[S50usbdevice / run.sh]
  S --> UART[configure UART1/UART3]
  S --> BLE[BLE on UART4 at 921600]
  S --> GPIO[IR-cut GPIO initialization]
  S --> FS[fsck + mount /dev/mmcblk0p10]
  S --> USB[USB mass storage + RNDIS]
  S --> FTP[vsftpd]
  S --> SSH[sshd]
  S --> HTTP[nginx]
  S --> Main[bilbo]
  S --> Upgrade[bilbo_upgrade]
```

`run.sh` mounts the exFAT media partition at `/DWARF_mini`, configures a USB
gadget, and starts the visible services. It initializes IR-cut GPIOs 70, 71, 2,
and 3. BLE uses UART4 and a Broadcom BSA server with GPIO 48 as reset. UART1 and
UART3 are configured; their exact motor assignments are not proven. **VERIFIED**

`bilbo` output is redirected to `/dev/null`; its internal zlog and downloadable
log facilities are therefore more useful than stdout. **VERIFIED**
