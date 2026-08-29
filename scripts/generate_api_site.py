from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "apk-analysis" / "api-inventory.json"
FIRMWARE_INVENTORY_PATH = ROOT / "firmware-analysis" / "metadata" / "inventory.json"
FIRMWARE_PROTO_PATH = ROOT / "firmware-analysis" / "metadata" / "bilbo-protos.json"
SITE_DIR = ROOT / "docs" / "site"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _dwarfalp_openapi() -> dict[str, Any]:
    app = build_app(
        Settings(
            force_simulation=True,
            discovery_enabled=False,
            dwarf_device_model="dwarf3",
        )
    )
    specification = app.openapi()
    specification["info"].update(
        {
            "title": "DwarfAlp ASCOM Alpaca API",
            "description": (
                "ASCOM Alpaca telescope, camera, focuser and filter-wheel API for "
                "DWARF 2, DWARF 3 and DWARF mini. The API follows Alpaca response "
                "envelopes; device-specific behavior is documented in the companion registry."
            ),
            "license": {"name": "See repository LICENSE", "identifier": "MIT"},
        }
    )
    specification["servers"] = [
        {
            "url": "http://{host}:{port}",
            "description": "Running DwarfAlp server",
            "variables": {
                "host": {"default": "127.0.0.1"},
                "port": {"default": "11111"},
            },
        }
    ]
    specification["x-documentation-evidence"] = {
        "alpaca": "Generated from the FastAPI application routes",
        "deviceProtocol": "Derived from DWARFLAB APK 3.4.1 and hardware captures",
    }
    slew_operation = specification["paths"][
        "/api/v1/telescope/0/slewtocoordinatesasync"
    ]["put"]
    slew_operation["description"] = (
        "Slew to right ascension and declination. ASCOM Alpaca does not define a "
        "target-name parameter for this operation. When NINA's local sky-atlas "
        "database is available, DwarfAlp matches both J2000 and current-epoch "
        "coordinates and sends the resolved catalogue name (for example M11) to "
        "the DWARF instead of Custom."
    )
    slew_operation["x-dwarfalp-target-name-source"] = "NINA/NINA.sqlite coordinate match"
    exposure_operation = specification["paths"][
        "/api/v1/camera/0/startexposure"
    ]["put"]
    exposure_operation["description"] = (
        "Start a DWARF exposure. For V3 astronomy captures, delayed firmware code "
        "-11514 is treated as a nonfatal warning when the device continues shooting. "
        "Progress notification 15209 current_count identifies when the requested raw "
        "frames exist; the driver stops there without waiting for the later stacked_count. "
        "Before a following exposure it waits for capture-state notification 15208 to "
        "report idle/stopped, using the APK-equivalent 16405 device-state query as recovery. "
        "The result is retrieved as FITS through FTP or through the app-equivalent "
        "album mediaType=4, astroImageDetails.srcDir, /album/astro/fitsList sequence."
    )
    return specification


def _schema_for_java_type(java_type: str) -> dict[str, Any]:
    normalized = java_type.replace(" ", "")
    if normalized in {"int", "Integer", "long", "Long"}:
        return {"type": "integer"}
    if normalized in {"float", "Float", "double", "Double"}:
        return {"type": "number"}
    if normalized in {"boolean", "Boolean"}:
        return {"type": "boolean"}
    if normalized == "String":
        return {"type": "string"}
    if normalized.startswith("List<"):
        item_type = normalized[5:-1]
        return {"type": "array", "items": _schema_for_java_type(item_type)}
    return {"type": "object", "x-java-type": java_type}


def _device_openapi(inventory: dict[str, Any]) -> dict[str, Any]:
    schemas: dict[str, Any] = {
        "DeviceResponse": {
            "type": "object",
            "properties": {
                "code": {"type": "integer", "example": 0},
                "message": {"type": "string"},
                "data": {},
            },
            "required": ["code"],
        },
        "AstroFitsInfo": {
            "type": "object",
            "properties": {
                "url": {"type": ["string", "null"]},
                "isFailed": {"type": "boolean"},
                "filePath": {"type": "string"},
            },
            "required": ["isFailed", "filePath"],
            "x-apk-evidence": (
                "com/convergence/dwarflab/data/bean/album/AstroFitsInfo.java"
            ),
        },
        "AstroFitsResponseData": {
            "type": "object",
            "properties": {
                "totalCount": {"type": "integer"},
                "fitsInfo": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/AstroFitsInfo"},
                },
            },
            "required": ["totalCount", "fitsInfo"],
            "x-apk-evidence": (
                "com/convergence/dwarflab/data/http/response/AstroFitsResp.java"
            ),
        },
    }
    for model in inventory["http_request_models"]:
        schemas[model["name"]] = {
            "type": "object",
            "properties": {
                field["name"]: _schema_for_java_type(field["java_type"])
                for field in model["fields"]
            },
            "required": [field["name"] for field in model["fields"]],
            "x-apk-evidence": model["evidence"],
        }

    paths: dict[str, Any] = {}
    for endpoint in inventory["http_endpoints"]:
        if endpoint["scope"] != "device" or endpoint["path"] == "<dynamic-url>":
            continue
        path = "/" + endpoint["path"].lstrip("/")
        method = endpoint["method"].lower()
        operation = {
            "operationId": endpoint["operation"],
            "summary": endpoint["operation"],
            "description": (
                "Registered by the DWARFLAB 3.4.1 device Retrofit interface. "
                "Availability and response fields can vary by model and firmware."
            ),
            "tags": [path.strip("/").split("/", 1)[0] or "device"],
            "responses": {
                "200": {
                    "description": "Device response",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/DeviceResponse"}
                        }
                    },
                }
            },
            "x-apk-evidence": endpoint["evidence"],
            "x-apk-signature": endpoint["signature"],
        }
        dangerous_terms = ("delete", "reset", "activate", "uploadfirmware", "update")
        if any(term in path.lower() for term in dangerous_terms):
            operation["x-dangerous-operation"] = True
        body_types = endpoint.get("body_types", [])
        if endpoint.get("has_body") or body_types:
            body_type = body_types[0] if body_types else ""
            body_schema = (
                {"$ref": f"#/components/schemas/{body_type}"}
                if body_type in schemas
                else {"type": "object", "additionalProperties": True}
            )
            operation["requestBody"] = {
                "required": False,
                "content": {"application/json": {"schema": body_schema}},
            }
        if path == "/update":
            operation["parameters"] = [
                {"name": "version", "in": "query", "required": False, "schema": {"type": "string"}}
            ]
        if path == "/album/astro/fitsList":
            operation["summary"] = "List FITS files for an astronomy capture"
            operation["description"] = (
                "Confirmed DWARFLAB app retrieval step. Read "
                "astroImageDetails.srcDir from a mediaType=4 album entry, POST it "
                "as srcDir, ignore records where isFailed is true, then download "
                "the selected filePath from the device static server on port 80."
            )
            operation["responses"]["200"]["content"]["application/json"]["schema"] = {
                "allOf": [
                    {"$ref": "#/components/schemas/DeviceResponse"},
                    {
                        "type": "object",
                        "properties": {
                            "data": {
                                "$ref": "#/components/schemas/AstroFitsResponseData"
                            }
                        },
                    },
                ]
            }
            operation["x-hardware-status"] = "capture-created FITS confirmed"
        # Retrofit exposes coroutine and Rx overloads for a few operations.
        # Preserve both evidence records without creating invalid duplicate methods.
        existing = paths.setdefault(path, {}).get(method)
        if existing is not None:
            overloads = existing.setdefault("x-apk-overloads", [])
            overloads.append(
                {
                    "operation": endpoint["operation"],
                    "signature": endpoint["signature"],
                    "evidence": endpoint["evidence"],
                }
            )
            continue
        paths[path][method] = operation

    paths["/{filePath}"] = {
        "get": {
            "operationId": "downloadDeviceFile",
            "summary": "Download an album or FITS file",
            "tags": ["files"],
            "servers": [
                {
                    "url": "http://{device}:80",
                    "variables": {"device": {"default": "192.168.88.1"}},
                }
            ],
            "parameters": [
                {
                    "name": "filePath",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "Path returned by an album endpoint, without the leading slash.",
                }
            ],
            "responses": {
                "200": {
                    "description": "FITS, JPEG, PNG or other device media",
                    "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
                }
            },
            "x-confidence": "hardware-observed",
        }
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "DWARFLAB Local Device HTTP API",
            "version": "3.4.1-apk",
            "description": (
                "Unofficial device-local API reconstructed from DWARFLAB 3.4.1. "
                "Destructive firmware, reset and delete operations are documented for "
                "completeness and must not be invoked without explicit authorization."
            ),
        },
        "servers": [
            {
                "url": "http://{device}:8082",
                "variables": {"device": {"default": "192.168.88.1"}},
            }
        ],
        "paths": paths,
        "components": {"schemas": schemas},
    }


def main() -> int:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    alpaca = _dwarfalp_openapi()
    device = _device_openapi(inventory)
    _write_json(SITE_DIR / "openapi.json", alpaca)
    _write_json(SITE_DIR / "device-openapi.json", device)
    _write_json(SITE_DIR / "protocol-inventory.json", inventory)
    if FIRMWARE_INVENTORY_PATH.exists() and FIRMWARE_PROTO_PATH.exists():
        firmware_inventory = json.loads(FIRMWARE_INVENTORY_PATH.read_text(encoding="utf-8"))
        firmware_protos = json.loads(FIRMWARE_PROTO_PATH.read_text(encoding="utf-8"))
        _write_json(SITE_DIR / "firmware-protobuf.json", firmware_protos)
        _write_json(
            SITE_DIR / "firmware-summary.json",
            {
                "artifact": {
                    "name": "dwarf_mini_upgrade_firmware_v1.1.3.2.zip",
                    "size": 13_076_330,
                    "sha256": "fe858626c2b13ef007983fa0171b49b4bb87e05fbd78fdf62fd9693c0809504d",
                    "kind": "application/update ZIP; not a complete root filesystem",
                },
                "extractedFiles": firmware_inventory["file_count"],
                "sourceBinarySha256": firmware_protos["source_sha256"],
                "protobufFiles": [item["name"] for item in firmware_protos["descriptors"]],
                "descriptorCount": len(firmware_protos["descriptors"]),
                "platform": {
                    "architecture": "ARMv7-A, little-endian, hard-float",
                    "libc": "uClibc",
                    "kernelModuleAbi": "Linux 5.10.160",
                    "soc": "Rockchip RV1106 (high confidence)",
                },
            },
        )
    _write_json(
        SITE_DIR / "summary.json",
        {
            "apkVersion": inventory["source"]["version_name"],
            "websocketCommands": len(inventory["commands"]),
            "documentedRequestPayloads": sum(
                bool(item["request_wrappers"]) for item in inventory["commands"]
            ),
            "documentedNotificationPayloads": sum(
                bool(item.get("notification_handlers")) for item in inventory["commands"]
            ),
            "responseCodes": len(inventory["response_codes"]),
            "deviceHttpOperations": sum(
                item["scope"] == "device" for item in inventory["http_endpoints"]
            ),
            "cloudHttpOperations": sum(
                item["scope"] != "device" for item in inventory["http_endpoints"]
            ),
            "bleCommands": len(inventory["ble"]["commands"]),
            "alpacaOperations": sum(len(methods) for methods in alpaca["paths"].values()),
        },
    )
    print(
        f"Generated site data: {len(alpaca['paths'])} Alpaca paths, "
        f"{len(device['paths'])} device HTTP paths, "
        f"{len(inventory['commands'])} WebSocket commands"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
