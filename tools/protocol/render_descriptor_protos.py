#!/usr/bin/env python3
"""Render reproducible proto3 source files from a FileDescriptorSet."""

from __future__ import annotations

import argparse
from pathlib import Path

from google.protobuf import descriptor_pb2

SCALAR_TYPES = {
    descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE: "double",
    descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT: "float",
    descriptor_pb2.FieldDescriptorProto.TYPE_INT64: "int64",
    descriptor_pb2.FieldDescriptorProto.TYPE_UINT64: "uint64",
    descriptor_pb2.FieldDescriptorProto.TYPE_INT32: "int32",
    descriptor_pb2.FieldDescriptorProto.TYPE_FIXED64: "fixed64",
    descriptor_pb2.FieldDescriptorProto.TYPE_FIXED32: "fixed32",
    descriptor_pb2.FieldDescriptorProto.TYPE_BOOL: "bool",
    descriptor_pb2.FieldDescriptorProto.TYPE_STRING: "string",
    descriptor_pb2.FieldDescriptorProto.TYPE_BYTES: "bytes",
    descriptor_pb2.FieldDescriptorProto.TYPE_UINT32: "uint32",
    descriptor_pb2.FieldDescriptorProto.TYPE_SFIXED32: "sfixed32",
    descriptor_pb2.FieldDescriptorProto.TYPE_SFIXED64: "sfixed64",
    descriptor_pb2.FieldDescriptorProto.TYPE_SINT32: "sint32",
    descriptor_pb2.FieldDescriptorProto.TYPE_SINT64: "sint64",
}


def _indent(lines: list[str], level: int = 1) -> list[str]:
    prefix = "    " * level
    return [prefix + line if line else "" for line in lines]


def _type_name(field: descriptor_pb2.FieldDescriptorProto) -> str:
    if field.type in SCALAR_TYPES:
        return SCALAR_TYPES[field.type]
    return field.type_name.removeprefix(".")


def _render_enum(enum: descriptor_pb2.EnumDescriptorProto) -> list[str]:
    lines = [f"enum {enum.name} {{"]
    if enum.options.allow_alias:
        lines.append("    option allow_alias = true;")
    for value in enum.value:
        lines.append(f"    {value.name} = {value.number};")
    for reserved in enum.reserved_range:
        end = reserved.end - 1
        lines.append(
            f"    reserved {reserved.start};"
            if end == reserved.start
            else f"    reserved {reserved.start} to {end};"
        )
    if enum.reserved_name:
        names = ", ".join(f'"{name}"' for name in enum.reserved_name)
        lines.append(f"    reserved {names};")
    lines.append("}")
    return lines


def _render_field(field: descriptor_pb2.FieldDescriptorProto, *, in_oneof: bool) -> str:
    qualifier = ""
    if not in_oneof:
        if field.proto3_optional:
            qualifier = "optional "
        elif field.label == descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED:
            qualifier = "repeated "
    return f"{qualifier}{_type_name(field)} {field.name} = {field.number};"


def _render_message(message: descriptor_pb2.DescriptorProto) -> list[str]:
    lines = [f"message {message.name} {{"]
    synthetic_oneofs = {
        field.oneof_index
        for field in message.field
        if field.proto3_optional and field.HasField("oneof_index")
    }
    real_oneofs = {
        index for index in range(len(message.oneof_decl)) if index not in synthetic_oneofs
    }
    oneof_fields: dict[int, list[descriptor_pb2.FieldDescriptorProto]] = {
        index: [] for index in real_oneofs
    }

    for enum in message.enum_type:
        lines.extend(_indent(_render_enum(enum)))
        lines.append("")
    for nested in message.nested_type:
        if nested.options.map_entry:
            continue
        lines.extend(_indent(_render_message(nested)))
        lines.append("")

    for reserved in message.reserved_range:
        end = reserved.end - 1
        lines.append(
            f"    reserved {reserved.start};"
            if end == reserved.start
            else f"    reserved {reserved.start} to {end};"
        )
    if message.reserved_name:
        names = ", ".join(f'"{name}"' for name in message.reserved_name)
        lines.append(f"    reserved {names};")

    nested_maps = {
        f".{nested.name}": nested
        for nested in message.nested_type
        if nested.options.map_entry
    }
    nested_maps.update(
        {
            nested.name: nested
            for nested in message.nested_type
            if nested.options.map_entry
        }
    )
    for field in message.field:
        if field.HasField("oneof_index") and field.oneof_index in real_oneofs:
            oneof_fields[field.oneof_index].append(field)
            continue
        map_message = next(
            (
                nested
                for key, nested in nested_maps.items()
                if field.type_name.endswith(key)
            ),
            None,
        )
        if map_message is not None:
            key, value = map_message.field
            lines.append(
                f"    map<{_type_name(key)}, {_type_name(value)}> {field.name} = {field.number};"
            )
        else:
            lines.append("    " + _render_field(field, in_oneof=False))

    for index in sorted(real_oneofs):
        lines.append(f"    oneof {message.oneof_decl[index].name} {{")
        for field in oneof_fields[index]:
            lines.append("        " + _render_field(field, in_oneof=True))
        lines.append("    }")
    while len(lines) > 1 and lines[-1] == "":
        lines.pop()
    lines.append("}")
    return lines


def _render_file(file_proto: descriptor_pb2.FileDescriptorProto) -> str:
    lines = [f'syntax = "{file_proto.syntax or "proto2"}";', ""]
    if file_proto.package:
        lines.extend([f"package {file_proto.package};", ""])
    for dependency in file_proto.dependency:
        lines.append(f'import "{dependency}";')
    if file_proto.dependency:
        lines.append("")
    for enum in file_proto.enum_type:
        lines.extend(_render_enum(enum))
        lines.append("")
    for message in file_proto.message_type:
        lines.extend(_render_message(message))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("descriptor_set", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    descriptor_set.ParseFromString(args.descriptor_set.read_bytes())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for file_proto in descriptor_set.file:
        path = args.output_dir / file_proto.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render_file(file_proto), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
