from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_published_openapi_and_protocol_inventory_are_complete() -> None:
    alpaca = json.loads((ROOT / "docs/site/openapi.json").read_text(encoding="utf-8"))
    device = json.loads(
        (ROOT / "docs/site/device-openapi.json").read_text(encoding="utf-8")
    )
    inventory = json.loads(
        (ROOT / "docs/site/protocol-inventory.json").read_text(encoding="utf-8")
    )

    assert alpaca["openapi"].startswith("3.")
    assert "/api/v1/camera/0/startexposure" in alpaca["paths"]
    assert device["openapi"] == "3.1.0"
    assert "/album/astro/fitsList" in device["paths"]
    assert device["paths"]["/resetDeviceInfo"]["post"]["x-dangerous-operation"]
    assert len(inventory["commands"]) == 356
    assert len(inventory["response_codes"]) == 123
    assert len(inventory["http_endpoints"]) == 50
    assert len(inventory["ble"]["commands"]) == 8
    assert all(item["command_id"] is not None for item in inventory["commands"])
