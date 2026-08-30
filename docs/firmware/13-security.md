# Security architecture

This section describes exposure without publishing secret values or destructive
instructions.

| Area | Observation | Confidence |
|---|---|---|
| Transport | nginx HTTP and FTP are unencrypted | VERIFIED |
| FTP | anonymous/local access and upload/mkdir/other-write are enabled | VERIFIED |
| CORS | nginx static media uses permissive CORS | VERIFIED |
| SSH | `sshd` starts; authentication configuration is absent | VERIFIED / UNKNOWN policy |
| Pairing/control | protobuf contains password-encryption and master-lock concepts | VERIFIED |
| Update trust | `bilbo_upgrade` enforces manifest-provided per-file MD5; no cryptographic outer-bundle verification path has yet been demonstrated | VERIFIED inner integrity / UNKNOWN authentication |
| Cloud activation trust | `bilbo` verifies SHA-256 digests with RSA for activation-service messages | VERIFIED |
| Privilege boundary | startup manipulates GPIO, mounts, configfs, and services; service users are absent | HIGH root-like startup / UNKNOWN runtime UID |

The device assumes a trusted local/AP network more strongly than a modern
zero-trust service would. Owners should avoid exposing device services beyond a
trusted LAN. This is a defensive architectural observation, not evidence of a
remotely exploitable vulnerability.

Credentials, certificates, and public/private key material are redacted even
where their existence is visible. No live device data or user database was read.
