import numpy as np

from dwarf_alpaca.dwarf.session import DwarfSession


def _fits_card(keyword: str, value: str) -> bytes:
    return f"{keyword:<8}= {value:<20}".ljust(80).encode("ascii")


def _fits_end_card() -> bytes:
    return "END".ljust(80).encode("ascii")


def _build_test_fits() -> bytes:
    cards = [
        _fits_card("SIMPLE", "T"),
        _fits_card("BITPIX", "16"),
        _fits_card("NAXIS", "2"),
        _fits_card("NAXIS1", "2"),
        _fits_card("NAXIS2", "2"),
        _fits_card("BSCALE", "1"),
        _fits_card("BZERO", "0"),
        _fits_end_card(),
    ]
    header = b"".join(cards)
    padding = (2880 - (len(header) % 2880)) % 2880
    header += b" " * padding
    pixel_values = np.array([0, 100, 200, 300], dtype=">i2")
    data = pixel_values.tobytes()
    return header + data


def test_decode_fits_basic():
    fits_bytes = _build_test_fits()
    frame = DwarfSession._decode_fits(fits_bytes)
    assert frame.shape == (2, 2)
    assert frame.dtype == np.uint16
    expected = np.array([[0, 100], [200, 300]], dtype=np.uint16)
    np.testing.assert_array_equal(frame, expected)
