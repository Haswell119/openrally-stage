"""Interface en ligne de commande ``rsb``.

* ``rsb build <stage.toml>``  — pipeline complet → stage bundle + preview 3D.
* ``rsb preview <bundle_dir>`` — re-rend la preview 3D depuis une bundle existante.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rsb.config import SurfaceKind, load_stage
from rsb.ir.bundle import load_bundle
from rsb.pipeline import build_stage


def _reminders(cfg_path: Path) -> str:
    return (
        "\n⚠️  À AFFINER depuis votre roadbook (usage HUMAIN) :\n"
        f"   • waypoints (départ/vias/arrivée) dans {cfg_path}\n"
        "   • segments de surface (surface_overrides : distances de la portion « terre »)\n"
        "   • largeur de route par défaut (route.default_width_m) si besoin\n"
    )


def _cmd_build(args: argparse.Namespace) -> int:
    cfg_path = Path(args.stage)
    cfg = load_stage(cfg_path)
    out_dir = Path(args.out) if args.out else Path("outputs") / cfg.name

    print(f"▶ Construction de la spéciale « {cfg.name} »")
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rsb", description="rally-stage-builder")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="pipeline complet → stage bundle + preview")
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

    v = sub.add_parser("preview", help="re-rend la preview 3D d'une bundle existante")
    v.add_argument("bundle", help="dossier d'une stage bundle")
    v.add_argument("--out", help="chemin du PNG (défaut : <bundle>/preview.png)")
    v.set_defaults(func=_cmd_preview)

    dt = sub.add_parser("detail", help="vue détaillée d'une spéciale (plan large + analyses)")
    dt.add_argument("bundle", help="dossier d'une stage bundle")
    dt.add_argument("--out", help="chemin du PNG (défaut : <bundle>/detail.png)")
    dt.set_defaults(func=_cmd_detail)

    r = sub.add_parser("build-rally", help="construit TOUTES les spéciales d'un rallye")
    r.add_argument("rally", help="dossier du rallye (ou chemin d'un rally.toml)")
    r.add_argument("--cache", default="data", help="cache tuiles/OSM (défaut : data)")
    r.add_argument("--only", nargs="+", help="ne construire que ces id de spéciales")
    r.add_argument("--force", action="store_true", help="reconstruire même si déjà fait")
    r.add_argument("--dem-res", type=float, default=None, choices=[0.5, 2.0], dest="dem_res")
    r.add_argument("--no-preview", action="store_true", help="ne pas rendre les previews")
    r.set_defaults(func=_cmd_build_rally)

    ls = sub.add_parser("list", help="liste les spéciales d'un rallye")
    ls.add_argument("rally", help="dossier du rallye (ou chemin d'un rally.toml)")
    ls.set_defaults(func=_cmd_list)

    ns = sub.add_parser("new-stage", help="crée une spéciale (template) dans un rallye")
    ns.add_argument("rally", help="dossier du rallye (ou chemin d'un rally.toml)")
    ns.add_argument("id", help="identifiant de la spéciale (ex. ss3-nom)")
    ns.set_defaults(func=_cmd_new_stage)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    func = args.func
    result: int = func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
