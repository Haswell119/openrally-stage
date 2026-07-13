# DECISIONS.md — journal des décisions d'architecture

Chaque choix d'architecture significatif est consigné ici : date, décision,
justification. Le plus récent en haut.

---

## 2026-07-13 — T0 : stack, packaging et hygiène du dépôt public

**Décision.** Python 3.11+, gestion des dépendances et de l'environnement avec
`uv`. Packaging `src/rsb` via `hatchling`. Qualité : `ruff` (lint + format),
`mypy --strict`, `pytest`. CI GitHub Actions exécutant lint + typecheck + tests
hors-ligne.

**Justification.** `uv` est rapide et reproductible. La disposition `src/`
évite les imports accidentels depuis le répertoire de travail. `mypy --strict`
impose le typing strict demandé. Les tests réseau (swisstopo/OSM) sont marqués
`@pytest.mark.network` et **exclus de la CI** pour garder celle-ci déterministe
et rapide ; le cœur géométrique est testé sur des fixtures synthétiques.

**Hygiène publique.** `LICENSE` MIT (code), `ATTRIBUTION.md` (OSM ODbL —
attribution obligatoire ; swisstopo OGD — mention appréciée), `.gitignore`
excluant `data/`, `outputs/`, `*.tif`, `*.kn5`, `*.fbx`, `.env`. Aucune
géodonnée ni secret n'est committé.

---

## 2026-07-13 — T2 : altimétrie derrière `DEMProvider` (strategy pattern)

**Décision.** L'accès à l'altitude passe par une ABC `DEMProvider` exposant une
API minimale (récupérer les tuiles / échantillonner Z sur une bbox).
`SwissAlti3DProvider` est la première implémentation (STAC swisstopo,
`ch.swisstopo.swissalti3d`, GeoTIFF 0,5 m, EPSG:2056).

**Justification.** *Suisse-first, pas Suisse-locked.* L'inversion de dépendance
permet d'ajouter IGN (France), PNOA (Espagne), Copernicus (Europe) **sans
toucher** au reste du pipeline (drape, camber, bundle ne connaissent que l'ABC).

---

## 2026-07-13 — T3 : routage WGS84 puis projection ; nearest_node maison

**Décision.** La centerline route sur le graphe OSM **non projeté** (osmnx 2.x,
`graph_from_bbox(bbox=(W,S,E,N))`, filtre `custom_filter` permissif), suit la
géométrie réelle des arêtes, **puis** projette la polyligne en EPSG:2056 avant le
rééchantillonnage. Le snapping des waypoints utilise un `nearest_node` maison
(équirectangulaire).

**Justification.** osmnx calcule `length` en mètres même sur graphe géographique,
donc le routage est correct sans projeter tout le graphe. `nearest_node` maison
évite la dépendance lourde **scikit-learn** (BallTree) exigée par
`osmnx.nearest_nodes` sur graphe non projeté. Cœur géométrique pur (resample,
caps, stitching) testé sans réseau.

## 2026-07-13 — T5 : convention de dévers + lissage médian

**Décision.** `camber_rad` **positif = la route penche à droite** (bord droit
plus bas), ajusté sur la portion centrale (largeur route). La largeur est
détectée depuis le MNT **seulement** en cas de rupture bilatérale nette
(plateforme/digue), sinon retour à la largeur config. Un filtre **médian** le
long du tracé (`camber.smooth_window_m`) atténue les pics de bruit du MNT.

**Justification.** Le MNT bare-earth ne révèle la largeur de route que sur les
talus ; ailleurs la config est plus honnête qu'une détection hasardeuse. Le
médian est robuste aux pics ponctuels (ponts, bords de talus) sans écraser les
tendances réelles.

## 2026-07-13 — T8/T9 : formats IR + preview AVANT KN5

**Décision.** La bundle sérialise en **GeoJSON** (EPSG:2056) + **OBJ** (mesh
corridor) + un **CSV localisé** aligné sur la convention d'axes de
`io_import_accsv` (colonnes AC X, Z, Y ; origine locale dans le manifeste). La
**preview 3D matplotlib** est produite systématiquement.

**Justification.** GeoJSON/OBJ sont universels et inspectables. Le CSV localisé
rend le passage à Blender immédiat. La preview permet de **valider avant**
d'investir dans le maillon manuel coûteux (KN5).

## 2026-07-13 — IR : stage bundle agnostique de l'éditeur (inversion de dépendance)

**Décision.** Le pipeline produit une **représentation intermédiaire (IR)** —
la *stage bundle* — qui ne dépend d'**aucun** éditeur. Les exporteurs (Blender,
RTB) sont des **adaptateurs** qui consomment l'IR.

**Justification.** Découpler la géométrie de rallye (centerline + Z + camber +
surfaces + barriers + mesh) de la cible d'export. On peut valider l'IR en 3D
(matplotlib) **avant** d'investir dans le maillon manuel coûteux (Blender/KN5).
