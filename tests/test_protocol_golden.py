from dwarf_alpaca.proto import (
    astro_pb2,
    base_pb2,
    camera_pb2,
    focus_pb2,
    motor_control_pb2,
    notify_pb2,
    param_pb2,
    protocol_pb2,
    task_center_pb2,
)


def test_task_center_and_preview_requests_match_apk_golden_bytes() -> None:
    assert task_center_pb2.ReqSwitchShootingMode(mode=8).SerializeToString() == bytes.fromhex(
        "0808"
    )
    enter = task_center_pb2.ReqEnterCamera(
        client_param=task_center_pb2.ClientParams(encode_type=1)
    )
    assert enter.SerializeToString() == bytes.fromhex("1a020801")
    assert task_center_pb2.ReqSwitchShootingTech(tech=2).SerializeToString() == bytes.fromhex(
        "0802"
    )
    assert camera_pb2.ReqSetPreviewQuality(level=1).SerializeToString() == bytes.fromhex(
        "0801"
    )


def test_parameter_requests_match_firmware_descriptor_golden_bytes() -> None:
    exposure = param_pb2.ReqSetExposure(
        param_id=0x0201000000000001,
        mode=1,
        value=120,
    )
    assert exposure.SerializeToString() == bytes.fromhex(
        "08818080808080c0800210011878"
    )
    general = param_pb2.ReqSetGeneralIntParam(
        param_id=0x0202000000000010,
        value=2,
    )
    assert general.SerializeToString() == bytes.fromhex("089080808080808081021002")


def test_goto_and_joystick_requests_have_no_legacy_extra_fields() -> None:
    goto = astro_pb2.ReqGotoDSO(
        ra=220.225,
        dec=69.5667,
        target_name="M11",
        goto_only=True,
    )
    assert goto.SerializeToString() == bytes.fromhex(
        "093333333333876b40112aa913d0446451401a034d31312001"
    )
    joystick = motor_control_pb2.ReqMotorServiceJoystick(
        vector_angle=45.0,
        vector_length=0.5,
    )
    assert joystick.SerializeToString() == bytes.fromhex(
        "09000000000080464011000000000000e03f"
    )
    assert {field.number for field in joystick.DESCRIPTOR.fields} == {1, 2}


def test_optional_temperature_presence_and_empty_requests_are_preserved() -> None:
    temperature = notify_pb2.CmosTemperature(temperature=0, camera_type=1)
    assert temperature.HasField("temperature")
    assert temperature.SerializeToString() == bytes.fromhex("08001001")
    assert camera_pb2.ReqPhoto().SerializeToString() == b""
    assert focus_pb2.ReqGetUserInfinityPos().SerializeToString() == b""
    assert astro_pb2.ReqGetQuickSetList(camera_type=0).SerializeToString() == b""


def test_live_long_exposure_progress_payload_decodes_exactly() -> None:
    message = notify_pb2.LongExpPhotoProgress.FromString(
        bytes.fromhex("09000000000000f03f")
    )
    assert message.total_time == 1.0
    assert message.exposured_time == 0.0
    assert message.camera_type == 0


def test_v3_websocket_envelope_matches_captured_profile_shape() -> None:
    enter = task_center_pb2.ReqEnterCamera(
        client_param=task_center_pb2.ClientParams(encode_type=1)
    )
    packet = base_pb2.WsPacket(
        major_version=1,
        minor_version=20,
        device_id=4,
        module_id=14,
        cmd=16404,
        type=0,
        data=enter.SerializeToString(),
        client_id="test",
    )
    assert packet.SerializeToString() == bytes.fromhex(
        "080110141804200e289480013a041a020801420474657374"
    )


def test_correct_command_names_are_primary_with_compatibility_aliases() -> None:
    assert protocol_pb2.CMD_GLOBAL_TASK_MANAGER_SWITCH_SHOOTING_MODE == 16402
    assert protocol_pb2.CMD_GLOBAL_TASK_MANAGER_ENTER_CAMERA == 16404
    assert protocol_pb2.CMD_ASTRO_GET_QUICK_SET_LIST == 11040
    assert protocol_pb2.CMD_FOCUS_GET_USER_INFINITY_POS == 15011
    assert protocol_pb2.CMD_PARAM_SET_EXPOSURE == 16700
    assert protocol_pb2.CMD_NOTIFY_PANORAMA_UPLOAD_COMPLETE == 15245
    assert protocol_pb2.CMD_NOTIFY_LONG_EXP_PROGRESS == 15288
    assert protocol_pb2.DwarfCMD.Name(16404) == "CMD_GLOBAL_TASK_MANAGER_ENTER_CAMERA"


def test_one_click_goto_capture_decodes_exact_firmware_oneof() -> None:
    message = notify_pb2.OneClickGotoState.FromString(
        bytes.fromhex("220a08011206437573746f6d")
    )
    assert message.WhichOneof("current_state") == "astro_tracking_state"
    assert message.astro_tracking_state.state == notify_pb2.OPERATION_STATE_RUNNING
    assert message.astro_tracking_state.target_name == "Custom"
