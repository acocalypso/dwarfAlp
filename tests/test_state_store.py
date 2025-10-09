from dwarf_alpaca.dwarf.state import ConnectivityState, StateStore


def test_state_store_load_missing_wifi_credentials(tmp_path):
    path = tmp_path / "connectivity.json"
    path.write_text('{"sta_ip": "10.0.0.5", "mode": "sta"}', encoding="utf-8")

    store = StateStore(path=path)
    state = store.load()

    assert state.sta_ip == "10.0.0.5"
    assert state.mode == "sta"
    assert state.wifi_credentials == {}


def test_state_store_load_sanitizes_invalid_wifi_entries(tmp_path):
    path = tmp_path / "connectivity.json"
    path.write_text(
        '{"wifi_credentials": {"Home": "", "Cafe": 123, "Valid": "pass"}}',
        encoding="utf-8",
    )

    store = StateStore(path=path)
    state = store.load()

    assert state.wifi_credentials == {"Valid": "pass"}


def test_state_store_save_ignores_empty_wifi_passwords(tmp_path):
    path = tmp_path / "connectivity.json"
    store = StateStore(path=path)
    state = ConnectivityState(
        sta_ip="10.1.1.5",
        mode="sta",
        wifi_credentials={"Valid": "secret", "Empty": ""},
    )

    store.save(state)

    reloaded = store.load()
    assert reloaded.wifi_credentials == {"Valid": "secret"}