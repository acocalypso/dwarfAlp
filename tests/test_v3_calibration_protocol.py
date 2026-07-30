from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.v3_notify_pb2 import (
    V3ResNotifyCaliFrameProgress,
    V3ResNotifyCaliFrameState,
)


def test_calibration_frame_notification_command_ids():
    assert protocol_pb2.CMD_V3_NOTIFY_CALI_FRAME_STATE == 15290
    assert protocol_pb2.CMD_V3_NOTIFY_CALI_FRAME_PROGRESS == 15291


def test_calibration_frame_state_fixture_round_trip():
    # state=running, tele camera, dark calibration type
    payload = bytes.fromhex("080110001800")
    message = V3ResNotifyCaliFrameState.FromString(payload)

    assert message.state == 1
    assert message.camera_type == 0
    assert message.cali_frame_type == 0
    assert message.SerializeToString() == bytes.fromhex("0801")


def test_calibration_frame_progress_fields_round_trip():
    message = V3ResNotifyCaliFrameProgress(
        progress=42,
        camera_type=1,
        cali_frame_type=2,
    )

    decoded = V3ResNotifyCaliFrameProgress.FromString(message.SerializeToString())
    assert (decoded.progress, decoded.camera_type, decoded.cali_frame_type) == (42, 1, 2)
