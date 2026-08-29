from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_ASSET_RE = re.compile(r"(?:src|href)=[\"']([^\"']+)[\"']", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data"}


def _repository_markdown() -> list[Path]:
    command = [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        "*.md",
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return sorted(
        path
        for path in {ROOT / line for line in result.stdout.splitlines() if line}
        if path.exists()
    )


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).lower().strip()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", "-", value)


def _anchors(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for heading in HEADING_RE.findall(text):
        base = _slug(heading)
        duplicate = counts.get(base, 0)
        counts[base] = duplicate + 1
        anchors.add(base if duplicate == 0 else f"{base}-{duplicate}")
    anchors.update(re.findall(r"<a\s+(?:name|id)=[\"']([^\"']+)", text, re.IGNORECASE))
    return anchors


def _target(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        return raw[1 : raw.index(">")]
    return raw.split(maxsplit=1)[0]


def main() -> int:
    failures: list[str] = []
    checked = 0
    anchor_cache: dict[Path, set[str]] = {}
    for source in _repository_markdown():
        text = source.read_text(encoding="utf-8")
        candidates = MARKDOWN_LINK_RE.findall(text) + HTML_ASSET_RE.findall(text)
        for raw in candidates:
            target = _target(raw)
            split = urlsplit(target)
            if split.scheme.lower() in EXTERNAL_SCHEMES or target.startswith("//"):
                continue
            if not split.path and not split.fragment:
                continue
            checked += 1
            destination = source if not split.path else source.parent / unquote(split.path)
            if not destination.exists():
                failures.append(f"{source.relative_to(ROOT)} -> missing {target}")
                continue
            if split.fragment and destination.suffix.lower() == ".md":
                anchors = anchor_cache.setdefault(destination, _anchors(destination))
                if unquote(split.fragment) not in anchors:
                    failures.append(
                        f"{source.relative_to(ROOT)} -> missing anchor #{split.fragment} "
                        f"in {destination.relative_to(ROOT)}"
                    )
    if failures:
        print("Broken local Markdown links:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Checked {checked} local Markdown links and assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
