"""Interface en ligne de commande ``rsb``.

Commandes principales :

* ``rsb doctor``             — vérifie l'environnement (Python, dépendances, réseau).
* ``rsb build <stage.toml>`` — pipeline complet → stage bundle + dossier AC + preview 3D.
* ``rsb build-rally <dir>``  — construit TOUTES les spéciales d'un rallye.
* ``rsb preview <bundle>``   — re-rend la preview 3D depuis une bundle existante.
* ``rsb detail <bundle>``    — vue détaillée (plan large + virages + profil).
* ``rsb list <dir>``         — liste les spéciales d'un rallye.
* ``rsb new-stage <dir> id`` — crée le squelette d'une spéciale.

Les erreurs sont présentées en clair (pas de traceback) ; ajoutez ``--traceback``
(ou ``RSB_TRACEBACK=1``) pour la trace complète lors d'un débogage.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

from rsb import __version__
from rsb.config import SurfaceKind, load_stage
from rsb.ir.bundle import load_bundle
from rsb.pipeline import build_stage

# Points d'accès sondés par ``rsb doctor`` (les mêmes services que ``build`` utilise).
_STAC_URL = "https://data.geo.admin.ch/api/stac/v1/"
_OVERPASS_URL = "https://overpass-api.de/api/status"

# Dépendances tierces requises par le pipeline (nom d'import → paquet pip).
_REQUIRED_MODULES = [
    "numpy",
    "scipy",
    "shapely",
    "pyproj",
    "geopandas",
    "rasterio",
    "osmnx",
    "pystac_client",
    "matplotlib",
    "pydantic",
]


def _reminders(cfg_path: Path) -> str:
    return (
        "\n⚠️  À AFFINER depuis votre roadbook (usage HUMAIN) :\n"
        f"   • waypoints (départ/vias/arrivée) dans {cfg_path}\n"
        "   • segments de surface (surface_overrides : distances de la portion « terre »)\n"
        "   • largeur de route par défaut (route.default_width_m) si besoin\n"
    )


# --------------------------------------------------------------------- doctor
def _probe(url: str, timeout: float = 6.0) -> bool:
    """Vrai si ``url`` répond (serveur joignable), faux sinon. Best-effort."""
    try:
        import requests

        resp = requests.get(url, timeout=timeout)
        return resp.status_code < 500
    except Exception:  # noqa: BLE001 — tout échec = injoignable
        return False


def _cmd_doctor(args: argparse.Namespace) -> int:
    import importlib
    import platform

    ok = True
    print("rsb doctor — vérification de l'environnement\n")

    py_ok = sys.version_info >= (3, 11)
    print(f"  [{'✓' if py_ok else '✗'}] Python {platform.python_version()} (requis ≥ 3.11)")
    ok = ok and py_ok

    for mod in _REQUIRED_MODULES:
        try:
            m = importlib.import_module(mod)
            print(f"  [✓] {mod} {getattr(m, '__version__', '?')}")
        except Exception:  # noqa: BLE001
            ok = False
            print(f"  [✗] {mod} MANQUANT")

    if args.no_network:
        print("\n  (contrôle réseau ignoré : --no-network)")
    else:
        print("\n  Connectivité (nécessaire pour `build` — télécharge OSM + tuiles MNT) :")
        for label, url in (
            ("swisstopo / swissALTI3D (MNT)", _STAC_URL),
            ("OpenStreetMap / Overpass", _OVERPASS_URL),
        ):
            reachable = _probe(url)
            ok = ok and reachable
            state = "joignable" if reachable else "INJOIGNABLE"
            print(f"    [{'✓' if reachable else '✗'}] {label} : {state}")

    print()
    if ok:
        print("✓ Environnement prêt. Essayez :")
        print("    rsb build examples/evionnaz-test-stage/stage.toml")
    else:
        print("✗ Corrigez les points ci-dessus avant de construire une spéciale.")
        print('  Dépendances manquantes → `uv pip install -e ".[dev]"`.')
    return 0 if ok else 1


# ---------------------------------------------------------------------- build
def _cmd_build(args: argparse.Namespace) -> int:
    cfg_path = Path(args.stage)
    cfg = load_stage(cfg_path)
    out_dir = Path(args.out) if args.out else Path("outputs") / cfg.name

    print(f"▶ Construction de la spéciale « {cfg.name} »")
    if cfg.gpx is not None:
        print(
            f"  source : GPX {Path(cfg.gpx).name}"
            + (f" (track {cfg.gpx_track})" if cfg.gpx_track else "")
        )
    else:
        print(f"  bbox WGS84 : {cfg.effective_bbox().as_tuple()}")
    print(f"  MNT : swissALTI3D {args.dem_res} m — CRS {cfg.crs.work}")

    bundle = build_stage(
        cfg,
        cache_dir=args.cache,
        out_dir=out_dir,
        dem_resolution=args.dem_res,
        corridor_m=args.corridor,
        mesh_res=args.mesh_res,
        write=True,
    )
    cl = bundle.centerline
    runs = {str(s.kind): (s.start_m, s.end_m) for s in cfg.surface_overrides}
    print(f"✓ Bundle écrite dans {out_dir}")
    print(f"  longueur {cl.length_m:.0f} m — {len(cl)} stations")
    if cl.surface is not None:
        n_gravel = sum(1 for s in cl.surface if s is SurfaceKind.GRAVEL)
        print(f"  surfaces : {n_gravel} stations « terre » (overrides config : {runs or 'aucun'})")
    print(f"  dossier piste AC : {out_dir / 'ac' / cfg.name}/ (→ ksEditor, voir STAGE_GUIDE.md)")

    if not args.no_preview:
        from validate.preview3d import render_preview

        png = render_preview(bundle, out_dir / "preview.png")
        print(f"✓ Preview 3D : {png}")

    print(_reminders(cfg_path))
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    from validate.preview3d import render_preview

    bundle_dir = Path(args.bundle)
    bundle = load_bundle(bundle_dir)
    out = Path(args.out) if args.out else bundle_dir / "preview.png"
    png = render_preview(bundle, out)
    print(f"✓ Preview 3D : {png}")
    return 0


def _cmd_detail(args: argparse.Namespace) -> int:
    from validate.preview3d import render_detail

    bundle_dir = Path(args.bundle)
    bundle = load_bundle(bundle_dir)
    out = Path(args.out) if args.out else bundle_dir / "detail.png"
    png = render_detail(bundle, out)
    print(f"✓ Vue détaillée : {png}")
    return 0


def _cmd_build_rally(args: argparse.Namespace) -> int:
    from rsb.rally import build_rally

    print(f"▶ Construction du rallye « {args.rally} »")
    report = build_rally(
        args.rally,
        cache_dir=args.cache,
        only=args.only,
        force=args.force,
        preview=not args.no_preview,
        dem_resolution=args.dem_res,
    )
    print(f"\n=== {report.title} ===")
    for r in report.results:
        icon = {"ok": "✓", "skipped": "⏭", "failed": "✗"}.get(r.status, "?")
        ss = "/".join(f"SS{n}" for n in r.ss) if r.ss else "—"
        if r.status == "failed":
            print(f"  {icon} {ss:8} {r.id} — ÉCHEC : {r.error}")
        else:
            length = f"{r.length_m:.0f} m" if r.length_m else "?"
            print(f"  {icon} {ss:8} {r.id} — {length}")
    print(
        f"\nTotal : {report.total_length_m / 1000:.1f} km — "
        f"{len(report.ok)} construite(s), {len(report.failed)} en échec."
    )
    out_root = Path("outputs") / report.name
    print(f"Aperçu du rallye : {out_root / 'rally_overview.png'}")
    print(_reminders(Path(args.rally)))
    return 1 if report.failed else 0


def _cmd_list(args: argparse.Namespace) -> int:
    from rsb.rally import load_rally

    rally, _ = load_rally(args.rally)
    print(f"{rally.title}  ({rally.name}, {rally.country or '?'})")
    print(
        f"  provider MNT : {rally.dem_provider} {rally.dem_resolution} m — "
        f"{len(rally.stages)} spéciale(s)"
    )
    for s in rally.stages:
        ss = "/".join(f"SS{n}" for n in s.ss) if s.ss else "—"
        print(f"  • {ss:8} {s.id}" + (f"  ({s.note})" if s.note else ""))
    return 0


_STAGE_TEMPLATE = """\
# Spéciale « {id} » — {rally}
# Hérite des défauts de rally.toml (CRS, route, camber). ⚠️ waypoints SEED à affiner.

name = "{rally}-{id}"
title = "{rally} — {id}"
direction = "A → B"
default_surface = "tarmac"

[[waypoints]]
role = "start"
name = "Départ"
lat = 46.0000   # SEED — À REMPLACER depuis votre roadbook
lon = 7.0000

[[waypoints]]
role = "end"
name = "Arrivée"
lat = 46.0100   # SEED — À REMPLACER
lon = 7.0100

# Portion terre optionnelle (distances en m depuis le départ) :
# [[surface_overrides]]
# kind = "gravel"
# start_m = 0.0
# end_m = 500.0
"""


def _cmd_new_stage(args: argparse.Namespace) -> int:
    from rsb.rally import load_rally

    rally, base_dir = load_rally(args.rally)
    stage_dir = base_dir / args.id
    if stage_dir.exists():
        print(f"✗ {stage_dir} existe déjà.")
        return 1
    stage_dir.mkdir(parents=True)
    (stage_dir / "stage.toml").write_text(
        _STAGE_TEMPLATE.format(id=args.id, rally=rally.name), encoding="utf-8"
    )
    # ajoute une entrée [[stages]] au rally.toml
    rally_toml = base_dir / "rally.toml"
    with rally_toml.open("a", encoding="utf-8") as fh:
        fh.write(f'\n[[stages]]\nid = "{args.id}"\nss = []\nnote = "À compléter."\n')
    print(f"✓ Spéciale créée : {stage_dir / 'stage.toml'}")
    print("  → renseignez les waypoints (depuis votre roadbook) puis `rsb build-rally`.")
    return 0


# ------------------------------------------------------------- gestion erreurs
def _looks_like_network(exc: BaseException) -> bool:
    """Vrai si ``exc`` (ou une cause) ressemble à un problème réseau."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        name = type(cur).__name__.lower()
        if isinstance(cur, ConnectionError | TimeoutError) or any(
            k in name for k in ("connection", "timeout", "dns", "resolve", "ssl", "urlerror")
        ):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _print_error(exc: BaseException) -> None:
    """Formate une exception en message clair et actionnable (sur stderr)."""
    try:
        from pydantic import ValidationError
    except Exception:  # noqa: BLE001 — pydantic est une dépendance, mais restons robustes
        ValidationError = None  # type: ignore[assignment,misc]

    if isinstance(exc, FileNotFoundError):
        print(f"✗ Fichier introuvable : {exc.filename or exc}", file=sys.stderr)
    elif isinstance(exc, tomllib.TOMLDecodeError):
        print(f"✗ Fichier TOML invalide : {exc}", file=sys.stderr)
    elif ValidationError is not None and isinstance(exc, ValidationError):
        print("✗ Configuration invalide :", file=sys.stderr)
        for err in exc.errors()[:5]:
            loc = ".".join(str(x) for x in err["loc"])
            print(f"   • {loc or '(racine)'} : {err['msg']}", file=sys.stderr)
    elif _looks_like_network(exc):
        print(
            f"✗ Problème de réseau en joignant OSM/swisstopo : {exc}\n"
            "  Le build télécharge le réseau OSM et les tuiles MNT — vérifiez votre connexion.\n"
            "  Diagnostic : `rsb doctor`.",
            file=sys.stderr,
        )
    else:
        print(f"✗ {exc}", file=sys.stderr)


# ------------------------------------------------------------------ argparse
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--traceback",
        action="store_true",
        help="afficher la trace complète en cas d'erreur (débogage)",
    )

    p = argparse.ArgumentParser(
        prog="rsb",
        description="rally-stage-builder — spéciales de rallye réelles pour Assetto Corsa.",
        epilog=(
            "Exemples :\n"
            "  rsb doctor                                            # vérifier l'installation\n"
            "  rsb build examples/evionnaz-test-stage/stage.toml     # construire l'exemple\n"
            "  rsb build-rally stages/chablais-2026                  # tout un rallye\n"
            "  rsb preview outputs/<rallye>/<ss>/                    # revoir la preview 3D"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"rsb {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    doc = sub.add_parser(
        "doctor",
        parents=[common],
        help="vérifier l'environnement (Python, dépendances, réseau)",
    )
    doc.add_argument(
        "--no-network", action="store_true", help="ne pas tester la connectivité OSM/swisstopo"
    )
    doc.set_defaults(func=_cmd_doctor)

    b = sub.add_parser(
        "build", parents=[common], help="pipeline complet → stage bundle + dossier AC + preview"
    )
    b.add_argument("stage", help="chemin d'un stage.toml")
    b.add_argument("--out", help="dossier de sortie (défaut : outputs/<name>)")
    b.add_argument("--cache", default="data", help="cache tuiles/OSM (défaut : data)")
    b.add_argument("--dem-res", type=float, default=0.5, choices=[0.5, 2.0], dest="dem_res")
    b.add_argument("--corridor", type=float, default=30.0, help="demi-largeur du mesh terrain (m)")
    b.add_argument(
        "--mesh-res", type=float, default=2.0, dest="mesh_res", help="résolution mesh (m)"
    )
    b.add_argument("--no-preview", action="store_true", help="ne pas rendre la preview 3D")
    b.set_defaults(func=_cmd_build)

    v = sub.add_parser(
        "preview", parents=[common], help="re-rend la preview 3D d'une bundle existante"
    )
    v.add_argument("bundle", help="dossier d'une stage bundle")
    v.add_argument("--out", help="chemin du PNG (défaut : <bundle>/preview.png)")
    v.set_defaults(func=_cmd_preview)

    dt = sub.add_parser(
        "detail", parents=[common], help="vue détaillée d'une spéciale (plan large + analyses)"
    )
    dt.add_argument("bundle", help="dossier d'une stage bundle")
    dt.add_argument("--out", help="chemin du PNG (défaut : <bundle>/detail.png)")
    dt.set_defaults(func=_cmd_detail)

    r = sub.add_parser(
        "build-rally", parents=[common], help="construit TOUTES les spéciales d'un rallye"
    )
    r.add_argument("rally", help="dossier du rallye (ou chemin d'un rally.toml)")
    r.add_argument("--cache", default="data", help="cache tuiles/OSM (défaut : data)")
    r.add_argument("--only", nargs="+", help="ne construire que ces id de spéciales")
    r.add_argument("--force", action="store_true", help="reconstruire même si déjà fait")
    r.add_argument("--dem-res", type=float, default=None, choices=[0.5, 2.0], dest="dem_res")
    r.add_argument("--no-preview", action="store_true", help="ne pas rendre les previews")
    r.set_defaults(func=_cmd_build_rally)

    ls = sub.add_parser("list", parents=[common], help="liste les spéciales d'un rallye")
    ls.add_argument("rally", help="dossier du rallye (ou chemin d'un rally.toml)")
    ls.set_defaults(func=_cmd_list)

    ns = sub.add_parser(
        "new-stage", parents=[common], help="crée une spéciale (template) dans un rallye"
    )
    ns.add_argument("rally", help="dossier du rallye (ou chemin d'un rally.toml)")
    ns.add_argument("id", help="identifiant de la spéciale (ex. ss3-nom)")
    ns.set_defaults(func=_cmd_new_stage)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    show_tb = getattr(args, "traceback", False) or os.environ.get("RSB_TRACEBACK") == "1"
    try:
        result: int = args.func(args)
        return result
    except KeyboardInterrupt:
        print("\n✗ Interrompu.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 — surface CLI : message clair, pas de traceback
        if show_tb:
            raise
        _print_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
