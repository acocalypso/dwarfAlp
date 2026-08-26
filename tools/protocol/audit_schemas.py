#!/usr/bin/env python3
"""Compare DwarfAlp protobuf schemas with recovered firmware descriptors."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from google.protobuf import descriptor_pb2
from google.protobuf.message import Message
from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[2]
PROTO_DIR = ROOT / "src" / "dwarf_alpaca" / "proto"

TYPE_NAMES = {
    value.number: value.name.removeprefix("TYPE_").lower()
    for value in descriptor_pb2.FieldDescriptorProto.Type.DESCRIPTOR.values
}
LABEL_NAMES = {
    value.number: value.name.removeprefix("LABEL_").lower()
    for value in descriptor_pb2.FieldDescriptorProto.Label.DESCRIPTOR.values
}


def _compile_current_protos() -> descriptor_pb2.FileDescriptorSet:
    with tempfile.TemporaryDirectory(prefix="dwarfalp-schema-audit-") as temp_name:
        output = Path(temp_name) / "current.pb"
        proto_files = sorted(PROTO_DIR.glob("*.proto"))
        result = protoc.main(
            [
                "protoc",
                f"-I{PROTO_DIR}",
                f"--descriptor_set_out={output}",
                "--include_imports",
                *(str(path) for path in proto_files),
            ]
        )
        if result:
            raise RuntimeError(f"grpc_tools.protoc failed with exit code {result}")
        descriptor_set = descriptor_pb2.FileDescriptorSet()
        descriptor_set.ParseFromString(output.read_bytes())
        return descriptor_set


def _load_descriptor_set(path: Path) -> descriptor_pb2.FileDescriptorSet:
    descriptor_set = descriptor_pb2.FileDescriptorSet()
    descriptor_set.ParseFromString(path.read_bytes())
    return descriptor_set


def _load_runtime_facade_descriptor() -> descriptor_pb2.FileDescriptorSet:
    sys.path.insert(0, str(ROOT / "src"))
    try:
        module = importlib.import_module("dwarf_alpaca.proto.dwarf_messages")
        descriptors = {
            value.DESCRIPTOR.file.name: value.DESCRIPTOR.file
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, Message)
            and value.DESCRIPTOR is not None
        }
    finally:
        sys.path.pop(0)
    result = descriptor_pb2.FileDescriptorSet()
    for name in sorted(descriptors):
        file_proto = result.file.add()
        descriptors[name].CopyToProto(file_proto)
    return result


def _field_record(field: descriptor_pb2.FieldDescriptorProto, oneofs: list[str]) -> dict[str, Any]:
    type_name = field.type_name.rsplit(".", 1)[-1] if field.type_name else None
    return {
        "name": field.name,
        "number": field.number,
        "type": TYPE_NAMES[field.type],
        "type_name": type_name,
        "label": LABEL_NAMES[field.label],
        "oneof": oneofs[field.oneof_index] if field.HasField("oneof_index") else None,
        "proto3_optional": field.proto3_optional,
    }


def _index_descriptor_set(descriptor_set: descriptor_pb2.FileDescriptorSet) -> dict[str, Any]:
    messages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    enums: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add_enum(enum: descriptor_pb2.EnumDescriptorProto, file_name: str, prefix: str) -> None:
        full_name = f"{prefix}.{enum.name}" if prefix else enum.name
        enums[enum.name].append(
            {
                "file": file_name,
                "full_name": full_name,
                "values": {value.name: value.number for value in enum.value},
            }
        )

    def add_message(
        message: descriptor_pb2.DescriptorProto, file_name: str, prefix: str
    ) -> None:
        full_name = f"{prefix}.{message.name}" if prefix else message.name
        oneofs = [item.name for item in message.oneof_decl]
        messages[message.name].append(
            {
                "file": file_name,
                "full_name": full_name,
                "fields": [_field_record(field, oneofs) for field in message.field],
            }
        )
        for nested in message.nested_type:
            add_message(nested, file_name, full_name)
        for enum in message.enum_type:
            add_enum(enum, file_name, full_name)

    for file_proto in descriptor_set.file:
        prefix = file_proto.package
        for message in file_proto.message_type:
            add_message(message, file_proto.name, prefix)
        for enum in file_proto.enum_type:
            add_enum(enum, file_proto.name, prefix)
    return {
        "files": sorted(file_proto.name for file_proto in descriptor_set.file),
        "messages": dict(messages),
        "enums": dict(enums),
    }


def _wire_field(field: dict[str, Any]) -> tuple[Any, ...]:
    return field["number"], field["type"], field["type_name"], field["label"]


def _field_by_number(fields: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {field["number"]: field for field in fields}


def _wire_type(field: dict[str, Any]) -> tuple[Any, ...]:
    return field["type"], field["type_name"], field["label"]


def _compare_unique_records(current: dict[str, Any], firmware: dict[str, Any]) -> dict[str, Any]:
    message_comparisons = []
    for name in sorted(set(current["messages"]) | set(firmware["messages"])):
        current_items = current["messages"].get(name, [])
        firmware_items = firmware["messages"].get(name, [])
        record: dict[str, Any] = {
            "name": name,
            "current": current_items,
            "firmware": firmware_items,
        }
        if not current_items:
            record["status"] = "firmware_only"
        elif not firmware_items:
            record["status"] = "current_only"
        elif len(current_items) != 1 or len(firmware_items) != 1:
            record["status"] = "ambiguous"
        else:
            current_fields = current_items[0]["fields"]
            firmware_fields = firmware_items[0]["fields"]
            current_wire = {_wire_field(field) for field in current_fields}
            firmware_wire = {_wire_field(field) for field in firmware_fields}
            current_schema = {
                (*_wire_field(field), field["name"], field["oneof"], field["proto3_optional"])
                for field in current_fields
            }
            firmware_schema = {
                (*_wire_field(field), field["name"], field["oneof"], field["proto3_optional"])
                for field in firmware_fields
            }
            if current_schema == firmware_schema:
                record["status"] = "exact"
            elif current_wire == firmware_wire:
                record["status"] = "wire_match_schema_difference"
            else:
                current_by_number = _field_by_number(current_fields)
                firmware_by_number = _field_by_number(firmware_fields)
                shared_numbers = set(current_by_number) & set(firmware_by_number)
                conflicts = [
                    {
                        "number": number,
                        "current": current_by_number[number],
                        "firmware": firmware_by_number[number],
                    }
                    for number in sorted(shared_numbers)
                    if _wire_type(current_by_number[number])
                    != _wire_type(firmware_by_number[number])
                ]
                if conflicts:
                    record["status"] = "conflicting_field"
                    record["conflicting_fields"] = conflicts
                elif set(current_by_number) < set(firmware_by_number):
                    record["status"] = "current_subset"
                elif set(firmware_by_number) < set(current_by_number):
                    record["status"] = "current_superset"
                else:
                    record["status"] = "different_fields"
                record["current_only_fields"] = [
                    current_by_number[number]
                    for number in sorted(set(current_by_number) - set(firmware_by_number))
                ]
                record["firmware_only_fields"] = [
                    firmware_by_number[number]
                    for number in sorted(set(firmware_by_number) - set(current_by_number))
                ]
        message_comparisons.append(record)

    enum_comparisons = []
    for name in sorted(set(current["enums"]) | set(firmware["enums"])):
        current_items = current["enums"].get(name, [])
        firmware_items = firmware["enums"].get(name, [])
        record = {"name": name, "current": current_items, "firmware": firmware_items}
        if not current_items:
            record["status"] = "firmware_only"
        elif not firmware_items:
            record["status"] = "current_only"
        elif len(current_items) != 1 or len(firmware_items) != 1:
            record["status"] = "ambiguous"
        elif current_items[0]["values"] == firmware_items[0]["values"]:
            record["status"] = "exact"
        else:
            record["status"] = "value_mismatch"
        enum_comparisons.append(record)
    return {"messages": message_comparisons, "enums": enum_comparisons}


def _counts(index: dict[str, Any]) -> dict[str, int]:
    message_records = [item for values in index["messages"].values() for item in values]
    enum_records = [item for values in index["enums"].values() for item in values]
    return {
        "files": len(index["files"]),
        "messages": len(message_records),
        "fields": sum(len(item["fields"]) for item in message_records),
        "enums": len(enum_records),
        "enum_values": sum(len(item["values"]) for item in enum_records),
    }


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record["status"]] += 1
    return dict(sorted(counts.items()))


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Firmware protobuf comparison",
        "",
        "Generated by `tools/protocol/audit_schemas.py`. Matching is by unique message or enum name; ambiguous names are retained rather than guessed.",
        "",
        "## Inventory",
        "",
        "| Surface | Files | Messages | Fields | Enums | Enum values |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("canonical", "runtime_facade", "firmware"):
        counts = report["counts"][name]
        lines.append(
            f"| {name} | {counts['files']} | {counts['messages']} | {counts['fields']} | {counts['enums']} | {counts['enum_values']} |"
        )
    for comparison_name in ("canonical_vs_firmware", "runtime_facade_vs_firmware"):
        comparison = report[comparison_name]
        lines.extend(
            [
                "",
                f"## {comparison_name.replace('_', ' ')}",
                "",
                f"Message results: `{json.dumps(_status_counts(comparison['messages']), sort_keys=True)}`",
                "",
                f"Enum results: `{json.dumps(_status_counts(comparison['enums']), sort_keys=True)}`",
                "",
                "### Non-exact shared messages",
                "",
                "| Message | Current source | Firmware source |",
                "|---|---|---|",
            ]
        )
        mismatches = [
            item
            for item in comparison["messages"]
            if item["status"]
            in {
                "conflicting_field",
                "current_subset",
                "current_superset",
                "different_fields",
            }
        ]
        for item in mismatches:
            current_files = ", ".join(record["file"] for record in item["current"])
            firmware_files = ", ".join(record["file"] for record in item["firmware"])
            lines.append(
                f"| `{item['name']}` ({item['status']}) | `{current_files}` | `{firmware_files}` |"
            )
        if not mismatches:
            lines.append("| _None_ | | |")
        lines.extend(
            [
                "",
                "### Enum value mismatches",
                "",
                "| Enum | Current source | Firmware source |",
                "|---|---|---|",
            ]
        )
        enum_mismatches = [
            item for item in comparison["enums"] if item["status"] == "value_mismatch"
        ]
        for item in enum_mismatches:
            current_files = ", ".join(record["file"] for record in item["current"])
            firmware_files = ", ".join(record["file"] for record in item["firmware"])
            lines.append(f"| `{item['name']}` | `{current_files}` | `{firmware_files}` |")
        if not enum_mismatches:
            lines.append("| _None_ | | |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--firmware",
        type=Path,
        default=ROOT / "firmware-analysis" / "metadata" / "bilbo-protos.pb",
    )
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    canonical = _index_descriptor_set(_compile_current_protos())
    runtime_facade = _index_descriptor_set(_load_runtime_facade_descriptor())
    firmware = _index_descriptor_set(_load_descriptor_set(args.firmware))
    report = {
        "counts": {
            "canonical": _counts(canonical),
            "runtime_facade": _counts(runtime_facade),
            "firmware": _counts(firmware),
        },
        "canonical_vs_firmware": _compare_unique_records(canonical, firmware),
        "runtime_facade_vs_firmware": _compare_unique_records(runtime_facade, firmware),
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(_markdown(report), encoding="utf-8", newline="\n")
    if not args.json and not args.markdown:
        print(json.dumps(report["counts"], indent=2))
        for key in ("canonical_vs_firmware", "runtime_facade_vs_firmware"):
            print(key, _status_counts(report[key]["messages"]), _status_counts(report[key]["enums"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
