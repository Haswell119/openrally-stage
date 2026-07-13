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


def smooth_along_track(values: FloatArray, distance_m: FloatArray, window_m: float) -> FloatArray:
    """Filtre médian le long du tracé (robuste aux pics de bruit du MNT).

    ``window_m <= 0`` → aucun lissage. La fenêtre est convertie en nombre impair
    d'échantillons à partir du pas médian. Utilitaire 1D réutilisable.
    """
    values = np.asarray(values, dtype=np.float64)
    if window_m <= 0 or len(values) < 3:
        return values
    from scipy.ndimage import median_filter

    steps = np.diff(np.asarray(distance_m, dtype=np.float64))
    step = float(np.median(steps)) if len(steps) else 1.0
    size = max(3, int(round(window_m / step)) if step > 0 else 3)
    if size % 2 == 0:
        size += 1
    return np.asarray(median_filter(values, size=size, mode="nearest"), dtype=np.float64)


def despike_elevation(
    z: FloatArray,
    distance_m: FloatArray,
    *,
    window_m: float = 60.0,
    n_sigma: float = 3.5,
    min_dev_m: float = 0.8,
    max_grade: float = 0.20,
    smooth_window_m: float = 6.0,
    iters: int = 3,
) -> FloatArray:
    """Rend un profil d'altitude **cohérent** : retire les pics aberrants.

    Réutilisable sur n'importe quel profil Z(s) (abscisse curviligne). Les pics
    non physiques — ponts/passages (le MNT bare-earth plonge sous le tablier),
    canopée, artefacts — sont détectés puis **interpolés** à travers, ce qui
    « pontifie » proprement la route au-dessus du ravin.

    Méthode (robuste, sans casser les vraies montées/descentes) :

    1. **Filtre de Hampel** (médiane glissante + MAD) sur ``iters`` passes :
       un point s'écartant de la tendance locale de plus de ``n_sigma·σ``
       (σ = 1,4826·MAD) ou de ``min_dev_m`` est marqué, puis remplacé par
       interpolation linéaire à partir des points sains voisins.
    2. **Garde-fou de pente** : les points dont la pente locale dépasse
       ``max_grade`` (ex. 20 %, plus raide que toute route) sont interpolés.
    3. **Lissage** final léger (``smooth_window_m``) pour un profil roulable.
    """
    z = np.asarray(z, dtype=np.float64).copy()
    s = np.asarray(distance_m, dtype=np.float64)
    n = len(z)
    if n < 5:
        return z
    from scipy.ndimage import median_filter

    steps = np.diff(s)
    step = float(np.median(steps)) if len(steps) else 1.0
    win = max(5, int(round(window_m / step)) if step > 0 else 5)
    if win % 2 == 0:
        win += 1

    flagged = np.zeros(n, dtype=bool)
    for _ in range(max(1, iters)):
        trend = median_filter(z, size=win, mode="nearest")
        mad = median_filter(np.abs(z - trend), size=win, mode="nearest")
        sigma = 1.4826 * mad
        thresh = np.maximum(n_sigma * sigma, min_dev_m)
        new = np.abs(z - trend) > thresh
        if not new.any():
            break
        flagged |= new
        good = ~flagged
        if good.sum() >= 2:
            z[flagged] = np.interp(s[flagged], s[good], z[good])

    # « pontifie » les zones de pente non physique (ponts/échangeurs) sous max_grade
    z = _bridge_steep_segments(z, s, max_grade)
    if smooth_window_m > 0:
        z = smooth_along_track(z, s, smooth_window_m)
        z = _bridge_steep_segments(z, s, max_grade)  # garantit la borne après lissage
    return z


def _bridge_steep_segments(z: FloatArray, s: FloatArray, max_grade: float) -> FloatArray:
    """Interpole itérativement les points bordant un **segment** trop pentu.

    Détecte la pente **de segment à segment** (pas la différence centrée, qui
    laisse passer les pics en zigzag), jusqu'à convergence sous ``max_grade``.
    """
    z = np.asarray(z, dtype=np.float64).copy()
    n = len(z)
    for _ in range(30):
        ds = np.diff(s)
        seg_slope = np.abs(np.diff(z)) / np.maximum(ds, 1e-6)
        bad = seg_slope > max_grade
        if not bad.any():
            break
        steep = np.zeros(n, dtype=bool)
        steep[:-1] |= bad  # extrémité gauche du segment pentu
        steep[1:] |= bad  # extrémité droite
        good = ~steep
        if good.sum() < 2:
            break
        bridged = z.copy()
        bridged[steep] = np.interp(s[steep], s[good], z[good])
        if np.allclose(bridged, z):
            break
        z = bridged
    return z


def despike_centerline(cl: Centerline, **kwargs: Any) -> Centerline:
    """Rend cohérente l'altitude de la centerline (``cl.z``) — mutation en place."""
    cl.z = despike_elevation(cl.require_z(), cl.distance_m, **kwargs)
    return cl
