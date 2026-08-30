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
    firmware = json.loads(
        (ROOT / "docs/site/firmware-summary.json").read_text(encoding="utf-8")
    )
    firmware_protobuf = json.loads(
        (ROOT / "docs/site/firmware-protobuf.json").read_text(encoding="utf-8")
    )
    alignment = json.loads(
        (ROOT / "docs/site/protocol-alignment-summary.json").read_text(encoding="utf-8")
    )

    assert alpaca["openapi"].startswith("3.")
    assert "/api/v1/camera/0/startexposure" in alpaca["paths"]
    assert device["openapi"] == "3.1.0"
    assert "/album/astro/fitsList" in device["paths"]
    fits_operation = device["paths"]["/album/astro/fitsList"]["post"]
    assert "astroImageDetails.srcDir" in fits_operation["description"]
    assert "AstroFitsResponseData" in json.dumps(fits_operation)
    assert "-11514" in alpaca["paths"]["/api/v1/camera/0/startexposure"]["put"][
        "description"
    ]
    assert "current_count" in alpaca["paths"][
        "/api/v1/camera/0/startexposure"
    ]["put"]["description"]
    assert "NINA's local sky-atlas" in alpaca["paths"][
        "/api/v1/telescope/0/slewtocoordinatesasync"
    ]["put"]["description"]
    index = (ROOT / "docs/site/index.html").read_text(encoding="utf-8")
    assert "Latest integration findings" in index
    assert "CODE_ASTRO_NEED_ADJUST_SHOOT_PARAM" in index
    assert "Raw-frame completion" in index
    assert "Repeated exposures" in index
    assert "Inside the DWARF Linux stack" in index
    assert device["paths"]["/resetDeviceInfo"]["post"]["x-dangerous-operation"]
    assert len(inventory["commands"]) == 356
    assert len(inventory["response_codes"]) == 137
    assert len(inventory["http_endpoints"]) == 50
    assert len(inventory["ble"]["commands"]) == 8
    assert all(item["command_id"] is not None for item in inventory["commands"])
    assert firmware["artifact"]["sha256"] == (
        "fe858626c2b13ef007983fa0171b49b4bb87e05fbd78fdf62fd9693c0809504d"
    )
    assert firmware["extractedFiles"] == 43
    assert firmware["descriptorCount"] == 16
    assert firmware["decompilationFindings"]["servicePorts"] == {
        "websocket": 9900,
        "deviceHttp": 8082,
        "rawJpegHttp": 8085,
        "jpegGuideStream": 8092,
        "rtsp": 554,
        "internalLoopback": 3893,
    }
    assert firmware["decompilationFindings"]["liveMiniValidation"] == {
        "board": "Rockchip RV1106G EVB1 V10",
        "ramKiB": 185_916,
        "partitionCount": 10,
        "teleSensor": "Sony IMX662 at I2C 0x1a",
        "wideSensor": "OmniVision OS02K10 at I2C 0x21",
        "databaseInspection": "schema, row counts, and non-secret runtime parameters",
        "privateRecordValuesPublished": False,
        "systemImageAcquisition": {
            "capturedPartitions": "p1-p9",
            "sourceHashVerifiedPartitions": 7,
            "liveSnapshotPartitions": ["p8-oem", "p9-userdata"],
            "mediaPartitionCaptured": False,
            "bootFormat": "signed Rockchip FIT",
            "fitIntegrityMetadata": "SHA-256/RSA-2048",
        },
    }
    assert firmware["decompilationFindings"]["fitsListMethod"] == "POST"
    assert firmware["decompilationFindings"]["runtimeFindings"] == {
        "parameterLayers": {
            "0": "default/base",
            "1": "saved normal settings",
            "2": "current/runtime",
        },
        "currentModeId": 1_000,
        "focusErrorMinus14511": "StepMotor 3 needs reset",
    }
    assert firmware["decompilationFindings"]["bilboProgramInventory"] == {
        "functions": 13_306,
        "imports": 1_108,
        "definedStrings": 8_544,
        "callEdges": 115_098,
        "memoryBlocks": 32,
    }
    assert firmware_protobuf["source_binary"] == "dwarf_mini_v1.1.3.2/bin/bilbo"
    assert alignment["schemas"]["exactUniquelyNamedMessages"] == 420
    assert alignment["schemas"]["nonExactUniquelyNamedSharedMessages"] == 0
    assert alignment["registry"]["canonicalCorrectCommands"] == 238
    assert alignment["registry"]["matchingResponseCodes"] == 137
    assert alignment["liveValidation"]["exposures"] == 2
    assert alignment["liveValidation"]["notification15288"] == "LongExpPhotoProgress"
