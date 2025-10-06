from dwarf_alpaca.proto.dwarf_messages import ReqsetMasterLock


def test_master_lock_round_trip():
    message = ReqsetMasterLock()
    message.lock = True

    encoded = message.SerializeToString()

    decoded = ReqsetMasterLock()
    decoded.ParseFromString(encoded)

    assert decoded.lock is True
