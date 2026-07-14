"""Écriture **directe** d'un modèle Assetto Corsa ``.kn5`` (SANS ksEditor).

Le format KN5 (magic ``sc6969``, version 5) est réimplémenté d'après la
documentation publique reverse-engineerée du format (site hagn.io) et
recoupé octet par octet avec deux implémentations indépendantes
(export Blender ``moppius/blender-assetto-corsa-tools`` et lecteur
``MarvinSt/kn5-obj-converter``). Aucune ligne de ces projets n'est copiée :
seul le *layout binaire* — qui est une interface, non une œuvre — est suivi.

Disposition du fichier ::

    b"sc6969" + uint32 version(=5)
    TEXTURES : int32 count, [ int32 actif=1, string nom, blob données ] *
    MATERIALS: int32 count, [ string nom, string shader, byte alphaBlend,
               bool alphaTested, int32 depthMode,
               uint32 nProps, [string nom, float A, vec2 B, vec3 C, vec4 D]*,
               uint32 nTex,  [string input, uint32 slot, string texture]* ] *
    NODES    : arbre profondeur-d'abord depuis une racine « Node ».
               Node  (type 1) : name, uint32 nChildren, bool actif, matrix(16f)
               Mesh  (type 2) : name, uint32 nChildren(=0), bool actif,
                                bool castShadows, bool visible, bool transparent,
                                uint32 nVerts, [vec3 pos, vec3 nrm, vec2 uv,
                                vec3 tangent]*, uint32 nIdx, uint16 idx*,
                                uint32 materialId, uint32 layer, float lodIn,
                                float lodOut, vec3 bsphereC, float bsphereR,
                                bool renderable

Repère AC : Y up, mètres. Les sommets sont écrits en coordonnées AC via
``to_ac_xyz`` (identique à la conversion de l'export Blender officiel). La
translation d'un ``Node`` occupe les flottants 12–14 de la matrice (dernière
colonne, convention colonne-major) — les deux implémentations de référence
sont d'accord sur ce point.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.export.ac_track import AcTrack, NamedMesh

FloatArray = NDArray[np.floating[Any]]

KN5_MAGIC = b"sc6969"
KN5_VERSION = 5
_MAX_VERTS = 65535  # index uint16 → un mesh est découpé au-delà
_FACES_PER_CHUNK = _MAX_VERTS // 3  # expansion à plat : 3 sommets / triangle

# Couleur (RGB) de la texture unie par surface (le shader ksPerPixel n'exige pas
# de texture, mais une couleur rend chaque surface distincte à l'écran).
_SURFACE_RGB: dict[str, tuple[int, int, int]] = {
    "1ROAD": (56, 56, 60),
    "1KERB": (176, 42, 42),
    "1WALL": (150, 150, 156),
    "1GRASS": (78, 112, 60),
}
_DEFAULT_RGB = (128, 128, 128)


# --------------------------------------------------------------- primitives
def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _i32(v: int) -> bytes:
    return struct.pack("<i", v)


def _f32(v: float) -> bytes:
    return struct.pack("<f", v)


def _string(s: str) -> bytes:
    raw = s.encode("utf-8")
    return _u32(len(raw)) + raw


def _blob(b: bytes) -> bytes:
    return _u32(len(b)) + b


def _solid_png(rgb: tuple[int, int, int], size: int = 4) -> bytes:
    """Encode un PNG RGBA uni ``size×size`` (sans dépendance externe)."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF
        )

    r, g, b = rgb
    row = bytes([0]) + bytes([r, g, b, 255]) * size  # filtre 0 + pixels RGBA
    raw = row * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


# --------------------------------------------------------------- géométrie
def to_ac(vertices_en: FloatArray) -> FloatArray:
    """(E, N, Z) → coordonnées AC (X=E, Y=Z, Z=−N), vectorisé."""
    v = np.asarray(vertices_en, dtype=np.float64)
    return np.column_stack([v[:, 0], v[:, 2], -v[:, 1]])


@dataclass
class _Chunk:
    """Un bloc de mesh prêt pour KN5 : sommets entrelacés + indices séquentiels."""

    positions: FloatArray  # (V, 3) AC
    normals: FloatArray  # (V, 3)
    uvs: FloatArray  # (V, 2)
    tangents: FloatArray  # (V, 3)


def _face_tangents(
    p0: FloatArray,
    p1: FloatArray,
    p2: FloatArray,
    uv0: FloatArray,
    uv1: FloatArray,
    uv2: FloatArray,
    nrm: FloatArray,
) -> FloatArray:
    """Tangente par face depuis les UV ; repli orthogonal à la normale."""
    e1 = p1 - p0
    e2 = p2 - p0
    duv1 = uv1 - uv0
    duv2 = uv2 - uv0
    denom = duv1[:, 0] * duv2[:, 1] - duv2[:, 0] * duv1[:, 1]
    safe = np.abs(denom) > 1e-12
    r = np.where(safe, 1.0 / np.where(safe, denom, 1.0), 0.0)[:, None]
    tan = (e1 * duv2[:, 1, None] - e2 * duv1[:, 1, None]) * r
    # repli : une direction quelconque non colinéaire à la normale
    fallback = np.cross(nrm, np.array([1.0, 0.0, 0.0]))
    deg = np.linalg.norm(fallback, axis=1) < 1e-6
    fallback[deg] = np.cross(nrm[deg], np.array([0.0, 0.0, 1.0]))
    tan[~safe] = fallback[~safe]
    # orthonormalise contre la normale (Gram-Schmidt) puis normalise
    tan = tan - nrm * np.sum(nrm * tan, axis=1)[:, None]
    norm = np.linalg.norm(tan, axis=1)
    norm[norm < 1e-9] = 1.0
    result: FloatArray = tan / norm[:, None]
    return result


def _mesh_chunks(mesh: NamedMesh, uv_scale: float = 8.0) -> list[_Chunk]:
    """Convertit un ``NamedMesh`` en blocs KN5 (expansion à plat, découpe uint16).

    Chaque triangle donne 3 sommets indépendants portant la normale de face
    (ombrage plat, gère les faces double-face) ; les faces non finies sont
    ignorées. Les indices d'un bloc sont simplement ``0,1,2,…``.
    """
    vac = to_ac(mesh.vertices)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if len(faces) == 0:
        return []
    # écarte les triangles référençant un sommet non fini
    finite = np.all(np.isfinite(vac), axis=1)
    faces = faces[np.all(finite[faces], axis=1)]
    if len(faces) == 0:
        return []

    chunks: list[_Chunk] = []
    for start in range(0, len(faces), _FACES_PER_CHUNK):
        fchunk = faces[start : start + _FACES_PER_CHUNK]
        a = vac[fchunk[:, 0]]
        b = vac[fchunk[:, 1]]
        c = vac[fchunk[:, 2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n, axis=1)
        ln[ln < 1e-12] = 1.0
        n = n / ln[:, None]

        pos = np.empty((len(fchunk) * 3, 3), dtype=np.float64)
        pos[0::3], pos[1::3], pos[2::3] = a, b, c
        nrm = np.repeat(n, 3, axis=0)
        uv = np.column_stack([pos[:, 0] / uv_scale, pos[:, 2] / uv_scale])

        uv0, uv1, uv2 = uv[0::3], uv[1::3], uv[2::3]
        ftan = _face_tangents(a, b, c, uv0, uv1, uv2, n)
        tan = np.repeat(ftan, 3, axis=0)
        chunks.append(_Chunk(pos, nrm, uv, tan))
    return chunks


def _bounding_sphere(pos: FloatArray) -> tuple[tuple[float, float, float], float]:
    lo = pos.min(axis=0)
    hi = pos.max(axis=0)
    center = (lo + hi) / 2.0
    radius = float(np.max((hi - lo) / 2.0)) * 2.0
    return (float(center[0]), float(center[1]), float(center[2])), radius


# --------------------------------------------------------------- matériaux
@dataclass
class _Material:
    name: str
    shader: str
    texture: str


def _materials_for(track: AcTrack) -> tuple[list[_Material], dict[str, int], dict[str, bytes]]:
    """Un matériau (ksPerPixel + txDiffuse uni) par nom de mesh distinct."""
    materials: list[_Material] = []
    mat_index: dict[str, int] = {}
    textures: dict[str, bytes] = {}
    for mesh in track.meshes:
        if mesh.name in mat_index:
            continue
        rgb = _SURFACE_RGB.get(mesh.name, _DEFAULT_RGB)
        tex_name = f"{mesh.name.lower()}_rsb.png"
        textures[tex_name] = _solid_png(rgb)
        mat_index[mesh.name] = len(materials)
        materials.append(_Material(f"{mesh.name}_mat", "ksPerPixel", tex_name))
    return materials, mat_index, textures


def _material_bytes(mat: _Material) -> bytes:
    out = bytearray()
    out += _string(mat.name)
    out += _string(mat.shader)
    out += struct.pack("<B", 0)  # alphaBlendMode = Opaque
    out += struct.pack("<?", False)  # alphaTested
    out += _i32(0)  # depthMode = DepthNormal
    props = [("ksDiffuse", 0.5), ("ksAmbient", 0.5), ("ksSpecular", 0.1), ("ksSpecularEXP", 12.0)]
    out += _u32(len(props))
    for name, value_a in props:
        out += _string(name)
        out += _f32(value_a)
        out += struct.pack("<2f", 0.0, 0.0)  # valueB
        out += struct.pack("<3f", 0.0, 0.0, 0.0)  # valueC
        out += struct.pack("<4f", 0.0, 0.0, 0.0, 0.0)  # valueD
    out += _u32(1)  # une texture : txDiffuse
    out += _string("txDiffuse")
    out += _u32(0)  # slot
    out += _string(mat.texture)
    return bytes(out)


# --------------------------------------------------------------- nœuds
def _matrix_bytes(
    translation: tuple[float, float, float], heading_rad: float | None
) -> bytes:
    """Matrice 4×4 colonne-major : [right|up|forward|translation].

    Translation aux flottants 12–14. Avec ``heading_rad``, oriente l'axe
    *forward* (colonne 2) le long de la route (cap AC), sinon rotation identité.
    """
    tx, ty, tz = translation
    if heading_rad is None:
        cols = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    else:
        h = float(heading_rad)
        fx, fz = np.cos(h), -np.sin(h)  # forward (E,N)->AC : (cos h, 0, -sin h)
        rx, rz = -np.sin(h), -np.cos(h)  # right = up × forward
        cols = [rx, 0.0, rz, 0.0, 0.0, 1.0, 0.0, 0.0, fx, 0.0, fz, 0.0]
    vals = cols + [tx, ty, tz, 1.0]
    return struct.pack("<16f", *vals)


def _base_node_bytes(
    name: str,
    n_children: int,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    heading_rad: float | None = None,
) -> bytes:
    out = bytearray()
    out += _u32(1)  # class Node
    out += _string(name)
    out += _u32(n_children)
    out += struct.pack("<?", True)  # active
    out += _matrix_bytes(translation, heading_rad)
    return bytes(out)


def _mesh_node_bytes(name: str, chunk: _Chunk, material_id: int) -> bytes:
    out = bytearray()
    out += _u32(2)  # class Mesh
    out += _string(name)
    out += _u32(0)  # pas d'enfant
    out += struct.pack("<?", True)  # active
    out += struct.pack("<?", True)  # castShadows
    out += struct.pack("<?", True)  # visible
    out += struct.pack("<?", False)  # transparent
    n = len(chunk.positions)
    out += _u32(n)
    inter = np.empty((n, 11), dtype=np.float32)
    inter[:, 0:3] = chunk.positions
    inter[:, 3:6] = chunk.normals
    inter[:, 6:8] = chunk.uvs
    inter[:, 8:11] = chunk.tangents
    out += inter.tobytes()
    out += _u32(n)  # indices séquentiels 0..n-1 (expansion à plat)
    out += np.arange(n, dtype="<u2").tobytes()
    out += _u32(material_id)
    out += _u32(0)  # layer
    out += _f32(0.0)  # lodIn
    out += _f32(1.0e9)  # lodOut (toujours visible)
    center, radius = _bounding_sphere(chunk.positions)
    out += struct.pack("<3f", *center)
    out += _f32(radius)
    out += struct.pack("<?", True)  # renderable
    return bytes(out)


# --------------------------------------------------------------- API
def write_kn5(track: AcTrack) -> bytes:
    """Sérialise ``track`` en un modèle KN5 (bytes) prêt pour ``content/tracks/``."""
    materials, mat_index, textures = _materials_for(track)

    # blocs de mesh (avec découpe uint16) + comptage des enfants de la racine
    mesh_nodes: list[bytes] = []
    for mesh in track.meshes:
        mid = mat_index[mesh.name]
        for chunk in _mesh_chunks(mesh):
            mesh_nodes.append(_mesh_node_bytes(mesh.name, chunk, mid))

    object_nodes: list[bytes] = []
    for obj in track.objects:
        ac_pos = to_ac(np.asarray([obj.pos]))[0]
        heading = getattr(obj, "heading_rad", None)
        object_nodes.append(
            _base_node_bytes(
                obj.name,
                0,
                (float(ac_pos[0]), float(ac_pos[1]), float(ac_pos[2])),
                heading,
            )
        )

    out = bytearray()
    out += KN5_MAGIC
    out += _u32(KN5_VERSION)

    # textures
    tex_items = list(textures.items())
    out += _i32(len(tex_items))
    for tex_name, data in tex_items:
        out += _i32(1)  # actif
        out += _string(tex_name)
        out += _blob(data)

    # matériaux
    out += _i32(len(materials))
    for mat in materials:
        out += _material_bytes(mat)

    # nœuds : racine + meshes + objets (tous enfants directs de la racine)
    n_children = len(mesh_nodes) + len(object_nodes)
    out += _base_node_bytes(track.name or "root", n_children)
    for nb in mesh_nodes:
        out += nb
    for nb in object_nodes:
        out += nb

    return bytes(out)


# --------------------------------------------------------------- lecteur
class _Reader:
    """Petit lecteur binaire (pour valider une sortie par aller-retour)."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        b = self.data[self.pos : self.pos + n]
        if len(b) != n:
            raise ValueError("KN5 tronqué")
        self.pos += n
        return b

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def i32(self) -> int:
        return int(struct.unpack("<i", self.take(4))[0])

    def f32(self) -> float:
        return float(struct.unpack("<f", self.take(4))[0])

    def string(self) -> str:
        return self.take(self.u32()).decode("utf-8")


def read_kn5(data: bytes) -> dict[str, Any]:
    """Parse un KN5 (version 5) et **consomme tout le fichier**.

    Lève ``ValueError`` si la structure est incohérente (magic, version, octets
    résiduels). Retourne ``{textures, materials, nodes}`` — sert de contrôle de
    non-régression du binaire produit par :func:`write_kn5`.
    """
    r = _Reader(data)
    if r.take(6) != KN5_MAGIC:
        raise ValueError("magic KN5 invalide")
    version = r.u32()
    if version != KN5_VERSION:
        raise ValueError(f"version KN5 non gérée : {version}")

    textures = []
    for _ in range(r.i32()):
        r.i32()  # actif
        name = r.string()
        blob = r.take(r.u32())
        textures.append({"name": name, "size": len(blob)})

    materials = []
    for _ in range(r.i32()):
        name = r.string()
        shader = r.string()
        r.take(1)  # alphaBlend
        r.take(1)  # alphaTested
        r.i32()  # depthMode
        for _p in range(r.u32()):
            r.string()  # prop name
            r.take(4 + 8 + 12 + 16)  # A + B + C + D
        tex_maps = []
        for _t in range(r.u32()):
            input_name = r.string()
            r.u32()  # slot
            tex_maps.append({"input": input_name, "texture": r.string()})
        materials.append({"name": name, "shader": shader, "textures": tex_maps})

    nodes: list[dict[str, Any]] = []

    def read_node() -> None:
        node_class = r.u32()
        name = r.string()
        n_children = r.u32()
        r.take(1)  # active
        node: dict[str, Any] = {"class": node_class, "name": name, "children": n_children}
        if node_class == 1:
            node["matrix"] = struct.unpack("<16f", r.take(64))
        elif node_class == 2:
            r.take(3)  # castShadows, visible, transparent
            n_verts = r.u32()
            verts = np.frombuffer(r.take(n_verts * 11 * 4), dtype="<f4").reshape(n_verts, 11)
            n_idx = r.u32()
            idx = np.frombuffer(r.take(n_idx * 2), dtype="<u2")
            node["material_id"] = r.u32()
            r.take(4 + 4 + 4)  # layer, lodIn, lodOut
            r.take(12 + 4)  # bounding sphere center + radius
            r.take(1)  # renderable
            node["vertices"] = verts
            node["indices"] = idx
        else:
            raise ValueError(f"classe de nœud non gérée : {node_class}")
        nodes.append(node)
        for _c in range(n_children):
            read_node()

    read_node()
    if r.pos != len(data):
        raise ValueError(f"octets résiduels : {len(data) - r.pos}")
    return {"version": version, "textures": textures, "materials": materials, "nodes": nodes}
