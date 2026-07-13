"""Abstraction d'altimétrie : ``DEMRaster`` + ``DEMProvider`` (strategy pattern).

*Suisse-first, pas Suisse-locked.* Le reste du pipeline (drape, camber, bundle)
ne dépend **que** de :

* ``DEMRaster`` — une grille d'altitude en mémoire, dans un CRS métrique, avec
  échantillonnage bilinéaire. C'est le seul objet raster que la couche géo
  manipule (inversion de dépendance : testable avec une grille synthétique, sans
  réseau).
* ``DEMProvider`` (ABC) — produit un ``DEMRaster`` pour une bbox WGS84.
  ``SwissAlti3DProvider`` (voir plus bas) est la première implémentation ;
  IGN / PNOA / Copernicus pourront s'ajouter **sans toucher** au reste.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from affine import Affine
from numpy.typing import NDArray

# Alias permissif : les MNT natifs sont souvent en float32 ; les calculs upcast en float64.
FloatArray = NDArray[np.floating[Any]]


@dataclass(frozen=True)
class DEMRaster:
    """Grille d'altitude régulière dans un CRS métrique (north-up).

    ``data`` est indexé ``[row, col]`` (row 0 = haut/nord). ``transform`` est
    l'``Affine`` rasterio qui envoie les coordonnées pixel *coin* (col, row) vers
    les coordonnées monde (x, y). Les valeurs ``nodata`` sont converties en NaN
    à l'échantillonnage.
    """

    data: FloatArray
    transform: Affine
    crs: str
    nodata: float | None = None

    def __post_init__(self) -> None:
        if self.data.ndim != 2:
            raise ValueError("DEMRaster.data doit être 2D [row, col]")

    # ------------------------------------------------------------------ infos
    @property
    def height(self) -> int:
        return int(self.data.shape[0])

    @property
    def width(self) -> int:
        return int(self.data.shape[1])

    @property
    def res(self) -> tuple[float, float]:
        """Résolution (x, y) en unités du CRS (valeurs positives)."""
        return (abs(self.transform.a), abs(self.transform.e))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) de l'emprise du raster."""
        x0, y0 = self.transform * (0, 0)
        x1, y1 = self.transform * (self.width, self.height)
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    # --------------------------------------------------------------- sampling
    def sample(self, en: FloatArray) -> FloatArray:
        """Interpolation bilinéaire de Z aux points ``en`` (M, 2) = (E, N).

        Retourne un tableau (M,) ; NaN hors emprise ou sur nodata. Les valeurs
        de la grille sont considérées situées au **centre** des pixels.
        """
        en = np.asarray(en, dtype=np.float64)
        if en.ndim != 2 or en.shape[1] != 2:
            raise ValueError("sample attend un tableau (M, 2) de (E, N)")
        x = en[:, 0]
        y = en[:, 1]

        inv = ~self.transform
        # coordonnées pixel (convention coin) puis passage au centre des pixels
        col = inv.a * x + inv.b * y + inv.c - 0.5
        row = inv.d * x + inv.e * y + inv.f - 0.5

        c0 = np.floor(col).astype(np.int64)
        r0 = np.floor(row).astype(np.int64)
        fc = col - c0
        fr = row - r0

        h, w = self.data.shape
        out = np.full(x.shape, np.nan, dtype=np.float64)

        # au moins un des 4 voisins doit exister ; on exige les 4 (bord = NaN)
        valid = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < w) & (r0 + 1 < h)
        if np.any(valid):
            ci = c0[valid]
            ri = r0[valid]
            fci = fc[valid]
            fri = fr[valid]
            v00 = self.data[ri, ci]
            v01 = self.data[ri, ci + 1]
            v10 = self.data[ri + 1, ci]
            v11 = self.data[ri + 1, ci + 1]
            if self.nodata is not None:
                for v in (v00, v01, v10, v11):
                    v[v == self.nodata] = np.nan
            top = v00 * (1 - fci) + v01 * fci
            bot = v10 * (1 - fci) + v11 * fci
            out[valid] = top * (1 - fri) + bot * fri
        return out

    def sample_xy(self, x: FloatArray, y: FloatArray) -> FloatArray:
        """Variante pratique : x et y séparés."""
        return self.sample(np.column_stack([np.asarray(x), np.asarray(y)]))

    # ------------------------------------------------------------------ grille
    def xyz_grid(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Retourne (X, Y, Z) aux centres de pixels — pratique pour un mesh."""
        cols = np.arange(self.width, dtype=np.float64) + 0.5
        rows = np.arange(self.height, dtype=np.float64) + 0.5
        cc, rr = np.meshgrid(cols, rows)
        X = self.transform.a * cc + self.transform.b * rr + self.transform.c
        Y = self.transform.d * cc + self.transform.e * rr + self.transform.f
        Z = self.data.astype(np.float64).copy()
        if self.nodata is not None:
            Z[self.nodata == Z] = np.nan
        return X, Y, Z

    def clip(self, bbox_en: tuple[float, float, float, float], margin: float = 0.0) -> DEMRaster:
        """Découpe le raster à une bbox (min_x, min_y, max_x, max_y) du CRS de travail."""
        min_x, min_y, max_x, max_y = bbox_en
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin
        inv = ~self.transform
        corners_x = np.array([min_x, max_x, min_x, max_x])
        corners_y = np.array([min_y, max_y, max_y, min_y])
        cols = inv.a * corners_x + inv.b * corners_y + inv.c
        rows = inv.d * corners_x + inv.e * corners_y + inv.f
        c0 = max(int(np.floor(cols.min())), 0)
        c1 = min(int(np.ceil(cols.max())), self.width)
        r0 = max(int(np.floor(rows.min())), 0)
        r1 = min(int(np.ceil(rows.max())), self.height)
        if c1 <= c0 or r1 <= r0:
            raise ValueError("clip : la bbox ne recouvre pas le raster")
        sub = self.data[r0:r1, c0:c1].copy()
        new_transform = self.transform * Affine.translation(c0, r0)
        return DEMRaster(data=sub, transform=new_transform, crs=self.crs, nodata=self.nodata)

    # -------------------------------------------------------------- fabriques
    @classmethod
    def from_plane(
        cls,
        *,
        origin: tuple[float, float],
        res: float,
        shape: tuple[int, int],
        slope_x: float = 0.0,
        slope_y: float = 0.0,
        intercept: float = 0.0,
        crs: str = "EPSG:2056",
    ) -> DEMRaster:
        """Fabrique un MNT synthétique en plan incliné (pour les tests / TDD).

        Z(x, y) = intercept + slope_x * (x - x0) + slope_y * (y - y0).
        ``origin`` = (x0, y0) coin haut-gauche ; north-up (res_y négatif).
        """
        h, w = shape
        transform = Affine(res, 0.0, origin[0], 0.0, -res, origin[1])
        cols = np.arange(w, dtype=np.float64) + 0.5
        rows = np.arange(h, dtype=np.float64) + 0.5
        cc, rr = np.meshgrid(cols, rows)
        X = transform.a * cc + transform.c
        Y = transform.e * rr + transform.f
        Z = intercept + slope_x * (X - origin[0]) + slope_y * (Y - origin[1])
        return cls(data=Z, transform=transform, crs=crs, nodata=None)

    @classmethod
    def mosaic_geotiffs(
        cls,
        paths: list[Path],
        crs: str | None = None,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> DEMRaster:
        """Mosaïque une liste de GeoTIFF (même CRS) en un ``DEMRaster``.

        ``bounds`` (min_x, min_y, max_x, max_y, dans le CRS des tuiles) limite la
        mosaïque à l'emprise utile — essentiel pour la mémoire à 0,5 m. Le dtype
        natif (souvent float32) est conservé.
        """
        import rasterio
        from rasterio.merge import merge

        if not paths:
            raise ValueError("mosaic_geotiffs : aucune tuile fournie")
        # ExitStack ferme tous les datasets déjà ouverts même si un open échoue.
        with ExitStack() as stack:
            srcs = [stack.enter_context(rasterio.open(p)) for p in paths]
            arr, transform = merge(srcs, bounds=bounds)
            src_crs = crs or (str(srcs[0].crs) if srcs[0].crs else "EPSG:2056")
            nodata = srcs[0].nodata
        data = np.asarray(arr[0])
        return cls(data=data, transform=transform, crs=src_crs, nodata=nodata)


class DEMProvider(ABC):
    """Interface d'altimétrie. Une implémentation = un pays / une source MNT."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifiant court de la source (ex. 'swissalti3d')."""

    @property
    @abstractmethod
    def crs(self) -> str:
        """CRS natif métrique du MNT retourné (ex. 'EPSG:2056')."""

    @abstractmethod
    def get_dem(self, bbox_wgs84: tuple[float, float, float, float], cache_dir: Path) -> DEMRaster:
        """Prépare et retourne un ``DEMRaster`` couvrant ``bbox_wgs84``.

        ``bbox_wgs84`` = (min_lon, min_lat, max_lon, max_lat). Les tuiles
        téléchargées sont mises en cache sous ``cache_dir`` (jamais committées).
        """


class SwissAlti3DProvider(DEMProvider):
    """MNT swissALTI3D (swisstopo) via STAC — première implémentation, CRS EPSG:2056.

    *Suisse-first.* Télécharge les tuiles GeoTIFF (0,5 m par défaut) intersectant
    la bbox, puis les mosaïque en limitant l'emprise au strict nécessaire
    (mémoire). Ajouter un autre pays = une nouvelle sous-classe de ``DEMProvider``,
    sans rien changer au reste du pipeline.
    """

    NATIVE_CRS = "EPSG:2056"

    def __init__(self, resolution: float = 0.5) -> None:
        if resolution not in (0.5, 2.0):
            raise ValueError("swissALTI3D : résolution supportée = 0.5 ou 2.0 m")
        self._resolution = resolution

    @property
    def name(self) -> str:
        return "swissalti3d"

    @property
    def crs(self) -> str:
        return self.NATIVE_CRS

    @property
    def resolution(self) -> float:
        return self._resolution

    def get_dem(self, bbox_wgs84: tuple[float, float, float, float], cache_dir: Path) -> DEMRaster:
        from rsb.fetch.stac_swisstopo import download_assets, search_assets
        from rsb.geo.transforms import transform_bbox

        assets = search_assets(bbox_wgs84, self._resolution)
        if not assets:
            raise RuntimeError(
                f"aucune tuile swissALTI3D {self._resolution} m pour la bbox {bbox_wgs84} "
                "(hors couverture Suisse ?)"
            )
        paths = download_assets(assets, cache_dir / self.name)
        bounds_2056 = transform_bbox(bbox_wgs84, "EPSG:4326", self.NATIVE_CRS)
        return DEMRaster.mosaic_geotiffs(paths, crs=self.NATIVE_CRS, bounds=bounds_2056)
