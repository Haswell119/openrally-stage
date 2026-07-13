"""T9 — Preview 3D : validation d'une stage bundle AVANT Assetto Corsa.

Rend, avec matplotlib (backend headless), une figure multi-panneaux :

1. **Tracé 3D** (E, N, Z) coloré par surface, avec les bordures gauche/droite ;
2. **Profil altimétrique** (distance ↔ altitude) ;
3. **Dévers** (distance ↔ camber en degrés).

C'est l'outil de validation à regarder AVANT d'investir dans le KN5. Aucune
dépendance à Assetto Corsa : on valide l'IR (bundle) telle quelle.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless : rendu fichier, pas d'affichage

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from rsb.config import SurfaceKind  # noqa: E402
from rsb.ir.types import StageBundle  # noqa: E402

_SURFACE_COLORS = {
    SurfaceKind.TARMAC: "#444444",
    SurfaceKind.GRAVEL: "#b5651d",
    SurfaceKind.SAND: "#e0c068",
    SurfaceKind.SNOW: "#7fb0d0",
}


def build_preview_figure(bundle: StageBundle) -> Figure:
    """Construit la figure de validation (sans l'écrire)."""
    cl = bundle.centerline
    z = cl.require_z()
    dist = np.asarray(cl.distance_m, dtype=np.float64)
    e = np.asarray(cl.xy[:, 0], dtype=np.float64)
    n = np.asarray(cl.xy[:, 1], dtype=np.float64)
    # coordonnées locales pour un affichage lisible
    e0, n0 = float(e.min()), float(n.min())
    el, nl = e - e0, n - n0

    fig = plt.figure(figsize=(14, 9))
    title = str(bundle.metadata.get("title", bundle.name))
    direction = bundle.metadata.get("direction")
    fig.suptitle(f"{title}" + (f"  —  {direction}" if direction else ""), fontsize=13)

    # --- 1. tracé 3D ------------------------------------------------------
    ax3d = fig.add_subplot(2, 2, 1, projection="3d")
    surfaces = cl.surface or [SurfaceKind.TARMAC] * len(cl)
    colors = [_SURFACE_COLORS.get(s, "#444444") for s in surfaces]
    ax3d.scatter(el, nl, z, c=colors, s=2, depthshade=False)
    if bundle.barriers is not None:
        b = bundle.barriers
        bl_z = b.left_z if b.left_z is not None else z
        br_z = b.right_z if b.right_z is not None else z
        ax3d.plot(
            b.left_xy[:, 0] - e0, b.left_xy[:, 1] - n0, bl_z, color="#2266cc", lw=0.6, alpha=0.6
        )
        ax3d.plot(
            b.right_xy[:, 0] - e0, b.right_xy[:, 1] - n0, br_z, color="#cc2266", lw=0.6, alpha=0.6
        )
    ax3d.set_title("Tracé 3D (couleur = surface)")
    ax3d.set_xlabel("E local (m)")
    ax3d.set_ylabel("N local (m)")
    ax3d.set_zlabel("Z (m)")

    # --- 2. vue en plan (E, N) coloré surface -----------------------------
    ax_plan = fig.add_subplot(2, 2, 2)
    ax_plan.scatter(el, nl, c=colors, s=3)
    ax_plan.plot(el[0], nl[0], "g^", markersize=9, label="départ")
    ax_plan.plot(el[-1], nl[-1], "rv", markersize=9, label="arrivée")
    ax_plan.set_aspect("equal", adjustable="datalim")
    ax_plan.set_title("Vue en plan")
    ax_plan.set_xlabel("E local (m)")
    ax_plan.set_ylabel("N local (m)")
    ax_plan.legend(loc="best", fontsize=8)
    ax_plan.grid(True, alpha=0.3)

    # --- 3. profil altimétrique -------------------------------------------
    ax_prof = fig.add_subplot(2, 2, 3)
    ax_prof.plot(dist, z, color="#333333", lw=1.2)
    ax_prof.fill_between(dist, z.min() - 2, z, color="#cccccc", alpha=0.4)
    ax_prof.set_title(
        f"Profil altimétrique — long. {cl.length_m:.0f} m, dénivelé {z.max() - z.min():.1f} m"
    )
    ax_prof.set_xlabel("distance (m)")
    ax_prof.set_ylabel("altitude (m)")
    ax_prof.grid(True, alpha=0.3)

    # --- 4. dévers (camber) ------------------------------------------------
    ax_cam = fig.add_subplot(2, 2, 4)
    if cl.camber_rad is not None:
        camber_deg = np.degrees(np.asarray(cl.camber_rad, dtype=np.float64))
        ax_cam.plot(dist, camber_deg, color="#8844aa", lw=0.8)
        ax_cam.axhline(0.0, color="k", lw=0.5)
        ax_cam.set_ylabel("dévers (°) — + = penche à droite")
    else:
        ax_cam.text(0.5, 0.5, "dévers non calculé", ha="center", va="center")
    ax_cam.set_title("Dévers (camber) par station")
    ax_cam.set_xlabel("distance (m)")
    ax_cam.grid(True, alpha=0.3)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


def render_preview(bundle: StageBundle, out_path: str | Path, *, dpi: int = 130) -> Path:
    """Rend la preview et l'écrit en PNG. Retourne le chemin."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = build_preview_figure(bundle)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out
