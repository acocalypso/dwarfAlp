from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.device_profile import get_device_profile
from dwarf_alpaca.dwarf.session import DwarfSession, resolve_ws_client_id


def test_all_device_profiles_use_v3_protocol_with_model_specific_client_ids():
    dwarf2 = get_device_profile("DWARF 2")
    dwarf3 = get_device_profile("DWARF 3")
    mini = get_device_profile("DWARF mini")

    for profile in (dwarf2, dwarf3, mini):
        assert profile.protocol.family == "v3"
        assert (profile.protocol.ws_minor_version, profile.protocol.ws_device_id) == (20, 4)
        assert profile.protocol.camera_commands == "v3"
        assert profile.protocol.focus_commands == "v3"

    assert len({dwarf2.ws_client_id, dwarf3.ws_client_id, mini.ws_client_id}) == 3


def test_mini_uses_profile_client_id_unless_explicitly_overridden():
    mini = get_device_profile("dwarfmini")
    automatic = Settings(dwarf_device_model="dwarfmini")
    explicit = Settings(dwarf_device_model="dwarfmini", dwarf_ws_client_id="custom-client")

    assert resolve_ws_client_id(automatic) == mini.ws_client_id
    assert resolve_ws_client_id(explicit) == "custom-client"


def test_dwarf3_session_selects_shared_v3_commands_without_becoming_mini():
    session = DwarfSession(Settings(dwarf_device_model="dwarf3", force_simulation=True))

    assert session.profile.model_id == "dwarf3"
    assert session._is_dwarf_mini() is False
    assert session._uses_v3_protocol() is True
    assert session._ws_client.minor_version == 20
    assert session._ws_client.device_id == 4


def test_dwarf2_keeps_filterwheel_disabled_on_shared_v3_protocol():
    profile = get_device_profile("dwarf2")

    assert profile.protocol.family == "v3"
    assert profile.has_filterwheel is False
    assert profile.filters.labels == ()
    assert profile.filters.firmware_indices == ()


def test_v3_filter_indices_remain_model_specific():
    dwarf3 = get_device_profile("dwarf3")
    mini = get_device_profile("dwarfmini")

    assert dwarf3.filters.firmware_indices == (0, 1, 2)
    assert mini.filters.firmware_indices == (1, 2)
    assert dwarf3.filters.control_path == mini.filters.control_path == "astro-start-ir-index"


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
