"""Tests T5 (TDD) : coupes perpendiculaires → dévers (camber) + largeur par station."""

import math

import numpy as np
import pytest
from affine import Affine

from rsb.config import CamberConfig
from rsb.geo.camber import (
    compute_camber,
    cross_offsets,
    estimate_widths,
    fit_cross_slope,
    right_units,
    sample_cross_sections,
)
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster


def _straight_east_centerline(e0: float, e1: float, n: float, npts: int) -> Centerline:
    xy = np.column_stack([np.linspace(e0, e1, npts), np.full(npts, n)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    heading = np.zeros(npts)  # plein est
    return Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=heading)


def test_cross_offsets_symetrique() -> None:
    t = cross_offsets(12.0, 21)
    assert t.shape == (21,)
    assert t[0] == pytest.approx(-6.0)
    assert t[-1] == pytest.approx(6.0)
    assert t[10] == pytest.approx(0.0)


def test_right_units_cardinaux() -> None:
    # cap est (0) → droite = sud (0, -1) ; cap nord (pi/2) → droite = est (1, 0)
    r = right_units(np.array([0.0, math.pi / 2]))
    assert np.allclose(r[0], [0.0, -1.0], atol=1e-9)
    assert np.allclose(r[1], [1.0, 0.0], atol=1e-9)


def test_camber_signe_penche_a_droite() -> None:
    # plan Z croissant vers le nord (slope_y=0.1). Cap est → la droite (sud) est
    # plus basse → camber positif ≈ arctan(0.1).
    dem = DEMRaster.from_plane(
        origin=(2000.0, 1100.0), res=0.5, shape=(400, 400), slope_y=0.1, intercept=500.0
    )
    cl = _straight_east_centerline(2030.0, 2170.0, 1050.0, 30)
    offsets = cross_offsets(12.0, 25)
    Z = sample_cross_sections(dem, cl.xy, cl.heading_rad, offsets)
    camber = fit_cross_slope(offsets, Z, road_width=6.0)
    assert np.allclose(camber, math.atan(0.1), atol=1e-3)
    assert np.all(camber > 0)


def test_camber_nul_si_pente_seulement_le_long_du_trace() -> None:
    dem = DEMRaster.from_plane(
        origin=(2000.0, 1100.0), res=0.5, shape=(400, 400), slope_x=0.1, intercept=500.0
    )
    cl = _straight_east_centerline(2030.0, 2170.0, 1050.0, 30)
    offsets = cross_offsets(12.0, 25)
    Z = sample_cross_sections(dem, cl.xy, cl.heading_rad, offsets)
    camber = fit_cross_slope(offsets, Z, road_width=6.0)
    assert np.allclose(camber, 0.0, atol=1e-4)


def _road_with_verges_dem() -> DEMRaster:
    """MNT : plateforme plate (Z=0) pour |N-1050|<=3, talus montant au-delà."""
    res = 0.5
    h, w = 220, 220
    transform = Affine(res, 0.0, 2000.0, 0.0, -res, 1105.0)
    rows = np.arange(h)
    n_coord = transform.f + transform.e * (rows + 0.5)  # N au centre de chaque ligne
    dev = np.abs(n_coord - 1050.0)
    z_col = np.where(dev <= 3.0, 0.0, (dev - 3.0) * 0.5)
    data = np.repeat(z_col[:, None], w, axis=1).astype("float32")
    return DEMRaster(data=data, transform=transform, crs="EPSG:2056", nodata=None)


def test_width_detecte_plateforme_sur_talus() -> None:
    dem = _road_with_verges_dem()
    cl = _straight_east_centerline(2030.0, 2080.0, 1050.0, 20)
    offsets = cross_offsets(12.0, 49)
    Z = sample_cross_sections(dem, cl.xy, cl.heading_rad, offsets)
    widths = estimate_widths(offsets, Z, road_width=6.0, default_width=6.0)
    assert np.all(widths > 5.0)
    assert np.all(widths < 8.0)


def test_width_fallback_defaut_en_terrain_plat() -> None:
    # pente uniquement le long du tracé → pas de rupture transversale → défaut.
    dem = DEMRaster.from_plane(origin=(2000.0, 1100.0), res=0.5, shape=(400, 400), slope_x=0.1)
    cl = _straight_east_centerline(2030.0, 2170.0, 1050.0, 20)
    offsets = cross_offsets(12.0, 25)
    Z = sample_cross_sections(dem, cl.xy, cl.heading_rad, offsets)
    widths = estimate_widths(offsets, Z, road_width=6.0, default_width=6.0)
    assert np.allclose(widths, 6.0, atol=1e-6)


def test_compute_camber_renseigne_les_champs() -> None:
    dem = DEMRaster.from_plane(
        origin=(2000.0, 1100.0), res=0.5, shape=(400, 400), slope_y=0.05, intercept=480.0
    )
    cl = _straight_east_centerline(2030.0, 2170.0, 1050.0, 40)
    out = compute_camber(
        cl, dem, CamberConfig(cross_section_width_m=12.0, n_samples=25), default_width=6.0
    )
    assert out.camber_rad is not None and out.camber_rad.shape == (40,)
    assert out.width_m is not None and out.width_m.shape == (40,)
    assert np.all(out.camber_rad > 0)  # penche à droite (sud plus bas)
