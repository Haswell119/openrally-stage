"""Modèle de configuration d'une spéciale (``stage.toml``).

La configuration décrit *ce que l'utilisateur veut* (waypoints, surfaces,
largeur…) indépendamment de l'implémentation. Elle est validée par pydantic et
constitue le contrat d'entrée du pipeline ``rsb``.

Les waypoints sont donnés en **WGS84** (lat/lon, EPSG:4326) — c'est ce que
l'utilisateur lit sur une carte. Le CRS de *travail* (métrique) est
EPSG:2056 (CH1903+/LV95) par défaut.
"""

from __future__ import annotations

import math
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WaypointRole(StrEnum):
    """Rôle d'un waypoint dans la séquence de routage."""

    START = "start"
    VIA = "via"
    END = "end"


class SurfaceKind(StrEnum):
    """Type de surface d'un segment de la spéciale."""

    TARMAC = "tarmac"
    GRAVEL = "gravel"  # terre / gravier
    SNOW = "snow"
    SAND = "sand"


class Waypoint(BaseModel):
    """Un point de passage en WGS84 (lat/lon)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: WaypointRole
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude WGS84 (degrés).")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude WGS84 (degrés).")
    name: str | None = Field(default=None, description="Étiquette lisible (facultatif).")


class SurfaceSegment(BaseModel):
    """Segment de surface défini par distance curviligne le long du tracé.

    ``end_m = None`` signifie « jusqu'à la fin de la spéciale ». Ces segments
    **surchargent** la surface par défaut du parcours.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SurfaceKind
    start_m: float = Field(..., ge=0.0, description="Début du segment (m depuis le départ).")
    end_m: float | None = Field(default=None, description="Fin du segment (m) ; None = fin.")
    note: str | None = Field(default=None, description="Commentaire libre (roadbook).")

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.end_m is not None and self.end_m <= self.start_m:
            raise ValueError(
                f"segment surface invalide : end_m ({self.end_m}) <= start_m ({self.start_m})"
            )
        return self


class CrsConfig(BaseModel):
    """CRS géographique (entrée) et CRS de travail métrique (calculs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    geographic: str = Field(default="EPSG:4326", description="CRS des waypoints (WGS84).")
    work: str = Field(default="EPSG:2056", description="CRS métrique de travail (CH1903+/LV95).")


class BBox(BaseModel):
    """Boîte englobante en WGS84 (lon/lat). Optionnelle : sinon dérivée des waypoints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_lon: float = Field(..., ge=-180.0, le=180.0)
    min_lat: float = Field(..., ge=-90.0, le=90.0)
    max_lon: float = Field(..., ge=-180.0, le=180.0)
    max_lat: float = Field(..., ge=-90.0, le=90.0)

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.min_lon >= self.max_lon or self.min_lat >= self.max_lat:
            raise ValueError("bbox invalide : min doit être strictement < max sur lon et lat")
        return self

    def as_tuple(self) -> tuple[float, float, float, float]:
        """Retourne (min_lon, min_lat, max_lon, max_lat) — ordre STAC/WGS84."""
        return (self.min_lon, self.min_lat, self.max_lon, self.max_lat)


class RouteConfig(BaseModel):
    """Paramètres de routage et de rééchantillonnage de la centerline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    default_width_m: float = Field(
        default=6.0, gt=0.0, description="Largeur de route par défaut (m)."
    )
    resample_step_m: float = Field(default=2.0, gt=0.0, description="Pas de rééchantillonnage (m).")
    network_filter: Literal["permissive", "drive", "all"] = Field(
        default="permissive",
        description="Filtre OSM : 'permissive' inclut track/unclassified/service.",
    )
    simplify: bool = Field(default=True, description="Simplifier la topologie du graphe OSM.")


class CamberConfig(BaseModel):
    """Paramètres des coupes perpendiculaires (dévers/camber)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cross_section_width_m: float = Field(
        default=12.0, gt=0.0, description="Largeur totale de la coupe perpendiculaire (m)."
    )
    n_samples: int = Field(
        default=21, ge=3, description="Nombre d'échantillons par coupe (impair conseillé)."
    )
    smooth_window_m: float = Field(
        default=5.0,
        ge=0.0,
        description="Fenêtre de lissage médian du dévers/largeur (m ; 0 = aucun lissage).",
    )


class StageConfig(BaseModel):
    """Configuration complète d'une spéciale — contrat d'entrée du pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="Identifiant machine (slug).")
    title: str = Field(..., min_length=1, description="Titre lisible.")
    description: str | None = None
    direction: str | None = Field(default=None, description="Sens, ex. 'Evionnaz → Vernayaz'.")

    crs: CrsConfig = Field(default_factory=CrsConfig)
    bbox: BBox | None = Field(default=None, description="bbox WGS84 explicite (sinon dérivée).")
    bbox_margin_m: float = Field(
        default=300.0, ge=0.0, description="Marge autour des waypoints (m)."
    )

    route: RouteConfig = Field(default_factory=RouteConfig)
    camber: CamberConfig = Field(default_factory=CamberConfig)

    gpx: str | None = Field(
        default=None,
        description="Chemin d'un GPX (tracé réel) — source alternative aux waypoints.",
    )
    waypoints: list[Waypoint] = Field(default_factory=list)
    default_surface: SurfaceKind = Field(default=SurfaceKind.TARMAC)
    surface_overrides: list[SurfaceSegment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_source(self) -> Self:
        # source = GPX (tracé réel) OU waypoints (routage OSM). Au moins l'une.
        if self.gpx is not None:
            return self  # les waypoints sont facultatifs quand un GPX est fourni
        if len(self.waypoints) < 2:
            raise ValueError("il faut soit un `gpx`, soit au moins 2 waypoints")
        roles = [wp.role for wp in self.waypoints]
        n_start = roles.count(WaypointRole.START)
        n_end = roles.count(WaypointRole.END)
        if n_start != 1:
            raise ValueError(f"il faut exactement 1 waypoint 'start' (trouvé {n_start})")
        if n_end != 1:
            raise ValueError(f"il faut exactement 1 waypoint 'end' (trouvé {n_end})")
        if roles[0] != WaypointRole.START:
            raise ValueError("le premier waypoint doit être 'start'")
        if roles[-1] != WaypointRole.END:
            raise ValueError("le dernier waypoint doit être 'end'")
        if any(r not in (WaypointRole.START, WaypointRole.END, WaypointRole.VIA) for r in roles):
            raise ValueError("rôle de waypoint inconnu")
        # tous les intermédiaires doivent être 'via'
        if any(r != WaypointRole.VIA for r in roles[1:-1]):
            raise ValueError("les waypoints intermédiaires doivent avoir le rôle 'via'")
        return self

    def ordered_waypoints(self) -> list[Waypoint]:
        """Séquence de routage : start → vias (dans l'ordre) → end."""
        return list(self.waypoints)

    def effective_bbox(self) -> BBox:
        """bbox explicite si fournie, sinon dérivée des waypoints + marge.

        (Non applicable à une source GPX : la bbox y est dérivée du tracé.)
        """
        if self.bbox is not None:
            return self.bbox
        if not self.waypoints:
            raise ValueError(
                "effective_bbox : ni bbox explicite ni waypoints "
                "(source GPX → bbox dérivée du tracé, voir pipeline)"
            )
        lats = [wp.lat for wp in self.waypoints]
        lons = [wp.lon for wp in self.waypoints]
        return bbox_from_points(lats, lons, self.bbox_margin_m)


def bbox_from_points(lats: list[float], lons: list[float], margin_m: float) -> BBox:
    """bbox WGS84 englobant des points + marge (m).

    La marge est convertie en degrés (1° lat ≈ 111 320 m ; longitude ~ cos(lat)).
    """
    mid_lat = (min(lats) + max(lats)) / 2.0
    d_lat = margin_m / 111_320.0
    d_lon = margin_m / (111_320.0 * max(math.cos(math.radians(mid_lat)), 1e-6))
    return BBox(
        min_lon=min(lons) - d_lon,
        min_lat=min(lats) - d_lat,
        max_lon=max(lons) + d_lon,
        max_lat=max(lats) + d_lat,
    )


def load_stage(path: str | Path) -> StageConfig:
    """Charge et valide un ``stage.toml``. Résout un ``gpx`` relatif au fichier."""
    p = Path(path)
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = StageConfig.model_validate(raw)
    return resolve_gpx_path(cfg, p.parent)


def resolve_gpx_path(cfg: StageConfig, base_dir: Path) -> StageConfig:
    """Rend le chemin ``gpx`` absolu (relatif à ``base_dir`` si nécessaire)."""
    if cfg.gpx is None:
        return cfg
    gpx_path = Path(cfg.gpx)
    if not gpx_path.is_absolute():
        gpx_path = base_dir / gpx_path
    return cfg.model_copy(update={"gpx": str(gpx_path)})
