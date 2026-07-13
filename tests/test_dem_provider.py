"""Tests T2 : DEMRaster (échantillonnage bilinéaire), mosaïque GeoTIFF, provider."""

from pathlib import Path

import numpy as np
import pytest
from affine import Affine

from rsb.fetch.stac_swisstopo import is_geotiff_at_resolution
from rsb.providers.dem import DEMRaster, SwissAlti3DProvider


def test_sample_plan_incline_exact() -> None:
    # Z = 100 + 2*(x-2000) + 3*(y-1000) : bilinéaire exact sur un plan.
    dem = DEMRaster.from_plane(
        origin=(2000.0, 1200.0),
        res=0.5,
        shape=(400, 400),
        slope_x=2.0,
        slope_y=3.0,
        intercept=100.0,
    )
    # points strictement intérieurs (le bilinéaire vaut NaN sur le bord extérieur)
    pts = np.array([[2050.0, 1100.0], [2010.3, 1005.7], [2123.4, 1077.2]])
    got = dem.sample(pts)
    expected = 100.0 + 2.0 * (pts[:, 0] - 2000.0) + 3.0 * (pts[:, 1] - 1200.0)
    assert np.allclose(got, expected, atol=1e-6)


def test_sample_hors_emprise_est_nan() -> None:
    dem = DEMRaster.from_plane(origin=(0.0, 100.0), res=1.0, shape=(50, 50))
    got = dem.sample(np.array([[-10.0, 50.0], [1000.0, 50.0]]))
    assert np.all(np.isnan(got))


def test_bounds_et_resolution() -> None:
    dem = DEMRaster.from_plane(origin=(2000.0, 1100.0), res=0.5, shape=(100, 200))
    min_x, min_y, max_x, max_y = dem.bounds
    assert min_x == pytest.approx(2000.0)
    assert max_x == pytest.approx(2000.0 + 200 * 0.5)
    assert max_y == pytest.approx(1100.0)
    assert min_y == pytest.approx(1100.0 - 100 * 0.5)
    assert dem.res == pytest.approx((0.5, 0.5))


def test_clip_reduit_lemprise() -> None:
    dem = DEMRaster.from_plane(origin=(0.0, 500.0), res=1.0, shape=(500, 500))
    sub = dem.clip((100.0, 100.0, 200.0, 200.0))
    assert sub.width < dem.width and sub.height < dem.height
    # échantillon inchangé dans la zone commune
    pt = np.array([[150.0, 150.0]])
    assert np.allclose(dem.sample(pt), sub.sample(pt), atol=1e-6)


def _write_tile(
    path: Path, origin: tuple[float, float], res: float, shape: tuple[int, int], base: float
) -> None:
    import rasterio

    h, w = shape
    transform = Affine(res, 0.0, origin[0], 0.0, -res, origin[1])
    # valeurs = base + col + row pour vérifier le raccord
    rows, cols = np.mgrid[0:h, 0:w]
    data = (base + cols + rows).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs="EPSG:2056",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)


def test_mosaic_deux_geotiffs(tmp_path: Path) -> None:
    # deux tuiles adjacentes horizontalement (t1 à gauche, t2 à droite)
    t1 = tmp_path / "t1.tif"
    t2 = tmp_path / "t2.tif"
    _write_tile(t1, origin=(2000.0, 1100.0), res=1.0, shape=(10, 10), base=0.0)
    _write_tile(t2, origin=(2010.0, 1100.0), res=1.0, shape=(10, 10), base=100.0)
    dem = DEMRaster.mosaic_geotiffs([t1, t2], crs="EPSG:2056")
    assert dem.width == 20 and dem.height == 10
    # un point dans la tuile de gauche et un dans celle de droite
    left = dem.sample(np.array([[2000.5, 1099.5]]))[0]
    right = dem.sample(np.array([[2010.5, 1099.5]]))[0]
    assert left == pytest.approx(0.0, abs=1e-4)
    assert right == pytest.approx(100.0, abs=1e-4)


def test_predicat_selection_geotiff() -> None:
    gt = "image/tiff; application=geotiff; profile=cloud-optimized"
    assert is_geotiff_at_resolution(gt, 0.5, 0.5)
    assert not is_geotiff_at_resolution(gt, 2.0, 0.5)
    assert not is_geotiff_at_resolution("application/x.ascii-xyz+zip", 0.5, 0.5)
    assert not is_geotiff_at_resolution(None, 0.5, 0.5)
    assert not is_geotiff_at_resolution(gt, None, 0.5)


def test_provider_metadata() -> None:
    p = SwissAlti3DProvider()
    assert p.name == "swissalti3d"
    assert p.crs == "EPSG:2056"
    assert p.resolution == 0.5
    with pytest.raises(ValueError):
        SwissAlti3DProvider(resolution=1.0)


@pytest.mark.network
def test_provider_reel_valais(tmp_path: Path) -> None:
    # petite bbox dans la plaine du Rhône : altitude plausible ~450-500 m.
    p = SwissAlti3DProvider(resolution=2.0)  # 2 m pour un test léger
    bbox = (7.030, 46.150, 7.034, 46.153)
    dem = p.get_dem(bbox, tmp_path)
    assert dem.crs == "EPSG:2056"
    z = dem.sample(np.array([[dem.bounds[0] + 20, dem.bounds[3] - 20]]))[0]
    assert 350.0 < z < 700.0
