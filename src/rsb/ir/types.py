"""Types de la représentation intermédiaire (IR) — *stage bundle*.

Ces structures ne dépendent d'**aucun** éditeur (inversion de dépendance) : la
couche ``geo`` les produit, les exporteurs (Blender, RTB) les consomment. Elles
n'importent rien de la couche ``geo`` pour rester des données pures.

Conventions géométriques (CRS de travail métrique, ex. EPSG:2056) :

* ``xy`` : coordonnées (E, N) — Est, Nord.
* ``heading_rad`` : cap de progression, ``atan2(dN, dE)``.
* vecteur tangent ``t = (cos h, sin h)`` ; **gauche** de la route
  ``= (-sin h, cos h)`` (rotation +90° anti-horaire), **droite** ``= (sin h, -cos h)``.
* ``camber_rad`` : dévers de la coupe transversale. Signe **positif = la route
  penche vers la droite** (bord droit plus bas que le bord gauche).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.config import SurfaceKind

FloatArray = NDArray[np.floating[Any]]
IntArray = NDArray[np.integer[Any]]


@dataclass
class Centerline:
    """Tracé central rééchantillonné à pas constant, enrichi par le pipeline.

    ``xy`` et ``distance_m`` sont posés dès la construction (T3) ; ``z`` (T4),
    ``width_m`` / ``camber_rad`` (T5) et ``surface`` (T6) sont ajoutés ensuite.
    """

    crs: str
    xy: FloatArray  # (N, 2) — E, N
    distance_m: FloatArray  # (N,) — abscisse curviligne cumulée
    heading_rad: FloatArray  # (N,) — cap de progression
    z: FloatArray | None = None  # (N,) — altitude drapée
    width_m: FloatArray | None = None  # (N,) — largeur locale
    camber_rad: FloatArray | None = None  # (N,) — dévers local
    surface: list[SurfaceKind] | None = None  # (N,) — type de surface

    def __post_init__(self) -> None:
        n = self.xy.shape[0]
        if self.xy.ndim != 2 or self.xy.shape[1] != 2:
            raise ValueError("Centerline.xy doit être (N, 2)")
        for attr in ("distance_m", "heading_rad"):
            arr = getattr(self, attr)
            if arr.shape != (n,):
                raise ValueError(f"Centerline.{attr} doit être (N,) avec N={n}")

    def __len__(self) -> int:
        return int(self.xy.shape[0])

    @property
    def length_m(self) -> float:
        """Longueur totale de la spéciale (m)."""
        return float(self.distance_m[-1]) if len(self) else 0.0

    def require_z(self) -> FloatArray:
        if self.z is None:
            raise ValueError("centerline non drapée : Z manquant (voir geo.drape)")
        return self.z

    def xyz(self) -> FloatArray:
        """Retourne (N, 3) = E, N, Z (nécessite le drapage)."""
        z = self.require_z()
        return np.column_stack([self.xy, z])


@dataclass
class Barriers:
    """Bordures gauche/droite (offset du bord de route), en 2D ou 3D."""

    crs: str
    left_xy: FloatArray  # (N, 2)
    right_xy: FloatArray  # (N, 2)
    left_z: FloatArray | None = None  # (N,)
    right_z: FloatArray | None = None  # (N,)


@dataclass
class TerrainMesh:
    """Mesh de terrain (grille MNT clippée triangulée)."""

    crs: str
    vertices: FloatArray  # (V, 3) — E, N, Z
    faces: IntArray  # (F, 3) — indices de triangles

    def __post_init__(self) -> None:
        if self.vertices.ndim != 2 or self.vertices.shape[1] != 3:
            raise ValueError("TerrainMesh.vertices doit être (V, 3)")
        if self.faces.ndim != 2 or self.faces.shape[1] != 3:
            raise ValueError("TerrainMesh.faces doit être (F, 3)")


@dataclass
class StageBundle:
    """Représentation intermédiaire complète d'une spéciale."""

    name: str
    crs: str
    centerline: Centerline
    barriers: Barriers | None = None
    terrain: TerrainMesh | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
