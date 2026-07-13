# STAGE_GUIDE — du bundle à la spéciale jouable

Ce guide documente le **dernier maillon MANUEL** : transformer une *stage bundle*
produite par `rsb` en une piste Assetto Corsa jouable avec pacenotes.

```
 stage bundle (rsb)      →   Blender + io_import_accsv   →   KN5   →   AI line   →   Copilot (CSP)
 (geojson, obj, CSV)         (import + nommage AC)           (ksEditor)  (in-game)    (pacenotes)
```

> ⚠️ Recréation à **usage simulation personnel**. Respectez les licences
> (`ATTRIBUTION.md`) : **© OpenStreetMap contributors** (ODbL, attribution
> obligatoire) et **Source : swisstopo** (swissALTI3D). Ne redistribuez **aucun**
> contenu issu de rally-maps / roadbooks.

---

## 0. Ce que contient la bundle

Dossier `outputs/<name>/` produit par `rsb build` :

| Fichier | Contenu |
|---|---|
| `centerline.geojson` | Tracé LineString 3D (E, N, Z) + arrays par station (distance, **dévers**, largeur, cap, surface), en **EPSG:2056**. |
| `barriers.geojson` | Bordures gauche/droite (offset du bord de route), 3D. |
| `surfaces.geojson` | Segments de surface contigus (tarmac/terre). |
| `terrain.obj` | Mesh de terrain (corridor du MNT clippé, décimé) — décor de base. |
| `centerline_ac.csv` | Points **localisés** prêts pour `io_import_accsv` (voir §2). |
| `preview.png` | **Validation 3D** (tracé, profil, dévers) — à regarder AVANT tout. |
| `bundle.json` | Manifeste : `local_origin` (recalage LV95), stats, attribution. |

**Validez d'abord `preview.png`.** Si le tracé, le profil altimétrique ou le
dévers sont faux, corrigez `stage.toml` (waypoints / surfaces) et relancez
`rsb build` — n'investissez pas dans le KN5 tant que la preview n'est pas bonne.

---

## 1. Prérequis (à installer une fois)

- **Blender** (récent).
- **Addon `leBluem/io_import_accsv`** — <https://github.com/leBluem/io_import_accsv>.
  Installez l'**asset de RELEASE `io_import_accsv.zip`**, *pas* le « Source code
  (zip) » (ce dernier ne s'installe pas correctement).
- **SDK Assetto Corsa (ksEditor)** — pour l'export KN5 (chaîne recommandée).
- **Custom Shaders Patch (CSP) ≥ 0.2.4** — pour le mode Rally Stage + l'app
  **CSP Copilot** (pacenotes). Optionnel : **AI Line Helper** (Esotic).

---

## 2. Importer dans Blender

`rsb` peut générer un script d'import prêt à adapter :

```python
from rsb.export.blender_headless import write_blender_script
write_blender_script("outputs/chablais-2026-ss5-9-evionnaz-vernayaz")
# → outputs/.../blender_import.py  (blender --background --python blender_import.py)
```

Ou manuellement dans Blender (addon activé) : **File > Import > « AC side_x.CSV
(.csv) »** puis sélectionnez `centerline_ac.csv`, et importez `terrain.obj`.

### Convention d'axes (déjà gérée par la bundle)

`io_import_accsv` lit 3 colonnes **sans en-tête** et construit le sommet Blender
`(row[0], row[2], -row[1])`. `rsb` écrit donc `centerline_ac.csv` dans l'ordre AC
**X, Z, Y** (colonnes = `E_local , -(Z-Z0) , N_local`) pour obtenir en Blender un
sommet `(E_local, N_local, Z_local)` (Z = altitude, up). L'origine locale
`(E0, N0, Z0)` est dans `bundle.json → local_origin` (pour recaler en LV95 si besoin).

> ⚠️ « ACSV » n'est **pas** un format officiel : c'est du CSV AC (liste de points).
> Il n'y a **pas** de colonne largeur — la largeur/bordures vient des fichiers
> `side_l.csv`/`side_r.csv` ou des champs `distL/distR` du binaire `fast_lane.ai`
> (voir §4). Utilisez `barriers.geojson`/`width_m` de la bundle pour les modéliser.

---

## 3. Nommage Assetto Corsa (dans Blender)

AC déduit la physique du **nom des objets** (un nom commençant par un chiffre `>0`
devient collisionnable). Surfaces par défaut : `ROAD`, `GRASS`, `KERB`, `SAND`
(+ `WALL`). **Ne combinez jamais deux clés dans un même nom.**

| Élément | Nom |
|---|---|
| Route roulable | `1ROAD` (extrudez le tracé à la `width_m`) |
| Terrain / herbe | `1GRASS` (à partir de `terrain.obj`) |
| Portion terre | `1SAND` ou surface `GRAVEL` via CSP SurfacesFX |
| Murs / rails | `1WALL` (à partir de `barriers.geojson`) |

Objets logiques (empties) pour une spéciale **point-à-point** (A→B) :

| Empty | Rôle |
|---|---|
| `AC_AB_START_L` / `AC_AB_START_R` | Porte de **départ** |
| `AC_AB_FINISH_L` / `AC_AB_FINISH_R` | **Arrivée** |
| `AC_TIME_0_L` / `AC_TIME_0_R` | Split intermédiaire (une seule paire) |
| `AC_PIT_0` | Spawn (mode Practice), au départ |

> Évitez les suffixes de doublon Blender (`.001`) sur les objets `AC_` : le
> matching de nom d'AC casse. Le nombre de pits/starts se déclare dans
> `content/tracks/<piste>/ui/ui_track.json`.

---

## 4. Export KN5

**Chaîne recommandée (fiable) : Blender → FBX → ksEditor**
1. Exportez la scène en **FBX**.
2. Ouvrez ksEditor, réimportez le FBX **à l'échelle 0.01** (sinon piste ×100).
3. Affectez shaders/matériaux, puis **File > Save Persistence** → écrit
   `<track>.fbx.ini` (mémorise matériaux/objets tant que le nom du FBX ne change pas).
4. Exportez `<track>.kn5`.

**Alternative : export direct Blender → KN5** (opérateur « AC track .KN5
(experimental) » de l'addon, basé sur l'exporter Hagnhofer, format v5) — pratique
mais **expérimental**.

> Beaucoup de « la voiture tombe à travers la route » = mauvaise **échelle** (0.01)
> ou **nommage physique** manquant (`1ROAD`).

---

## 5. Générer l'AI line (`fast_lane.ai`) — prérequis dur pour les pacenotes

1. En jeu, chargez la piste, ouvrez l'app **AI** native et **enregistrez en
   conduisant** proprement (une voiture FWD rapide est conseillée ; la `.ai`
   porte aussi trajectoire/gaz/frein).
2. Cela produit `content/tracks/<piste>/ai/fast_lane.ai.candidate` → **retirez
   `.candidate`** → `fast_lane.ai`.
3. Bordures : enregistrez `side_l.csv`/`side_r.csv` avec l'**AI Line Helper**
   (Esotic), puis chargez la sim en maintenant **SHIFT** (avec les `side_*.csv`
   en place) pour « cuire » les bordures (`distL/distR`) dans la `fast_lane.ai`.

> Si vous exportez une AI line de base depuis Blender (`io_import_accsv`), elle
> est **incomplète** : finalisez-la en la (re)chargeant/sauvant dans **ksEditor**
> ou via le chargement SHIFT ci-dessus. À la création d'une nouvelle ligne,
> l'addon écrit un header de **version 7** (ne codez pas « 1 » en dur).

---

## 6. Pacenotes — CSP Copilot (co-pilote)

Avec **CSP ≥ 0.2.4**, l'app Lua **CSP Copilot** génère les pacenotes
**automatiquement et à la volée** depuis l'AI line (pas de recce). L'**AI line
est donc obligatoire** (§5).

- Mode **Rally Stage** : arrêt 2-3 m avant la ligne, frein à main, décompte ; le
  chrono démarre au « Go ». Résultats : `Documents\Assetto Corsa\savedData\rally-stages`.
- **Éditer** les notes : dans l'app, « create new from generated » ouvre un
  éditeur 3D. Jeux de pacenotes édités :
  `Documents\Assetto Corsa\cfg\extension\state\lua\app\RallyCopilot`.
- **Packs voix** (distinct) : `assettocorsa\apps\lua\RallyCopilot\voices`
  (audio + index `.txt`).

> Le co-driver classique de Patrick Brunner (`Documents\Assetto Corsa\plugins\
> Codriver\Tracks`) est un **système différent, non compatible** avec le Copilot
> CSP. Pour un format lisible/versionnable, voir l'app tierce `Koenvh1/PacenotePal`
> (YAML).

---

## 7. Récapitulatif des affinages à faire en amont (`stage.toml`)

Avant d'investir dans le KN5, affinez depuis votre **roadbook** (usage HUMAIN) :

- **waypoints** (départ / vias / arrivée) pour coller à la vraie route ;
- **`surface_overrides`** : distances réelles des portions « terre » ;
- **`route.default_width_m`** (et `camber.*`) si nécessaire.

Puis relancez `rsb build` et revalidez `preview.png`.

---

## Sources (vérifiées)

- `leBluem/io_import_accsv` (code source : `import_csv.py`, `export_ai.py`, `__init__.py`).
- Guides pistes : assettocorsamods.net (« build your first track »), site.hagn.io.
- Rallye / CSP Copilot : acrallycentral.com, acstuff.club (CSP 0.2.4), `Koenvh1/PacenotePal`.
