# WebSocket protocol

## Connection

The active URL builder emits
`ws://<device>:9900/?client_id=<application-client-id>`. LAN discovery probes
port 9900. Frames are binary protobuf; unexpected text frames are not part of
the observed control protocol. The app uses OkHttp's WebSocket implementation
and reconnects after failed sends.

## Envelope

DWARFLAB 3.4.1 embeds this proto3 descriptor:

```proto
message WsPacket {
  uint32 major_version = 1;
  uint32 minor_version = 2;
  uint32 device_id = 3;
  uint32 module_id = 4;
  uint32 cmd = 5;
  uint32 type = 6;
  bytes data = 7;
  string client_id = 8;
}
```

The application message-type enum and captures use request 0, response 1,
notification 2 and notification-response 3. `data` contains the command
protobuf. Unknown protobuf fields are preserved by the generated runtime when a
message is parsed and reserialized.

Requests are correlated primarily by expected response command, not an
independent sequence number: `WsRequestHandle` keeps a command-keyed list and
applies each request's matcher. dwarfAlp similarly keys pending requests by
module and command and supports explicit alternate response keys.

## Profiles

| Model/profile | Major | Minor | Device ID | Client ID | Confidence |
|---|---:|---:|---:|---|---|
| DWARF 2 legacy | 1 | 2 | 1 | DAF2 Bluetooth-base UUID | repository/vendor history; hardware unverified here |
| DWARF 3 legacy default | 1 | 2 | 1 | DAF3 Bluetooth-base UUID | repository/vendor history; hardware unverified here |
| DWARF Mini V3 | 1 | 20 | 4 | `0000DAF4-0000-1000-8000-00805F9B34FB` | app code and Mini traffic |

“V3” describes a newer command/profile family. It must not be interpreted as
proof that every newer command is Mini-only or absent from DWARF 3.

## Master lock and liveness

The app command registry maps system master mode to 13004. dwarfAlp also
supports the V3 master-lock exchange found in Mini traffic and waits for the
matching lock notification before treating the lock as acquired. WebSocket
control ping/pong is transport-level; the Android `HeartbeatService` observes
global connection state and manages user notifications and delayed service
shutdown. It is not evidence for a protobuf heartbeat command.

## Reconnect and failures

The manager rejects sends while disconnected, supports both text and binary
OkHttp payload objects, and starts reconnect after a failed send. Request
coroutines have command-specific matching and timeouts at their call sites.
Device `ComResponse.code` remains authoritative; dwarfAlp must not treat a
transport acknowledgement as physical completion.

The complete APK command registry and directly linked request wrappers are in
[api-inventory.json](api-inventory.json). A null `command_id` records a JADX
symbolic constant expression rather than guessing its numeric value.
