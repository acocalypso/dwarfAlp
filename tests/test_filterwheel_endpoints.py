from fastapi.testclient import TestClient
import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app
from dwarf_alpaca.devices import filterwheel
from dwarf_alpaca.dwarf.session import DwarfSession

def _value(response):
    payload = response.json()
    return payload.get("Value")


def test_filterwheel_can_connect_for_mini():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 200

    resp = mini_client.get("/api/v1/filterwheel/0/position")
    assert resp.status_code == 200
    assert _value(resp) == 0


def test_filterwheel_name_uses_mini_label():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    resp = mini_client.get("/api/v1/filterwheel/0/name")
    assert resp.status_code == 200
    assert _value(resp) == "DWARF mini Filter Wheel"


def test_filterwheel_names_for_mini_fallback():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 200

    resp = mini_client.get("/api/v1/filterwheel/0/names")
    assert resp.status_code == 200
    names = _value(resp)
    assert isinstance(names, list)
    assert names == ["Duo-Band", "Dark", "No Filter"]


def test_filterwheel_names_remap_legacy_labels_for_mini():
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))
    filterwheel.state.set_names(["VIS Filter", "Astro Filter", "Duo-Band Filter"])

    resp = mini_client.get("/api/v1/filterwheel/0/names")
    assert resp.status_code == 200
    assert _value(resp) == ["No Filter", "Dark", "Duo-Band"]


def test_filterwheel_connect_for_mini_tolerates_initial_timeout(monkeypatch: pytest.MonkeyPatch):
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))

    async def fake_set_filter_position(self, position: int) -> str:  # type: ignore[override]
        raise TimeoutError()

    monkeypatch.setattr(DwarfSession, "set_filter_position", fake_set_filter_position)

    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 200

    resp = mini_client.get("/api/v1/filterwheel/0/position")
    assert resp.status_code == 200
    assert _value(resp) == 0


def test_filterwheel_connect_for_mini_tolerates_pending_runtime(monkeypatch: pytest.MonkeyPatch):
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))

    async def fake_set_filter_position(self, position: int) -> str:  # type: ignore[override]
        raise RuntimeError("Another request for module 15 cmd 16703 is already pending")

    monkeypatch.setattr(DwarfSession, "set_filter_position", fake_set_filter_position)

    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 200

    resp = mini_client.get("/api/v1/filterwheel/0/position")
    assert resp.status_code == 200
    assert _value(resp) == 0


def test_filterwheel_position_falls_back_to_state_when_session_position_unknown(monkeypatch: pytest.MonkeyPatch):
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))

    async def fake_set_filter_position(self, position: int) -> str:  # type: ignore[override]
        raise TimeoutError()

    monkeypatch.setattr(DwarfSession, "set_filter_position", fake_set_filter_position)

    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 200

    # Position should remain readable even when the session position was not updated
    # by a physical filter write.
    resp = mini_client.get("/api/v1/filterwheel/0/position")
    assert resp.status_code == 200
    assert _value(resp) == 0


def test_filterwheel_connect_for_mini_skips_initial_hardware_write(monkeypatch: pytest.MonkeyPatch):
    mini_client = TestClient(build_app(Settings(force_simulation=True, dwarf_device_model="dwarfmini")))

    async def fail_if_called(self, position: int) -> str:  # type: ignore[override]
        raise AssertionError("set_filter_position should not be called during mini connect")

    monkeypatch.setattr(DwarfSession, "set_filter_position", fail_if_called)

    resp = mini_client.put("/api/v1/filterwheel/0/connected", json={"Connected": True})
    assert resp.status_code == 200

    resp = mini_client.get("/api/v1/filterwheel/0/position")
    assert resp.status_code == 200
    assert _value(resp) == 0
