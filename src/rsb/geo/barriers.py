"""T7 — Barriers : offset gauche/droite du bord de route → polylignes.

Qualité « good enough » (le décor est secondaire) : les bordures sont l'offset
latéral du bord de route (demi-largeur locale + marge), drapé sur le MNT si
fourni. Hook (non bloquant) : ``add_obstacles`` pour semer des obstacles.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.geo.drape import drape_z
from rsb.ir.types import Barriers, Centerline
from rsb.providers.dem import DEMRaster

FloatArray = NDArray[np.floating[Any]]


def _left_units(heading: FloatArray) -> FloatArray:
    """Vecteurs unitaires « gauche de la route » : (-sin h, cos h)."""
    h = np.asarray(heading, dtype=np.float64)
    return np.column_stack([-np.sin(h), np.cos(h)])


def offset_edges(
    xy: FloatArray, heading: FloatArray, half_width: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Bords gauche et droit décalés de ``half_width`` (par station) de part et d'autre."""
    xy = np.asarray(xy, dtype=np.float64)
    hw = np.asarray(half_width, dtype=np.float64).reshape(-1, 1)
    left_u = _left_units(heading)
    left = xy + hw * left_u
    right = xy - hw * left_u
    return left, right


def build_barriers(
    cl: Centerline,
    dem: DEMRaster | None = None,
    *,
    edge_offset_m: float = 0.5,
    default_width: float = 6.0,
) -> Barriers:
    """Construit les bordures depuis la centerline.

    La demi-largeur = ``width_m/2`` (si camber calculé, sinon ``default_width/2``)
    plus ``edge_offset_m`` (la bordure est légèrement au-delà du bord roulable).
    Z drapé sur le MNT si ``dem`` est fourni.
    """
    width = cl.width_m if cl.width_m is not None else np.full(len(cl), default_width)
    half = np.asarray(width, dtype=np.float64) / 2.0 + edge_offset_m
    left, right = offset_edges(cl.xy, cl.heading_rad, half)

    left_z: FloatArray | None = None
    right_z: FloatArray | None = None
    if dem is not None:
        left_z = drape_z(dem, left, cl.crs)
        right_z = drape_z(dem, right, cl.crs)
    elif cl.z is not None:
        left_z = cl.z.copy()
        right_z = cl.z.copy()

    return Barriers(crs=cl.crs, left_xy=left, right_xy=right, left_z=left_z, right_z=right_z)
