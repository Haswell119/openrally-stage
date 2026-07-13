"""Tests T9 : preview 3D (rendu headless) + rechargement de bundle + CLI."""

from pathlib import Path

import numpy as np

from rsb.cli import build_parser
from rsb.config import SurfaceKind
from rsb.ir.bundle import load_bundle, write_bundle
from rsb.ir.types import Barriers, Centerline, StageBundle


def _bundle() -> StageBundle:
    n = 40
    xy = np.column_stack([np.linspace(2000.0, 2078.0, n), np.linspace(1050.0, 1030.0, n)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=np.zeros(n))
    cl.z = np.linspace(460.0, 470.0, n)
    cl.camber_rad = np.linspace(-0.03, 0.03, n)
    cl.width_m = np.full(n, 6.0)
    cl.surface = [SurfaceKind.TARMAC] * 20 + [SurfaceKind.GRAVEL] * 20
    b = Barriers(crs="EPSG:2056", left_xy=xy.copy(), right_xy=xy.copy(), left_z=cl.z, right_z=cl.z)
    return StageBundle(
        name="demo",
        crs="EPSG:2056",
        centerline=cl,
        barriers=b,
        metadata={"title": "Démo", "direction": "A → B"},
    )


def test_render_preview_cree_png(tmp_path: Path) -> None:
    from validate.preview3d import render_preview

    out = render_preview(_bundle(), tmp_path / "preview.png")
    assert out.exists()
    assert out.stat().st_size > 5000  # PNG non trivial


def test_render_detail_cree_png(tmp_path: Path) -> None:
    from validate.preview3d import render_detail

    out = render_detail(_bundle(), tmp_path / "detail.png")
    assert out.exists()
    assert out.stat().st_size > 5000


def test_load_bundle_roundtrip(tmp_path: Path) -> None:
    bundle = _bundle()
    write_bundle(bundle, tmp_path)
    reloaded = load_bundle(tmp_path)
    assert reloaded.name == "demo"
    assert reloaded.crs == "EPSG:2056"
    cl0, cl1 = bundle.centerline, reloaded.centerline
    assert np.allclose(cl0.xy, cl1.xy)
    assert cl1.z is not None and np.allclose(cl0.z, cl1.z)
    assert cl1.camber_rad is not None and np.allclose(cl0.camber_rad, cl1.camber_rad)
    assert cl1.surface == cl0.surface
    assert reloaded.barriers is not None


def test_preview_depuis_bundle_rechargee(tmp_path: Path) -> None:
    from validate.preview3d import render_preview

    write_bundle(_bundle(), tmp_path)
    reloaded = load_bundle(tmp_path)
    out = render_preview(reloaded, tmp_path / "p.png")
    assert out.exists()


def test_cli_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(["build", "stages/x/stage.toml", "--dem-res", "2.0"])
    assert args.command == "build"
    assert args.dem_res == 2.0
    args2 = parser.parse_args(["preview", "outputs/demo"])
    assert args2.command == "preview"
    args3 = parser.parse_args(["detail", "outputs/demo"])
    assert args3.command == "detail"
