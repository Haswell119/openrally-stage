"""Tests du modèle de configuration (T1)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from rsb.config import (
    BBox,
    StageConfig,
    SurfaceKind,
    load_stage,
    resolve_gpx_path,
)

SEED = Path("stages/chablais-2026/ss5-9-evionnaz-vernayaz/stage.toml")


def _base_waypoints() -> list[dict[str, object]]:
    return [
        {"role": "start", "lat": 46.18, "lon": 7.02, "name": "A"},
        {"role": "via", "lat": 46.16, "lon": 7.03},
        {"role": "end", "lat": 46.13, "lon": 7.04, "name": "B"},
    ]


def test_seed_stage_charge_et_valide() -> None:
    cfg = load_stage(SEED)
    assert cfg.name == "chablais-2026-ss5-9-evionnaz-vernayaz"
    assert cfg.crs.work == "EPSG:2056"
    assert cfg.default_surface is SurfaceKind.TARMAC
    # source = GPX (tracé réel) ; chemin résolu, pas de waypoints
    assert cfg.gpx is not None and cfg.gpx.endswith("stage.gpx")
    assert cfg.waypoints == []


def test_config_gpx_sans_waypoints_valide() -> None:
    cfg = StageConfig(name="x", title="x", gpx="t.gpx")
    assert cfg.gpx == "t.gpx"
    assert cfg.waypoints == []


def test_ni_gpx_ni_waypoints_invalide() -> None:
    with pytest.raises(ValidationError):
        StageConfig(name="x", title="x")  # ni gpx ni assez de waypoints


def test_resolve_gpx_path_relatif(tmp_path: Path) -> None:
    cfg = StageConfig(name="x", title="x", gpx="stage.gpx")
    out = resolve_gpx_path(cfg, tmp_path)
    assert out.gpx == str(tmp_path / "stage.gpx")
    # chemin absolu inchangé
    abs_cfg = StageConfig(name="x", title="x", gpx="/abs/stage.gpx")
    assert resolve_gpx_path(abs_cfg, tmp_path).gpx == "/abs/stage.gpx"


def test_waypoints_exigent_un_start_et_un_end() -> None:
    wp = _base_waypoints()
    wp[0]["role"] = "via"  # plus de start
    with pytest.raises(ValidationError):
        StageConfig(name="x", title="x", waypoints=wp)


def test_premier_waypoint_doit_etre_start() -> None:
    wp = [
        {"role": "via", "lat": 46.1, "lon": 7.0},
        {"role": "start", "lat": 46.2, "lon": 7.0},
        {"role": "end", "lat": 46.3, "lon": 7.0},
    ]
    with pytest.raises(ValidationError):
        StageConfig(name="x", title="x", waypoints=wp)


def test_segment_surface_bornes_invalides() -> None:
    with pytest.raises(ValidationError):
        StageConfig(
            name="x",
            title="x",
            waypoints=_base_waypoints(),
            surface_overrides=[{"kind": "gravel", "start_m": 500.0, "end_m": 100.0}],
        )


def test_extra_champ_interdit() -> None:
    with pytest.raises(ValidationError):
        StageConfig(name="x", title="x", waypoints=_base_waypoints(), inconnu=1)


def test_effective_bbox_derivee_des_waypoints() -> None:
    cfg = StageConfig(name="x", title="x", waypoints=_base_waypoints(), bbox_margin_m=400.0)
    bb = cfg.effective_bbox()
    # englobe tous les waypoints avec une marge
    assert bb.min_lon < 7.02
    assert bb.max_lon > 7.04
    assert bb.min_lat < 46.13
    assert bb.max_lat > 46.18


def test_effective_bbox_explicite_prioritaire() -> None:
    bb = BBox(min_lon=6.0, min_lat=46.0, max_lon=7.5, max_lat=46.5)
    cfg = StageConfig(name="x", title="x", waypoints=_base_waypoints(), bbox=bb)
    assert cfg.effective_bbox() == bb


def test_bbox_ordre_invalide() -> None:
    with pytest.raises(ValidationError):
        BBox(min_lon=7.5, min_lat=46.0, max_lon=6.0, max_lat=46.5)
