"""T3 — Centerline : waypoints → tracé routé sur le vrai réseau OSM, nettoyé et
rééchantillonné à pas constant.

Le tracé n'est **jamais** modélisé à la main : ``osmnx`` charge le réseau réel
dans la bbox (filtre permissif incluant track/unclassified/service), route
départ → vias → arrivée sur ce réseau, on suit la géométrie réelle des arêtes,
on projette dans le CRS de travail (EPSG:2056) puis on rééchantillonne à pas
constant. Les fonctions géométriques pures (rééchantillonnage, caps, stitching)
sont isolées et testées sans réseau (TDD) ; ``build_centerline`` orchestre.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from rsb.config import StageConfig
from rsb.geo.transforms import transform_points
from rsb.ir.types import Centerline

FloatArray = NDArray[np.floating[Any]]

# Types de routes OSM autorisés (permissif) : les spéciales empruntent des routes
# mineures — on inclut donc track/unclassified/service/residential/living_street.
_PERMISSIVE_HIGHWAYS = (
    "motorway|motorway_link|trunk|trunk_link|primary|primary_link|"
    "secondary|secondary_link|tertiary|tertiary_link|"
    "unclassified|residential|living_street|service|track|road"
)


def permissive_filter() -> str:
    """Filtre ``custom_filter`` osmnx, permissif (routes mineures incluses)."""
    return f'["highway"~"{_PERMISSIVE_HIGHWAYS}"]'


# --------------------------------------------------------------------- pur/TDD
def resample_polyline(xy: FloatArray, step: float) -> tuple[FloatArray, FloatArray]:
    """Rééchantillonne une polyligne (N, 2) à pas ``step`` constant.

    Retourne ``(points (M, 2), distance_m (M,))``. Le dernier point (fin exacte
    du tracé) est toujours inclus. Les points consécutifs dupliqués sont retirés.
    """
    if step <= 0:
        raise ValueError("step doit être > 0")
    xy = np.asarray(xy, dtype=np.float64)
    if xy.ndim != 2 or xy.shape[1] != 2:
        raise ValueError("resample_polyline attend un tableau (N, 2)")

    # supprime les points consécutifs identiques
    keep = np.ones(len(xy), dtype=bool)
    if len(xy) > 1:
        keep[1:] = np.any(np.diff(xy, axis=0) != 0.0, axis=1)
    xy = xy[keep]
    if len(xy) < 2:
        return xy.copy(), np.zeros(len(xy), dtype=np.float64)

    seg = np.diff(xy, axis=0)
    seglen = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seglen)])
    total = float(cum[-1])

    targets = np.arange(0.0, total, step, dtype=np.float64)
    if targets.size == 0 or targets[-1] < total - 1e-9:
        targets = np.append(targets, total)

    x = np.interp(targets, cum, xy[:, 0])
    y = np.interp(targets, cum, xy[:, 1])
    return np.column_stack([x, y]), targets


def polyline_headings(xy: FloatArray) -> FloatArray:
    """Cap de progression (rad) à chaque station : ``atan2(dN, dE)``.

    Différences centrées (``np.gradient``) pour un cap lissé, cohérent avec les
    normales utilisées par camber/barriers.
    """
    xy = np.asarray(xy, dtype=np.float64)
    if len(xy) < 2:
        return np.zeros(len(xy), dtype=np.float64)
    gx = np.gradient(xy[:, 0])
    gy = np.gradient(xy[:, 1])
    return np.arctan2(gy, gx)


# --------------------------------------------------------------- routage osmnx
def nearest_node(graph: Any, lon: float, lat: float) -> int:
    """Nœud OSM le plus proche de (lon, lat), distance équirectangulaire.

    Évite la dépendance scikit-learn/BallTree d'``osmnx.nearest_nodes`` sur graphe
    géographique : le snapping sur une petite bbox n'exige pas mieux.
    """
    ids = list(graph.nodes)
    if not ids:
        raise ValueError("graphe vide")
    xs = np.fromiter((graph.nodes[n]["x"] for n in ids), dtype=np.float64, count=len(ids))
    ys = np.fromiter((graph.nodes[n]["y"] for n in ids), dtype=np.float64, count=len(ids))
    coslat = math.cos(math.radians(lat))
    dx = (xs - lon) * coslat
    dy = ys - lat
    return int(ids[int(np.argmin(dx * dx + dy * dy))])


def route_waypoints(graph: Any, waypoints_lonlat: list[tuple[float, float]]) -> list[int]:
    """Snappe les waypoints (lon, lat) aux nœuds les plus proches et route sur le
    réseau (plus court chemin pondéré par la longueur), leg par leg."""
    import osmnx as ox

    if len(waypoints_lonlat) < 2:
        raise ValueError("il faut au moins 2 waypoints")
    node_ids = [nearest_node(graph, lon, lat) for lon, lat in waypoints_lonlat]

    route: list[int] = [node_ids[0]]
    for u, v in zip(node_ids[:-1], node_ids[1:], strict=True):
        if u == v:
            continue
        path = ox.routing.shortest_path(graph, u, v, weight="length")
        if path is None:
            raise ValueError(f"aucun chemin routable entre les nœuds {u} et {v}")
        route.extend(int(n) for n in path[1:])
    if len(route) < 2:
        raise ValueError("route dégénérée (waypoints trop proches ?)")
    return route


def _edge_coords(graph: Any, u: int, v: int) -> FloatArray:
    """Coordonnées (lon, lat) de l'arête u→v : suit ``geometry`` si présente."""
    pu = np.array([graph.nodes[u]["x"], graph.nodes[u]["y"]], dtype=np.float64)
    pv = np.array([graph.nodes[v]["x"], graph.nodes[v]["y"]], dtype=np.float64)
    data = graph.get_edge_data(u, v)
    if not data:
        return np.vstack([pu, pv])
    best = min(data.values(), key=lambda d: d.get("length", math.inf))
    geom = best.get("geometry")
    if geom is None:
        return np.vstack([pu, pv])
    pts = np.asarray(geom.coords, dtype=np.float64)
    # oriente la géométrie de u vers v
    if np.hypot(*(pts[0] - pu)) > np.hypot(*(pts[0] - pv)):
        pts = pts[::-1]
    return pts


def nodes_to_coords(graph: Any, nodes: list[int]) -> FloatArray:
    """Reconstruit une polyligne (lon, lat) continue depuis une séquence de nœuds."""
    if len(nodes) < 2:
        raise ValueError("il faut au moins 2 nœuds")
    coords: list[list[float]] = []
    for u, v in zip(nodes[:-1], nodes[1:], strict=True):
        seg = _edge_coords(graph, u, v)
        if coords and np.allclose(coords[-1], seg[0], atol=1e-9):
            seg = seg[1:]
        coords.extend(seg.tolist())
    return np.asarray(coords, dtype=np.float64)


def load_network(cfg: StageConfig, cache_dir: Path) -> Any:
    """Charge le réseau OSM de la bbox effective (cache osmnx sous ``cache_dir``)."""
    import osmnx as ox

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(Path(cache_dir) / "osmnx_cache")
    bbox = cfg.effective_bbox().as_tuple()  # (W, S, E, N) en EPSG:4326
    nf = cfg.route.network_filter
    if nf == "permissive":
        return ox.graph_from_bbox(
            bbox, custom_filter=permissive_filter(), simplify=cfg.route.simplify
        )
    return ox.graph_from_bbox(bbox, network_type=nf, simplify=cfg.route.simplify)


def build_centerline(
    cfg: StageConfig, cache_dir: str | Path = "data", *, graph: Any | None = None
) -> Centerline:
    """Pipeline T3 complet : waypoints → tracé routé, projeté, rééchantillonné.

    ``graph`` peut être injecté (tests) pour court-circuiter le téléchargement OSM.
    """
    if graph is None:
        graph = load_network(cfg, Path(cache_dir))

    wps = [(wp.lon, wp.lat) for wp in cfg.ordered_waypoints()]
    route = route_waypoints(graph, wps)
    lonlat = nodes_to_coords(graph, route)

    x, y = transform_points(lonlat[:, 0], lonlat[:, 1], cfg.crs.geographic, cfg.crs.work)
    projected = np.column_stack([x, y])

    pts, dist = resample_polyline(projected, cfg.route.resample_step_m)
    heading = polyline_headings(pts)
    return Centerline(crs=cfg.crs.work, xy=pts, distance_m=dist, heading_rad=heading)
