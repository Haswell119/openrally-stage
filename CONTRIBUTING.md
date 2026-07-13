# Contribuer à rally-stage-builder

Merci de votre intérêt ! Ce projet est **public** et communique en **français**
(code et identifiants en anglais).

## Mise en route

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
```

## Règles de contribution

- **1 tâche = 1 commit atomique** avec un message clair.
- **TDD sur le cœur géométrique** (`centerline`, `drape`, `camber`) : écrire le
  test d'abord.
- **Typing strict** : le code doit passer `mypy --strict` (voir `pyproject.toml`).
- **Lint** : le code doit passer `ruff check` et `ruff format --check`.
- **Ne cassez pas les tâches déjà validées** : `pytest` doit rester vert.
- Toute décision d'architecture significative → **une entrée datée dans
  `DECISIONS.md`** avec sa justification.

## Vérifications avant de pousser

```bash
ruff check .
ruff format --check .
mypy src/rsb
pytest            # tests hors-ligne (les tests réseau sont marqués @network)
```

## Données & licences

Ne committez **jamais** de géodonnées (tuiles MNT, extraits OSM) ni de secrets.
Respectez les licences décrites dans `ATTRIBUTION.md`. Aucun contenu issu de
`rally-maps.com` ne doit être scrapé ni redistribué.
