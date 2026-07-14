# rally-stage-builder (`rsb`)

**Transforme une route réelle en spéciale de rallye pour Assetto Corsa, à partir
de géodonnées ouvertes — sans modéliser le tracé à la main.**

Tu donnes un **tracé** (un GPX de roadbook, ou un départ + une arrivée) ; l'outil
route la spéciale sur le **vrai réseau routier** (OpenStreetMap), la drape sur un
**modèle d'altitude haute résolution** (swissALTI3D, 0,5 m), calcule le **dévers**,
segmente les **surfaces** (tarmac / terre), pose des **bordures** et des
**barrières** d'après le relief, puis écrit un **dossier piste prêt pour AC**,
**`.kn5` compilé inclus** — tu le copies dans `content/tracks/` et tu roules.

> 🇨🇭 **Aujourd'hui, l'altitude ne couvre que la Suisse** (source swissALTI3D).
> Le reste de l'architecture est prêt pour d'autres pays, mais il faut y ajouter
> une source d'altitude (voir [Limites](#limites)).

---

## Ce que tu obtiens (et ce qu'il reste à faire)

À chaque build, `rsb` produit un dossier au **format piste Assetto Corsa**, prêt
à copier dans `content/tracks/` — **avec le `.kn5` déjà compilé** (ni Blender ni
ksEditor requis pour rouler) :

```
outputs/<rallye>/<ss>/ac/<track_id>/
├── <track_id>.kn5     ← modèle 3D compilé, PRÊT À JOUER (route/bordures/barrières/
│                        terrain + matériaux + objets AC). Écrit directement.
├── <track_id>.fbx     même géométrie, si tu veux affiner les shaders dans ksEditor
├── models.ini         référence le .kn5
├── data/
│   ├── surfaces.ini   ROAD / GRASS / KERB
│   ├── map.ini + map.png   minimap
│   └── ai/            (fast_lane.ai à enregistrer en jeu)
├── ui/
│   ├── ui_track.json  nom, longueur, tags
│   ├── preview.png    355×200
│   └── outline.png    355×200
└── README_IMPORT.txt  mode d'emploi
```

| ✅ `rsb` s'en occupe | 🛠️ À toi de finir (en jeu) |
|---|---|
| Tracé routé sur OSM, drapé sur le MNT | Enregistrer l'**AI line** (`fast_lane.ai`, app AI) |
| Dévers, largeur, surfaces | **Pacenotes** via CSP Copilot |
| Bordures + barrières d'après le relief | *(optionnel)* meilleurs shaders/textures dans ksEditor |
| **`.kn5` compilé** + matériaux + objets AC | |
| Minimap, previews UI, `ui_track.json` | |

Copie le dossier dans `content/tracks/`, lance AC en **Practice** → tu roules.
Le `.kn5` est écrit d'après un format public reverse-engineeré et **recoupé avec
deux lecteurs KN5 indépendants** ; les textures sont unies (une couleur par
surface). Pour un rendu plus riche, réimporte le `.fbx` dans ksEditor
(facultatif). Le chrono de spéciale et les pacenotes se règlent en jeu — voir
[`STAGE_GUIDE.md`](STAGE_GUIDE.md).

---

## Prérequis

- **Python 3.11+** et [**uv**](https://docs.astral.sh/uv/) (gestionnaire d'env
  recommandé ; un `pip` classique marche aussi, voir plus bas).
- Une **connexion internet** (le build télécharge le réseau OSM et les tuiles MNT).
- Pour le dernier maillon : **ksEditor** (SDK Kunos, gratuit) et, pour les
  pacenotes, **Custom Shaders Patch** ≥ 0.2.4. Voir [`STAGE_GUIDE.md`](STAGE_GUIDE.md).

## Installation

```bash
git clone <ce-dépôt> && cd rally-stage-builder

# avec uv (recommandé)
uv venv --python 3.11
uv pip install -e ".[dev]"

# …ou avec pip classique
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Active l'environnement pour disposer de la commande `rsb` :

```bash
source .venv/bin/activate       # …ou préfixe chaque commande par `uv run` (ex. `uv run rsb doctor`)
```

Vérifie que tout est prêt (Python, dépendances, accès OSM/swisstopo) :

```bash
rsb doctor
```

> `rsb doctor` te dit exactement ce qui manque avant de lancer un build. Ajoute
> `--no-network` pour ne tester que l'environnement local.

---

## Prise en main en 3 minutes (exemple fourni)

Le dépôt contient une spéciale de démonstration **prête à l'emploi**
(Evionnaz–Vernayaz), construite uniquement depuis des données redistribuables.

```bash
# 1) construis-la (télécharge OSM + MNT pour cette zone, ~1 min)
rsb build examples/evionnaz-test-stage/stage.toml

# 2) regarde la preview 3D AVANT d'aller plus loin
#    → outputs/evionnaz-test-stage/preview.png  (tracé + profil d'altitude + dévers)

# 3) le dossier piste AC (avec le .kn5 compilé) est là :
#    → outputs/evionnaz-test-stage/ac/evionnaz-test-stage/
#      copie-le dans <Assetto Corsa>/content/tracks/, lance AC → Practice → roule.
```

Pas envie d'attendre le build ? Une version **déjà construite** de cet exemple
(avec son `.kn5`) est versionnée dans
[`examples/evionnaz-test-stage/`](examples/evionnaz-test-stage/) : copie
`ac/evionnaz-test-stage/` dans `content/tracks/` et roule tout de suite.

> ⚠️ **Valide toujours `preview.png` d'abord.** Si le tracé, le profil d'altitude
> ou le dévers sont faux, corrige le `stage.toml` (waypoints / surfaces) et
> relance — inutile d'investir dans le KN5 tant que la preview n'est pas bonne.

---

## Construire ta propre spéciale

Il y a **deux façons** de fournir le tracé :

### A. Depuis un GPX (recommandé — le plus fidèle)

Un GPX de roadbook donne le **tracé réel dense**. Il est utilisé directement comme
centerline (projeté + rééchantillonné), puis drapé sur le MNT.

```toml
# stage.toml
name = "mon-rallye-ss1"
title = "Mon rallye — SS1"
direction = "Village A → Village B"
gpx = "mon-rallye.gpx"        # chemin relatif au stage.toml
gpx_track = "SS 1 - Nom"      # si le GPX contient plusieurs spéciales (nom ou index)
default_surface = "tarmac"
```

> ⚠️ Un GPX est un **contenu tiers** (roadbook / rally-maps). Il reste **local** :
> le dépôt ignore les `*.gpx`, ne les redistribue pas. `rally-maps.com` sert de
> **référence humaine** pour choisir la route — **aucun scraping**.

### B. Depuis un départ + une arrivée (routage OSM)

Sans GPX, liste des waypoints ; l'outil route sur le vrai réseau OSM. Pratique
pour esquisser une spéciale.

```toml
name = "mon-rallye-ss1"
title = "Mon rallye — SS1"

[[waypoints]]
role = "start"
name = "Départ"
lat = 46.1734
lon = 7.0216

# [[waypoints]] role = "via" … (points de passage intermédiaires, optionnels)

[[waypoints]]
role = "end"
name = "Arrivée"
lat = 46.1438
lon = 7.0377
```

Puis :

```bash
rsb build chemin/vers/stage.toml
```

### Un rallye entier (plusieurs spéciales)

Un **rallye** = un dossier avec un `rally.toml` (métadonnées + valeurs par défaut
héritées) et un sous-dossier `stage.toml` par spéciale.

```bash
rsb new-stage stages/mon-rallye ss1-nom   # crée le squelette d'une spéciale
rsb list       stages/mon-rallye          # liste les spéciales
rsb build-rally stages/mon-rallye         # construit TOUT + une carte d'ensemble
```

`build-rally` partage le cache OSM/MNT, **saute** les spéciales déjà construites
(sauf `--force`), est **résilient** (l'échec d'une SS n'interrompt pas les autres)
et produit un `rally_overview.png`. Modèle complet :
[`stages/chablais-2026/`](stages/chablais-2026/).

---

## Les commandes

| Commande | Rôle |
|---|---|
| `rsb doctor` | Vérifie Python, dépendances et connectivité (à lancer en premier). |
| `rsb build <stage.toml>` | Construit **une** spéciale → bundle + dossier AC + preview. |
| `rsb build-rally <dir>` | Construit **toutes** les spéciales d'un rallye + carte. |
| `rsb preview <bundle>` | Re-rend la preview 3D d'une bundle (sans réseau). |
| `rsb detail <bundle>` | Vue détaillée (plan large + virages + profil/pente/dévers). |
| `rsb list <dir>` | Liste les spéciales d'un rallye. |
| `rsb new-stage <dir> <id>` | Crée le squelette d'une spéciale. |

`rsb <commande> --help` détaille les options. En cas d'erreur, le message est
présenté en clair ; ajoute `--traceback` pour la trace complète.

Les sorties vont dans `outputs/` et les tuiles/graphes téléchargés dans `data/` :
**les deux sont ignorés par git** (sorties + contenu dérivé, à ne pas redistribuer).

---

## Limites

- **Altitude = Suisse uniquement.** swissALTI3D ne couvre que la Suisse. Pour un
  autre pays, il faut brancher une source d'altitude (IGN France, PNOA Espagne,
  Copernicus…) : l'architecture le permet via `DEMProvider`
  ([`src/rsb/providers/dem.py`](src/rsb/providers/dem.py)) **sans toucher au
  reste du pipeline**, mais ce provider reste à écrire.
- **`.kn5` généré, non testé dans AC ici.** Le modèle est écrit d'après un format
  public reverse-engineeré et recoupé avec deux lecteurs KN5 indépendants, mais il
  n'a pas pu être ouvert dans AC dans cet environnement. Textures unies (une par
  surface) ; pour des shaders soignés, réimporte le `.fbx` dans ksEditor.
- **En jeu, il reste** l'**AI line** (app AI) et les **pacenotes** (CSP Copilot)
  — voir [`STAGE_GUIDE.md`](STAGE_GUIDE.md).
- **Recréation à usage simulation personnel.** Respecte les licences des données.

## Licences & attribution

- **Code** : licence **MIT** (voir [`LICENSE`](LICENSE)).
- **Données** (attribution **obligatoire**, voir [`ATTRIBUTION.md`](ATTRIBUTION.md)) :
  - **© OpenStreetMap contributors** — réseau routier, licence ODbL.
  - **Source : Office fédéral de topographie swisstopo** — MNT swissALTI3D (OGD).
- **rally-maps / roadbooks** : référence **humaine** uniquement. **Aucun
  scraping, aucune redistribution** de leur contenu (les GPX restent locaux).

---

## Sous le capot (pour les curieux)

```
src/rsb/
├── config.py        stage.toml (pydantic)          providers/dem.py   DEMProvider + swissALTI3D
├── rally.py         rally.toml + build multi-SS     fetch/…            STAC swisstopo → tuiles
├── pipeline.py      orchestration build_stage       geo/centerline.py  OSM/GPX → tracé
├── cli.py           commandes rsb                    geo/drape.py       Z du MNT (+ dé-spiking)
├── ir/bundle.py     la « stage bundle » (IR)         geo/camber.py      coupes → largeur + dévers
└── export/ac_track  FBX + dossier AC                 geo/{surface,barriers}.py
validate/preview3d.py   previews 3D (matplotlib) + carte de rallye
```

La **stage bundle** (IR) ne dépend d'aucun éditeur : les exporteurs sont des
adaptateurs. Choix d'architecture : [`DECISIONS.md`](DECISIONS.md). Contribuer :
[`CONTRIBUTING.md`](CONTRIBUTING.md) (1 tâche = 1 commit atomique, `ruff` +
`mypy --strict` + `pytest` verts).

## Disclaimer

Ces recréations sont destinées à un **usage de simulation personnel**. Les auteurs
déclinent toute responsabilité quant à l'exactitude des tracés ou à l'usage qui en
est fait.
