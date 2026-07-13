"""Tests T8 : sérialisation de l'IR (geojson, mesh, AC CSV, manifeste)."""

import json
from pathlib import Path

import numpy as np
import pytest

from rsb.config import SurfaceKind
from rsb.ir.bundle import (
    barriers_to_geojson,
    centerline_to_ac_csv,
    centerline_to_geojson,
    dem_corridor_mesh,
    mesh_to_obj,
    write_bundle,
)
from rsb.ir.types import Barriers, Centerline, StageBundle, TerrainMesh
from rsb.providers.dem import DEMRaster


def _full_centerline(npts: int = 30) -> Centerline:
    xy = np.column_stack([np.linspace(2000.0, 2058.0, npts), np.full(npts, 1050.0)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=np.zeros(npts))
    cl.z = np.linspace(500.0, 505.0, npts)
    cl.camber_rad = np.full(npts, 0.02)
    cl.width_m = np.full(npts, 6.0)
    cl.surface = [SurfaceKind.TARMAC] * npts
    return cl


def test_dem_corridor_mesh_valide() -> None:
    dem = DEMRaster.from_plane(origin=(1990.0, 1080.0), res=0.5, shape=(120, 200), slope_x=0.05)
    xy = np.column_stack([np.linspace(2000.0, 2050.0, 40), np.full(40, 1050.0)])
    mesh = dem_corridor_mesh(dem, xy, corridor_m=8.0, target_res=1.0)
    assert mesh.vertices.shape[1] == 3
    assert mesh.faces.shape[1] == 3
    assert len(mesh.faces) > 0
    assert np.isfinite(mesh.vertices).all()
    # indices de faces valides
    assert mesh.faces.max() < len(mesh.vertices)
    assert mesh.faces.min() >= 0


def test_mesh_to_obj_format() -> None:
    mesh = TerrainMesh(
        crs="EPSG:2056",
        vertices=np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 2.0]]),
        faces=np.array([[0, 1, 2]]),
    )
    obj = mesh_to_obj(mesh)
    assert "v 0.000 0.000 1.000" in obj
    assert "f 1 2 3" in obj  # OBJ 1-indexé


def test_centerline_geojson_contient_z_et_camber() -> None:
    cl = _full_centerline()
    gj = centerline_to_geojson(cl)
    assert gj["geometry"]["type"] == "LineString"
    assert len(gj["geometry"]["coordinates"][0]) == 3  # E, N, Z
    props = gj["properties"]
    assert props["crs"] == "EPSG:2056"
    assert len(props["camber_rad"]) == len(cl)
    assert props["surface"][0] == "tarmac"


def test_ac_csv_colonnes_et_localisation() -> None:
    cl = _full_centerline()
    origin = (2000.0, 1050.0, 500.0)
    csv = centerline_to_ac_csv(cl, origin)
    first = csv.splitlines()[0].split(",")
    assert len(first) == 3
    # premier point : E-E0=0, -(Z-Z0)=0, N-N0=0
    assert float(first[0]) == pytest.approx(0.0, abs=1e-4)
    assert float(first[1]) == pytest.approx(0.0, abs=1e-4)
    assert float(first[2]) == pytest.approx(0.0, abs=1e-4)


def test_barriers_geojson_deux_cotes() -> None:
    n = 10
    b = Barriers(
        crs="EPSG:2056",
        left_xy=np.zeros((n, 2)),
        right_xy=np.ones((n, 2)),
        left_z=np.zeros(n),
        right_z=np.zeros(n),
    )
    gj = barriers_to_geojson(b)
    assert len(gj["features"]) == 2
    assert {f["properties"]["side"] for f in gj["features"]} == {"left", "right"}


def test_write_bundle_ecrit_tous_les_fichiers(tmp_path: Path) -> None:
    cl = _full_centerline()
    dem = DEMRaster.from_plane(origin=(1990.0, 1080.0), res=0.5, shape=(120, 200), slope_x=0.05)
    mesh = dem_corridor_mesh(dem, cl.xy, corridor_m=8.0, target_res=1.0)
    b = Barriers(
        crs="EPSG:2056",
        left_xy=cl.xy.copy(),
        right_xy=cl.xy.copy(),
        left_z=cl.z,
        right_z=cl.z,
    )
    bundle = StageBundle(name="demo", crs="EPSG:2056", centerline=cl, barriers=b, terrain=mesh)
    written = write_bundle(bundle, tmp_path)
    for name in (
        "centerline.geojson",
        "surfaces.geojson",
        "barriers.geojson",
        "terrain.obj",
        "centerline_ac.csv",
        "bundle.json",
    ):
        assert (tmp_path / name).exists(), name
        assert name in written
    manifest = json.loads((tmp_path / "bundle.json").read_text())
    assert manifest["name"] == "demo"
    assert manifest["n_stations"] == len(cl)
    assert "OpenStreetMap" in manifest["attribution"]["osm"]
    assert "swisstopo" in manifest["attribution"]["swisstopo"]
