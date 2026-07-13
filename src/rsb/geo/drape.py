"""T4 — Drape : échantillonne l'altitude Z du MNT le long du tracé.

``drape_z`` reprojette au besoin les points vers le CRS du MNT, échantillonne
en bilinéaire (voir ``DEMRaster.sample``) et rebouche les éventuels trous (NaN
hors emprise / nodata) par interpolation le long de l'abscisse curviligne.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.geo.transforms import transform_points
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster

FloatArray = NDArray[np.floating[Any]]


def fill_nan(z: FloatArray, x: FloatArray) -> FloatArray:
    """Interpole linéairement les NaN de ``z`` en fonction de ``x`` (monotone).

    Les bords sont extrapolés en plateau (valeur valide la plus proche). Lève si
    toutes les valeurs sont NaN.
    """
    z = np.asarray(z, dtype=np.float64).copy()
    x = np.asarray(x, dtype=np.float64)
    nan = np.isnan(z)
    if not nan.any():
        return z
    if nan.all():
        raise ValueError("aucune altitude valide (tracé hors couverture MNT ?)")
    valid = ~nan
    z[nan] = np.interp(x[nan], x[valid], z[valid])
    return z


def drape_z(dem: DEMRaster, xy: FloatArray, xy_crs: str) -> FloatArray:
    """Retourne Z (N,) le long des points ``xy`` (N, 2) exprimés dans ``xy_crs``.

    Reprojette vers ``dem.crs`` si nécessaire, échantillonne, puis rebouche les
    trous par interpolation le long de l'abscisse curviligne.
    """
    xy = np.asarray(xy, dtype=np.float64)
    if xy.ndim != 2 or xy.shape[1] != 2:
        raise ValueError("drape_z attend un tableau (N, 2)")
    if xy_crs != dem.crs:
        ex, ny = transform_points(xy[:, 0], xy[:, 1], xy_crs, dem.crs)
        sample_xy = np.column_stack([ex, ny])
    else:
        sample_xy = xy

    z = dem.sample(sample_xy)

    # abscisse curviligne pour le rebouchage (dans le CRS d'origine du tracé)
    seg = np.diff(xy, axis=0)
    dist = np.concatenate([[0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])
    return fill_nan(z, dist)


def drape_centerline(cl: Centerline, dem: DEMRaster) -> Centerline:
    """Drape la centerline : renseigne ``cl.z`` (mutation en place) et la retourne."""
    cl.z = drape_z(dem, cl.xy, cl.crs)
    return cl
