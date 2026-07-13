"""Transformations de CRS partagées (WGS84 ↔ CRS de travail métrique).

Fine couche au-dessus de ``pyproj`` avec ``always_xy=True`` (ordre lon/lat,
E/N — jamais lat/lon) pour éviter la confusion d'ordre des axes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer

FloatArray = NDArray[np.floating[Any]]


@lru_cache(maxsize=32)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def transform_points(
    lon_or_x: FloatArray, lat_or_y: FloatArray, src_crs: str, dst_crs: str
) -> tuple[FloatArray, FloatArray]:
    """Transforme des tableaux de coordonnées de ``src_crs`` vers ``dst_crs`` (ordre X/Y)."""
    tr = _transformer(src_crs, dst_crs)
    x, y = tr.transform(np.asarray(lon_or_x, dtype=float), np.asarray(lat_or_y, dtype=float))
    return np.asarray(x), np.asarray(y)


def transform_bbox(
    bbox: tuple[float, float, float, float], src_crs: str, dst_crs: str
) -> tuple[float, float, float, float]:
    """Reprojette une bbox (min_x, min_y, max_x, max_y).

    Les 4 coins sont transformés puis on reprend min/max (l'emprise reprojetée
    n'est plus un rectangle aligné, on prend son enveloppe).
    """
    min_x, min_y, max_x, max_y = bbox
    xs = np.array([min_x, max_x, min_x, max_x], dtype=float)
    ys = np.array([min_y, min_y, max_y, max_y], dtype=float)
    tx, ty = transform_points(xs, ys, src_crs, dst_crs)
    return (float(tx.min()), float(ty.min()), float(tx.max()), float(ty.max()))
