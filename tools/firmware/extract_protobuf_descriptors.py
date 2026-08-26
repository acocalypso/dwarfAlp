#!/usr/bin/env python3
"""Recover exact embedded protobuf FileDescriptorProto records from an ELF image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from google.protobuf.descriptor_pb2 import FileDescriptorProto, FileDescriptorSet

TYPE_NAMES = {
    1: "double",
    2: "float",
    3: "int64",
    4: "uint64",
    5: "int32",
    6: "fixed64",
    7: "fixed32",
    8: "bool",
    9: "string",
    10: "group",
    11: "message",
    12: "bytes",
    13: "uint32",
    14: "enum",
    15: "sfixed32",
    16: "sfixed64",
    17: "sint32",
    18: "sint64",
}

DEFAULT_NAMES = (
    "astro.proto",
    "base.proto",
    "ble.proto",
    "camera.proto",
    "device.proto",
    "factoryTest.proto",
    "focus.proto",
    "motor_control.proto",
    "notify.proto",
    "panorama.proto",
    "param.proto",
    "shooting_schedule.proto",
    "system.proto",
    "task_center.proto",
    "track.proto",
    "voice_assistant.proto",
)


def find_descriptor(raw: bytes, name: str, max_size: int) -> tuple[int, bytes, FileDescriptorProto]:
    encoded = name.encode("utf-8")
    if len(encoded) >= 128:
        raise ValueError(f"descriptor filename is too long for this extractor: {name}")
    marker = b"\x0a" + bytes([len(encoded)]) + encoded
    offsets = []
    position = 0
    while True:
        position = raw.find(marker, position)
        if position < 0:
            break
        offsets.append(position)
        position += 1

    for offset in offsets:
        for size in range(len(marker), min(max_size, len(raw) - offset) + 1):
            candidate = raw[offset : offset + size]
            descriptor = FileDescriptorProto()
            try:
                descriptor.ParseFromString(candidate)
            except Exception:
                continue
            if (
                descriptor.name == name
                and descriptor.syntax in {"proto2", "proto3"}
                and descriptor.SerializeToString() == candidate
            ):
                return offset, candidate, descriptor
    raise ValueError(f"no exact descriptor found for {name!r}; marker offsets={offsets}")


def message_to_dict(message, prefix: str) -> dict[str, object]:
    full_name = f"{prefix}.{message.name}" if prefix else message.name
    oneofs = [oneof.name for oneof in message.oneof_decl]
    return {
        "name": message.name,
        "full_name": full_name,
        "fields": [
            {
                "name": field.name,
                "number": field.number,
                "label": field.Label.Name(field.label).removeprefix("LABEL_").lower(),
                "type": TYPE_NAMES.get(field.type, f"unknown_{field.type}"),
                "type_name": field.type_name or None,
                "oneof": oneofs[field.oneof_index] if field.HasField("oneof_index") else None,
                "proto3_optional": field.proto3_optional,
            }
            for field in message.field
        ],
        "nested_messages": [message_to_dict(item, full_name) for item in message.nested_type],
        "nested_enums": [enum_to_dict(item, full_name) for item in message.enum_type],
    }


def enum_to_dict(enum, prefix: str) -> dict[str, object]:
    return {
        "name": enum.name,
        "full_name": f"{prefix}.{enum.name}" if prefix else enum.name,
        "values": [{"name": value.name, "number": value.number} for value in enum.value],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument(
        "--name",
        action="append",
        dest="names",
        help="Descriptor filename (repeatable; defaults to all 16 known files)",
    )
    parser.add_argument("--descriptor-set", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--max-size", type=int, default=65536)
    parser.add_argument(
        "--source-label",
        default=None,
        help="Stable source label for metadata (defaults to the binary filename)",
    )
    args = parser.parse_args()

    binary = args.binary.resolve(strict=True)
    raw = binary.read_bytes()
    descriptor_set = FileDescriptorSet()
    records = []
    for name in args.names or DEFAULT_NAMES:
        offset, encoded, descriptor = find_descriptor(raw, name, args.max_size)
        descriptor_set.file.add().CopyFrom(descriptor)
        package = descriptor.package
        records.append(
            {
                "name": descriptor.name,
                "package": package or None,
                "syntax": descriptor.syntax,
                "dependencies": list(descriptor.dependency),
                "offset": offset,
                "offset_hex": f"0x{offset:x}",
                "encoded_size": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "messages": [message_to_dict(item, package) for item in descriptor.message_type],
                "enums": [enum_to_dict(item, package) for item in descriptor.enum_type],
            }
        )

    args.descriptor_set.parent.mkdir(parents=True, exist_ok=True)
    args.descriptor_set.write_bytes(descriptor_set.SerializeToString())
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(
            {
                "source_binary": args.source_label or binary.name,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "descriptors": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
