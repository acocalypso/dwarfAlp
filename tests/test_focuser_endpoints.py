from fastapi.testclient import TestClient

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import build_app


client = TestClient(build_app(Settings(force_simulation=True)))


def _value(response):
    payload = response.json()
    return payload.get("Value")


def _connect_focuser():
    resp = client.put("/api/v1/focuser/0/connected", json={"Connected": True})
    assert resp.status_code == 200


def test_focuser_capabilities_and_move():
    _connect_focuser()

    resp = client.get("/api/v1/focuser/0/absolute")
    assert resp.status_code == 200 and _value(resp) is True

    resp = client.get("/api/v1/focuser/0/driverinfo")
    assert resp.status_code == 200 and "focuser" in _value(resp).lower()

    resp = client.get("/api/v1/focuser/0/maxstep")
    assert resp.status_code == 200 and _value(resp) > 0

    resp = client.get("/api/v1/focuser/0/supportedactions")
    assert resp.status_code == 200 and _value(resp) == []

    resp = client.put("/api/v1/focuser/0/move", params={"Position": 150})
    assert resp.status_code == 200

    resp = client.get("/api/v1/focuser/0/position")
    assert resp.status_code == 200 and _value(resp) == 150

    resp = client.put("/api/v1/focuser/0/move", json={"Position": 75})
    assert resp.status_code == 200

    resp = client.get("/api/v1/focuser/0/position")
    assert resp.status_code == 200 and _value(resp) == 75

    resp = client.put("/api/v1/focuser/0/tempcomp", params={"TempComp": False})
    assert resp.status_code == 200

    resp = client.put("/api/v1/focuser/0/isinverted", params={"Inverted": False})
    assert resp.status_code == 200

    resp = client.put("/api/v1/focuser/0/halt")
    assert resp.status_code == 200

    resp = client.get("/api/v1/focuser/0/temperature")
    assert resp.status_code == 200
