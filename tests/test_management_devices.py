from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app
from dwarf_alpaca.discovery import build_discovery_payload
from dwarf_alpaca.dwarf.session import configure_session


def _value(response):
    payload = response.json()
    return payload.get("Value")


def test_configured_devices_list_includes_camera_and_focuser():
    client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarf3")))
    resp = client.get("/management/v1/configureddevices")
    assert resp.status_code == 200
    devices = _value(resp)
    assert any(d["DeviceType"] == "Camera" and d["DeviceName"] == "DWARF 3 Camera" for d in devices)
    assert any(d["DeviceType"] == "Focuser" and d["DeviceName"] == "DWARF 3 Focuser" for d in devices)


def test_discovery_payload_contains_all_devices():
    settings = Settings(force_simulation=True, dwarf_device_model="dwarf3")
    payload = build_discovery_payload(settings, advertised_host="127.0.0.1")
    assert payload["DeviceCount"] == len(payload["Devices"])
    expected = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in payload["Devices"]}
    observed = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in payload["Devices"]}
    assert expected == observed


def test_management_device_list_matches_discovery_devices():
    settings = Settings(force_simulation=True, dwarf_device_model="dwarf3")
    client = TestClient(build_app(settings))
    resp = client.get("/management/v1/devicelist")
    assert resp.status_code == 200
    device_list = _value(resp)
    payload = build_discovery_payload(settings, advertised_host="127.0.0.1")
    expected_devices = payload["Devices"]
    expected = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in expected_devices}
    observed = {(
        entry["DeviceType"],
        entry["DeviceNumber"],
        entry["DeviceName"],
        entry["UniqueID"],
    ) for entry in device_list}
    assert expected == observed


def test_management_device_list_includes_filterwheel_for_mini():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    resp = mini_client.get("/management/v1/devicelist")
    assert resp.status_code == 200
    device_list = _value(resp)
    device_types = {entry["DeviceType"] for entry in device_list}
    assert "FilterWheel" in device_types
    assert any("DWARF mini" in entry["DeviceName"] for entry in device_list)

    # Reset shared profile state for other test modules.
    build_app(Settings(force_simulation=True))


def test_management_runtime_endpoint_exposes_v3_state_for_mini():
    settings = Settings(force_simulation=True, dwarf_device_model="dwarfmini")
    configure_session(settings)
    client = TestClient(build_app(settings))

    resp = client.get("/management/v1/runtime")
    assert resp.status_code == 200

    runtime = _value(resp)
    assert runtime["deviceModel"] == "dwarfmini"
    assert runtime["v3"]["is_mini"] is True
    assert runtime["v3"]["ws_minor_version"] == 20
    assert runtime["v3"]["ws_device_id"] == 4
