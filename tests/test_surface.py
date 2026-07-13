"""Tests T6 : segmentation de surface (tarmac/terre) depuis la config."""

import numpy as np

from rsb.config import StageConfig, SurfaceKind, SurfaceSegment
from rsb.geo.surface import assign_centerline_surfaces, assign_surfaces, surface_runs
from rsb.ir.types import Centerline


def _cl(dist: np.ndarray) -> Centerline:
    xy = np.column_stack([dist, np.zeros_like(dist)])
    return Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=np.zeros_like(dist))


def test_surface_par_defaut_partout() -> None:
    d = np.array([0.0, 10.0, 20.0, 30.0])
    s = assign_surfaces(d, SurfaceKind.TARMAC, [])
    assert s == [SurfaceKind.TARMAC] * 4


def test_segment_terre_applique_dans_lintervalle() -> None:
    d = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
    overrides = [SurfaceSegment(kind=SurfaceKind.GRAVEL, start_m=8.0, end_m=16.0)]
    s = assign_surfaces(d, SurfaceKind.TARMAC, overrides)
    # 10 et 15 dans [8,16) → gravel ; le reste tarmac
    assert s == [
        SurfaceKind.TARMAC,
        SurfaceKind.TARMAC,
        SurfaceKind.GRAVEL,
        SurfaceKind.GRAVEL,
        SurfaceKind.TARMAC,
    ]


def test_segment_end_none_va_jusqua_la_fin() -> None:
    d = np.array([0.0, 5.0, 10.0])
    overrides = [SurfaceSegment(kind=SurfaceKind.GRAVEL, start_m=5.0, end_m=None)]
    s = assign_surfaces(d, SurfaceKind.TARMAC, overrides)
    assert s == [SurfaceKind.TARMAC, SurfaceKind.GRAVEL, SurfaceKind.GRAVEL]


def test_override_le_plus_tardif_gagne() -> None:
    d = np.array([10.0])
    overrides = [
        SurfaceSegment(kind=SurfaceKind.GRAVEL, start_m=0.0, end_m=20.0),
        SurfaceSegment(kind=SurfaceKind.SAND, start_m=5.0, end_m=15.0),
    ]
    s = assign_surfaces(d, SurfaceKind.TARMAC, overrides)
    assert s == [SurfaceKind.SAND]


def test_assign_centerline_depuis_config() -> None:
    cfg = StageConfig(
        name="x",
        title="x",
        waypoints=[
            {"role": "start", "lat": 46.1, "lon": 7.0},
            {"role": "end", "lat": 46.2, "lon": 7.1},
        ],
        default_surface=SurfaceKind.TARMAC,
        surface_overrides=[{"kind": "gravel", "start_m": 5.0, "end_m": 15.0}],
    )
    cl = _cl(np.array([0.0, 10.0, 20.0]))
    out = assign_centerline_surfaces(cl, cfg)
    assert out.surface == [SurfaceKind.TARMAC, SurfaceKind.GRAVEL, SurfaceKind.TARMAC]


def test_surface_runs_compacte() -> None:
    d = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
    surf = [
        SurfaceKind.TARMAC,
        SurfaceKind.TARMAC,
        SurfaceKind.GRAVEL,
        SurfaceKind.GRAVEL,
        SurfaceKind.TARMAC,
    ]
    runs = surface_runs(d, surf)
    assert runs == [
        (SurfaceKind.TARMAC, 0.0, 10.0),
        (SurfaceKind.GRAVEL, 10.0, 20.0),
        (SurfaceKind.TARMAC, 20.0, 20.0),
    ]
