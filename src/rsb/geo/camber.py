"""T5 — Camber : coupes perpendiculaires du MNT → dévers + largeur par station.

Pour chaque station du tracé, on échantillonne le MNT le long de la **normale**
à la route (largeur de fenêtre = ``camber.cross_section_width_m``). On en déduit :

* le **dévers** (``camber_rad``) : pente transversale ajustée sur la portion
  centrale (largeur de route). Convention : **positif = la route penche à droite**
  (bord droit plus bas — voir ``ir.types``).
* une **largeur** par station : détectée quand le MNT montre une rupture claire
  de part et d'autre (plateforme sur talus/digue), sinon on retombe sur la
  largeur par défaut de la config. Hook (non bloquant) : une orthophoto
  (SWISSIMAGE) affinerait la largeur là où le MNT est plat.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.config import CamberConfig
from rsb.geo.drape import fill_nan, smooth_along_track
from rsb.ir.types import Centerline
from rsb.providers.dem import DEMRaster

FloatArray = NDArray[np.floating[Any]]


def cross_offsets(width: float, n: int) -> FloatArray:
    """Décalages transversaux réguliers de -W/2 à +W/2 (n points, positif = droite)."""
    if width <= 0 or n < 3:
        raise ValueError("width > 0 et n >= 3 requis")
    return np.linspace(-width / 2.0, width / 2.0, n)


def right_units(heading: FloatArray) -> FloatArray:
    """Vecteurs unitaires « droite de la route » : (sin h, -cos h) par station."""
    h = np.asarray(heading, dtype=np.float64)
    return np.column_stack([np.sin(h), -np.cos(h)])


def sample_cross_sections(
    dem: DEMRaster, xy: FloatArray, heading: FloatArray, offsets: FloatArray
) -> FloatArray:
    """Échantillonne Z sur les coupes perpendiculaires. Retour : (N_stations, n_offsets).

    Les NaN (bord d'emprise/nodata) sont rebouchés par ligne le long des offsets ;
    une ligne entièrement hors emprise reste NaN (traitée par défaut en aval).
    """
    xy = np.asarray(xy, dtype=np.float64)
    right = right_units(heading)  # (N, 2)
    # points (N, n, 2) = station + offset * direction droite
    pts = xy[:, None, :] + offsets[None, :, None] * right[:, None, :]
    n_stations, n_off = pts.shape[0], pts.shape[1]
    Z = dem.sample(pts.reshape(-1, 2)).reshape(n_stations, n_off)
    for i in range(n_stations):
        row = Z[i]
        if np.isnan(row).any() and np.isfinite(row).any():
            Z[i] = fill_nan(row, offsets)
    return Z


def fit_cross_slope(offsets: FloatArray, Z: FloatArray, road_width: float) -> FloatArray:
    """Dévers (rad) par station : régression de Z sur les offsets de la portion
    centrale (|offset| <= road_width/2). Positif = penche à droite."""
    offsets = np.asarray(offsets, dtype=np.float64)
    Z = np.asarray(Z, dtype=np.float64)
    central = np.abs(offsets) <= road_width / 2.0
    if central.sum() < 2:
        central = np.ones_like(offsets, dtype=bool)  # fenêtre trop étroite : tout
    tc = offsets[central]
    tc_c = tc - tc.mean()
    denom = float((tc_c**2).sum())
    Zc = Z[:, central]  # (N, m)

    slope = np.zeros(Z.shape[0], dtype=np.float64)
    valid = np.isfinite(Zc).all(axis=1)
    if denom > 0 and valid.any():
        num = ((Zc[valid] - Zc[valid].mean(axis=1, keepdims=True)) * tc_c).sum(axis=1)
        slope[valid] = num / denom
    return np.arctan(-slope)  # positif = bord droit plus bas


def estimate_widths(
    offsets: FloatArray,
    Z: FloatArray,
    road_width: float,
    default_width: float,
    *,
    flat_threshold: float = 0.2,
) -> FloatArray:
    """Largeur (m) par station.

    On ajuste le plan de la route (portion centrale), puis on cherche de chaque
    côté la première rupture (|résidu| > ``flat_threshold``). Si les deux côtés
    rompent dans la fenêtre → largeur = écart entre ruptures ; sinon (terrain
    plat, pas de signal) → ``default_width``. Résultat borné à la fenêtre.
    """
    offsets = np.asarray(offsets, dtype=np.float64)
    Z = np.asarray(Z, dtype=np.float64)
    n_stations, n_off = Z.shape
    window = float(offsets[-1] - offsets[0])
    center = int(np.argmin(np.abs(offsets)))
    central = np.abs(offsets) <= road_width / 2.0
    tc = offsets[central]
    tc_mean = tc.mean()
    denom = float(((tc - tc_mean) ** 2).sum())

    widths = np.full(n_stations, default_width, dtype=np.float64)
    for i in range(n_stations):
        z = Z[i]
        if not np.isfinite(z).all():
            continue  # ligne incomplète → défaut
        zc = z[central]
        a = float(((zc - zc.mean()) * (tc - tc_mean)).sum() / denom) if denom > 0 else 0.0
        b = float(zc.mean() - a * tc_mean)
        resid = np.abs(z - (a * offsets + b))

        # marche vers la gauche puis vers la droite depuis le centre
        left_edge = 0
        for j in range(center, -1, -1):
            if resid[j] > flat_threshold:
                left_edge = j + 1
                break
        right_edge = n_off - 1
        for j in range(center, n_off):
            if resid[j] > flat_threshold:
                right_edge = j - 1
                break

        broke_left = left_edge > 0
        broke_right = right_edge < n_off - 1
        if broke_left and broke_right:
            w = float(offsets[right_edge] - offsets[left_edge])
            widths[i] = min(max(w, 0.5), window)
        # sinon : pas de rupture bilatérale claire → défaut (déjà en place)
    return widths


def compute_camber(
    cl: Centerline, dem: DEMRaster, cfg: CamberConfig, default_width: float
) -> Centerline:
    """Renseigne ``cl.camber_rad`` et ``cl.width_m`` (mutation en place).

    Un filtre médian (``cfg.smooth_window_m``) atténue les pics de dévers/largeur
    dus au bruit du MNT (bords de talus, ponts, végétation).
    """
    offsets = cross_offsets(cfg.cross_section_width_m, cfg.n_samples)
    Z = sample_cross_sections(dem, cl.xy, cl.heading_rad, offsets)
    camber = fit_cross_slope(offsets, Z, road_width=default_width)
    width = estimate_widths(offsets, Z, road_width=default_width, default_width=default_width)
    cl.camber_rad = smooth_along_track(camber, cl.distance_m, cfg.smooth_window_m)
    cl.width_m = smooth_along_track(width, cl.distance_m, cfg.smooth_window_m)
    return cl
