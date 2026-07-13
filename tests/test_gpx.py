"""Tests du chargement GPX (source de tracé réel)."""

from pathlib import Path

import numpy as np
import pytest

from rsb.geo.gpx import load_gpx_track

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


def test_load_gpx_trop_court(tmp_path: Path) -> None:
    gpx = (
        '<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="46.1" lon="7.0"></trkpt></trkseg></trk></gpx>'
    )
    p = tmp_path / "t.gpx"
    p.write_text(gpx, encoding="utf-8")
    with pytest.raises(ValueError):
        load_gpx_track(p)
