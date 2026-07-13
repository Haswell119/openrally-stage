"""Tests de l'export « prêt pour Assetto Corsa » (géométrie + FBX/OBJ)."""

import numpy as np

from rsb.export.ac_track import (
    build_ac_track,
    build_road,
    detect_wall_sides,
    to_ac_xyz,
    write_fbx,
    write_obj,
)
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster


def _straight_east(n: int = 40, north: float = 1100.0) -> Centerline:
    xy = np.column_stack([np.linspace(2000.0, 2078.0, n), np.full(n, north)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=np.zeros(n))
    cl.z = np.full(n, 450.0)
    cl.width_m = np.full(n, 6.0)
    return cl


def test_to_ac_xyz_axe_y_up() -> None:
    # (E, N, Z) → (X=E, Y=Z, Z=-N)
    assert to_ac_xyz(np.array([10.0, 20.0, 5.0])) == (10.0, 5.0, -20.0)


def test_build_road_ruban() -> None:
    cl = _straight_east()
    road = build_road(cl, cl.require_z(), np.full(len(cl), 3.0))
    assert road.name == "1ROAD"
    assert road.vertices.shape == (2 * len(cl), 3)
    assert road.faces.shape == (2 * (len(cl) - 1), 3)
    assert road.faces.max() < len(road.vertices)
    # largeur : écart gauche/droite ~ 6 m (en N, cap est → gauche = +N)
    left = road.vertices[: len(cl)]
    right = road.vertices[len(cl) :]
    assert np.allclose(left[:, 1] - right[:, 1], 6.0)


def test_detect_wall_sides_chute_a_droite() -> None:
    # MNT qui plonge vers le sud (−N) : le côté droit (cap est) doit être marqué.
    dem = DEMRaster.from_plane(
        origin=(1990.0, 1130.0), res=1.0, shape=(80, 120), slope_y=0.3, intercept=450.0
    )
    cl = _straight_east(north=1100.0)
    road_z = dem.sample(cl.xy)
    left_flag, right_flag = detect_wall_sides(cl, dem, road_z, np.full(len(cl), 3.0))
    assert right_flag.mean() > 0.8  # quasi tout à droite
    assert left_flag.mean() < 0.2  # rien à gauche (le terrain monte)


def test_build_ac_track_complet() -> None:
    dem = DEMRaster.from_plane(
        origin=(1990.0, 1130.0), res=1.0, shape=(80, 120), slope_y=0.3, intercept=450.0
    )
    cl = _straight_east(north=1100.0)
    cl.z = dem.sample(cl.xy)
    track = build_ac_track(cl, dem, "demo", default_width=6.0)
    names = {m.name for m in track.meshes}
    assert "1ROAD" in names
    assert "1WALL" in names  # chute à droite → barrière
    obj_names = {o.name for o in track.objects}
    assert {"AC_AB_START_L", "AC_AB_FINISH_R", "AC_PIT_0"} <= obj_names
    # tout est localisé autour de 0
    road = next(m for m in track.meshes if m.name == "1ROAD")
    assert road.vertices[:, 0].min() >= -1.0


def test_write_obj_objets_nommes() -> None:
    cl = _straight_east()
    dem = DEMRaster.from_plane(origin=(1990.0, 1130.0), res=1.0, shape=(80, 120))
    cl.z = dem.sample(cl.xy)
    track = build_ac_track(cl, dem, "demo", default_width=6.0)
    obj = write_obj(track)
    assert "o 1ROAD" in obj
    assert obj.count("\nv ") >= 2 * len(cl)  # au moins le ruban de route
    assert "\nf " in obj


def test_write_ac_folder_structure(tmp_path: object) -> None:
    from pathlib import Path

    from rsb.export.ac_track import write_ac_folder

    cl = _straight_east()
    dem = DEMRaster.from_plane(origin=(1990.0, 1130.0), res=1.0, shape=(80, 120))
    cl.z = dem.sample(cl.xy)
    track = build_ac_track(cl, dem, "demo-track", default_width=6.0)
    root, proj = write_ac_folder(track, Path(str(tmp_path)), 1234.0)
    # structure AC : content/tracks/<id>/
    assert (root / "demo-track.fbx").exists()
    assert (root / "models.ini").exists()
    assert (root / "README_IMPORT.txt").exists()
    assert (root / "data" / "surfaces.ini").exists()
    assert (root / "data" / "map.ini").exists()
    assert (root / "data" / "ai").is_dir()
    assert (root / "ui" / "ui_track.json").exists()
    assert "SCALE_FACTOR" in proj and proj["SCALE_FACTOR"] > 0


def test_write_fbx_structure() -> None:
    cl = _straight_east()
    dem = DEMRaster.from_plane(origin=(1990.0, 1130.0), res=1.0, shape=(80, 120))
    cl.z = dem.sample(cl.xy)
    track = build_ac_track(cl, dem, "demo", default_width=6.0)
    fbx = write_fbx(track)
    assert "FBXVersion: 7400" in fbx
    assert "Geometry::1ROAD" in fbx
    assert "Model::AC_PIT_0" in fbx
    assert "Connections:" in fbx
    assert 'C: "OO"' in fbx
