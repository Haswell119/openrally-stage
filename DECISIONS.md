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

## 2026-07-13 — IR : stage bundle agnostique de l'éditeur (inversion de dépendance)

**Décision.** Le pipeline produit une **représentation intermédiaire (IR)** —
la *stage bundle* — qui ne dépend d'**aucun** éditeur. Les exporteurs (Blender,
RTB) sont des **adaptateurs** qui consomment l'IR.

**Justification.** Découpler la géométrie de rallye (centerline + Z + camber +
surfaces + barriers + mesh) de la cible d'export. On peut valider l'IR en 3D
(matplotlib) **avant** d'investir dans le maillon manuel coûteux (Blender/KN5).
