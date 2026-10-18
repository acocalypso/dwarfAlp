#!/usr/bin/env python3
"""Download and verify an official DWARFLAB release without contacting a device."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--app-version", default="3.4.3")
    parser.add_argument("--output-dir", type=Path, default=Path("firmware"))
    parser.add_argument("--metadata-dir", type=Path, default=Path("firmware-analysis/metadata/releases"))
    args = parser.parse_args()
    query = urllib.parse.urlencode({
        "deviceId": args.device_id, "firmwareVer": args.version,
        "appOs": 1, "appVer": args.app_version,
    })
    api_url = "https://api-front.dwarflabapp.com/api-front/v1/version/firmware/up-version-ex?" + query
    with urllib.request.urlopen(api_url, timeout=45) as response:
        payload = json.load(response)
    release = payload.get("data")
    if payload.get("code") != 0 or not isinstance(release, dict):
        raise RuntimeError(f"Firmware API rejected request: {payload}")
    if release.get("version") != args.version or release.get("deviceId") != args.device_id:
        raise RuntimeError("API returned a different version or device; refusing to mislabel it")
    filename = release["fileName"]
    if Path(filename).name != filename or not filename.endswith(".zip"):
        raise RuntimeError("Unexpected release filename")
    url = release["link"]
    if urllib.parse.urlparse(url).scheme != "https":
        raise RuntimeError("Expected an HTTPS release URL")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / filename
    candidate = target if target.exists() else target.with_suffix(".zip.part")
    if not target.exists():
        with urllib.request.urlopen(url, timeout=120) as response, candidate.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    data = candidate.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    if len(data) != release["fileSize"] or md5.lower() != release["fileMd5"].lower():
        raise RuntimeError("Downloaded size or MD5 does not match vendor metadata")
    with zipfile.ZipFile(candidate) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failed: {bad}")
        members = [{"path": item.filename, "size": item.file_size} for item in archive.infolist()]
    if candidate != target:
        candidate.replace(target)
    record = {
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "api_url": api_url, "api_response": payload, "artifact": {
            "filename": filename, "size": len(data), "md5": md5,
            "sha256": hashlib.sha256(data).hexdigest(), "zip_crc_verified": True,
            "members": members,
        },
        "scope": "Download and archive verification only; no device update or payload execution.",
    }
    args.metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata = args.metadata_dir / f"{target.stem}.json"
    metadata.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(target), "metadata": str(metadata),
                      **{key: value for key, value in record["artifact"].items() if key != "members"}}))


if __name__ == "__main__":
    main()
