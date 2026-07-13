"""Orchestration du pipeline : config → stage bundle (T2 → T8).

``build_stage`` enchaîne : MNT (DEMProvider) → centerline (osmnx) → drape Z →
camber → surfaces → barriers → mesh terrain → StageBundle. Le MNT et/ou le
graphe OSM peuvent être injectés (tests hors-ligne).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rsb.config import StageConfig, bbox_from_points
from rsb.geo.barriers import build_barriers
from rsb.geo.camber import compute_camber
from rsb.geo.centerline import build_centerline, centerline_from_lonlat
from rsb.geo.drape import drape_centerline
from rsb.geo.gpx import load_gpx_track
from rsb.geo.surface import assign_centerline_surfaces
from rsb.ir.bundle import dem_corridor_mesh, write_bundle
from rsb.ir.types import Centerline, StageBundle
from rsb.providers.dem import DEMProvider, DEMRaster, SwissAlti3DProvider


def build_stage(
    cfg: StageConfig,
    *,
    dem: DEMRaster | None = None,
    dem_provider: DEMProvider | None = None,
    graph: Any | None = None,
    cache_dir: str | Path = "data",
    out_dir: str | Path | None = None,
    dem_resolution: float = 0.5,
    corridor_m: float = 30.0,
    mesh_res: float = 2.0,
    write: bool = True,
) -> StageBundle:
    """Construit (et écrit) la stage bundle d'une spéciale.

    Retourne le ``StageBundle``. Si ``out_dir`` est fourni et ``write`` vrai, les
    fichiers de la bundle y sont écrits.
    """
    # Source du tracé : GPX (trace réelle) OU waypoints (routage OSM).
    gpx_lonlat = None
    if cfg.gpx is not None:
        gpx_lonlat, _ele = load_gpx_track(cfg.gpx, cfg.gpx_track)
        bbox_wgs84 = bbox_from_points(
            gpx_lonlat[:, 1].tolist(), gpx_lonlat[:, 0].tolist(), cfg.bbox_margin_m
        ).as_tuple()
    else:
        bbox_wgs84 = cfg.effective_bbox().as_tuple()

    if dem is None:
        provider = dem_provider or SwissAlti3DProvider(resolution=dem_resolution)
        dem = provider.get_dem(bbox_wgs84, Path(cache_dir))
        provider_name = provider.name
    else:
        provider_name = dem_provider.name if dem_provider is not None else "injected"

    cl: Centerline
    if gpx_lonlat is not None:
        cl = centerline_from_lonlat(gpx_lonlat, cfg)
    else:
        cl = build_centerline(cfg, cache_dir=cache_dir, graph=graph)
    drape_centerline(cl, dem)
    compute_camber(cl, dem, cfg.camber, cfg.route.default_width_m)
    assign_centerline_surfaces(cl, cfg)
    barriers = build_barriers(cl, dem=dem, default_width=cfg.route.default_width_m)
    terrain = dem_corridor_mesh(dem, cl.xy, corridor_m=corridor_m, target_res=mesh_res)

    bundle = StageBundle(
        name=cfg.name,
        crs=cfg.crs.work,
        centerline=cl,
        barriers=barriers,
        terrain=terrain,
        metadata={
            "title": cfg.title,
            "direction": cfg.direction,
            "source": "gpx" if cfg.gpx is not None else "osm",
            "dem_provider": provider_name,
            "dem_crs": dem.crs,
            "waypoints": [
                {"role": str(wp.role), "lat": wp.lat, "lon": wp.lon, "name": wp.name}
                for wp in cfg.ordered_waypoints()
            ],
        },
    )

    if write and out_dir is not None:
        write_bundle(bundle, out_dir)
    return bundle
