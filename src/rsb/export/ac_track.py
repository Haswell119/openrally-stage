"""Export « prêt pour Assetto Corsa » SANS Blender.

À partir de l'IR (centerline drapée + MNT), génère la **géométrie AC** :

* ``1ROAD``  — ruban de route roulable (à la vraie largeur, profil lissé) ;
* ``1KERB``  — bordures/trottoirs surélevés dans les virages ;
* ``1WALL``  — barrières de sécurité, placées **d'après le MNT** là où le terrain
  s'effondre au bord de la route (dévers/ravin) ;
* ``1GRASS`` — terrain (corridor MNT) ;

plus les **objets logiques AC** (départ/arrivée point-à-point, pit, chrono) et les
**métadonnées** (surfaces.ini, ui_track.json, map.png). Sortie : un FBX importable
dans **ksEditor** (SDK Kunos) + un OBJ multi-objets de secours.

Convention : coordonnées **locales** (origine soustraite). Axe AC = **Y up**
(voir ``to_ac_xyz``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.geo.camber import smooth_along_track
from rsb.geo.drape import drape_z
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster

FloatArray = NDArray[np.floating[Any]]
IntArray = NDArray[np.integer[Any]]

WALL_HEIGHT_M = 0.9
KERB_WIDTH_M = 0.45
KERB_HEIGHT_M = 0.10
WALL_DROP_THRESHOLD_M = 1.2  # chute du terrain au bord → barrière
WALL_PROBE_M = 3.0  # distance au-delà du bord où l'on sonde le MNT
KERB_MAX_RADIUS_M = 40.0  # bordures dans les virages plus serrés que ça


@dataclass
class NamedMesh:
    """Un objet nommé (convention AC) : sommets locaux (E, N, Z) + triangles."""

    name: str
    vertices: FloatArray  # (V, 3) local E, N, Z
    faces: IntArray  # (F, 3)


@dataclass
class AcObject:
    """Objet logique AC (empty) : nom + position locale (E, N, Z)."""

    name: str
    pos: tuple[float, float, float]


@dataclass
class AcTrack:
    """Ensemble prêt pour l'export AC."""

    name: str
    origin: tuple[float, float, float]  # E0, N0, Z0 (pour recaler en LV95)
    meshes: list[NamedMesh] = field(default_factory=list)
    objects: list[AcObject] = field(default_factory=list)


# --------------------------------------------------------------------- helpers
def _left_units(heading: FloatArray) -> FloatArray:
    h = np.asarray(heading, dtype=np.float64)
    return np.column_stack([-np.sin(h), np.cos(h)])


def _radius_m(heading: FloatArray, dist: FloatArray) -> FloatArray:
    theta = np.unwrap(np.asarray(heading, dtype=np.float64))
    kappa = np.abs(np.gradient(theta, np.asarray(dist, dtype=np.float64)))
    return 1.0 / np.maximum(kappa, 1e-6)


def _ribbon(left: FloatArray, right: FloatArray) -> tuple[FloatArray, IntArray]:
    """Triangule un ruban entre deux polylignes 3D de même longueur."""
    n = len(left)
    verts = np.vstack([left, right])
    faces: list[tuple[int, int, int]] = []
    for i in range(n - 1):
        li, ri, li1, ri1 = i, n + i, i + 1, n + i + 1
        faces.append((li, ri, ri1))
        faces.append((li, ri1, li1))
    return verts, np.asarray(faces, dtype=np.int64).reshape(-1, 3)


def _runs(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Segments contigus [start, end) où ``mask`` est vrai (au moins 2 stations)."""
    runs: list[tuple[int, int]] = []
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= 2:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


# ----------------------------------------------------------------- geometry
def build_road(cl: Centerline, road_z: FloatArray, half_width: FloatArray) -> NamedMesh:
    """Ruban de route roulable (profil lissé, section plane à la hauteur d'axe)."""
    left_u = _left_units(cl.heading_rad)
    hw = half_width.reshape(-1, 1)
    left = np.column_stack([cl.xy + hw * left_u, road_z])
    right = np.column_stack([cl.xy - hw * left_u, road_z])
    verts, faces = _ribbon(left, right)
    return NamedMesh("1ROAD", verts, faces)


def build_kerbs(cl: Centerline, road_z: FloatArray, half_width: FloatArray) -> NamedMesh | None:
    """Bordures/trottoirs surélevés le long des virages (rayon < seuil)."""
    radius = _radius_m(cl.heading_rad, cl.distance_m)
    corner = radius < KERB_MAX_RADIUS_M
    runs = _runs(corner)
    if not runs:
        return None
    left_u = _left_units(cl.heading_rad)
    all_v: list[FloatArray] = []
    all_f: list[IntArray] = []
    offset = 0
    for side in (+1, -1):  # bordure des deux côtés dans les virages
        for a, b in runs:
            sl = slice(a, b)
            hw = half_width[sl].reshape(-1, 1)
            inner = np.column_stack(
                [cl.xy[sl] + side * hw * left_u[sl], road_z[sl] + KERB_HEIGHT_M]
            )
            outer_xy = cl.xy[sl] + side * (hw + KERB_WIDTH_M) * left_u[sl]
            outer = np.column_stack([outer_xy, road_z[sl] + KERB_HEIGHT_M])
            v, f = _ribbon(inner, outer)
            all_v.append(v)
            all_f.append(f + offset)
            offset += len(v)
    if not all_v:
        return None
    return NamedMesh("1KERB", np.vstack(all_v), np.vstack(all_f))


def detect_wall_sides(
    cl: Centerline, dem: DEMRaster, road_z: FloatArray, half_width: FloatArray
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """Marque, par station, les côtés où poser une barrière : terrain qui plonge
    de plus de ``WALL_DROP_THRESHOLD_M`` juste au-delà du bord de route."""
    left_u = _left_units(cl.heading_rad)
    probe = (half_width + WALL_PROBE_M).reshape(-1, 1)
    left_pts = cl.xy + probe * left_u
    right_pts = cl.xy - probe * left_u
    zl = drape_z(dem, left_pts, cl.crs)
    zr = drape_z(dem, right_pts, cl.crs)
    left_drop = (road_z - zl) > WALL_DROP_THRESHOLD_M
    right_drop = (road_z - zr) > WALL_DROP_THRESHOLD_M
    return left_drop, right_drop


def build_walls(
    cl: Centerline,
    road_z: FloatArray,
    half_width: FloatArray,
    left_flag: NDArray[np.bool_],
    right_flag: NDArray[np.bool_],
) -> NamedMesh | None:
    """Barrières verticales le long des segments marqués (guardrail ~0,9 m)."""
    left_u = _left_units(cl.heading_rad)
    all_v: list[FloatArray] = []
    all_f: list[IntArray] = []
    offset = 0
    for side, flag in ((+1, left_flag), (-1, right_flag)):
        for a, b in _runs(flag):
            sl = slice(a, b)
            hw = (half_width[sl] + 0.3).reshape(-1, 1)
            base_xy = cl.xy[sl] + side * hw * left_u[sl]
            bottom = np.column_stack([base_xy, road_z[sl]])
            top = np.column_stack([base_xy, road_z[sl] + WALL_HEIGHT_M])
            v, f = _ribbon(bottom, top)
            all_v.append(v)
            all_f.append(f + offset)
            offset += len(v)
    if not all_v:
        return None
    return NamedMesh("1WALL", np.vstack(all_v), np.vstack(all_f))


def ac_objects(cl: Centerline, road_z: FloatArray, half_width: FloatArray) -> list[AcObject]:
    """Objets logiques AC : portes départ/arrivée (point-à-point), pit, chrono."""
    left_u = _left_units(cl.heading_rad)
    mid = len(cl) // 2

    def gate(i: int, prefix: str) -> list[AcObject]:
        hw = float(half_width[i]) + 1.0
        cx, cy = cl.xy[i]
        lx, ly = left_u[i]
        z = float(road_z[i])
        return [
            AcObject(f"{prefix}_L", (cx + hw * lx, cy + hw * ly, z)),
            AcObject(f"{prefix}_R", (cx - hw * lx, cy - hw * ly, z)),
        ]

    objs = gate(0, "AC_AB_START")
    objs += gate(len(cl) - 1, "AC_AB_FINISH")
    objs += gate(mid, "AC_TIME_0")
    objs.append(AcObject("AC_PIT_0", (float(cl.xy[0, 0]), float(cl.xy[0, 1]), float(road_z[0]))))
    return objs


def build_ac_track(
    cl: Centerline,
    dem: DEMRaster,
    name: str,
    *,
    default_width: float,
    terrain: NamedMesh | None = None,
    smooth_window_m: float = 10.0,
) -> AcTrack:
    """Assemble la géométrie AC depuis une centerline drapée + le MNT."""
    z_raw = cl.require_z()
    road_z = smooth_along_track(z_raw, cl.distance_m, smooth_window_m)
    width = cl.width_m if cl.width_m is not None else np.full(len(cl), default_width)
    half_width = np.asarray(width, dtype=np.float64) / 2.0

    e0 = float(cl.xy[:, 0].min())
    n0 = float(cl.xy[:, 1].min())
    z0 = float(np.nanmin(road_z))
    origin = (e0, n0, z0)

    meshes: list[NamedMesh] = [build_road(cl, road_z, half_width)]
    kerbs = build_kerbs(cl, road_z, half_width)
    if kerbs is not None:
        meshes.append(kerbs)
    lflag, rflag = detect_wall_sides(cl, dem, road_z, half_width)
    walls = build_walls(cl, road_z, half_width, lflag, rflag)
    if walls is not None:
        meshes.append(walls)
    if terrain is not None:
        meshes.append(NamedMesh("1GRASS", terrain.vertices, terrain.faces))

    objs = ac_objects(cl, road_z, half_width)

    # localise tout (origine soustraite)
    local_meshes = [NamedMesh(m.name, m.vertices - np.array([e0, n0, z0]), m.faces) for m in meshes]
    local_objs = [AcObject(o.name, (o.pos[0] - e0, o.pos[1] - n0, o.pos[2] - z0)) for o in objs]
    return AcTrack(name=name, origin=origin, meshes=local_meshes, objects=local_objs)


# ------------------------------------------------------------------ axe AC
def to_ac_xyz(v: FloatArray) -> tuple[float, float, float]:
    """(E, N, Z_local) → axe Assetto Corsa (Y up) : X = E, Y = altitude, Z = -N."""
    return (float(v[0]), float(v[2]), -float(v[1]))


# ------------------------------------------------------------------ writers
def write_obj(track: AcTrack) -> str:
    """OBJ multi-objets (un ``o <nom AC>`` par mesh), en axe AC."""
    lines = [f"# rally-stage-builder AC track: {track.name}"]
    voff = 1
    for m in track.meshes:
        lines.append(f"o {m.name}")
        for v in m.vertices:
            x, y, z = to_ac_xyz(v)
            lines.append(f"v {x:.4f} {y:.4f} {z:.4f}")
        for f in m.faces:
            lines.append(f"f {int(f[0]) + voff} {int(f[1]) + voff} {int(f[2]) + voff}")
        voff += len(m.vertices)
    return "\n".join(lines) + "\n"


def _face_normals_uv(verts_ac: FloatArray, faces: IntArray) -> tuple[list[float], list[float]]:
    """Normales (ByPolygonVertex) et UV planaires (X,Z) pour un mesh en axe AC."""
    normals: list[float] = []
    uvs: list[float] = []
    for f in faces:
        a, b, c = verts_ac[f[0]], verts_ac[f[1]], verts_ac[f[2]]
        n = np.cross(b - a, c - a)
        norm = float(np.linalg.norm(n))
        n = n / norm if norm > 1e-9 else np.array([0.0, 1.0, 0.0])
        for idx in (f[0], f[1], f[2]):
            normals.extend([float(n[0]), float(n[1]), float(n[2])])
            v = verts_ac[idx]
            uvs.extend([float(v[0]) / 4.0, float(v[2]) / 4.0])  # 1 UV = 4 m
    return normals, uvs


def _fmt_floats(vals: list[float] | FloatArray) -> str:
    return ",".join(f"{float(v):.5f}" for v in np.asarray(vals).ravel())


def _geometry_block(gid: int, mesh: NamedMesh) -> str:
    verts_ac = np.array([to_ac_xyz(v) for v in mesh.vertices], dtype=np.float64)
    coords: list[float] = verts_ac.ravel().tolist()
    # PolygonVertexIndex : dernier indice de chaque triangle négativé (~k = -k-1)
    pvi: list[int] = []
    for f in mesh.faces:
        pvi.extend([int(f[0]), int(f[1]), -int(f[2]) - 1])
    normals, uvs = _face_normals_uv(verts_ac, mesh.faces)
    return f"""	Geometry: {gid}, "Geometry::{mesh.name}", "Mesh" {{
		Vertices: *{len(coords)} {{
			a: {_fmt_floats(coords)}
		}}
		PolygonVertexIndex: *{len(pvi)} {{
			a: {",".join(str(i) for i in pvi)}
		}}
		GeometryVersion: 124
		LayerElementNormal: 0 {{
			Version: 101
			Name: ""
			MappingInformationType: "ByPolygonVertex"
			ReferenceInformationType: "Direct"
			Normals: *{len(normals)} {{
				a: {_fmt_floats(normals)}
			}}
		}}
		LayerElementUV: 0 {{
			Version: 101
			Name: "UVMap"
			MappingInformationType: "ByPolygonVertex"
			ReferenceInformationType: "Direct"
			UV: *{len(uvs)} {{
				a: {_fmt_floats(uvs)}
			}}
		}}
		LayerElementMaterial: 0 {{
			Version: 101
			Name: ""
			MappingInformationType: "AllSame"
			ReferenceInformationType: "IndexToDirect"
			Materials: *1 {{
				a: 0
			}}
		}}
		Layer: 0 {{
			Version: 100
			LayerElement:  {{ Type: "LayerElementNormal"; TypedIndex: 0 }}
			LayerElement:  {{ Type: "LayerElementUV"; TypedIndex: 0 }}
			LayerElement:  {{ Type: "LayerElementMaterial"; TypedIndex: 0 }}
		}}
	}}"""


def _model_block(mid: int, name: str, kind: str, pos: tuple[float, float, float] | None) -> str:
    trans = ""
    if pos is not None:
        trans = (
            '\n\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A+",'
            f"{pos[0]:.5f},{pos[1]:.5f},{pos[2]:.5f}"
        )
    return f"""	Model: {mid}, "Model::{name}", "{kind}" {{
		Version: 232
		Properties70:  {{{trans}
		}}
		Shading: Y
		Culling: "CullingOff"
	}}"""


def write_fbx(track: AcTrack) -> str:
    """Sérialise la piste en FBX ASCII 7.4 (importable dans ksEditor).

    Meshes nommés (1ROAD/1KERB/1WALL/1GRASS) + objets AC (Null). Axe Y up, mètres,
    coordonnées locales. ⚠️ Selon la version de ksEditor, si la piste est 100× trop
    grande, réimporter à l'échelle 0.01.
    """
    gid = 1000000
    mid = 2000000
    objects: list[str] = []
    connections: list[str] = []
    n_geom = 0
    n_model = 0

    for mesh in track.meshes:
        g, m = gid, mid
        gid += 1
        mid += 1
        objects.append(_geometry_block(g, mesh))
        objects.append(_model_block(m, mesh.name, "Mesh", None))
        connections.append(f'\tC: "OO", {m}, 0')
        connections.append(f'\tC: "OO", {g}, {m}')
        n_geom += 1
        n_model += 1

    for obj in track.objects:
        m = mid
        mid += 1
        objects.append(_model_block(m, obj.name, "Null", to_ac_xyz(np.asarray(obj.pos))))
        connections.append(f'\tC: "OO", {m}, 0')
        n_model += 1

    header = f"""; FBX 7.4.0 project file
; Généré par rally-stage-builder — piste Assetto Corsa
; ----------------------------------------------------

FBXHeaderExtension:  {{
	FBXHeaderVersion: 1003
	FBXVersion: 7400
	Creator: "rally-stage-builder"
}}
GlobalSettings:  {{
	Version: 1000
	Properties70:  {{
		P: "UpAxis", "int", "Integer", "",1
		P: "UpAxisSign", "int", "Integer", "",1
		P: "FrontAxis", "int", "Integer", "",2
		P: "FrontAxisSign", "int", "Integer", "",1
		P: "CoordAxis", "int", "Integer", "",0
		P: "CoordAxisSign", "int", "Integer", "",1
		P: "UnitScaleFactor", "double", "Number", "",1
	}}
}}

Definitions:  {{
	Version: 100
	Count: {n_geom + n_model + 1}
	ObjectType: "GlobalSettings" {{ Count: 1 }}
	ObjectType: "Geometry" {{ Count: {n_geom} }}
	ObjectType: "Model" {{ Count: {n_model} }}
}}
"""
    objects_section = "Objects:  {\n" + "\n".join(objects) + "\n}\n"
    connections_section = "Connections:  {\n" + "\n".join(connections) + "\n}\n"
    return header + "\n" + objects_section + "\n" + connections_section


_SURFACE_INI = """; surfaces.ini — types de surface Assetto Corsa (généré)
[SURFACE_0]
KEY=ROAD
FRICTION=1.0
WAV=asphalt.wav
DIRT_ADDITIVE=0
IS_VALID_TRACK=1
DAMPING=0
SIN_HEIGHT=0
SIN_LENGTH=0
VIBRATION_GAIN=0
VIBRATION_LENGTH=0

[SURFACE_1]
KEY=GRASS
FRICTION=0.6
WAV=grass.wav
DIRT_ADDITIVE=0.4
IS_VALID_TRACK=0
DAMPING=0.1

[SURFACE_2]
KEY=KERB
FRICTION=0.92
WAV=kerb.wav
DIRT_ADDITIVE=0
IS_VALID_TRACK=1
VIBRATION_GAIN=1.0
VIBRATION_LENGTH=1.5
"""


def surfaces_ini() -> str:
    """surfaces.ini AC de base (ROAD / GRASS / KERB)."""
    return _SURFACE_INI


def ui_track_json(track: AcTrack, length_m: float) -> dict[str, Any]:
    """Métadonnées ui_track.json (content/tracks/<piste>/ui/)."""
    return {
        "name": track.name,
        "description": "Spéciale générée par rally-stage-builder (usage simulation personnel).",
        "tags": ["rally", "point to point"],
        "country": "Switzerland",
        "length": f"{length_m:.0f}",
        "pitboxes": "1",
        "run": "point to point",
        "author": "rally-stage-builder",
        "version": "0.1",
    }


def write_ac_track(track: AcTrack, out_dir: str | Path, length_m: float) -> dict[str, str]:
    """Écrit les fichiers AC (OBJ + FBX + surfaces.ini + ui_track.json + objets)."""
    import json

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    def _w(name: str, text: str) -> None:
        (out / name).write_text(text, encoding="utf-8")
        written[name] = str(out / name)

    _w("track.obj", write_obj(track))
    _w("track.fbx", write_fbx(track))
    _w("surfaces.ini", surfaces_ini())
    _w(
        "ui_track.json",
        json.dumps(ui_track_json(track, length_m), ensure_ascii=False, indent=2),
    )
    _w(
        "ac_objects.json",
        json.dumps(
            {
                "origin_lv95": {"E": track.origin[0], "N": track.origin[1], "Z": track.origin[2]},
                "objects": [
                    {"name": o.name, "ac_xyz": to_ac_xyz(np.asarray(o.pos))} for o in track.objects
                ],
                "meshes": [
                    {"name": m.name, "vertices": len(m.vertices), "faces": len(m.faces)}
                    for m in track.meshes
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return written
