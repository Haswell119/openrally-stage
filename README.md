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

## Deux sources de tracé : GPX (recommandé) ou waypoints OSM

* **GPX** (recommandé pour une spéciale connue) : un fichier GPX exporté depuis
  votre roadbook / rally-maps donne le **tracé réel dense**. Il est utilisé
  **directement** comme centerline (projeté + rééchantillonné), puis drapé sur
  swissALTI3D. C'est le plus fidèle (à quelques mètres près de la longueur réelle).
  Dans le `stage.toml` : `gpx = "stage.gpx"` (chemin relatif).
  ⚠️ Le GPX est un **contenu tiers** : gardé **local** (gitignoré `*.gpx`),
  **non redistribué**.
* **Waypoints OSM** : sans GPX, listez `[[waypoints]]` (départ / vias / arrivée) et
  l'outil **route** sur le vrai réseau OSM. Pratique pour esquisser une spéciale.

## Quickstart

Prérequis : Python 3.11+, [`uv`](https://docs.astral.sh/uv/).

```bash
# Installation
uv venv --python 3.11
uv pip install -e ".[dev]"

# Vérifications
ruff check . && mypy src/rsb && pytest

# Construire UNE spéciale (Evionnaz–Vernayaz, Rallye du Chablais)
# NB : télécharge des tuiles MNT + le réseau OSM (accès réseau requis).
uv run rsb build stages/chablais-2026/ss5-9-evionnaz-vernayaz/stage.toml

# Construire TOUT un rallye (toutes les spéciales) + carte d'ensemble
uv run rsb build-rally stages/chablais-2026

# Lister les spéciales, ajouter une spéciale (template à affiner)
uv run rsb list stages/chablais-2026
uv run rsb new-stage stages/chablais-2026 ss3-mon-tracé

# Ré-ouvrir une preview 3D depuis un bundle existant (sans réseau)
uv run rsb preview outputs/chablais-2026/ss5-9-evionnaz-vernayaz/

# Vue DÉTAILLÉE d'une spéciale (plan large + virages + profil/pente/dévers)
uv run rsb detail outputs/chablais-2026/ss5-9-evionnaz-vernayaz/
```

Les sorties (bundles, mesh, previews, carte du rallye, **dossiers piste AC**) vont
dans `outputs/` et les tuiles téléchargées dans `data/` — **les deux sont ignorés
par git** (ce sont des sorties + du contenu dérivé de vos données ; ne pas
redistribuer).

### Dossier piste prêt pour Assetto Corsa

Chaque build produit un **dossier piste au format AC**, prêt à copier :

```
outputs/<rallye>/<ss>/ac/<track_id>/          ← copiez CE dossier dans
  ├── <track_id>.fbx        Import ksEditor → export <track_id>.kn5 ICI
  ├── models.ini            content/tracks/
  ├── README_IMPORT.txt     (mode d'emploi ksEditor, sans Blender)
  ├── data/
  │   ├── surfaces.ini      ROAD / GRASS / KERB
  │   ├── map.ini + map.png minimap
  │   └── ai/               fast_lane.ai (à générer en jeu)
  └── ui/
      ├── ui_track.json     nom, longueur, tags
      ├── preview.png       355×200
      └── outline.png       355×200
```

**Il ne manque que le `.kn5`** (modèle 3D compilé) : ouvrez `<track_id>.fbx` dans
**ksEditor** (outil Kunos, **pas de Blender**), assignez les matériaux, exportez
le `.kn5` dans le dossier, puis copiez le tout dans
`Assetto Corsa/content/tracks/`. Détails : [`STAGE_GUIDE.md`](STAGE_GUIDE.md) §0bis.
L'**AI line** et les **pacenotes** se génèrent en jeu (§5–6).

### Utiliser avec un autre rallye

1. Créez un dossier `stages/<mon-rallye>/` avec un `rally.toml` (nom, provider MNT,
   valeurs par défaut, liste des spéciales — voir `stages/chablais-2026/rally.toml`).
2. Ajoutez vos **GPX** (roadbook / export perso) dans ce dossier (ils restent
   **locaux**, gitignorés). Un GPX multi-spéciales : une track par SS.
3. Un sous-dossier + `stage.toml` par spéciale, pointant vers le GPX + sa track :
   ```toml
   name = "mon-rallye-ss1"
   title = "Mon rallye — SS1"
   gpx = "../mon-rallye.gpx"
   gpx_track = "SS 1 - Nom"          # ou waypoints si pas de GPX
   ```
   Ou laissez `rsb new-stage stages/<mon-rallye> ss1-nom` créer le squelette.
4. `uv run rsb build-rally stages/<mon-rallye>` → un dossier piste AC par SS.

> **Hors Suisse** : swissALTI3D ne couvre que la Suisse. Pour un autre pays, il
> faut ajouter un `DEMProvider` (IGN, PNOA, Copernicus…) — l'architecture le
> permet sans toucher au reste (voir `providers/dem.py`).

### Un rallye entier

Un **rallye** = un dossier `stages/<rallye>/` avec un `rally.toml` (métadonnées +
**valeurs par défaut** héritées par chaque spéciale) et un sous-dossier
`stage.toml` par spéciale :

```
stages/chablais-2026/
├── rally.toml                       # défauts (CRS, provider, largeur…) + liste des SS
├── ss5-9-evionnaz-vernayaz/stage.toml
└── ss-demo-plaine-evionnaz/stage.toml   # minimal : hérite des défauts du rallye
```

`rsb build-rally` construit **toutes** les spéciales en **partageant le cache**
MNT/OSM, **saute** celles déjà construites (sauf `--force`), est **résilient**
(l'échec d'une spéciale n'interrompt pas les autres), et produit un
`rally.json` + une carte d'ensemble `rally_overview.png`.

## Architecture

```
rally-stage-builder/
├── stages/
│   └── chablais-2026/            # 1 dossier = 1 RALLYE
│       ├── rally.toml            # défauts hérités + liste des spéciales (SS)
│       └── ss5-9-evionnaz-vernayaz/stage.toml   # 1 sous-dossier = 1 spéciale
├── src/rsb/
│   ├── config.py                 # modèle stage.toml (pydantic)
│   ├── rally.py                  # modèle rally.toml + build_rally (multi-spéciales)
│   ├── pipeline.py               # build_stage : orchestration T2→T8
│   ├── cli.py                    # rsb build / build-rally / list / new-stage / preview
│   ├── providers/dem.py          # DEMProvider (ABC) + SwissAlti3DProvider
│   ├── fetch/stac_swisstopo.py   # STAC → tuiles GeoTIFF sur bbox
│   ├── geo/centerline.py         # osmnx : waypoints → tracé routé, rééchantillonné
│   ├── geo/drape.py              # Z du MNT le long du tracé
│   ├── geo/camber.py             # coupes perpendiculaires → largeur + dévers
│   ├── geo/surface.py            # segmentation tarmac/terre (+ hook ortho)
│   ├── geo/barriers.py           # offset bord de route + hook obstacles
│   ├── ir/bundle.py              # écrit la stage bundle (geojson + mesh terrain)
│   └── export/                   # adaptateurs (Blender, RTB) — stubs
├── validate/preview3d.py         # visu matplotlib 3D (profil + dévers) + carte rallye
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
