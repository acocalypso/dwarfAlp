from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

COMMAND_RE = re.compile(
    r'public static final WsCmd (?P<name>CMD_[A-Z0-9_]+) = '
    r'new WsCmd\("(?P=name)",\s*(?P<ordinal>\d+),\s*(?P<value>[^;]+)\);'
)
CLASS_RE = re.compile(r"public final class (?P<name>Ws[A-Za-z0-9_]+)")
CMD_REF_RE = re.compile(r"return WsCmd\.(?P<name>CMD_[A-Z0-9_]+);")
MESSAGE_RE = re.compile(r"(?P<name>[A-Za-z0-9_]+Proto\.[A-Za-z0-9_]+)\.newBuilder\(")
RESPONSE_CODE_RE = re.compile(
    r'public static final WsRespCode (?P<name>[A-Z0-9_]+) = '
    r'new WsRespCode\("(?P=name)",\s*(?P<ordinal>\d+),\s*(?P<value>-?\d+)\);'
)

KNOWN_CONSTANT_VALUES = {
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

    commands: dict[str, dict[str, object]] = {}
    for match in COMMAND_RE.finditer(command_text):
        raw_value = match.group("value").strip()
        commands[match.group("name")] = {
            "name": match.group("name"),
            "ordinal": int(match.group("ordinal")),
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

    for request_path in sorted(request_dir.glob("Ws*.java")):
        text = request_path.read_text(encoding="utf-8", errors="replace")
        class_match = CLASS_RE.search(text)
        cmd_match = CMD_REF_RE.search(text)
        if class_match is None or cmd_match is None:
            continue
        command = commands.get(cmd_match.group("name"))
        if command is None:
            continue
        messages = sorted({match.group("name") for match in MESSAGE_RE.finditer(text)})
        wrapper = {
            "class": class_match.group("name"),
            "protobuf_messages": messages,
            "evidence": {
                "source": request_path.relative_to(source_root).as_posix(),
                "line": _line_number(text, cmd_match.start()),
            },
        }
        request_wrappers = command["request_wrappers"]
        assert isinstance(request_wrappers, list)
        request_wrappers.append(wrapper)

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
        "schema_version": 2,
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
        "commands": sorted(commands.values(), key=lambda item: int(item["ordinal"])),
        "response_codes": response_codes,
    }


def render_markdown(inventory: dict[str, object]) -> str:
    commands = inventory["commands"]
    response_codes = inventory["response_codes"]
    assert isinstance(commands, list) and isinstance(response_codes, list)
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
        wrapper_names = ", ".join(wrapper["class"] for wrapper in wrappers) or "—"
        command_id = item.get("command_id")
        display_id = str(command_id) if command_id is not None else f"unresolved: `{item['raw_value_expression']}`"
        lines.append(f"| {display_id} | `{item['name']}` | {item['direction']} | {wrapper_names} |")
    lines.extend([
        "",
        f"## Response and error codes ({len(response_codes)})",
        "",
        "| Code | Name |",
        "|---:|---|",
    ])
    for item in response_codes:
        lines.append(f"| {item['code']} | `{item['name']}` |")
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
        f"{len(inventory['response_codes'])} response codes to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
