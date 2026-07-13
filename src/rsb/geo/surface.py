"""T6 — Surface : applique les segments tarmac/terre de la config par station.

La segmentation part de la surface **par défaut** de la config ; chaque
``surface_override`` (défini par distance curviligne) la surcharge sur son
intervalle. En cas de recouvrement, le **dernier** override de la liste gagne.

Hook (non bloquant) : ``classify_from_ortho`` reste à implémenter pour affiner la
segmentation depuis une orthophoto SWISSIMAGE (swisstopo) — la config prime tant
qu'aucune ortho n'est fournie.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.config import StageConfig, SurfaceKind, SurfaceSegment
from rsb.ir.types import Centerline

FloatArray = NDArray[np.floating[Any]]


def assign_surfaces(
    distance_m: FloatArray,
    default_surface: SurfaceKind,
    overrides: list[SurfaceSegment],
) -> list[SurfaceKind]:
    """Type de surface par station selon la distance curviligne.

    Un segment couvre ``[start_m, end_m)`` (``end_m = None`` → jusqu'à la fin).
    """
    distance_m = np.asarray(distance_m, dtype=np.float64)
    surfaces = [default_surface] * len(distance_m)
    for i, d in enumerate(distance_m):
        for seg in overrides:  # le dernier override couvrant d gagne
            end = seg.end_m if seg.end_m is not None else float("inf")
            if seg.start_m <= d < end:
                surfaces[i] = seg.kind
    return surfaces


def assign_centerline_surfaces(cl: Centerline, cfg: StageConfig) -> Centerline:
    """Renseigne ``cl.surface`` depuis la config (mutation en place)."""
    cl.surface = assign_surfaces(cl.distance_m, cfg.default_surface, cfg.surface_overrides)
    return cl


def surface_runs(
    distance_m: FloatArray, surfaces: list[SurfaceKind]
) -> list[tuple[SurfaceKind, float, float]]:
    """Compacte la liste par station en segments contigus ``(kind, start_m, end_m)``.

    Représentation légère pour la sérialisation (IR / bundle).
    """
    distance_m = np.asarray(distance_m, dtype=np.float64)
    if len(surfaces) == 0:
        return []
    runs: list[tuple[SurfaceKind, float, float]] = []
    start = float(distance_m[0])
    current = surfaces[0]
    for i in range(1, len(surfaces)):
        if surfaces[i] != current:
            runs.append((current, start, float(distance_m[i])))
            current = surfaces[i]
            start = float(distance_m[i])
    runs.append((current, start, float(distance_m[-1])))
    return runs


def classify_from_ortho(*args: Any, **kwargs: Any) -> None:
    """Hook futur : classification tarmac/terre depuis une orthophoto SWISSIMAGE.

    Non implémenté (non bloquant) : la config prime pour l'instant.
    """
    raise NotImplementedError(
        "classification orthophoto SWISSIMAGE non implémentée (hook futur, non bloquant)"
    )
