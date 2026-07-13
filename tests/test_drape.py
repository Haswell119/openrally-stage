"""Tests T4 (TDD) : drapage de Z sur le MNT le long du tracé."""

import numpy as np
import pytest

from rsb.geo.drape import (
    despike_elevation,
    drape_centerline,
    drape_z,
    fill_nan,
    smooth_along_track,
)
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster


def _line_centerline(xy: np.ndarray, crs: str = "EPSG:2056") -> Centerline:
    seg = np.diff(xy, axis=0)
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])
    heading = np.zeros(len(xy))
    return Centerline(crs=crs, xy=xy, distance_m=dist, heading_rad=heading)


def test_drape_plan_incline_exact() -> None:
    # MNT = plan Z = 500 + 0.1*(x-x0) - 0.05*(y-y0)
    dem = DEMRaster.from_plane(
        origin=(2000.0, 1200.0),
        res=0.5,
        shape=(400, 400),
        slope_x=0.1,
        slope_y=-0.05,
        intercept=500.0,
    )
    xy = np.array([[2050.0, 1100.0], [2080.0, 1100.0], [2110.0, 1090.0]])
    z = drape_z(dem, xy, "EPSG:2056")
    expected = 500.0 + 0.1 * (xy[:, 0] - 2000.0) - 0.05 * (xy[:, 1] - 1200.0)
    assert np.allclose(z, expected, atol=1e-5)


def test_drape_pente_constante_gradient_connu() -> None:
    dem = DEMRaster.from_plane(
        origin=(2000.0, 1200.0), res=0.5, shape=(400, 400), slope_x=0.08, intercept=400.0
    )
    xy = np.column_stack([np.linspace(2020.0, 2120.0, 51), np.full(51, 1100.0)])
    cl = _line_centerline(xy)
    drape_centerline(cl, dem)
    assert cl.z is not None
    # dZ/dS = pente * (dx/dS) = 0.08 le long de +x
    dzds = np.diff(cl.z) / np.diff(cl.distance_m)
    assert np.allclose(dzds, 0.08, atol=1e-6)


def test_fill_nan_interpole_les_trous() -> None:
    x = np.arange(6, dtype=float)
    z = np.array([10.0, np.nan, np.nan, 40.0, 50.0, 60.0])
    filled = fill_nan(z, x)
    assert not np.isnan(filled).any()
    assert filled[1] == pytest.approx(20.0)
    assert filled[2] == pytest.approx(30.0)


def test_fill_nan_tout_nan_leve() -> None:
    with pytest.raises(ValueError):
        fill_nan(np.array([np.nan, np.nan]), np.array([0.0, 1.0]))


def test_drape_remplit_les_nan_hors_emprise() -> None:
    dem = DEMRaster.from_plane(origin=(2000.0, 1200.0), res=1.0, shape=(50, 50), slope_x=0.1)
    # un point hors emprise au milieu → doit être rempli, pas NaN
    xy = np.array([[2010.0, 1180.0], [5000.0, 1180.0], [2030.0, 1180.0]])
    z = drape_z(dem, xy, "EPSG:2056")
    assert not np.isnan(z).any()


def test_despike_supprime_notch_garde_montee() -> None:
    s = np.arange(0.0, 2000.0, 2.0)  # pas 2 m
    z_true = 450.0 + 0.015 * s  # vraie montée douce (1,5 %)
    z = z_true.copy()
    notch = (s >= 1000.0) & (s < 1024.0)  # « pont » : chute aberrante de 8 m sur 24 m
    z[notch] -= 8.0
    out = despike_elevation(z, s)
    # le notch est ponté (retour au niveau réel de la route)
    assert np.max(np.abs(out[notch] - z_true[notch])) < 2.0
    # la vraie montée est préservée (~30 m de dénivelé)
    assert (out[-1] - out[0]) == pytest.approx(30.0, abs=3.0)


def test_despike_supprime_pic_positif() -> None:
    s = np.arange(0.0, 1000.0, 2.0)
    z = np.full_like(s, 500.0)
    z[200:205] += 12.0  # pic vers le haut (canopée/tablier)
    out = despike_elevation(z, s)
    assert np.max(np.abs(out - 500.0)) < 1.0


def test_despike_profil_propre_inchange() -> None:
    s = np.arange(0.0, 1000.0, 2.0)
    z = 500.0 + 0.02 * s  # rampe régulière
    out = despike_elevation(z, s)
    assert np.allclose(out, z, atol=1.0)


def test_smooth_along_track_importable_depuis_drape() -> None:
    d = np.arange(10, dtype=float)
    v = np.zeros(10)
    v[5] = 5.0
    assert smooth_along_track(v, d, 3.0)[5] == pytest.approx(0.0)


def test_drape_preserve_les_autres_champs() -> None:
    dem = DEMRaster.from_plane(origin=(2000.0, 1200.0), res=1.0, shape=(60, 60), slope_x=0.1)
    xy = np.column_stack([np.linspace(2010.0, 2050.0, 10), np.full(10, 1180.0)])
    cl = _line_centerline(xy)
    original_xy = cl.xy.copy()
    drape_centerline(cl, dem)
    assert np.allclose(cl.xy, original_xy)
    assert cl.z is not None and cl.z.shape == (10,)
