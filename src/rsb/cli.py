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
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    func = args.func
    result: int = func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
