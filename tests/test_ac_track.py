"""Tests de l'export « prêt pour Assetto Corsa » (géométrie + FBX/OBJ)."""

import numpy as np

from rsb.export.ac_track import (
    NamedMesh,
    _face_normals_uv,
    build_ac_track,
    build_kerbs,
    build_road,
    detect_wall_sides,
    to_ac_xyz,
    write_fbx,
    write_obj,
)
from rsb.ir.bundle import dem_corridor_mesh
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster


def _mean_normal_y(mesh: NamedMesh) -> float:
    vac = np.array([to_ac_xyz(v) for v in mesh.vertices])
    nrm, _ = _face_normals_uv(vac, mesh.faces)
    return float(np.array(nrm).reshape(-1, 3)[:, 1].mean())


def _is_double_sided(mesh: NamedMesh) -> bool:
    # chaque face (a,b,c) doit avoir sa jumelle inversée (c,b,a) dans le mesh.
    faces = {tuple(int(i) for i in f) for f in mesh.faces}
    return len(mesh.faces) % 2 == 0 and all((c, b, a) in faces for a, b, c in faces)


def _straight_east(n: int = 40, north: float = 1100.0) -> Centerline:
    xy = np.column_stack([np.linspace(2000.0, 2078.0, n), np.full(n, north)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=np.zeros(n))
    cl.z = np.full(n, 450.0)
    cl.width_m = np.full(n, 6.0)
    return cl


def _arc(n: int = 60, radius: float = 25.0) -> Centerline:
    # arc serré (rayon < KERB_MAX_RADIUS_M) pour forcer la génération de bordures.
    theta = np.linspace(0.0, np.pi / 2, n)
    xy = np.column_stack([2000.0 + radius * np.sin(theta), 1100.0 + radius * np.cos(theta)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    heading = np.arctan2(np.gradient(xy[:, 1]), np.gradient(xy[:, 0]))
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=heading)
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


def test_normales_orientees_vers_le_haut() -> None:
    # RÉGRESSION : route + terrain doivent avoir leurs normales vers le HAUT
    # (Y+ en axe AC) sinon le back-face culling d'AC les rend invisibles ;
    # les barrières doivent être double-face (vues depuis la route ET l'extérieur).
    dem = DEMRaster.from_plane(
        origin=(1990.0, 1130.0), res=1.0, shape=(80, 120), slope_y=0.3, intercept=450.0
    )
    cl = _straight_east(north=1100.0)
    cl.z = dem.sample(cl.xy)
    terrain = dem_corridor_mesh(dem, cl.xy, corridor_m=30.0)
    track = build_ac_track(
        cl,
        dem,
        "demo",
        default_width=6.0,
        terrain=NamedMesh("1GRASS", terrain.vertices, terrain.faces),
    )
    by_name = {m.name: m for m in track.meshes}
    assert _mean_normal_y(by_name["1ROAD"]) > 0.5  # route vers le haut
    assert _mean_normal_y(by_name["1GRASS"]) > 0.5  # terrain vers le haut
    if "1KERB" in by_name:
        assert _mean_normal_y(by_name["1KERB"]) > 0.5  # bordures vers le haut
    assert _is_double_sided(by_name["1WALL"])  # barrière visible des deux côtés


def test_bordures_normales_vers_le_haut() -> None:
    # RÉGRESSION : les deux côtés d'une bordure (virage) doivent pointer vers le
    # haut — le côté droit était retourné (normale vers le bas) → invisible dans AC.
    cl = _arc()
    kerbs = build_kerbs(cl, cl.require_z(), np.full(len(cl), 3.0))
    assert kerbs is not None
    assert _mean_normal_y(kerbs) > 0.5


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


def test_fbx_ascii_accolades_equilibrees_hors_commentaires() -> None:
    # RÉGRESSION : en FBX ASCII, ';' démarre un commentaire jusqu'à la fin de ligne
    # → une accolade fermante après un ';' est « avalée » (ksEditor voit un point).
    cl = _straight_east()
    dem = DEMRaster.from_plane(origin=(1990.0, 1130.0), res=1.0, shape=(80, 120), slope_y=0.3)
    cl.z = dem.sample(cl.xy)
    track = build_ac_track(cl, dem, "demo", default_width=6.0)
    fbx = write_fbx(track)
    depth = 0
    for line in fbx.splitlines():
        code = line.split(";", 1)[0]  # retire le commentaire FBX
        depth += code.count("{") - code.count("}")
        assert depth >= 0, "accolade fermante avant ouvrante"
    assert depth == 0, "accolades déséquilibrées (commentaire ';' avale une '}')"
