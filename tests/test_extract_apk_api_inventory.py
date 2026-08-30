from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "extract_apk_api_inventory.py"
SPEC = importlib.util.spec_from_file_location("extract_apk_api_inventory", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
extract_inventory = MODULE.extract_inventory


def test_extract_inventory_preserves_numeric_and_symbolic_values(tmp_path: Path):
    source_root = tmp_path / "sources"
    ws_dir = (
        source_root
        / "com"
        / "convergence"
        / "dwarflab"
        / "data"
        / "bean"
        / "ws"
    )
    request_dir = ws_dir / "request"
    request_dir.mkdir(parents=True)
    (ws_dir / "WsCmd.java").write_text(
        "\n".join(
            (
                'public static final WsCmd CMD_NUMERIC = new WsCmd("CMD_NUMERIC", 0, 11005);',
                "public static final WsCmd CMD_SYMBOLIC = "
                'new WsCmd("CMD_SYMBOLIC", Library.ORDINAL, Library.VALUE);',
            )
        ),
        encoding="utf-8",
    )
    (ws_dir / "WsRespCode.java").write_text(
        'public static final WsRespCode CODE_TEST = new WsRespCode("CODE_TEST", 0, -11530);',
        encoding="utf-8",
    )
    (request_dir / "WsNumericReq.java").write_text(
        """
public final class WsNumericReq {
    public WsCmd getCmd() {
        return WsCmd.CMD_NUMERIC;
    }
    public Object getMessage() {
        return AstroProto.ReqCapture.newBuilder().build();
    }
}
""",
        encoding="utf-8",
    )

    inventory = extract_inventory(source_root)

    numeric, symbolic = inventory["commands"]
    assert numeric["command_id"] == 11005
    assert numeric["request_wrappers"][0]["class"] == "WsNumericReq"
    assert numeric["request_wrappers"][0]["protobuf_messages"] == [
        "AstroProto.ReqCapture"
    ]
    assert symbolic["command_id"] is None
    assert symbolic["ordinal"] is None
    assert symbolic["raw_ordinal_expression"] == "Library.ORDINAL"
    assert symbolic["raw_value_expression"] == "Library.VALUE"
    assert inventory["response_codes"][0]["code"] == -11530


def test_extract_inventory_supports_current_jadx_enum_and_package_prefixes(
    tmp_path: Path,
):
    source_root = tmp_path / "sources"
    ws_dir = (
        source_root
        / "com"
        / "convergence"
        / "dwarflab"
        / "data"
        / "bean"
        / "p021ws"
    )
    request_dir = ws_dir / "request"
    request_dir.mkdir(parents=True)
    (ws_dir / "WsCmd.java").write_text(
        "public enum WsCmd {\n    CMD_FIRST(11000),\n    CMD_LAST(16407);\n}\n",
        encoding="utf-8",
    )
    (ws_dir / "WsRespCode.java").write_text(
        "public enum WsRespCode {\n    WS_OK(0),\n    CODE_LAST(-16600);\n}\n",
        encoding="utf-8",
    )

    inventory = extract_inventory(source_root)

    assert [item["command_id"] for item in inventory["commands"]] == [11000, 16407]
    assert [item["ordinal"] for item in inventory["commands"]] == [0, 1]
    assert inventory["commands"][0]["evidence"][0]["source"].endswith(
        "data/bean/ws/WsCmd.java"
    )
    assert [item["code"] for item in inventory["response_codes"]] == [0, -16600]
