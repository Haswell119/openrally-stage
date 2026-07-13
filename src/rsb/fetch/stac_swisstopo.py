"""Client STAC swisstopo → tuiles GeoTIFF du MNT swissALTI3D sur une bbox.

API STAC v1 : ``https://data.geo.admin.ch/api/stac/v1/``, collection
``ch.swisstopo.swissalti3d``. Le paramètre ``bbox`` de recherche est **toujours
en WGS84 (EPSG:4326)**, ordre (min_lon, min_lat, max_lon, max_lat). Chaque item
couvre une tuile 1 km² (LV95) et expose 4 assets : GeoTIFF (COG) et XYZ, chacun
en 0,5 m et 2 m. On sélectionne le GeoTIFF à la bonne résolution via le champ
STAC ``gsd`` + le media type GeoTIFF (nom du fichier : ``..._0.5_2056_*.tif``).

Licence : swisstopo Open Government Data (mention de la source appréciée).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

STAC_URL = "https://data.geo.admin.ch/api/stac/v1/"
COLLECTION = "ch.swisstopo.swissalti3d"


@dataclass(frozen=True)
class TileAsset:
    """Référence à un asset GeoTIFF d'une tuile MNT."""

    item_id: str
    key: str
    href: str
    gsd: float


def is_geotiff_at_resolution(media_type: str | None, gsd: object, resolution: float) -> bool:
    """Prédicat pur : cet asset est-il un GeoTIFF à la résolution demandée ?

    Isolé pour être testable sans réseau.
    """
    if not media_type or "geotiff" not in media_type.lower():
        return False
    if gsd is None:
        return False
    try:
        return abs(float(gsd) - resolution) < 1e-9  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def search_assets(
    bbox_wgs84: tuple[float, float, float, float],
    resolution: float = 0.5,
    *,
    url: str = STAC_URL,
    collection: str = COLLECTION,
) -> list[TileAsset]:
    """Cherche les tuiles GeoTIFF intersectant ``bbox_wgs84`` à ``resolution`` (m)."""
    from pystac_client import Client

    client = Client.open(url)
    search = client.search(collections=[collection], bbox=list(bbox_wgs84))
    found: list[TileAsset] = []
    for item in search.items():
        for key, asset in item.assets.items():
            gsd = asset.extra_fields.get("gsd")
            if is_geotiff_at_resolution(asset.media_type, gsd, resolution):
                found.append(TileAsset(item.id, key, asset.href, float(gsd)))  # type: ignore[arg-type]
    return found


def download_assets(
    assets: list[TileAsset],
    cache_dir: Path,
    *,
    session: requests.Session | None = None,
    timeout: float = 120.0,
) -> list[Path]:
    """Télécharge les tuiles dans ``cache_dir`` (idempotent : saute si déjà là)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()
    paths: list[Path] = []
    for asset in assets:
        fname = asset.href.rsplit("/", 1)[-1]
        dst = cache_dir / fname
        if not dst.exists() or dst.stat().st_size == 0:
            _download_one(asset.href, dst, sess, timeout)
        paths.append(dst)
    return paths


def _download_one(url: str, dst: Path, session: requests.Session, timeout: float) -> None:
    tmp = dst.with_suffix(dst.suffix + ".part")
    with session.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
    tmp.replace(dst)
