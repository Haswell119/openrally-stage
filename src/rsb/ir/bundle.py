"""T8 — Bundle : sérialise la représentation intermédiaire (IR) sur disque.

La *stage bundle* est **agnostique de l'éditeur** (inversion de dépendance).
Elle contient :

* ``centerline.geojson`` — LineString 3D (E, N, Z) + arrays par station
  (distance, dévers, largeur, cap, surface) en propriétés.
* ``barriers.geojson`` — bordures gauche/droite 3D.
* ``surfaces.geojson`` — segments de surface contigus (tarmac/terre).
* ``terrain.obj`` — mesh de terrain (corridor du MNT clippé, décimé).
* ``centerline_ac.csv`` — points localisés prêts pour ``io_import_accsv``
  (ordre de colonnes AC : X, Z, Y — voir ``STAGE_GUIDE.md``).
* ``bundle.json`` — manifeste (métadonnées, origine locale, attribution, stats).

Rien ici n'importe d'éditeur : les exporteurs (Blender, RTB) consomment ces
fichiers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from rsb.geo.surface import surface_runs
from rsb.ir.types import Barriers, Centerline, StageBundle, TerrainMesh
from rsb.providers.dem import DEMRaster

FloatArray = NDArray[np.floating[Any]]

ATTRIBUTION = {
    "osm": "© OpenStreetMap contributors (ODbL) — attribution obligatoire",
    "swisstopo": "Source : Office fédéral de topographie swisstopo (swissALTI3D, OGD)",
    "note": "Recréation à usage simulation personnel. Ne pas redistribuer de contenu rally-maps.",
}


# --------------------------------------------------------------- mesh terrain
def dem_corridor_mesh(
    dem: DEMRaster,
    centerline_xy: FloatArray,
    *,
    corridor_m: float = 30.0,
    target_res: float = 2.0,
) -> TerrainMesh:
    """Mesh de terrain : grille MNT décimée, restreinte au corridor autour du tracé.

    Décime le MNT à ``target_res`` (m), garde les cellules à moins de ``corridor_m``
    du tracé (cKDTree), triangule et élague les sommets non référencés. Ruban de
    terrain léger autour de la route.
    """
    centerline_xy = np.asarray(centerline_xy, dtype=np.float64)
    stride = max(1, int(round(target_res / dem.res[0])))
    X, Y, Z = dem.xyz_grid()
    Xc = X[::stride, ::stride]
    Yc = Y[::stride, ::stride]
    Zc = Z[::stride, ::stride].astype(np.float64)
    h, w = Xc.shape

    pts = np.column_stack([Xc.ravel(), Yc.ravel()])
    dist, _ = cKDTree(centerline_xy).query(pts)
    within = (dist <= corridor_m).reshape(h, w)
    ok = within & np.isfinite(Zc)

    vidx = np.arange(h * w).reshape(h, w)
    v00, v01 = vidx[:-1, :-1], vidx[:-1, 1:]
    v10, v11 = vidx[1:, :-1], vidx[1:, 1:]
    cell_ok = ok[:-1, :-1] & ok[:-1, 1:] & ok[1:, :-1] & ok[1:, 1:]
    if not cell_ok.any():
        raise ValueError("mesh terrain vide : corridor hors emprise MNT ?")

    t1 = np.stack([v00, v01, v11], axis=-1)[cell_ok]
    t2 = np.stack([v00, v11, v10], axis=-1)[cell_ok]
    faces = np.vstack([t1, t2])

    used = np.unique(faces)
    remap = np.full(h * w, -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    vertices = np.column_stack([Xc.ravel()[used], Yc.ravel()[used], Zc.ravel()[used]])
    faces = remap[faces]
    return TerrainMesh(crs=dem.crs, vertices=vertices, faces=faces)


def mesh_to_obj(mesh: TerrainMesh) -> str:
    """Sérialise un ``TerrainMesh`` au format Wavefront OBJ (faces 1-indexées)."""
    lines = [f"# rally-stage-builder terrain mesh ({mesh.crs})"]
    lines += [f"v {v[0]:.3f} {v[1]:.3f} {v[2]:.3f}" for v in mesh.vertices]
    lines += [f"f {f[0] + 1} {f[1] + 1} {f[2] + 1}" for f in mesh.faces]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- geojson IR
def _surface_list(cl: Centerline) -> list[str]:
    return [str(s) for s in cl.surface] if cl.surface is not None else []


def centerline_to_geojson(cl: Centerline) -> dict[str, Any]:
    """LineString 3D (E, N, Z) + arrays par station en propriétés."""
    z = cl.z if cl.z is not None else np.zeros(len(cl))
    coords = [[float(x), float(y), float(zz)] for (x, y), zz in zip(cl.xy, z, strict=True)]
    props: dict[str, Any] = {
        "crs": cl.crs,
        "length_m": cl.length_m,
        "distance_m": [float(d) for d in cl.distance_m],
        "heading_rad": [float(h) for h in cl.heading_rad],
    }
    if cl.camber_rad is not None:
        props["camber_rad"] = [float(c) for c in cl.camber_rad]
    if cl.width_m is not None:
        props["width_m"] = [float(v) for v in cl.width_m]
    if cl.surface is not None:
        props["surface"] = _surface_list(cl)
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": props,
    }


def _line_feature(xy: FloatArray, z: FloatArray | None, props: dict[str, Any]) -> dict[str, Any]:
    if z is not None:
        coords = [[float(x), float(y), float(zz)] for (x, y), zz in zip(xy, z, strict=True)]
    else:
        coords = [[float(x), float(y)] for x, y in xy]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": props,
    }


def barriers_to_geojson(b: Barriers) -> dict[str, Any]:
    """FeatureCollection : bordure gauche + bordure droite."""
    return {
        "type": "FeatureCollection",
        "properties": {"crs": b.crs},
        "features": [
            _line_feature(b.left_xy, b.left_z, {"side": "left"}),
            _line_feature(b.right_xy, b.right_z, {"side": "right"}),
        ],
    }


def surfaces_to_geojson(cl: Centerline) -> dict[str, Any]:
    """FeatureCollection : segments de surface contigus (par distance)."""
    if cl.surface is None:
        return {"type": "FeatureCollection", "features": []}
    runs = surface_runs(cl.distance_m, cl.surface)
    features = [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {"surface": str(kind), "start_m": start, "end_m": end},
        }
        for kind, start, end in runs
    ]
    return {"type": "FeatureCollection", "properties": {"crs": cl.crs}, "features": features}


# ---------------------------------------------------------------- AC CSV
def centerline_to_ac_csv(cl: Centerline, origin: tuple[float, float, float]) -> str:
    """CSV localisé pour ``io_import_accsv`` : colonnes AC ``X, Z, Y``.

    L'importeur Blender lit ``(row[0], row[2], -row[1])`` → sommet
    ``(E_local, N_local, Z_local)`` (Blender Z-up). On écrit donc, par point,
    ``E-E0 , -(Z-Z0) , N-N0``. ``origin`` (E0, N0, Z0) est reporté dans le manifeste.
    """
    e0, n0, z0 = origin
    z = cl.z if cl.z is not None else np.zeros(len(cl))
    rows = [
        f"{float(x) - e0:.4f},{-(float(zz) - z0):.4f},{float(y) - n0:.4f}"
        for (x, y), zz in zip(cl.xy, z, strict=True)
    ]
    return "\n".join(rows) + "\n"


def _origin(cl: Centerline) -> tuple[float, float, float]:
    z = cl.z if cl.z is not None else np.zeros(len(cl))
    return (float(cl.xy[:, 0].min()), float(cl.xy[:, 1].min()), float(np.nanmin(z)))


# ---------------------------------------------------------------- write
def write_bundle(bundle: StageBundle, out_dir: str | Path) -> dict[str, str]:
    """Écrit tous les fichiers de la bundle sous ``out_dir``. Retourne les chemins."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cl = bundle.centerline
    origin = _origin(cl)
    written: dict[str, str] = {}

    def _dump(name: str, obj: Any) -> None:
        p = out / name
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        written[name] = str(p)

    def _text(name: str, text: str) -> None:
        p = out / name
        p.write_text(text, encoding="utf-8")
        written[name] = str(p)

    _dump("centerline.geojson", centerline_to_geojson(cl))
    _dump("surfaces.geojson", surfaces_to_geojson(cl))
    _text("centerline_ac.csv", centerline_to_ac_csv(cl, origin))
    if bundle.barriers is not None:
        _dump("barriers.geojson", barriers_to_geojson(bundle.barriers))
    if bundle.terrain is not None:
        _text("terrain.obj", mesh_to_obj(bundle.terrain))

    runs = surface_runs(cl.distance_m, cl.surface) if cl.surface is not None else []
    manifest = {
        "name": bundle.name,
        "crs": bundle.crs,
        "length_m": cl.length_m,
        "n_stations": len(cl),
        "local_origin": {"E": origin[0], "N": origin[1], "Z": origin[2]},
        "surface_runs": [{"surface": str(k), "start_m": s, "end_m": e} for k, s, e in runs],
        "files": {k: Path(v).name for k, v in written.items()},
        "attribution": ATTRIBUTION,
        "metadata": bundle.metadata,
    }
    _dump("bundle.json", manifest)
    return written
