# Network services and IPC

```mermaid
flowchart LR
  App[LAN client] -->|TCP 80 verified| Nginx[nginx static media]
  App -->|TCP 21/default verified| FTP[vsftpd /DWARF_mini]
  App -->|WebSocket, port unresolved statically| Bilbo[bilbo]
  App -->|device HTTP, port unresolved statically| Bilbo
  App -->|JPEG/RTSP, ports unresolved statically| Bilbo
  Host[USB host] -->|RNDIS 10.10.10.1 + mass storage| USB[configfs gadget]
  WiFi[wpa_supplicant] <-->|Unix control socket| Bilbo
  BLE[UART4 BLE] --> Bilbo
  Bilbo -->|UART1/UART3| MCU[controller MCU(s)]
```

| Port/interface | Protocol/process | Reachability | Purpose | Confidence |
|---|---|---|---|---|
| TCP 80 | nginx HTTP | LAN/USB network | `/DWARF_mini` static files, permissive CORS | VERIFIED |
| TCP 21 default | vsftpd | LAN/USB network | media storage access | VERIFIED |
| TCP 22 default | sshd | likely LAN | shell/maintenance | MEDIUM; port config absent |
| TCP 9900 | `bilbo` WebSocket | known from clients/captures | protobuf device commands | HIGH; firmware bind constant unresolved |
| TCP 8082 | `bilbo` HTTP API | known from app/client evidence | album/config/update API | HIGH; firmware bind constant unresolved |
| TCP 8092 | JPEG service | known from app/client evidence | live/stacked images | HIGH; firmware bind constant unresolved |
| TCP 554 default | RTSP service | likely LAN | preview/video stream | MEDIUM |
| USB 10.10.10.1 | RNDIS | attached host only | direct network link | VERIFIED |

The USB script also contains dormant declarations for ADB, MTP, UVC, NTB, ACM,
UAC, and HID. The current startup enables mass storage and RNDIS; presence of
the dormant functions does not prove those interfaces are exposed. **VERIFIED**

No MQTT, D-Bus, ZeroMQ, or explicit application Unix socket was found.
Absence cannot be proven because the full rootfs is unavailable. **UNKNOWN**
