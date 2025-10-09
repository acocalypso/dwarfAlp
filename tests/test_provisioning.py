import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.provisioning.workflow import create_state_store, provision_sta
from dwarf_alpaca.provisioning.cli import provision_guide_command


@pytest.mark.asyncio
async def test_provision_sta_saves_wifi_password(tmp_path, monkeypatch):
    settings = Settings(state_directory=tmp_path, ble_password="blepass")

    async def fake_provision(self, ssid, password, *, adapter=None, ble_password=None, timeout=None, device=None):
        from dwarf_alpaca.dwarf.ble_provisioner import ProvisioningResult

        assert ssid == "TestSSID"
        assert password == "supersecret"
        return ProvisioningResult(True, "ok", sta_ip="10.0.0.5")

    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.workflow.DwarfBleProvisioner.provision",
        fake_provision,
        raising=True,
    )

    await provision_sta(
        settings=settings,
        ssid="TestSSID",
        password="supersecret",
        adapter=None,
        ble_password="blepass",
        device_address="AA:BB",
    )

    state_store = create_state_store(tmp_path)
    state = state_store.load()
    assert state.sta_ip == "10.0.0.5"
    assert state.mode == "sta"
    assert state.wifi_credentials.get("TestSSID") == "supersecret"


@pytest.mark.asyncio
async def test_provision_sta_rejects_empty_password(tmp_path, monkeypatch):
    settings = Settings(state_directory=tmp_path, ble_password="blepass")

    called = False

    async def fake_provision(self, ssid, password, *, adapter=None, ble_password=None, timeout=None, device=None):
        nonlocal called
        called = True
        raise AssertionError("Provisioner should not be called when password is empty")

    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.workflow.DwarfBleProvisioner.provision",
        fake_provision,
        raising=True,
    )

    with pytest.raises(RuntimeError, match="Wi-Fi password is required"):
        await provision_sta(
            settings=settings,
            ssid="TestSSID",
            password="",
            adapter=None,
            ble_password="blepass",
            device_address="AA:BB",
        )

    assert called is False

    state_store = create_state_store(tmp_path)
    state = state_store.load()
    assert state.last_error == "Wi-Fi password missing for provisioning"


@pytest.mark.asyncio
async def test_guide_reuses_saved_wifi_password(tmp_path, monkeypatch):
    settings = Settings(state_directory=tmp_path, ble_password="blepass")

    state_store = create_state_store(tmp_path)
    state = state_store.load()
    state.wifi_credentials["MyHome"] = "storedpass"
    state_store.save(state)

    class FakeDevice:
        name = "DWARF3"
        address = "AA:BB"

    async def fake_discover_devices(*, adapter=None, timeout=10.0):
        return [FakeDevice()]

    async def fake_fetch_wifi_list(self, *, device, adapter, ble_password, timeout=None):
        return ["MyHome", "Other"]

    prompts = []

    async def fake_prompt(message: str, *, default: str | None = None, secret: bool = False) -> str:
        prompts.append((message, default, secret))
        if message.startswith("Select device"):
            return "1"
        if message.startswith("Select Wi-Fi network"):
            return "1"
        if message.startswith("Enter Wi-Fi password"):
            return ""  # reuse stored password
        raise AssertionError(f"Unexpected prompt: {message}")

    recorded = {}

    async def fake_provision_sta(*, settings, ssid, password, adapter, ble_password, device_address):
        recorded.update(
            ssid=ssid,
            password=password,
            adapter=adapter,
            ble_password=ble_password,
            device_address=device_address,
        )

    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli.DwarfBleProvisioner.discover_devices",
        staticmethod(fake_discover_devices),
        raising=True,
    )
    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli.DwarfBleProvisioner.fetch_wifi_list",
        fake_fetch_wifi_list,
        raising=True,
    )
    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli._prompt",
        fake_prompt,
        raising=True,
    )
    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli.provision_sta",
        fake_provision_sta,
        raising=True,
    )

    await provision_guide_command(settings=settings, adapter=None, ble_password="blepass")

    assert recorded["ssid"] == "MyHome"
    assert recorded["password"] == "storedpass"
    assert ("Enter Wi-Fi password", None, True) in prompts


@pytest.mark.asyncio
async def test_guide_reprompts_on_empty_password(tmp_path, monkeypatch):
    settings = Settings(state_directory=tmp_path, ble_password="blepass")

    class FakeDevice:
        name = "DWARF3"
        address = "AA:BB"

    async def fake_discover_devices(*, adapter=None, timeout=10.0):
        return [FakeDevice()]

    async def fake_fetch_wifi_list(self, *, device, adapter, ble_password, timeout=None):
        return ["MyHome"]

    responses = iter(["1", "1", "", "newpass"])
    prompts: list[str] = []

    async def fake_prompt(message: str, *, default: str | None = None, secret: bool = False) -> str:
        prompts.append(message)
        try:
            return next(responses)
        except StopIteration:  # pragma: no cover - safety
            raise AssertionError("Unexpected prompt sequence")

    recorded = {}

    async def fake_provision_sta(*, settings, ssid, password, adapter, ble_password, device_address):
        recorded.update(
            ssid=ssid,
            password=password,
            adapter=adapter,
            ble_password=ble_password,
            device_address=device_address,
        )

    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli.DwarfBleProvisioner.discover_devices",
        staticmethod(fake_discover_devices),
        raising=True,
    )
    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli.DwarfBleProvisioner.fetch_wifi_list",
        fake_fetch_wifi_list,
        raising=True,
    )
    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli._prompt",
        fake_prompt,
        raising=True,
    )
    monkeypatch.setattr(
        "dwarf_alpaca.provisioning.cli.provision_sta",
        fake_provision_sta,
        raising=True,
    )

    await provision_guide_command(settings=settings, adapter=None, ble_password="blepass")

    assert recorded["ssid"] == "MyHome"
    assert recorded["password"] == "newpass"
    assert prompts.count("Enter Wi-Fi password") == 2
