from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "src" / "dwarf_alpaca" / "proto"
IMPORT_RE = re.compile(r"^import ([A-Za-z0-9_]+_pb2) as ", re.MULTILINE)


def _generate(output: Path) -> list[Path]:
    proto_files = sorted(PROTO_DIR.glob("*.proto"))
    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        "-I",
        str(PROTO_DIR),
        f"--python_out={output}",
        *(str(path) for path in proto_files),
    ]
    subprocess.run(command, check=True)
    generated = sorted(output.glob("*_pb2.py"))
    for path in generated:
        content = path.read_text(encoding="utf-8")
        content = IMPORT_RE.sub(r"from . import \1 as ", content)
        path.write_text(content, encoding="utf-8", newline="\n")
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DWARF protobuf Python bindings.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if checked-in bindings are missing or stale.",
    )
    args = parser.parse_args()

    if not args.check:
        generated = _generate(PROTO_DIR)
        print(f"Generated {len(generated)} protobuf modules with grpcio-tools.")
        return 0

    with tempfile.TemporaryDirectory(prefix="dwarf-alpaca-proto-") as temp_name:
        temp_dir = Path(temp_name)
        generated = _generate(temp_dir)
        stale: list[str] = []
        expected_names = {path.name for path in generated}
        tracked_names = {path.name for path in PROTO_DIR.glob("*_pb2.py")}
        for generated_path in generated:
            target = PROTO_DIR / generated_path.name
            if not target.exists() or target.read_bytes() != generated_path.read_bytes():
                stale.append(generated_path.name)
        stale.extend(sorted(tracked_names - expected_names))
        if stale:
            print("Missing or stale protobuf modules: " + ", ".join(sorted(set(stale))))
            return 1
    print(f"All {len(generated)} protobuf modules are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
