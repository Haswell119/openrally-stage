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
from typing import TYPE_CHECKING, Any

import matplotlib

matplotlib.use("Agg")  # headless : rendu fichier, pas d'affichage

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from rsb.config import SurfaceKind  # noqa: E402
from rsb.ir.types import StageBundle  # noqa: E402

if TYPE_CHECKING:
    from rsb.export.ac_track import AcTrack
    from rsb.rally import RallyReport

_AC_COLORS = {"1ROAD": "#555555", "1KERB": "#d62728", "1WALL": "#1f77b4", "1GRASS": "#8fbf8f"}

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


def _named_waypoints_local(
    bundle: StageBundle, e0: float, n0: float
) -> list[tuple[str, float, float]]:
    """Projette les waypoints NOMMÉS (chicanes…) du bundle en coords locales."""
    from rsb.geo.transforms import transform_points

    wps = bundle.metadata.get("waypoints") or []
    named = [w for w in wps if w.get("name")]
    if not named:
        return []
    lons = np.array([float(w["lon"]) for w in named])
    lats = np.array([float(w["lat"]) for w in named])
    ex, ny = transform_points(lons, lats, "EPSG:4326", bundle.crs)
    return [
        (str(w["name"]), float(x) - e0, float(y) - n0)
        for w, x, y in zip(named, ex, ny, strict=True)
    ]


def _gradient_pct(z: np.ndarray, dist: np.ndarray) -> np.ndarray:
    g = np.gradient(z, dist) * 100.0
    return np.asarray(g, dtype=np.float64)


def _radius_m(heading: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """Rayon de courbure (m) par station ; grand = ligne droite, petit = virage serré."""
    theta = np.unwrap(np.asarray(heading, dtype=np.float64))
    kappa = np.abs(np.gradient(theta, dist))
    return 1.0 / np.maximum(kappa, 1e-6)


def build_detail_figure(bundle: StageBundle) -> Figure:
    """Vue DÉTAILLÉE d'une spéciale : plan (ruban à la vraie largeur) + analyses.

    Panneau principal : route à sa largeur (bordures), colorée par surface, départ/
    arrivée, chicanes nommées, repères de distance (500 m), virages serrés marqués.
    Panneaux latéraux : profil altimétrique, pente (%), dévers (°).
    """
    from matplotlib.gridspec import GridSpec

    from rsb.geo.drape import smooth_along_track

    cl = bundle.centerline
    z_raw = cl.require_z()
    dist = np.asarray(cl.distance_m, dtype=np.float64)
    # dépique le profil pour la lisibilité (les pics ponctuels du MNT — ponts,
    # passages sur le Rhône/rail — fausseraient la pente ; le profil brut reste
    # dans preview.png).
    z = smooth_along_track(z_raw, dist, 15.0)
    e = np.asarray(cl.xy[:, 0], dtype=np.float64)
    n = np.asarray(cl.xy[:, 1], dtype=np.float64)
    e0, n0 = float(e.min()), float(n.min())
    el, nl = e - e0, n - n0

    fig = plt.figure(figsize=(18, 11))
    title = str(bundle.metadata.get("title", bundle.name))
    direction = bundle.metadata.get("direction")
    fig.suptitle(
        f"{title}" + (f"  —  {direction}" if direction else "") + f"   ({cl.length_m:.0f} m)",
        fontsize=15,
    )
    gs = GridSpec(3, 2, width_ratios=[2.2, 1.0], figure=fig)
    ax = fig.add_subplot(gs[:, 0])  # plan (hero)

    # --- ruban de route à la vraie largeur (bordures) ---
    if bundle.barriers is not None:
        b = bundle.barriers
        lx, ly = b.left_xy[:, 0] - e0, b.left_xy[:, 1] - n0
        rx, ry = b.right_xy[:, 0] - e0, b.right_xy[:, 1] - n0
        poly_x = np.concatenate([lx, rx[::-1]])
        poly_y = np.concatenate([ly, ry[::-1]])
        ax.fill(poly_x, poly_y, color="#d9d9d9", edgecolor="#9a9a9a", linewidth=0.4, zorder=1)

    # --- centerline colorée par surface ---
    surfaces = cl.surface or [SurfaceKind.TARMAC] * len(cl)
    colors = [_SURFACE_COLORS.get(s, "#444444") for s in surfaces]
    ax.scatter(el, nl, c=colors, s=6, zorder=3)

    # --- virages serrés (rayon < 40 m), minima locaux ---
    radius = _radius_m(cl.heading_rad, dist)
    tight = radius < 40.0
    if tight.any():
        ax.scatter(
            el[tight],
            nl[tight],
            s=28,
            facecolors="none",
            edgecolors="#d62728",
            linewidths=1.0,
            zorder=4,
            label="virage serré (<40 m)",
        )

    # --- repères de distance tous les 500 m ---
    for d in np.arange(500.0, cl.length_m, 500.0):
        i = int(np.argmin(np.abs(dist - d)))
        ax.plot(el[i], nl[i], "o", color="#333333", markersize=3, zorder=5)
        ax.annotate(
            f"{d / 1000:.1f} km",
            (el[i], nl[i]),
            fontsize=7,
            color="#333333",
            xytext=(4, 3),
            textcoords="offset points",
            zorder=6,
        )

    # --- départ / arrivée + chicanes nommées ---
    ax.plot(el[0], nl[0], "^", color="#1a9850", markersize=14, zorder=7, label="départ")
    ax.plot(el[-1], nl[-1], "v", color="#d73027", markersize=14, zorder=7, label="arrivée")
    for name, wx, wy in _named_waypoints_local(bundle, e0, n0):
        ax.plot(wx, wy, "s", color="#6a3d9a", markersize=7, zorder=7)
        ax.annotate(
            name,
            (wx, wy),
            fontsize=8,
            color="#6a3d9a",
            fontweight="bold",
            xytext=(6, -10),
            textcoords="offset points",
            zorder=8,
        )

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_title("Plan détaillé — route à la vraie largeur, couleur = surface")
    ax.set_xlabel("E local (m)")
    ax.set_ylabel("N local (m)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)

    # --- panneaux d'analyse (axe distance commun) ---
    ax_prof = fig.add_subplot(gs[0, 1])
    ax_prof.plot(dist, z, color="#333333", lw=1.2)
    ax_prof.fill_between(dist, z.min() - 1, z, color="#cccccc", alpha=0.4)
    ax_prof.set_title(f"Profil — dénivelé {z.max() - z.min():.1f} m", fontsize=10)
    ax_prof.set_ylabel("alt. (m)")
    ax_prof.grid(True, alpha=0.3)

    ax_grad = fig.add_subplot(gs[1, 1], sharex=ax_prof)
    grad = _gradient_pct(z, dist)
    ax_grad.axhline(0.0, color="k", lw=0.5)
    ax_grad.fill_between(dist, 0, grad, where=grad >= 0, color="#c0392b", alpha=0.5)  # type: ignore[arg-type]
    ax_grad.fill_between(dist, 0, grad, where=grad < 0, color="#2980b9", alpha=0.5)  # type: ignore[arg-type]
    # borne l'échelle sur le gros de la distribution (les artefacts de pont sortent)
    span = max(float(np.percentile(np.abs(grad), 98)), 3.0)
    ax_grad.set_ylim(-1.3 * span, 1.3 * span)
    ax_grad.set_title("Pente (%)", fontsize=10)
    ax_grad.set_ylabel("%")
    ax_grad.grid(True, alpha=0.3)

    ax_cam = fig.add_subplot(gs[2, 1], sharex=ax_prof)
    if cl.camber_rad is not None:
        ax_cam.plot(
            dist, np.degrees(np.asarray(cl.camber_rad, dtype=np.float64)), color="#8844aa", lw=0.7
        )
        ax_cam.axhline(0.0, color="k", lw=0.5)
    ax_cam.set_title("Dévers (°) — + = penche à droite", fontsize=10)
    ax_cam.set_ylabel("°")
    ax_cam.set_xlabel("distance (m)")
    ax_cam.grid(True, alpha=0.3)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


def render_detail(bundle: StageBundle, out_path: str | Path, *, dpi: int = 160) -> Path:
    """Rend la vue détaillée et l'écrit en PNG. Retourne le chemin."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = build_detail_figure(bundle)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out


def build_rally_overview_figure(report: RallyReport) -> Figure:
    """Carte d'ensemble d'un rallye : toutes les spéciales construites en un plan.

    Positionne les spéciales dans leurs vraies coordonnées relatives (LV95) et
    récapitule longueurs et surfaces.
    """
    ok = [r for r in report.ok if r.bundle is not None]
    fig = plt.figure(figsize=(14, 8))
    fig.suptitle(f"{report.title} — aperçu du rallye", fontsize=14)
    ax = fig.add_subplot(1, 2, 1)
    ax_txt = fig.add_subplot(1, 2, 2)
    ax_txt.axis("off")

    # origine globale commune (min E/N sur toutes les spéciales) pour un plan lisible
    all_xy = [r.bundle.centerline.xy for r in ok if r.bundle is not None]
    if all_xy:
        e0 = min(float(xy[:, 0].min()) for xy in all_xy)
        n0 = min(float(xy[:, 1].min()) for xy in all_xy)
    else:
        e0 = n0 = 0.0

    cmap = plt.get_cmap("tab10")
    lines = ["Spéciales construites :", ""]
    for i, r in enumerate(ok):
        assert r.bundle is not None
        xy = r.bundle.centerline.xy
        color = cmap(i % 10)
        ax.plot(xy[:, 0] - e0, xy[:, 1] - n0, color=color, lw=1.6)
        ax.plot(xy[0, 0] - e0, xy[0, 1] - n0, "o", color=color, markersize=5)
        ss = "/".join(f"SS{n}" for n in r.ss) if r.ss else "—"
        ax.annotate(
            r.id,
            (xy[0, 0] - e0, xy[0, 1] - n0),
            fontsize=7,
            color=color,
            xytext=(4, 4),
            textcoords="offset points",
        )
        lines.append(f"• {ss:8}  {r.id}")
        lines.append(f"          {r.length_m:.0f} m — {r.n_stations} stations")

    ax.set_aspect("equal", adjustable="datalim")
    ax.set_title("Carte des spéciales (coordonnées LV95 locales)")
    ax.set_xlabel("E local (m)")
    ax.set_ylabel("N local (m)")
    ax.grid(True, alpha=0.3)

    lines.append("")
    lines.append(
        f"Total construit : {report.total_length_m / 1000:.1f} km sur {len(ok)} spéciale(s)."
    )
    if report.failed:
        lines.append("")
        lines.append(f"⚠ {len(report.failed)} en échec : " + ", ".join(r.id for r in report.failed))
    ax_txt.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=9, family="monospace")

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def build_ac_layers_figure(track: AcTrack) -> Figure:
    """Contrôle visuel des couches AC : plan (placement route/bordures/barrières) +
    coupe 3D zoomée (route + barrières en relief)."""
    fig = plt.figure(figsize=(16, 8))
    fig.suptitle(f"Couches AC — {track.name}", fontsize=13)
    ax = fig.add_subplot(1, 2, 1)
    ax3d = fig.add_subplot(1, 2, 2, projection="3d")

    def by_name(n: str) -> Any:
        return next((m for m in track.meshes if m.name == n), None)

    # --- plan : placement de chaque couche ---
    for m in track.meshes:
        if m.name == "1GRASS":
            continue  # trop dense en plan
        v = m.vertices
        ax.scatter(v[:, 0], v[:, 1], s=2, color=_AC_COLORS.get(m.name, "#333"), label=m.name)
    for o in track.objects:
        ax.plot(o.pos[0], o.pos[1], "kx", markersize=6)
        ax.annotate(
            o.name, (o.pos[0], o.pos[1]), fontsize=6, xytext=(3, 3), textcoords="offset points"
        )
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_title("Plan — route, bordures (rouge), barrières (bleu), objets AC")
    ax.set_xlabel("E local (m)")
    ax.set_ylabel("N local (m)")
    ax.legend(loc="best", fontsize=8, markerscale=3)
    ax.grid(True, alpha=0.3)

    # --- 3D : fenêtre zoomée (là où il y a des barrières, sinon le début) ---
    wall = by_name("1WALL")
    road = by_name("1ROAD")
    if road is not None:
        focus = wall.vertices if wall is not None else road.vertices
        cx, cy = float(focus[:, 0].mean()), float(focus[:, 1].mean())
        half = 120.0
        for m in track.meshes:
            v = m.vertices
            sel = (np.abs(v[:, 0] - cx) < half) & (np.abs(v[:, 1] - cy) < half)
            if sel.sum() < 3:
                continue
            ax3d.plot_trisurf(
                v[:, 0],
                v[:, 1],
                v[:, 2],
                triangles=m.faces,
                color=_AC_COLORS.get(m.name, "#888"),
                alpha=0.85 if m.name != "1GRASS" else 0.3,
                linewidth=0,
                shade=True,
            )
        ax3d.set_xlim(cx - half, cx + half)
        ax3d.set_ylim(cy - half, cy + half)
    ax3d.set_title("Coupe 3D (~240 m) — route + barrières en relief")
    ax3d.set_xlabel("E (m)")
    ax3d.set_ylabel("N (m)")
    ax3d.set_zlabel("Z (m)")

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


def _fit_limits(
    x: np.ndarray, y: np.ndarray, aspect_wh: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Limites couvrant les données à un ratio largeur/hauteur donné (échelle égale)."""
    x0, x1 = float(x.min()), float(x.max())
    y0, y1 = float(y.min()), float(y.max())
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w = max(x1 - x0, 1.0) * 1.1
    h = max(y1 - y0, 1.0) * 1.1
    if w / h < aspect_wh:
        w = h * aspect_wh
    else:
        h = w / aspect_wh
    return (cx - w / 2, cx + w / 2), (cy - h / 2, cy + h / 2)


def render_ac_images(track: AcTrack, track_dir: str | Path, proj: dict[str, float]) -> None:
    """Rend les images AC : ui/preview.png (355×200), ui/outline.png (355×200,
    transparent), data/map.png (minimap selon ``proj``)."""
    d = Path(track_dir)
    road = next((m for m in track.meshes if m.name == "1ROAD"), track.meshes[0])
    v = road.vertices
    n = len(v) // 2
    # coords top-down AC : x = E, y = -N
    ex, ny = v[:, 0], -v[:, 1]
    poly_x = np.concatenate([ex[:n], ex[n:][::-1]])
    poly_y = np.concatenate([ny[:n], ny[n:][::-1]])

    # --- ui/preview.png (355×200) : carte colorée ---
    fig = plt.figure(figsize=(3.55, 2.0), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    ax.set_facecolor("#e8eef0")
    fig.patch.set_facecolor("#e8eef0")
    ax.fill(poly_x, poly_y, color="#555555")
    for o in track.objects:
        if o.name == "AC_PIT_0":
            ax.plot(o.pos[0], -o.pos[1], "g^", markersize=7)
        if o.name == "AC_AB_FINISH_L":
            ax.plot(o.pos[0], -o.pos[1], "rv", markersize=7)
    xlim, ylim = _fit_limits(poly_x, poly_y, 3.55 / 2.0)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    fig.savefig(d / "ui" / "preview.png", dpi=100)
    plt.close(fig)

    # --- ui/outline.png (355×200, transparent) : tracé blanc ---
    fig = plt.figure(figsize=(3.55, 2.0), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    ax.fill(poly_x, poly_y, color="white")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    fig.savefig(d / "ui" / "outline.png", dpi=100, transparent=True)
    plt.close(fig)

    # --- data/map.png (minimap, coords pixel selon proj) ---
    w, h = int(proj["WIDTH"]), int(proj["HEIGHT"])
    sc, xo, zo = proj["SCALE_FACTOR"], proj["X_OFFSET"], proj["Z_OFFSET"]
    px = (poly_x + xo) * sc
    py = (poly_y + zo) * sc
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.fill(px, py, color="white")
    ax.invert_yaxis()
    fig.savefig(d / "data" / "map.png", dpi=100, transparent=True)
    plt.close(fig)


def render_ac_layers(track: AcTrack, out_path: str | Path, *, dpi: int = 130) -> Path:
    """Rend le contrôle visuel des couches AC en PNG."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = build_ac_layers_figure(track)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out


def render_rally_overview(report: RallyReport, out_path: str | Path, *, dpi: int = 130) -> Path:
    """Rend l'aperçu du rallye et l'écrit en PNG. Retourne le chemin."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = build_rally_overview_figure(report)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out
