from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app
from dwarf_alpaca.discovery import build_discovery_payload, DEVICE_LIST


client = TestClient(build_app(Settings(force_simulation=True)))


def _value(response):
    payload = response.json()
    return payload.get("Value")


def test_configured_devices_list_includes_camera_and_focuser():
    resp = client.get("/management/v1/configureddevices")
    assert resp.status_code == 200
    devices = _value(resp)
    assert any(d["DeviceType"] == "Camera" and d["DeviceName"] == "DWARF 3 Camera" for d in devices)
    assert any(d["DeviceType"] == "Focuser" and d["DeviceName"] == "DWARF 3 Focuser" for d in devices)


def test_discovery_payload_contains_all_devices():
    settings = Settings(force_simulation=True)
    payload = build_discovery_payload(settings, advertised_host="127.0.0.1")
    assert payload["DeviceCount"] == len(DEVICE_LIST)
    expected = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in DEVICE_LIST}
    observed = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in payload["Devices"]}
    assert expected == observed


def test_management_device_list_matches_discovery_devices():
    resp = client.get("/management/v1/devicelist")
    assert resp.status_code == 200
    device_list = _value(resp)
    expected = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in DEVICE_LIST}
    observed = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in device_list}
    assert expected == observed
