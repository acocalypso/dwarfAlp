from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.discovery import DEVICE_LIST, build_discovery_payload


def test_discovery_payload_lists_all_devices():
    settings = Settings()
    payload = build_discovery_payload(settings, "192.168.1.100")

    assert payload["DeviceCount"] == len(DEVICE_LIST)
    assert payload["Devices"] == DEVICE_LIST
    assert payload["DeviceList"] == DEVICE_LIST
    assert payload["AlpacaPort"] == settings.http_port

    device_types = {device["DeviceType"] for device in payload["Devices"]}
    assert device_types == {"Telescope", "Camera", "Focuser"}

    assert payload["ServerUrl"] == "http://192.168.1.100:11111"
