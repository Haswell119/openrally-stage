# Exemples

## `evionnaz-test-stage/` — piste de démonstration prête pour Assetto Corsa

Preview committée montrant que le pipeline produit une piste AC complète.

- `stage.toml` — config (2 bornes routées sur **OpenStreetMap**, sans GPX rally-maps).
- `ac/evionnaz-test-stage/` — **dossier piste au format AC**, à copier dans
  `Assetto Corsa/content/tracks/`. Il ne manque que le `.kn5` : générez-le depuis
  `evionnaz-test-stage.fbx` dans **ksEditor** (voir `README_IMPORT.txt` dans le dossier).

Données : © OpenStreetMap contributors (ODbL) ; Source swisstopo swissALTI3D (OGD).
Le tracé est une démonstration (routage OSM à 2 points), pas le tracé exact de la
spéciale. Régénérer : `uv run rsb build examples/evionnaz-test-stage/stage.toml`.
