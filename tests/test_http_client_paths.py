from dwarf_alpaca.dwarf.http_client import DwarfHttpClient


def test_build_jpeg_url_normalizes_sdcard_prefix():
    client = DwarfHttpClient("192.168.88.1")
    url = client.build_jpeg_url("/sdcard/DWARF_II/Normal_Photos/sample.jpeg")
    assert url.startswith("http://192.168.88.1:8092/")
    assert url.endswith("Normal_Photos/sample.jpeg")


def test_build_jpeg_url_allows_plain_filename():
    client = DwarfHttpClient("192.168.88.1")
    url = client.build_jpeg_url("example.jpeg")
    assert url == "http://192.168.88.1:8092/example.jpeg"
