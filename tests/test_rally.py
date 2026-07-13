"""Tests niveau rallye : config, héritage des défauts, build résilient, aperçu."""

from pathlib import Path

import networkx as nx
import numpy as np
import pytest
from shapely.geometry import LineString

from rsb.providers.dem import DEMRaster
from rsb.rally import (
    RallyConfig,
    build_rally,
    deep_merge,
    load_rally,
    load_rally_stage,
)

CHABLAIS = "stages/chablais-2026"


def test_deep_merge_le_stage_gagne() -> None:
    base = {
        "crs": {"work": "EPSG:2056", "geographic": "EPSG:4326"},
        "route": {"default_width_m": 6.0},
    }
    override = {"crs": {"work": "EPSG:9999"}, "name": "x"}
    out = deep_merge(base, override)
    assert out["crs"]["work"] == "EPSG:9999"  # surcharge
    assert out["crs"]["geographic"] == "EPSG:4326"  # préservé
    assert out["route"]["default_width_m"] == 6.0  # préservé
    assert out["name"] == "x"


def test_load_rally_chablais() -> None:
    rally, base = load_rally(CHABLAIS)
    assert rally.name == "chablais-2026"
    assert rally.dem_provider == "swissalti3d"
    ids = [s.id for s in rally.stages]
    assert "ss5-9-evionnaz-vernayaz" in ids
    # une spéciale courue en SS5 et SS9
    ss59 = next(s for s in rally.stages if s.id == "ss5-9-evionnaz-vernayaz")
    assert ss59.ss == [5, 9]


def test_stage_demo_herite_des_defauts() -> None:
    rally, base = load_rally(CHABLAIS)
    ref = next(s for s in rally.stages if s.id == "ss-demo-plaine-evionnaz")
    cfg = load_rally_stage(rally, base, ref)
    # le stage.toml démo ne définit PAS ces valeurs → héritées des défauts du rallye
    assert cfg.crs.work == "EPSG:2056"
    assert cfg.route.network_filter == "permissive"
    assert cfg.camber.smooth_window_m == 5.0


def test_provider_inconnu_leve() -> None:
    r = RallyConfig(
        name="x",
        title="x",
        dem_provider="martien",
        stages=[{"id": "a"}],
    )
    with pytest.raises(ValueError):
        r.provider()


def _toy_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"
    coords = {1: (7.00, 46.10), 2: (7.01, 46.10), 3: (7.02, 46.10)}
    for n, (x, y) in coords.items():
        G.add_node(n, x=x, y=y)
    for u, v in [(1, 2), (2, 3)]:
        p1, p2 = coords[u], coords[v]
        length = np.hypot(p2[0] - p1[0], p2[1] - p1[1]) * 111_000
        G.add_edge(u, v, key=0, length=length, geometry=LineString([p1, p2]))
        G.add_edge(v, u, key=0, length=length, geometry=LineString([p2, p1]))
    return G


def _covering_dem() -> DEMRaster:
    # MNT synthétique couvrant les coords projetées du toy graph (Valais).
    from rsb.geo.transforms import transform_bbox

    minx, miny, maxx, maxy = transform_bbox((6.99, 46.09, 7.03, 46.11), "EPSG:4326", "EPSG:2056")
    return DEMRaster.from_plane(
        origin=(minx - 50, maxy + 50),
        res=1.0,
        shape=(int(maxy - miny) + 200, int(maxx - minx) + 200),
        slope_x=0.02,
        intercept=460.0,
    )


def test_build_rally_resilient(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Build d'un rallye jouet : 1 spéciale OK + 1 spéciale en échec → lot non interrompu."""
    # rallye jouet
    rally_dir = tmp_path / "toy"
    (rally_dir / "ok").mkdir(parents=True)
    (rally_dir / "bad").mkdir(parents=True)
    (rally_dir / "rally.toml").write_text(
        'name = "toy"\ntitle = "Toy"\n'
        "[defaults.crs]\nwork = 'EPSG:2056'\n"
        '[[stages]]\nid = "ok"\nss = [1]\n'
        '[[stages]]\nid = "bad"\nss = [2]\n',
        encoding="utf-8",
    )
    (rally_dir / "ok" / "stage.toml").write_text(
        'name = "ok"\ntitle = "OK"\n'
        '[[waypoints]]\nrole="start"\nlat=46.1005\nlon=7.001\n'
        '[[waypoints]]\nrole="end"\nlat=46.1002\nlon=7.019\n',
        encoding="utf-8",
    )
    # 'bad' n'a PAS de stage.toml → build échoue proprement pour cette SS
    (rally_dir / "bad" / "placeholder").write_text("", encoding="utf-8")

    dem = _covering_dem()
    graph = _toy_graph()
    # injecte dem + graphe dans build_stage pour éviter tout réseau
    import rsb.rally as rally_mod

    real_build_stage = rally_mod.build_stage

    def fake_build_stage(cfg, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.pop("dem_provider", None)
        return real_build_stage(cfg, dem=dem, graph=graph, **kwargs)

    monkeypatch.setattr(rally_mod, "build_stage", fake_build_stage)

    report = build_rally(
        rally_dir, out_root=tmp_path / "out", cache_dir=tmp_path / "cache", preview=False
    )
    statuses = {r.id: r.status for r in report.results}
    assert statuses["ok"] == "ok"
    assert statuses["bad"] == "failed"  # échec isolé, lot poursuivi
    assert len(report.ok) == 1
    # manifeste rallye écrit
    assert (tmp_path / "out" / "toy" / "rally.json").exists()
    # aperçu rallye rendu (au moins 1 spéciale OK)
    assert (tmp_path / "out" / "toy" / "rally_overview.png").exists()


def test_build_rally_skip_si_deja_construit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rally_dir = tmp_path / "toy"
    (rally_dir / "ok").mkdir(parents=True)
    (rally_dir / "rally.toml").write_text(
        'name = "toy"\ntitle = "Toy"\n[[stages]]\nid = "ok"\n', encoding="utf-8"
    )
    (rally_dir / "ok" / "stage.toml").write_text(
        'name = "ok"\ntitle = "OK"\n'
        '[[waypoints]]\nrole="start"\nlat=46.1005\nlon=7.001\n'
        '[[waypoints]]\nrole="end"\nlat=46.1002\nlon=7.019\n',
        encoding="utf-8",
    )
    out = tmp_path / "out" / "toy" / "ok"
    out.mkdir(parents=True)
    (out / "bundle.json").write_text('{"length_m": 1234.0}', encoding="utf-8")

    report = build_rally(rally_dir, out_root=tmp_path / "out", preview=False, write_overview=False)
    assert report.results[0].status == "skipped"
    assert report.results[0].length_m == 1234.0
