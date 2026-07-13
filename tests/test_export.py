"""Tests T10 : stubs d'export (Blender / RTB)."""

from pathlib import Path

import pytest

from rsb.export.blender_headless import blender_import_script, to_kn5, write_blender_script
from rsb.export.rtb import export_rtb


def test_blender_script_reference_le_csv_et_le_nommage_ac() -> None:
    script = blender_import_script("/tmp/bundle", name="demo")
    assert "centerline_ac.csv" in script
    assert "import_csv.read" in script  # opérateur io_import_accsv
    assert "AC_AB_START_L" in script  # portes point-à-point
    assert "AC_AB_FINISH_R" in script
    assert "1ROAD" in script


def test_write_blender_script(tmp_path: Path) -> None:
    out = write_blender_script(tmp_path, name="demo")
    assert out.exists()
    assert out.name == "blender_import.py"
    assert "centerline_ac.csv" in out.read_text(encoding="utf-8")


def test_to_kn5_est_un_stub() -> None:
    with pytest.raises(NotImplementedError):
        to_kn5()


def test_export_rtb_est_un_stub(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError):
        export_rtb(tmp_path, tmp_path)
