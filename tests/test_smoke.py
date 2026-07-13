"""Test de fumée : le paquet s'importe et expose sa version."""

import rsb


def test_version_exposee() -> None:
    assert isinstance(rsb.__version__, str)
    assert rsb.__version__
