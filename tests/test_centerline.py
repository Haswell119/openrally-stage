"""Tests T3 (TDD) : rééchantillonnage, caps, stitching de route, build_centerline."""

import math

import networkx as nx
import numpy as np
import pytest
from shapely.geometry import LineString

from rsb.config import StageConfig
from rsb.geo.centerline import (
    build_centerline,
    centerline_from_lonlat,
    nodes_to_coords,
    permissive_filter,
    polyline_headings,
    resample_polyline,
    route_waypoints,
)


def test_resample_ligne_droite_pas_constant() -> None:
    xy = np.array([[0.0, 0.0], [10.0, 0.0]])
    pts, dist = resample_polyline(xy, step=2.0)
    # 0,2,4,6,8,10 → 6 points
    assert pts.shape == (6, 2)
    assert np.allclose(dist, [0, 2, 4, 6, 8, 10])
    assert np.allclose(pts[:, 1], 0.0)
    assert np.allclose(pts[:, 0], [0, 2, 4, 6, 8, 10])


def test_resample_inclut_toujours_le_dernier_point() -> None:
    xy = np.array([[0.0, 0.0], [7.0, 0.0]])
    pts, dist = resample_polyline(xy, step=2.0)
    # 0,2,4,6 puis 7 (endpoint) → dernier = 7
    assert dist[-1] == pytest.approx(7.0)
    assert np.allclose(pts[-1], [7.0, 0.0])


def test_resample_coude_conserve_la_longueur() -> None:
    xy = np.array([[0.0, 0.0], [0.0, 6.0], [8.0, 6.0]])  # L : 6 + 8 = 14
    pts, dist = resample_polyline(xy, step=1.0)
    assert dist[-1] == pytest.approx(14.0)
    # abscisses curvilignes monotones croissantes
    assert np.all(np.diff(dist) > 0)


def test_resample_supprime_points_dupliques() -> None:
    xy = np.array([[0.0, 0.0], [0.0, 0.0], [4.0, 0.0]])
    pts, dist = resample_polyline(xy, step=2.0)
    assert dist[-1] == pytest.approx(4.0)


def test_headings_directions_cardinales() -> None:
    east = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    north = np.array([[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]])
    diag = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    assert np.allclose(polyline_headings(east), 0.0)
    assert np.allclose(polyline_headings(north), math.pi / 2)
    assert np.allclose(polyline_headings(diag), math.pi / 4)


def test_permissive_filter_inclut_routes_mineures() -> None:
    f = permissive_filter()
    for kind in ("track", "unclassified", "service", "residential"):
        assert kind in f


def _toy_graph() -> nx.MultiDiGraph:
    """Petit graphe géographique : chaîne A-B-C-D le long de +lon, avec géométrie."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"
    coords = {1: (7.00, 46.10), 2: (7.01, 46.10), 3: (7.02, 46.10), 4: (7.03, 46.10)}
    for n, (x, y) in coords.items():
        G.add_node(n, x=x, y=y)
    for u, v in [(1, 2), (2, 3), (3, 4)]:
        p1, p2 = coords[u], coords[v]
        length = math.dist(p1, p2) * 111_000  # approx m
        G.add_edge(u, v, key=0, length=length, geometry=LineString([p1, p2]))
        G.add_edge(v, u, key=0, length=length, geometry=LineString([p2, p1]))
    return G


def test_route_waypoints_snap_et_chemin() -> None:
    G = _toy_graph()
    # waypoints proches de A puis D
    nodes = route_waypoints(G, [(7.001, 46.1005), (7.029, 46.1002)])
    assert nodes[0] == 1
    assert nodes[-1] == 4
    # passe par tous les nœuds intermédiaires
    assert nodes == [1, 2, 3, 4]


def test_nodes_to_coords_suit_la_geometrie() -> None:
    G = _toy_graph()
    coords = nodes_to_coords(G, [1, 2, 3, 4])
    assert coords.shape[1] == 2
    # commence près de A, finit près de D, longitudes croissantes
    assert coords[0, 0] == pytest.approx(7.00, abs=1e-6)
    assert coords[-1, 0] == pytest.approx(7.03, abs=1e-6)
    assert np.all(np.diff(coords[:, 0]) >= -1e-9)


def test_build_centerline_avec_graphe_injecte() -> None:
    G = _toy_graph()
    cfg = StageConfig(
        name="toy",
        title="toy",
        waypoints=[
            {"role": "start", "lat": 46.1005, "lon": 7.001},
            {"role": "end", "lat": 46.1002, "lon": 7.029},
        ],
        route={"resample_step_m": 5.0},
    )
    cl = build_centerline(cfg, graph=G)
    assert cl.crs == "EPSG:2056"
    assert len(cl) >= 2
    # coordonnées projetées plausibles pour le Valais (E~2.5M, N~1.1M)
    assert 2_400_000 < cl.xy[0, 0] < 2_800_000
    assert 1_050_000 < cl.xy[0, 1] < 1_300_000
    # pas de rééchantillonnage ~ constant
    steps = np.diff(cl.distance_m)
    assert np.all(steps > 0)
    assert steps[:-1].max() - steps[:-1].min() < 1e-6 or len(steps) < 3
    # heading défini partout
    assert cl.heading_rad.shape == (len(cl),)


def test_centerline_from_lonlat_projette_et_rechantillonne() -> None:
    # trace (lon, lat) type GPX → centerline projetée en EPSG:2056
    lonlat = np.array([[7.0216, 46.1734], [7.030, 46.158], [7.0377, 46.1438]])
    cfg = StageConfig(name="x", title="x", gpx="dummy.gpx", route={"resample_step_m": 5.0})
    cl = centerline_from_lonlat(lonlat, cfg)
    assert cl.crs == "EPSG:2056"
    assert cl.length_m > 3000.0  # ~3,5 km
    assert 2_400_000 < cl.xy[0, 0] < 2_800_000  # E plausible (Valais)
    assert 1_050_000 < cl.xy[0, 1] < 1_300_000  # N plausible
    assert np.all(np.diff(cl.distance_m) > 0)


@pytest.mark.network
def test_build_centerline_reel_osm() -> None:
    # routage OSM réel entre 2 bornes (le seed utilise désormais un GPX)
    cfg = StageConfig(
        name="t",
        title="t",
        waypoints=[
            {"role": "start", "lat": 46.173, "lon": 7.022},
            {"role": "end", "lat": 46.144, "lon": 7.038},
        ],
    )
    cl = build_centerline(cfg)
    assert cl.length_m > 2000.0
    assert cl.crs == "EPSG:2056"
