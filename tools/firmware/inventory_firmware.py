#!/usr/bin/env python3
"""Create a deterministic firmware evidence inventory without modifying inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entropy(path: Path) -> float:
    counts: Counter[int] = Counter()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            counts.update(chunk)
            total += len(chunk)
    if not total:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def file_type(path: Path) -> str:
    try:
        result = subprocess.run(
            ["file", "-b", "--", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown (file utility unavailable)"
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Read-only directory to inventory")
    parser.add_argument("--json", type=Path, help="Optional JSON output path")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown output path")
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
                "entropy": round(entropy(path), 4),
                "type": file_type(path),
            }
        )

    # Keep curated metadata reproducible without publishing an analyst's local
    # username or workstation path.
    document = {"root": root.name, "file_count": len(rows), "artifacts": rows}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "| Artifact | Size | Type | SHA-256 | Entropy |",
            "|---|---:|---|---|---:|",
        ]
        for row in rows:
            kind = str(row["type"]).replace("|", "\\|")
            lines.append(
                f"| `{row['path']}` | {row['size']} | {kind} | `{row['sha256']}` | "
                f"{row['entropy']:.4f} |"
            )
        args.markdown.write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )
    if not args.json and not args.markdown:
        print(json.dumps(document, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
