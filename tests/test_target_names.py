import sqlite3
from pathlib import Path

from dwarf_alpaca.astronomy.target_names import _precess_j2000, resolve_nina_target_name


def _make_catalog(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE dsodetail (id TEXT, ra REAL, dec REAL)")
    connection.execute(
        "CREATE TABLE cataloguenr (dsodetailid TEXT, catalogue TEXT, designation TEXT)"
    )
    connection.execute("INSERT INTO dsodetail VALUES ('NGC6705', 282.77083333, -6.27)")
    connection.execute("INSERT INTO cataloguenr VALUES ('NGC6705', 'NGC', '6705')")
    connection.execute("INSERT INTO cataloguenr VALUES ('NGC6705', 'M', '11')")
    connection.commit()
    connection.close()


def test_resolves_m11_from_current_epoch_coordinates(tmp_path: Path):
    catalog = tmp_path / "NINA.sqlite"
    _make_catalog(catalog)
    current_ra, current_dec = _precess_j2000(282.77083333, -6.27)

    assert (
        resolve_nina_target_name(current_ra / 15.0, current_dec, catalog_path=catalog)
        == "M11"
    )


def test_does_not_label_unmatched_coordinates(tmp_path: Path):
    catalog = tmp_path / "NINA.sqlite"
    _make_catalog(catalog)

    assert resolve_nina_target_name(1.0, 45.0, catalog_path=catalog) is None
