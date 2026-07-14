"""Tests du writer KN5 direct (SANS ksEditor) : aller-retour + invariants AC.

Le format binaire produit ici a par ailleurs été recoupé hors-test avec un
lecteur KN5 indépendant (``MarvinSt/kn5-obj-converter``, lignée différente) :
mêmes nœuds, mêmes comptes de sommets/indices, bornes identiques.
"""

import numpy as np
import pytest

from rsb.export.ac_track import NamedMesh, build_ac_track
from rsb.export.kn5 import read_kn5, to_ac, write_kn5
from rsb.ir.bundle import dem_corridor_mesh
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster


def _arc_track(n: int = 80, radius: float = 25.0) -> object:
    theta = np.linspace(0.0, np.pi / 2, n)
    xy = np.column_stack([2000.0 + radius * np.sin(theta), 1100.0 + radius * np.cos(theta)])
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    heading = np.arctan2(np.gradient(xy[:, 1]), np.gradient(xy[:, 0]))
    cl = Centerline(crs="EPSG:2056", xy=xy, distance_m=dist, heading_rad=heading)
    dem = DEMRaster.from_plane(
        origin=(1980.0, 1140.0), res=1.0, shape=(120, 120), slope_y=0.3, intercept=450.0
    )
    cl.z = dem.sample(cl.xy)
    cl.width_m = np.full(n, 6.0)
    terrain = dem_corridor_mesh(dem, cl.xy, corridor_m=30.0)
    return build_ac_track(
        cl, dem, "arc", default_width=6.0, terrain=NamedMesh("1GRASS", terrain.vertices, terrain.faces)
    )


def test_kn5_entete_et_version() -> None:
    data = write_kn5(_arc_track())
    assert data[:6] == b"sc6969"
    parsed = read_kn5(data)
    assert parsed["version"] == 5


def test_kn5_consomme_tout_le_fichier() -> None:
    # read_kn5 lève si des octets restent → garantit un layout cohérent.
    data = write_kn5(_arc_track())
    read_kn5(data)  # ne doit pas lever
    with pytest.raises(ValueError):
        read_kn5(data[:-4])  # tronqué
    with pytest.raises(ValueError):
        read_kn5(data + b"\x00\x00")  # octets en trop


def test_kn5_materiaux_et_textures() -> None:
    track = _arc_track()
    parsed = read_kn5(write_kn5(track))
    mesh_names = {m.name for m in track.meshes}
    # un matériau ksPerPixel + une texture par surface distincte
    assert len(parsed["materials"]) == len(mesh_names)
    for mat in parsed["materials"]:
        assert mat["shader"] == "ksPerPixel"
        assert mat["textures"][0]["input"] == "txDiffuse"
    assert len(parsed["textures"]) == len(mesh_names)


def test_kn5_noeuds_et_objets_ac() -> None:
    track = _arc_track()
    parsed = read_kn5(write_kn5(track))
    names = [n["name"] for n in parsed["nodes"]]
    # racine + meshes physiques + objets logiques AC
    assert names[0] == "arc"  # racine
    for surf in ("1ROAD", "1WALL", "1GRASS"):
        assert surf in names
    for obj in ("AC_START_0", "AC_PIT_0", "AC_AB_START_L", "AC_AB_FINISH_R"):
        assert obj in names


def test_kn5_geometrie_finie_et_conservee() -> None:
    track = _arc_track()
    parsed = read_kn5(write_kn5(track))
    mesh_nodes = [n for n in parsed["nodes"] if n["class"] == 2]
    # somme des triangles = somme des faces de la piste (expansion à plat)
    kn5_tris = sum(len(n["indices"]) // 3 for n in mesh_nodes)
    track_tris = sum(len(m.faces) for m in track.meshes)
    assert kn5_tris == track_tris
    allv = np.vstack([n["vertices"][:, 0:3] for n in mesh_nodes])
    assert np.all(np.isfinite(allv))
    # bornes cohérentes avec les sommets AC de la piste
    ref = np.vstack([to_ac(m.vertices) for m in track.meshes])
    assert np.allclose(allv.min(axis=0), ref.min(axis=0), atol=1e-3)
    assert np.allclose(allv.max(axis=0), ref.max(axis=0), atol=1e-3)


def test_kn5_spawn_oriente_selon_la_route() -> None:
    track = _arc_track()
    parsed = read_kn5(write_kn5(track))
    pit = next(n for n in parsed["nodes"] if n["name"] == "AC_PIT_0")
    m = np.array(pit["matrix"])
    forward = m[8:11]  # colonne 2 = forward
    # orienté (non identité) et horizontal (composante Y nulle)
    assert not np.allclose(forward, [0.0, 0.0, 1.0])
    assert abs(forward[1]) < 1e-6
    assert np.isclose(np.linalg.norm(forward), 1.0, atol=1e-4)


def test_kn5_decoupe_limite_uint16() -> None:
    # un mesh de > 65535 sommets (après expansion ×3) est découpé en plusieurs
    # nœuds de même nom, chacun sous la limite d'index uint16.
    from rsb.export.ac_track import AcTrack

    n = 30000  # 30000 triangles → 90000 sommets > 65535
    verts = np.random.default_rng(0).uniform(0, 100, size=(n * 3, 3))
    faces = np.arange(n * 3).reshape(n, 3)
    big = NamedMesh("1GRASS", verts, faces)
    track = AcTrack(name="big", origin=(0.0, 0.0, 0.0), meshes=[big], objects=[])
    parsed = read_kn5(write_kn5(track))
    grass_nodes = [x for x in parsed["nodes"] if x["name"] == "1GRASS"]
    assert len(grass_nodes) >= 2
    for node in grass_nodes:
        assert len(node["vertices"]) <= 65535
    assert sum(len(x["indices"]) // 3 for x in grass_nodes) == n
