from dwarf_alpaca.dwarf.ftp_client import DwarfFtpClient


def test_astro_directory_sort_key_handles_v3_timestamp_formats():
    standard = "DWARF_RAW_TELE_M11_EXP_1_GAIN_60_2026-08-08-21-41-38-905"
    compact = "DWARF_RAW_WIDE_M31_20260713-072542679"
    older = "DWARF_RAW_TELE_M42_EXP_15_GAIN_60_2025-10-13-19-24-18-462"

    assert DwarfFtpClient._astro_directory_sort_key(standard) == 20260808214138905
    assert DwarfFtpClient._astro_directory_sort_key(compact) == 20260713072542679
    assert DwarfFtpClient._astro_directory_sort_key(standard) > (
        DwarfFtpClient._astro_directory_sort_key(older)
    )


def test_astro_directory_sort_key_keeps_unknown_names_last():
    assert DwarfFtpClient._astro_directory_sort_key("CALI_FRAME") == 0
