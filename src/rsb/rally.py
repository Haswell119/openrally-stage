"""Orchestration au niveau RALLYE : plusieurs spéciales en un lot.

Un rallye = un ``rally.toml`` + des sous-dossiers de spéciales. Le rallye fournit
des **valeurs par défaut** (deep-merge) héritées par chaque ``stage.toml`` (DRY
sur CRS/provider/largeur…), et ``build_rally`` construit **toutes** les spéciales
de façon **résiliente** : l'échec d'une spéciale n'interrompt pas les autres.
"""

from __future__ import annotations

import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rsb.config import StageConfig
from rsb.ir.types import StageBundle
from rsb.pipeline import build_stage
from rsb.providers.dem import DEMProvider, SwissAlti3DProvider

_PROVIDERS: dict[str, type[DEMProvider]] = {"swissalti3d": SwissAlti3DProvider}


class RallyStageRef(BaseModel):
    """Référence à une spéciale dans un rallye."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., min_length=1)
    dir: str | None = Field(default=None, description="Sous-dossier (défaut : id).")
    ss: list[int] = Field(default_factory=list, description="Numéros de SS où le tracé est couru.")
    day: int | None = None
    note: str | None = None

    def subdir(self) -> str:
        return self.dir or self.id


class RallyConfig(BaseModel):
    """Configuration d'un rallye complet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    country: str | None = None
    dem_provider: str = Field(default="swissalti3d")
    dem_resolution: float = Field(default=0.5)
    defaults: dict[str, Any] = Field(default_factory=dict)
    stages: list[RallyStageRef] = Field(..., min_length=1)

    def provider(self) -> DEMProvider:
        """Instancie le DEMProvider du rallye (extensible : IGN/PNOA/Copernicus…)."""
        cls = _PROVIDERS.get(self.dem_provider)
        if cls is None:
            raise ValueError(
                f"provider MNT inconnu : {self.dem_provider!r} (connus : {sorted(_PROVIDERS)})"
            )
        if cls is SwissAlti3DProvider:
            return SwissAlti3DProvider(resolution=self.dem_resolution)
        return cls()  # pragma: no cover — futurs providers


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Fusion récursive : ``override`` gagne ; les sous-dicts sont fusionnés."""
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_rally(path: str | Path) -> tuple[RallyConfig, Path]:
    """Charge un ``rally.toml`` (ou un dossier le contenant). Retourne (config, base_dir)."""
    p = Path(path)
    if p.is_dir():
        p = p / "rally.toml"
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    return RallyConfig.model_validate(raw), p.parent


def load_rally_stage(rally: RallyConfig, base_dir: Path, ref: RallyStageRef) -> StageConfig:
    """Charge un ``stage.toml`` avec les défauts du rallye fusionnés dessous."""
    stage_path = base_dir / ref.subdir() / "stage.toml"
    with stage_path.open("rb") as fh:
        raw = tomllib.load(fh)
    merged = deep_merge(rally.defaults, raw)  # le stage surcharge les défauts
    return StageConfig.model_validate(merged)


@dataclass
class StageResult:
    """Résultat de build d'une spéciale au sein d'un rallye."""

    id: str
    status: str  # "ok" | "skipped" | "failed"
    ss: list[int] = field(default_factory=list)
    length_m: float | None = None
    n_stations: int | None = None
    out_dir: str | None = None
    error: str | None = None
    bundle: StageBundle | None = None


@dataclass
class RallyReport:
    """Synthèse du build d'un rallye."""

    name: str
    title: str
    results: list[StageResult]

    @property
    def ok(self) -> list[StageResult]:
        return [r for r in self.results if r.status == "ok"]

    @property
    def failed(self) -> list[StageResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def total_length_m(self) -> float:
        return sum(r.length_m or 0.0 for r in self.results if r.status in ("ok", "skipped"))


def build_rally(
    rally_path: str | Path,
    *,
    out_root: str | Path = "outputs",
    cache_dir: str | Path = "data",
    only: list[str] | None = None,
    force: bool = False,
    preview: bool = True,
    write_overview: bool = True,
    dem_resolution: float | None = None,
    corridor_m: float = 30.0,
    mesh_res: float = 2.0,
) -> RallyReport:
    """Construit toutes les spéciales d'un rallye (résilient aux échecs).

    Le cache MNT/OSM est partagé entre spéciales. Une spéciale déjà construite est
    sautée sauf ``force``. Écrit ``<out_root>/<rally>/rally.json`` et un aperçu.
    """
    import json

    from rsb.ir.bundle import write_bundle

    rally, base_dir = load_rally(rally_path)
    if dem_resolution is not None:
        rally = rally.model_copy(update={"dem_resolution": dem_resolution})
    provider = rally.provider()
    rally_out = Path(out_root) / rally.name
    rally_out.mkdir(parents=True, exist_ok=True)

    selected = [s for s in rally.stages if only is None or s.id in only]
    results: list[StageResult] = []

    for ref in selected:
        out_dir = rally_out / ref.id
        manifest = out_dir / "bundle.json"
        if not force and manifest.exists():
            length = _existing_length(manifest)
            results.append(
                StageResult(
                    id=ref.id, status="skipped", ss=ref.ss, length_m=length, out_dir=str(out_dir)
                )
            )
            continue
        try:
            cfg = load_rally_stage(rally, base_dir, ref)
            bundle = build_stage(
                cfg,
                dem_provider=provider,
                cache_dir=cache_dir,
                out_dir=out_dir,
                corridor_m=corridor_m,
                mesh_res=mesh_res,
                write=True,
            )
            bundle.metadata["ss"] = ref.ss
            bundle.metadata["day"] = ref.day
            write_bundle(bundle, out_dir)  # ré-écrit avec les métadonnées SS
            if preview:
                from validate.preview3d import render_preview

                render_preview(bundle, out_dir / "preview.png")
            results.append(
                StageResult(
                    id=ref.id,
                    status="ok",
                    ss=ref.ss,
                    length_m=bundle.centerline.length_m,
                    n_stations=len(bundle.centerline),
                    out_dir=str(out_dir),
                    bundle=bundle,
                )
            )
        except Exception as exc:  # résilience : une SS ratée n'arrête pas le lot
            results.append(
                StageResult(
                    id=ref.id, status="failed", ss=ref.ss, error=f"{type(exc).__name__}: {exc}"
                )
            )

    report = RallyReport(name=rally.name, title=rally.title, results=results)

    rally_manifest = {
        "name": rally.name,
        "title": rally.title,
        "country": rally.country,
        "dem_provider": rally.dem_provider,
        "dem_resolution": rally.dem_resolution,
        "total_length_m": report.total_length_m,
        "generated_epoch": int(time.time()),
        "stages": [
            {
                "id": r.id,
                "ss": r.ss,
                "status": r.status,
                "length_m": r.length_m,
                "n_stations": r.n_stations,
                "error": r.error,
            }
            for r in results
        ],
        "attribution": {
            "osm": "© OpenStreetMap contributors (ODbL) — attribution obligatoire",
            "swisstopo": "Source : Office fédéral de topographie swisstopo (swissALTI3D, OGD)",
        },
    }
    (rally_out / "rally.json").write_text(
        json.dumps(rally_manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    if write_overview and report.ok:
        from validate.preview3d import render_rally_overview

        render_rally_overview(report, rally_out / "rally_overview.png")

    return report


def _existing_length(manifest: Path) -> float | None:
    import json

    try:
        return float(json.loads(manifest.read_text(encoding="utf-8")).get("length_m"))
    except (OSError, ValueError, TypeError):
        return None
