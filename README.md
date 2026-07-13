# rally-stage-builder

**Génère des spéciales de rallye réelles, prêtes pour Assetto Corsa, à partir
de géodonnées ouvertes.**

À partir d'un point de départ + arrivée (+ points de passage optionnels),
l'outil route le tracé le long du **vrai réseau routier** (OpenStreetMap),
le drape sur un **MNT haute résolution** (swissALTI3D 0,5 m), échantillonne le
**dévers**, segmente les **surfaces** (tarmac/terre), génère des **bordures**,
et produit une **stage bundle** (représentation intermédiaire, IR) agnostique de
l'éditeur, plus une **preview 3D validable hors Assetto Corsa**.

> ⚠️ **Le tracé n'est jamais modélisé à la main.** Il est toujours routé sur le
> réseau OSM réel puis drapé sur le MNT.

---

## Pourquoi

Recréer une spéciale de rallye fidèle est fastidieux : il faut la bonne route,
la bonne altitude, le bon dévers, les bonnes surfaces. Cet outil automatise tout
le travail géométrique à partir de **données ouvertes** et ne laisse que le
**dernier maillon manuel** (Blender → KN5 → AI line → pacenotes), documenté dans
[`STAGE_GUIDE.md`](STAGE_GUIDE.md).

**Suisse-first, pas Suisse-locked** : l'altimétrie passe par une abstraction
`DEMProvider`. swissALTI3D est la première source ; IGN (France), PNOA (Espagne)
et Copernicus (Europe) pourront être ajoutés **sans toucher au reste**.

## Le workflow : waypoints → bundle → Blender → KN5

```
  stage.toml            rsb (ce dépôt)                 maillon manuel
 ┌──────────┐   T2..T9  ┌───────────────────┐  T10   ┌────────────────────┐
 │ waypoints │────────▶ │ stage bundle (IR)  │──────▶ │ Blender + io_import │
 │ + surfaces│          │  + preview 3D      │        │ _accsv → KN5        │
 └──────────┘          └───────────────────┘        │ → AI line → Copilot │
                             ▲ validation             └────────────────────┘
                             │  matplotlib 3D
                        (AVANT d'investir dans le KN5)
```

1. **Vous** définissez départ / vias / arrivée + segments de surface dans un
   `stages/<nom>/stage.toml` (référence : votre roadbook — usage **humain**).
2. **rsb** route, drape, calcule le dévers, segmente, génère les bordures, et
   écrit la **stage bundle** + une **preview 3D**.
3. **Vous** validez la preview 3D (tracé, profil altimétrique, dévers).
4. **Vous** importez le bundle dans Blender, exportez en KN5, générez l'AI line,
   ajoutez les pacenotes Copilot (CSP). Voir [`STAGE_GUIDE.md`](STAGE_GUIDE.md).

## Quickstart

Prérequis : Python 3.11+, [`uv`](https://docs.astral.sh/uv/).

```bash
# Installation
uv venv --python 3.11
uv pip install -e ".[dev]"

# Vérifications
ruff check . && mypy src/rsb && pytest

# Construire la première spéciale (Evionnaz–Vernayaz, Rallye du Chablais)
# NB : télécharge des tuiles MNT + le réseau OSM (accès réseau requis).
uv run rsb build stages/chablais-2026-ss5-9-evionnaz-vernayaz/stage.toml

# Ouvrir la preview 3D (sans télécharger, si le bundle existe déjà)
uv run rsb preview outputs/chablais-2026-ss5-9-evionnaz-vernayaz/
```

Les sorties (bundle, mesh, preview) vont dans `outputs/` et les tuiles
téléchargées dans `data/` — **les deux sont ignorés par git**.

## Architecture

```
rally-stage-builder/
├── stages/                       # 1 dossier = 1 spéciale (config versionnée)
│   └── chablais-2026-ss5-9-evionnaz-vernayaz/stage.toml
├── src/rsb/
│   ├── providers/dem.py          # DEMProvider (ABC) + SwissAlti3DProvider
│   ├── fetch/stac_swisstopo.py   # STAC → tuiles GeoTIFF sur bbox
│   ├── geo/centerline.py         # osmnx : waypoints → tracé routé, rééchantillonné
│   ├── geo/drape.py              # Z du MNT le long du tracé
│   ├── geo/camber.py             # coupes perpendiculaires → largeur + dévers
│   ├── geo/surface.py            # segmentation tarmac/terre (+ hook ortho)
│   ├── geo/barriers.py           # offset bord de route + hook obstacles
│   ├── ir/bundle.py              # écrit la stage bundle (geojson + mesh terrain)
│   └── export/                   # adaptateurs (Blender, RTB) — stubs
├── validate/preview3d.py         # visu matplotlib 3D (profil + dévers) AVANT AC
└── tests/
```

L'**IR (stage bundle)** ne dépend d'aucun éditeur : c'est le point d'inversion de
dépendance. Les exporteurs sont des adaptateurs. Voir [`DECISIONS.md`](DECISIONS.md).

## ⚠️ Disclaimer

- Ces recréations sont destinées à un **usage de simulation personnel**.
- **Respectez les licences des données** (voir [`ATTRIBUTION.md`](ATTRIBUTION.md)) :
  OpenStreetMap (© OpenStreetMap contributors, ODbL — **attribution
  obligatoire**), swisstopo (Open Government Data — mention de la source
  appréciée).
- `rally-maps.com` et les roadbooks sont une **référence humaine** pour choisir
  les routes. **Aucun scraping**, **aucune redistribution** de leur contenu.
- Les auteurs déclinent toute responsabilité quant à l'exactitude des tracés ou
  à l'usage qui en est fait.

## Attribution (résumé)

- **© OpenStreetMap contributors** — réseau routier, licence ODbL.
- **Source : Office fédéral de topographie swisstopo** — MNT swissALTI3D (OGD).

Détails complets : [`ATTRIBUTION.md`](ATTRIBUTION.md).

## Licence

Code sous licence **MIT** (voir [`LICENSE`](LICENSE)). Les **données** restent
soumises à leurs licences respectives (OSM ODbL, swisstopo OGD).

## Contribuer

Voir [`CONTRIBUTING.md`](CONTRIBUTING.md). En résumé : 1 tâche = 1 commit atomique,
TDD sur le cœur géométrique, `ruff` + `mypy --strict` + `pytest` verts.
