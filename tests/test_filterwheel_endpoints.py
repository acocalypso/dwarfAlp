from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app

def _value(response):
    payload = response.json()
    return payload.get("Value")


def test_filterwheel_unavailable_for_mini_connect():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 400
    assert "not available" in resp.json().get("detail", "").lower()


def test_filterwheel_name_uses_mini_label():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    resp = mini_client.get("/api/v1/filterwheel/0/name")
    assert resp.status_code == 200
    assert _value(resp) == "DWARF mini Filter Wheel"
