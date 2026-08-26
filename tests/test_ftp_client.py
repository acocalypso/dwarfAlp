from datetime import datetime

from dwarf_alpaca.dwarf.ftp_client import DwarfFtpClient, FtpPhotoEntry


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


def test_embedded_capture_timestamp_prefers_frame_time_over_directory_time():
    path = (
        "/Astronomy/DWARF_RAW_TELE_EXP_15_GAIN_60_2026-08-26-12-44-02-379/"
        "15s60_VIS_20260826-124422893_45C.fits"
    )

    timestamp = DwarfFtpClient._embedded_capture_timestamp(path)

    assert timestamp == datetime(2026, 8, 26, 12, 44, 22, 893000).timestamp()


def test_current_capture_rejects_stale_path_when_mdtm_is_fresh():
    requested_at = datetime(2026, 8, 26, 12, 56, 0).timestamp()
    entry = FtpPhotoEntry(
        directory="/Astronomy/old",
        name="stacked-16_15s60_VIS_20260826-124408676.fits",
        timestamp=requested_at + 5,
        path=(
            "/Astronomy/DWARF_RAW_TELE_EXP_15_GAIN_60_2026-08-26-12-44-02-379/"
            "stacked-16_15s60_VIS_20260826-124408676.fits"
        ),
    )

    assert not DwarfFtpClient._is_current_capture(entry, requested_at)


def test_current_capture_accepts_recent_embedded_frame_time():
    requested_at = datetime(2026, 8, 26, 12, 44, 20).timestamp()
    entry = FtpPhotoEntry(
        directory="/Astronomy/new",
        name="15s60_VIS_20260826-124422893_45C.fits",
        timestamp=requested_at,
        path="/Astronomy/new/15s60_VIS_20260826-124422893_45C.fits",
    )

    assert DwarfFtpClient._is_current_capture(entry, requested_at)
