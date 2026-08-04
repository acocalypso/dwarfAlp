from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

COMMAND_RE = re.compile(
    r'public static final WsCmd (?P<name>CMD_[A-Z0-9_]+) = '
    r'new WsCmd\("(?P=name)",\s*(?P<ordinal>[^,]+),\s*(?P<value>[^;]+)\);'
)
CLASS_RE = re.compile(r"public (?:final |abstract )?class (?P<name>[A-Za-z0-9_$]+)")
CMD_REF_RE = re.compile(r"WsCmd\.(?P<name>CMD_[A-Z0-9_]+)")
MESSAGE_RE = re.compile(r"(?P<name>[A-Za-z0-9_]+Proto\.[A-Za-z0-9_]+)\.newBuilder\(")
RESPONSE_CLASS_RE = re.compile(
    r"WsRequestHandle\.a\([^;]*?,\s*(?P<name>[A-Za-z0-9_]+Proto\.[A-Za-z0-9_]+)\.class"
)
RESPONSE_CODE_RE = re.compile(
    r'public static final WsRespCode (?P<name>[A-Z0-9_]+) = '
    r'new WsRespCode\("(?P=name)",\s*(?P<ordinal>\d+),\s*(?P<value>-?\d+)\);'
)
HTTP_ANNOTATION_RE = re.compile(
    r'@(?P<method>GET|POST|PUT|DELETE|PATCH)\s*(?:\(\s*"(?P<path>[^"]*)"\s*\))?'
)
HTTP_GENERIC_RE = re.compile(
    r'@HTTP\(hasBody\s*=\s*(?P<has_body>true|false),\s*method\s*=\s*"(?P<method>[A-Z]+)",\s*path\s*=\s*"(?P<path>[^"]+)"\)'
)
HTTP_METHOD_NAME_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
JAVA_FIELD_RE = re.compile(
    r"^\s*private(?:\s+final)?\s+(?P<type>[A-Za-z0-9_<>?,. ]+)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*;",
    re.MULTILINE,
)
UUID_RE = re.compile(r'UUID\.fromString\("(?P<uuid>[0-9A-Fa-f-]+)"\)')
NOTIFICATION_HANDLER_RE = re.compile(
    r"class\s+(?P<class>[A-Za-z0-9_]+)\s+extends\s+[^<{]+<"
    r"(?P<message>[A-Za-z0-9_]+Proto\.[A-Za-z0-9_]+)>\s*\{.*?"
    r"super\(WsCmd\.(?P<cmd>CMD_[A-Z0-9_]+),\s*null\);",
    re.DOTALL,
)

KNOWN_CONSTANT_VALUES = {
    # R8/JADX substituted this unrelated library constant for the literal.
    # The surrounding system-command registry and the existing wire protocol
    # both identify CMD_SYSTEM_SET_TIME as command 13000.
    "ComposeVersion.version": 13000,
    "IMediaPlayer.MEDIA_INFO_VIDEO_DECODED_START": 10004,
    "IMediaPlayer.MEDIA_INFO_FIND_STREAM_INFO": 10006,
    "IMediaPlayer.MEDIA_INFO_VIDEO_SEEK_RENDERING_START": 10008,
    "IMediaPlayer.MEDIA_INFO_AUDIO_SEEK_RENDERING_START": 10009,
    "RequestManager.NOTIFY_CONNECT_SUCCESS": 10011,
    "RequestManager.NOTIFY_CONNECT_FAILED": 10012,
    "RequestManager.NOTIFY_CONNECT_SUSPENDED": 10013,
    "FirebaseError.ERROR_INVALID_CUSTOM_TOKEN": 17000,
    "FirebaseError.ERROR_CUSTOM_TOKEN_MISMATCH": 17002,
}


def _extract_http_endpoints(source_root: Path) -> list[dict[str, object]]:
    api_sources = [
        ("device", "com/convergence/dwarflab/data/http/Api.java"),
        ("cloud", "com/convergence/dwarflab/net/NetApi.java"),
        ("cloud-log-analysis", "com/convergence/dwarflab/net/LogAnalysisApi.java"),
    ]
    endpoints: list[dict[str, object]] = []
    for scope, relative in api_sources:
        path = source_root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        pending: dict[str, object] | None = None
        for line_no, line in enumerate(text.splitlines(), start=1):
            generic = HTTP_GENERIC_RE.search(line)
            annotation = HTTP_ANNOTATION_RE.search(line)
            if generic:
                pending = {
                    "scope": scope,
                    "method": generic.group("method"),
                    "path": generic.group("path"),
                    "has_body": generic.group("has_body") == "true",
                    "evidence": {"source": relative, "line": line_no},
                }
                continue
            if annotation:
                pending = {
                    "scope": scope,
                    "method": annotation.group("method"),
                    "path": annotation.group("path") or "<dynamic-url>",
                    "has_body": annotation.group("method") not in {"GET", "DELETE"},
                    "evidence": {"source": relative, "line": line_no},
                }
                continue
            if pending is None or not line.strip().endswith(");"):
                continue
            method_names = list(HTTP_METHOD_NAME_RE.finditer(line))
            if not method_names:
                continue
            # The Retrofit operation is the first method call in the declaration;
            # annotation argument calls occur on earlier lines.
            pending["operation"] = method_names[0].group("name")
            pending["signature"] = line.strip()
            pending["body_types"] = sorted(
                set(
                    re.findall(
                        r"@Body\s+(?:@\w+\s+)*(?:final\s+)?([A-Za-z0-9_$.<>?]+)",
                        line,
                    )
                )
            )
            pending["multipart"] = "@Part" in line
            endpoints.append(pending)
            pending = None
    return endpoints


def _extract_http_models(source_root: Path) -> list[dict[str, object]]:
    model_dir = source_root / "com/convergence/dwarflab/data/http/request"
    models: list[dict[str, object]] = []
    for path in sorted(model_dir.glob("*.java")):
        text = path.read_text(encoding="utf-8", errors="replace")
        fields = [
            {"name": match.group("name"), "java_type": match.group("type").strip()}
            for match in JAVA_FIELD_RE.finditer(text)
        ]
        if fields:
            models.append(
                {
                    "name": path.stem,
                    "fields": fields,
                    "evidence": path.relative_to(source_root).as_posix(),
                }
            )
    return models


def _extract_ble_registry(source_root: Path) -> dict[str, object]:
    uuid_path = source_root / "defpackage/tn1.java"
    uuid_text = (
        uuid_path.read_text(encoding="utf-8", errors="replace")
        if uuid_path.exists()
        else ""
    )
    uuids = [
        {
            "uuid": match.group("uuid").upper(),
            "evidence": {
                "source": uuid_path.relative_to(source_root).as_posix(),
                "line": _line_number(uuid_text, match.start()),
            },
        }
        for match in UUID_RE.finditer(uuid_text)
    ]
    return {
        "transport": "bluetooth-low-energy",
        "commands": [
            {"id": 1, "request": "ReqGetconfig", "response": "ResGetconfig"},
            {"id": 2, "request": "ReqAp", "response": "ResAp"},
            {"id": 3, "request": "ReqSta", "response": "ResSta"},
            {"id": 4, "request": "ReqSetblewifi", "response": "ResSetblewifi"},
            {"id": 5, "request": "ReqReset", "response": "ResReset"},
            {"id": 6, "request": "ReqGetwifilist", "response": "ResWifilist"},
            {"id": 7, "request": "ReqGetsysteminfo", "response": "ResGetsysteminfo"},
            {"id": 8, "request": "ReqCheckFile", "response": "ResCheckFile"},
        ],
        "uuids": uuids,
        "protobuf_evidence": "com/convergence/dwarflab/proto/BleProto.java",
    }


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def extract_inventory(source_root: Path) -> dict[str, object]:
    """Extract an evidence-preserving command inventory from JADX Java output."""
    command_path = (
        source_root
        / "com"
        / "convergence"
        / "dwarflab"
        / "data"
        / "bean"
        / "ws"
        / "WsCmd.java"
    )
    request_dir = command_path.parent / "request"
    command_text = command_path.read_text(encoding="utf-8", errors="replace")

    response_messages_by_wrapper: dict[str, set[str]] = {}
    response_evidence_by_wrapper: dict[str, list[dict[str, object]]] = {}
    for response_source in sorted(request_dir.glob("*.java")):
        response_text = response_source.read_text(encoding="utf-8", errors="replace")
        response_matches = list(RESPONSE_CLASS_RE.finditer(response_text))
        if not response_matches:
            continue
        wrapper_prefix = response_source.name.split("$", 1)[0]
        if wrapper_prefix.endswith("Kt"):
            wrapper_prefix = wrapper_prefix[:-2]
        response_messages_by_wrapper.setdefault(wrapper_prefix, set()).update(
            match.group("name") for match in response_matches
        )
        evidence = response_evidence_by_wrapper.setdefault(wrapper_prefix, [])
        evidence.extend(
            {
                "source": response_source.relative_to(source_root).as_posix(),
                "line": _line_number(response_text, match.start()),
            }
            for match in response_matches
        )

    commands: dict[str, dict[str, object]] = {}
    for match in COMMAND_RE.finditer(command_text):
        raw_ordinal = match.group("ordinal").strip()
        raw_value = match.group("value").strip()
        commands[match.group("name")] = {
            "name": match.group("name"),
            "ordinal": int(raw_ordinal) if raw_ordinal.isdecimal() else None,
            "raw_ordinal_expression": raw_ordinal,
            "command_id": (
                int(raw_value)
                if raw_value.isdecimal()
                else KNOWN_CONSTANT_VALUES.get(raw_value)
            ),
            "raw_value_expression": raw_value,
            "transport": "websocket",
            "direction": (
                "notification"
                if match.group("name").startswith("CMD_NOTIFY_")
                else "request"
            ),
            "request_wrappers": [],
            "evidence": [
                {
                    "source": command_path.relative_to(source_root).as_posix(),
                    "line": _line_number(command_text, match.start()),
                    "kind": "APK enum declaration",
                }
            ],
            "confidence": "confirmed in app code",
        }

    for request_path in sorted(request_dir.glob("*.java")):
        text = request_path.read_text(encoding="utf-8", errors="replace")
        class_match = CLASS_RE.search(text)
        cmd_matches = list(CMD_REF_RE.finditer(text))
        if class_match is None or not cmd_matches:
            continue
        messages = sorted({match.group("name") for match in MESSAGE_RE.finditer(text)})
        wrapper_name = class_match.group("name")
        responses = set(match.group("name") for match in RESPONSE_CLASS_RE.finditer(text))
        response_evidence: list[dict[str, object]] = []
        for prefix, prefix_responses in response_messages_by_wrapper.items():
            if prefix.startswith(wrapper_name) or wrapper_name.startswith(prefix):
                responses.update(prefix_responses)
                response_evidence.extend(response_evidence_by_wrapper.get(prefix, []))
        wrapper = {
            "class": wrapper_name,
            "protobuf_messages": messages,
            "response_messages": sorted(responses),
            "response_evidence": response_evidence,
            "evidence": {
                "source": request_path.relative_to(source_root).as_posix(),
            },
        }
        for cmd_match in cmd_matches:
            command = commands.get(cmd_match.group("name"))
            if command is None:
                continue
            command_wrapper = {
                **wrapper,
                "evidence": {
                    **wrapper["evidence"],
                    "line": _line_number(text, cmd_match.start()),
                },
            }
            request_wrappers = command["request_wrappers"]
            assert isinstance(request_wrappers, list)
            if command_wrapper not in request_wrappers:
                request_wrappers.append(command_wrapper)

    websocket_dir = source_root / "com/convergence/dwarflab/data/websocket"
    for handler_path in sorted(websocket_dir.rglob("*.java")):
        text = handler_path.read_text(encoding="utf-8", errors="replace")
        for match in NOTIFICATION_HANDLER_RE.finditer(text):
            command = commands.get(match.group("cmd"))
            if command is None:
                continue
            handlers = command.setdefault("notification_handlers", [])
            assert isinstance(handlers, list)
            handler = {
                "class": match.group("class"),
                "protobuf_message": match.group("message"),
                "evidence": {
                    "source": handler_path.relative_to(source_root).as_posix(),
                    "line": _line_number(text, match.start()),
                },
            }
            if handler not in handlers:
                handlers.append(handler)

    response_path = command_path.with_name("WsRespCode.java")
    response_text = response_path.read_text(encoding="utf-8", errors="replace")
    response_codes = [
        {
            "name": match.group("name"),
            "ordinal": int(match.group("ordinal")),
            "code": int(match.group("value")),
            "evidence": {
                "source": response_path.relative_to(source_root).as_posix(),
                "line": _line_number(response_text, match.start()),
            },
            "confidence": "confirmed in app code",
        }
        for match in RESPONSE_CODE_RE.finditer(response_text)
    ]

    return {
        "schema_version": 3,
        "source": {
            "application": "DWARFLAB",
            "package": "com.convergence.dwarflab",
            "version_name": "3.4.1",
            "version_code": 677,
            "apk_sha256": "1E4F676A35EBE6F9D8CB7B3FB4720346C45C41FC41B7E7807151B0080C5DE294",
            "generator": "scripts/extract_apk_api_inventory.py",
        },
        "limitations": [
            "Symbolic third-party constants are resolved only where their library value is known; "
            "raw_value_expression always preserves the JADX evidence.",
            "Presence in WsCmd proves registration in app code, not support on every model.",
            "Only request wrappers with a directly traceable WsCmd return are linked.",
        ],
        "commands": sorted(
            commands.values(),
            key=lambda item: (
                item["ordinal"] is None,
                int(item["ordinal"]) if item["ordinal"] is not None else item["name"],
            ),
        ),
        "response_codes": response_codes,
        "http_endpoints": _extract_http_endpoints(source_root),
        "http_request_models": _extract_http_models(source_root),
        "ble": _extract_ble_registry(source_root),
    }


def render_markdown(inventory: dict[str, object]) -> str:
    commands = inventory["commands"]
    response_codes = inventory["response_codes"]
    http_endpoints = inventory["http_endpoints"]
    ble = inventory["ble"]
    assert isinstance(commands, list) and isinstance(response_codes, list)
    assert isinstance(http_endpoints, list) and isinstance(ble, dict)
    lines = [
        "# DWARFLAB APK 3.4.1 WebSocket code registry",
        "",
        "Generated from the decompiled `WsCmd` and `WsRespCode` registries. Registration in the app does not prove model/firmware support.",
        "",
        f"## Commands ({len(commands)})",
        "",
        "| ID | Name | Direction | Request wrappers |",
        "|---:|---|---|---|",
    ]
    for item in commands:
        wrappers = item.get("request_wrappers", [])
        handler_names = ", ".join(
            f"{handler['class']} ({handler['protobuf_message']})"
            for handler in item.get("notification_handlers", [])
        )
        wrapper_names = ", ".join(wrapper["class"] for wrapper in wrappers)
        mapping_names = "; ".join(part for part in (wrapper_names, handler_names) if part) or "—"
        command_id = item.get("command_id")
        display_id = str(command_id) if command_id is not None else f"unresolved: `{item['raw_value_expression']}`"
        lines.append(f"| {display_id} | `{item['name']}` | {item['direction']} | {mapping_names} |")
    lines.extend([
        "",
        f"## Response and error codes ({len(response_codes)})",
        "",
        "| Code | Name |",
        "|---:|---|",
    ])
    for item in response_codes:
        lines.append(f"| {item['code']} | `{item['name']}` |")
    lines.extend(
        [
            "",
            f"## HTTP operations ({len(http_endpoints)})",
            "",
            "Device-local and DWARFLAB cloud interfaces are separated by scope. Cloud registration is documentation only and is not part of local telescope control.",
            "",
            "| Scope | Method | Path | Operation | Body model |",
            "|---|---|---|---|---|",
        ]
    )
    for item in http_endpoints:
        body_types = ", ".join(item.get("body_types", [])) or "—"
        lines.append(
            f"| {item['scope']} | `{item['method']}` | `{item['path']}` | "
            f"`{item['operation']}` | {body_types} |"
        )
    ble_commands = ble.get("commands", [])
    ble_uuids = ble.get("uuids", [])
    lines.extend(
        [
            "",
            f"## BLE provisioning commands ({len(ble_commands)})",
            "",
            "| ID | Request | Response |",
            "|---:|---|---|",
        ]
    )
    for item in ble_commands:
        lines.append(f"| {item['id']} | `{item['request']}` | `{item['response']}` |")
    lines.extend(["", f"## Registered BLE UUIDs ({len(ble_uuids)})", ""])
    lines.extend(f"- `{item['uuid']}`" for item in ble_uuids)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract DWARFLAB WebSocket commands from JADX Java output."
    )
    parser.add_argument("source_root", type=Path, help="JADX sources directory")
    parser.add_argument("output", type=Path, help="Output JSON path")
    parser.add_argument("--markdown-output", type=Path, help="Optional complete Markdown registry")
    args = parser.parse_args()

    inventory = extract_inventory(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(
            render_markdown(inventory), encoding="utf-8", newline="\n"
        )
    print(
        f"Wrote {len(inventory['commands'])} commands and "
        f"{len(inventory['response_codes'])} response codes, "
        f"{len(inventory['http_endpoints'])} HTTP operations, and "
        f"{len(inventory['ble']['commands'])} BLE commands to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
