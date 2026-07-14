"""Tests de l'interface CLI ``rsb`` : version, doctor, messages d'erreur clairs."""

import pytest

from rsb import __version__
from rsb.cli import _looks_like_network, _print_error, build_parser, main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse action="version" imprime puis lève SystemExit(0).
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_doctor_offline_ok(capsys: pytest.CaptureFixture[str]) -> None:
    # sans réseau : Python + dépendances (installées dans l'env de dev) → succès.
    code = main(["doctor", "--no-network"])
    out = capsys.readouterr().out
    assert code == 0
    assert "numpy" in out
    assert "contrôle réseau ignoré" in out


def test_build_fichier_introuvable(capsys: pytest.CaptureFixture[str]) -> None:
    # un stage.toml inexistant → message clair, pas de traceback, code 1.
    code = main(["build", "n-existe-pas/stage.toml"])
    err = capsys.readouterr().err
    assert code == 1
    assert "introuvable" in err.lower()


def test_config_invalide(tmp_path: object, capsys: pytest.CaptureFixture[str]) -> None:
    from pathlib import Path

    bad = Path(str(tmp_path)) / "stage.toml"
    bad.write_text('name = "x"\ntitle = "X"\n', encoding="utf-8")  # ni gpx ni waypoints
    code = main(["build", str(bad)])
    err = capsys.readouterr().err
    assert code == 1
    assert "invalide" in err.lower()


def test_traceback_relance(tmp_path: object) -> None:
    from pathlib import Path

    from pydantic import ValidationError

    bad = Path(str(tmp_path)) / "stage.toml"
    bad.write_text('name = "x"\ntitle = "X"\n', encoding="utf-8")
    # avec --traceback l'exception d'origine remonte (pas de capture silencieuse).
    with pytest.raises(ValidationError):
        main(["build", str(bad), "--traceback"])


def test_looks_like_network() -> None:
    assert _looks_like_network(ConnectionError("refused"))
    assert _looks_like_network(TimeoutError())
    assert not _looks_like_network(ValueError("autre"))
    # remonte la chaîne de causes
    try:
        try:
            raise ConnectionError("down")
        except ConnectionError as e:
            raise RuntimeError("échec build") from e
    except RuntimeError as top:
        assert _looks_like_network(top)


def test_print_error_reseau(capsys: pytest.CaptureFixture[str]) -> None:
    _print_error(ConnectionError("boom"))
    err = capsys.readouterr().err
    assert "réseau" in err.lower()
    assert "doctor" in err


def test_parser_expose_toutes_les_commandes() -> None:
    parser = build_parser()
    # smoke : le parser se construit et chaque sous-commande a une fonction.
    positionals = {
        "doctor": [],
        "build": ["x"],
        "build-rally": ["x"],
        "preview": ["x"],
        "detail": ["x"],
        "list": ["x"],
        "new-stage": ["x", "y"],
    }
    for cmd, extra in positionals.items():
        ns = parser.parse_args([cmd, *extra])
        assert hasattr(ns, "func")
