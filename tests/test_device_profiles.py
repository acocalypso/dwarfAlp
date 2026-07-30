from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.device_profile import get_device_profile
from dwarf_alpaca.dwarf.session import DwarfSession, resolve_ws_client_id


def test_device_protocol_profiles_are_model_specific():
    dwarf2 = get_device_profile("DWARF 2")
    dwarf3 = get_device_profile("DWARF 3")
    mini = get_device_profile("DWARF mini")

    assert (dwarf2.protocol.ws_minor_version, dwarf2.protocol.ws_device_id) == (2, 1)
    assert (dwarf3.protocol.ws_minor_version, dwarf3.protocol.ws_device_id) == (2, 1)
    assert (mini.protocol.ws_minor_version, mini.protocol.ws_device_id) == (20, 4)
    assert dwarf3.protocol.camera_commands == "v2"
    assert mini.protocol.camera_commands == "v3"
    assert dwarf3.ws_client_id != mini.ws_client_id


def test_mini_uses_profile_client_id_unless_explicitly_overridden():
    mini = get_device_profile("dwarfmini")
    automatic = Settings(dwarf_device_model="dwarfmini")
    explicit = Settings(dwarf_device_model="dwarfmini", dwarf_ws_client_id="custom-client")

    assert resolve_ws_client_id(automatic) == mini.ws_client_id
    assert resolve_ws_client_id(explicit) == "custom-client"


def test_dwarf3_session_does_not_select_mini_v3_commands():
    session = DwarfSession(Settings(dwarf_device_model="dwarf3", force_simulation=True))

    assert session.profile.model_id == "dwarf3"
    assert session._is_dwarf_mini() is False
    assert session._ws_client.minor_version == 2
    assert session._ws_client.device_id == 1


def test_capture_capabilities_report_distinct_stop_and_abort():
    for model in ("dwarf2", "dwarf3", "dwarfmini"):
        capture = get_device_profile(model).capture
        assert capture.supports_stop is False
        assert capture.supports_abort is True


def test_mini_camera_limits_match_hardware_reported_astro_presets():
    camera = get_device_profile("dwarfmini").camera

    assert camera.min_exposure_s == 1.0
    assert camera.max_exposure_s == 180.0
    assert camera.min_gain_db == 40.0
    assert camera.max_gain_db == 100.0
    assert camera.max_binning == 1
