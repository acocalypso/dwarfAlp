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
            "command_id": int(raw_value) if raw_value.isdecimal() else None,
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

    return {
        "schema_version": 1,
        "source": {
            "application": "DWARFLAB",
            "package": "com.convergence.dwarflab",
            "version_name": "3.4.1",
            "version_code": 677,
            "apk_sha256": "1E4F676A35EBE6F9D8CB7B3FB4720346C45C41FC41B7E7807151B0080C5DE294",
            "generator": "scripts/extract_apk_api_inventory.py",
        },
        "limitations": [
            "A null command_id means JADX emitted a symbolic third-party constant; "
            "raw_value_expression preserves the evidence without guessing.",
            "Presence in WsCmd proves registration in app code, not support on every model.",
            "Only request wrappers with a directly traceable WsCmd return are linked.",
        ],
        "commands": sorted(commands.values(), key=lambda item: int(item["ordinal"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract DWARFLAB WebSocket commands from JADX Java output."
    )
    parser.add_argument("source_root", type=Path, help="JADX sources directory")
    parser.add_argument("output", type=Path, help="Output JSON path")
    args = parser.parse_args()

    inventory = extract_inventory(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {len(inventory['commands'])} commands to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
