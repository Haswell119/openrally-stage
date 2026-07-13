"""Tests T7 : bordures par offset gauche/droite du bord de route."""

import numpy as np

from rsb.geo.barriers import build_barriers, offset_edges
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster


def _straight_east_centerline(npts: int = 20) -> Centerline:
    xy = np.column_stack([np.linspace(2000.0, 2100.0, npts), np.full(npts, 1050.0)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=np.zeros(npts))
    cl.width_m = np.full(npts, 6.0)
    return cl


def test_offset_edges_gauche_nord_droite_sud() -> None:
    xy = np.array([[2000.0, 1050.0], [2010.0, 1050.0]])
    heading = np.zeros(2)
    left, right = offset_edges(xy, heading, np.full(2, 3.0))
    # cap est : gauche = nord (+N), droite = sud (-N)
    assert np.allclose(left[:, 1], 1053.0)
    assert np.allclose(right[:, 1], 1047.0)
    # E inchangé
    assert np.allclose(left[:, 0], xy[:, 0])


def test_offset_symetrique_autour_du_centre() -> None:
    xy = np.array([[2000.0, 1050.0], [2000.0, 1060.0]])  # cap nord
    heading = np.full(2, np.pi / 2)
    left, right = offset_edges(xy, heading, np.full(2, 4.0))
    mid = (left + right) / 2.0
    assert np.allclose(mid, xy, atol=1e-9)


def test_build_barriers_shapes_et_offset() -> None:
    cl = _straight_east_centerline()
    b = build_barriers(cl, edge_offset_m=0.5)
    assert b.left_xy.shape == cl.xy.shape
    assert b.right_xy.shape == cl.xy.shape
    # demi-largeur 3 + 0.5 = 3.5 → gauche à +3.5 N, droite à -3.5 N
    assert np.allclose(b.left_xy[:, 1], 1053.5)
    assert np.allclose(b.right_xy[:, 1], 1046.5)


def test_build_barriers_drape_z_si_dem() -> None:
    cl = _straight_east_centerline()
    dem = DEMRaster.from_plane(origin=(1990.0, 1080.0), res=0.5, shape=(120, 260), slope_x=0.1)
    b = build_barriers(cl, dem=dem, edge_offset_m=0.5)
    assert b.left_z is not None and b.left_z.shape == (len(cl),)
    assert b.right_z is not None
    assert not np.isnan(b.left_z).any()
