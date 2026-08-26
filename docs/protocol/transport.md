# WebSocket transport and framing

The control connection is `ws://DEVICE_IP:9900/`. Every binary WebSocket frame
is one serialized `WsPacket`:

| Field | Number | Type | Meaning |
|---|---:|---|---|
| `major_version` | 1 | `uint32` | profile-selected protocol major |
| `minor_version` | 2 | `uint32` | profile-selected protocol minor |
| `device_id` | 3 | `uint32` | profile-selected device family |
| `module_id` | 4 | `uint32` | command namespace |
| `cmd` | 5 | `uint32` | command/notification ID |
| `type` | 6 | `uint32` | request 0, response 1, notification 2, notification-response 3 |
| `data` | 7 | `bytes` | command-specific protobuf payload |
| `client_id` | 8 | `string` | app-compatible client identity |

WebSocket supplies frame length and integrity. The protobuf envelope has no
magic, CRC, length prefix, sequence number or transaction ID.

Responses are correlated by `(module_id, cmd)`. Only one same-key request may
be pending. A command may declare alternate response keys where verified app or
capture behavior completes the operation via a differently numbered event.
Type-2 packets remain asynchronous notifications and are dispatched to state
handlers even when they also satisfy such an alternate response.

Malformed protobuf frames, text frames and unknown notifications do not close
the process. Disconnects fail pending futures; request timeouts remove their
pending key. Session policy decides whether a timeout should close the socket.

