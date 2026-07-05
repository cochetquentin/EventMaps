# Contributing to EventMaps

## Gel de stabilisation (début : 6 juin 2026 — fin : définie lors de STAB-004)

Le dépôt est en phase de **stabilisation**. Seules les contributions suivantes sont acceptées :

| Type autorisé | Exemples |
|---|---|
| `fix` | Correction de bug |
| `test` | Ajout ou correction de tests |
| `refactor` | Refactoring sans changement de comportement |
| `chore` | Outillage, dépendances, CI |
| `docs` | Documentation uniquement |
| `ci` | Pipelines GitHub Actions |

**`feat` est bloqué** : aucune nouvelle fonctionnalité produit ne sera mergée pendant cette période.

Les demandes produit reçues pendant le gel doivent être étiquetées `product-backlog` et reportées après la revue de sortie de stabilisation (STAB-004).

## Prérequis

- **Python 3.13+** géré par [uv](https://docs.astral.sh/uv/)
- **Node.js 18+** pour les tests frontend (Vitest)
- Git

## Setup

```bash
git clone <repo>
cd EventMaps

# Installer les dépendances Python
uv sync

# Installer les dépendances Node (Vitest)
npm ci

# Copier et adapter la configuration locale
cp .env.example .env
```

Le fichier `.env` est chargé automatiquement par `pydantic-settings`. Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour la liste complète des variables.

## Commandes essentielles

```bash
# Serveur de développement
uv run uvicorn api.app:app --reload
# → http://localhost:8000

# Tests Python (avec coverage ≥ 80 %)
uv run python -m pytest --cov=. --cov-fail-under=80 tests/ -q

# Tests Python filtrés
uv run python -m pytest tests/test_api.py -v

# Lint + format (Ruff)
uv run ruff check --fix . && uv run ruff format .

# CLI scraping (sans serveur)
uv run python main.py tc           # Tokyo Cheapo → SQLite
uv run python main.py hanabi       # Hanabi Walker (région Kantō)
uv run python main.py all          # Les deux sources

# Tests frontend (Vitest)
npx vitest run
```

## Stratégie de branches

### Principes

- **`main` protégée** : aucun commit direct, toujours via PR
- **Branches courtes** : une branche = une issue = une PR ; supprimée dès le merge
- **Pas de branche longue permanente** : pas de `develop`, `staging` ou équivalent

### Conventions de nommage

| Format | Exemples |
|--------|---------|
| `type/issue-NNN-description-courte` | `fix/issue-42-cors-headers`, `docs/issue-71-branch-strategy` |
| `type/description-courte` (sans issue dédiée) | `chore/update-deps` |
| Dependabot | `dependabot/pip/…` (géré automatiquement) |

Les types valides sont les mêmes que pour les commits : `fix`, `feat`, `test`, `refactor`, `chore`, `docs`, `ci`.

### Protection de main

Avant tout merge, la CI exige :

| Check | Description |
|-------|-------------|
| `Python / Format` | Ruff format |
| `Python / Lint` | Ruff lint |
| `Python / Security` | Bandit |
| `Python / Tests` | pytest + coverage ≥ 80 % |
| `Frontend / Tests` | Vitest |
| `Docker / Build and smoke test` | Build image + smoke |

La branche doit également être **à jour avec `main`** (strict mode) et la règle s'applique **aux admins** (`enforce_admins`). Force-push et suppression directe de `main` sont interdits.

### Règles de merge

- Méthode : **squash merge** — un commit propre par PR dans `main`
- Titre du commit squash = titre de la PR (conventions de commit appliquées)
- Les branches de PR sont **supprimées automatiquement** après merge (paramètre dépôt activé)

### Exceptions

| Cas | Règle |
|-----|-------|
| Branches Dependabot | Nommage automatique `dependabot/…` ; merge dès que CI vert |
| Hotfix urgent | Branche `fix/` courte — mêmes checks, aucune exception CI |

## Workflow PR

1. Créer une branche depuis `main` : `git checkout -b type/issue-NNN-description-courte`
2. Faire les modifications
3. Lancer Ruff avant tout commit : `uv run ruff check --fix . && uv run ruff format .`
4. Vérifier que les tests passent avec coverage ≥ 80 %
5. Commiter et ouvrir une PR vers `main`

**Règle :** une PR = une tâche atomique. Ne pas regrouper des corrections sans rapport.

## Conventions de commit

Format : `type(scope): message`

| Type | Usage |
|------|-------|
| `fix` | Correction de bug |
| `feat` | Nouvelle fonctionnalité |
| `test` | Ajout ou correction de tests |
| `refactor` | Refactoring sans changement de comportement |
| `chore` | Outillage, dépendances, CI |
| `docs` | Documentation uniquement |
| `ci` | Pipelines GitHub Actions |

Exemples :
```
fix(scraper): corriger la validation des dates Hanabi
feat(api): ajouter filtre bbox sur GET /events
test(store): couvrir upsert avec conflit de clé
```

## Style Python

- **Ruff** est le seul linter/formatter utilisé (config dans `pyproject.toml`)
- Type hints obligatoires sur les signatures publiques
- Python 3.13 — utiliser les nouveautés du langage sans hésitation
- Imports regroupés : stdlib → third-party → first-party (`api`, `db`, `models`, `scrapers`, `config`)

## Tests — Règles importantes

### Jamais de scraping en live

Les tests ne font **jamais** de vraies requêtes HTTP vers les sources tierces. Utiliser :
- Des fixtures HTML statiques dans `tests/fixtures/` (HTML sauvegardé manuellement)
- `unittest.mock` (stdlib) pour mocker les appels `requests`

Ajouter une fixture :
1. Sauvegarder le HTML dans `tests/fixtures/{source}/{category}/{type}[_{variante}].html`
   — où `{source}` est `tc`, `hanabi` ou `tot` ; `{category}` est `real` ou `synthetic`.
   Exemples : `tests/fixtures/tc/synthetic/event_no_price.html`, `tests/fixtures/tot/real/event_full.html`.
2. Déclarer le fichier dans `tests/fixtures/MANIFEST.yml` (voir `tests/fixtures/POLICY.md` §3-4).
3. Charger ce fichier dans le test avec `Path(__file__).parent / "fixtures" / "{source}/{category}/{nom}.html"`

### Coverage

Le gate de coverage est **80 %** vérifié par la CI. Toute nouvelle fonctionnalité doit être couverte. Vérifier localement avant de pousser :

```bash
uv run python -m pytest --cov=. --cov-fail-under=80 tests/ -q
```

### Tests frontend

Les tests JS dans `frontend/tests/` sont exécutés avec Vitest. Ils couvrent les fonctions pures (helpers, escaping, parsing) — pas l'intégration Leaflet.

```bash
npx vitest run
```

## Politique scraping respectueux

Les scrapers doivent :
- Déclarer un `User-Agent` explicite (`EventMaps/1.0`, configurable via `EVENTMAPS_SCRAPE_USER_AGENT`)
- Ne jamais être exécutés de façon automatique non contrôlée (le rate limit de `POST /scrape` est 2 req/h)
- Ne pas contourner les robots.txt des sites ciblés

Note : tenacity est configuré pour les **retries** uniquement (backoff entre tentatives échouées), pas comme mécanisme de throttling entre requêtes.

## Structure du projet

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) pour la description complète des modules, du schéma de données, et des endpoints API.
