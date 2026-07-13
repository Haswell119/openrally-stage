"""Tests du chargement GPX (source de tracé réel)."""

from pathlib import Path

import numpy as np
import pytest

from rsb.geo.gpx import list_gpx_tracks, load_gpx_track

_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk><trkseg>
    <trkpt lat="46.1734" lon="7.0216"></trkpt>
    <trkpt lat="46.1580" lon="7.0300"></trkpt>
    <trkpt lat="46.1438" lon="7.0377"><ele>450.5</ele></trkpt>
  </trkseg></trk>
</gpx>
"""


def test_load_gpx_track(tmp_path: Path) -> None:
    p = tmp_path / "t.gpx"
    p.write_text(_GPX, encoding="utf-8")
    lonlat, ele = load_gpx_track(p)
    assert lonlat.shape == (3, 2)
    # colonne 0 = lon, colonne 1 = lat
    assert lonlat[0, 0] == pytest.approx(7.0216)
    assert lonlat[0, 1] == pytest.approx(46.1734)
    assert lonlat[-1, 0] == pytest.approx(7.0377)
    # ele partiellement présent → tableau retourné (NaN sur les points sans ele)
    assert ele is not None
    assert ele[-1] == pytest.approx(450.5)
    assert np.isnan(ele[0])


def test_load_gpx_sans_ele(tmp_path: Path) -> None:
    gpx = (
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="46.1" lon="7.0"></trkpt><trkpt lat="46.2" lon="7.1"></trkpt>'
        "</trkseg></trk></gpx>"
    )
    p = tmp_path / "t.gpx"
    p.write_text(gpx, encoding="utf-8")
    lonlat, ele = load_gpx_track(p)
    assert lonlat.shape == (2, 2)
    assert ele is None  # aucune altitude → None


_MULTI = """<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Alpha</name><trkseg>
    <trkpt lat="46.10" lon="7.00"></trkpt>
    <trkpt lat="46.11" lon="7.01"></trkpt>
    <trkpt lat="46.12" lon="7.02"></trkpt>
  </trkseg></trk>
  <trk><name>Alpha</name><trkseg>
    <trkpt lat="46.10" lon="7.00"></trkpt>
  </trkseg></trk>
  <trk><name>Beta</name><trkseg>
    <trkpt lat="46.20" lon="7.10"></trkpt>
    <trkpt lat="46.21" lon="7.11"></trkpt>
  </trkseg></trk>
</gpx>
"""


def test_multi_track_selection_par_nom(tmp_path: Path) -> None:
    p = tmp_path / "m.gpx"
    p.write_text(_MULTI, encoding="utf-8")
    assert list_gpx_tracks(p) == ["Alpha", "Alpha", "Beta"]
    # "Beta" → sa track
    beta, _ = load_gpx_track(p, "Beta")
    assert beta.shape == (2, 2)
    # "Alpha" homonyme → la plus longue (3 points, pas le fragment)
    alpha, _ = load_gpx_track(p, "Alpha")
    assert alpha.shape == (3, 2)


def test_multi_track_selection_par_index(tmp_path: Path) -> None:
    p = tmp_path / "m.gpx"
    p.write_text(_MULTI, encoding="utf-8")
    beta, _ = load_gpx_track(p, 2)
    assert beta.shape == (2, 2)


def test_multi_track_sans_selection_leve(tmp_path: Path) -> None:
    p = tmp_path / "m.gpx"
    p.write_text(_MULTI, encoding="utf-8")
    with pytest.raises(ValueError):
        load_gpx_track(p)  # ambigu : plusieurs tracks


def test_track_inconnue_leve(tmp_path: Path) -> None:
    p = tmp_path / "m.gpx"
    p.write_text(_MULTI, encoding="utf-8")
    with pytest.raises(ValueError):
        load_gpx_track(p, "Gamma")


def test_load_gpx_trop_court(tmp_path: Path) -> None:
    gpx = (
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="46.1" lon="7.0"></trkpt></trkseg></trk></gpx>'
    )
    p = tmp_path / "t.gpx"
    p.write_text(gpx, encoding="utf-8")
    with pytest.raises(ValueError):
        load_gpx_track(p)
