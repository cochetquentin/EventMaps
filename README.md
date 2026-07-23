# EventMaps

Scrapers d'événements géolocalisés pour alimenter une carte interactive.

## Installation

```bash
uv sync
cp .env.example .env   # configurer les variables si besoin
```

## Structure

```
EventMaps/
├── scrapers/          # Scrapers Tokyo Cheapo, Hanabi Walker, TimeoutTokyo et Ichiban Japan
├── models/            # Modèles Pydantic (Event, attributes, identity)
├── db/                # Persistance SQLite (EventStore, migrations)
├── api/               # API FastAPI (routes events, scrape, health)
├── frontend/          # UI carte interactive (Leaflet.js, ES modules)
├── tests/             # Tests Python + tests frontend Vitest
├── docs/              # Documentation technique
├── data/              # Base de données et exports CSV (gitignored)
└── main.py            # CLI de scraping
```

## Scraping

```bash
# Scraper Tokyo Cheapo → SQLite
uv run python main.py tc

# Scraper Hanabi Walker → SQLite (région Kantō par défaut)
uv run python main.py hanabi --region ar0300

# Scraper TimeoutTokyo → SQLite
uv run python main.py tot

# Scraper Ichiban Japan → SQLite
uv run python main.py ij

# Scraper toutes les sources
uv run python main.py all

# Exporter en CSV au lieu de SQLite (--output est un flag global, avant le sous-commande)
uv run python main.py --output csv tc > output.csv
```

**Codes région Hanabi Walker :**

| Code | Région |
|---|---|
| `ar0300` | Kantō (défaut) |
| `ar0100` | Hokkaido |
| `ar0200` | Tōhoku |
| `ar0400` | Chūbu |
| `ar0500` | Kansai |
| `ar0600` | Chūgoku |
| `ar0700` | Shikoku |
| `ar0800` | Kyūshū / Okinawa |

## UI carte interactive

```bash
uv run uvicorn api.app:app --reload
# → ouvrir http://localhost:8000
```

Affiche tous les événements géolocalisés sur une carte OpenStreetMap :
- **Bleu** → Tokyo Cheapo · **Orange** → Hanabi · **Rouge** → TimeoutTokyo · **Violet** → Ichiban Japan
- Clustering automatique des marqueurs proches
- Popup au clic : titre, date, lieu, prix / feux d'artifice, lien
- Filtres par source et par date (sidebar gauche)

## API

```bash
uv run uvicorn api.app:app --reload
```

### Endpoints

```
GET  /                              → UI carte (Leaflet.js)
GET  /events                        → liste des événements (filtres, pagination)
GET  /events/{id}                   → détail d'un événement
GET  /events/{id}.ics               → export iCal d'un événement
GET  /events.ics                    → export iCal des événements filtrés (max 5 000 ; tronqué via headers si dépassé)
POST /scrape                        → déclenche un job de scraping (async)
GET  /scrape/status                 → état du dernier job (filtrable par source ou job_id)
GET  /scrape/config                 → indique si /scrape est public (sans token)
GET  /health                        → healthcheck DB
GET  /docs                          → Swagger UI
```

**Paramètres `GET /events` :**

| Paramètre | Type | Description |
|---|---|---|
| `source` | `tc` \| `hanabi` \| `tot` \| `ij` | Filtre par source |
| `date` | `YYYY-MM-DD` | Filtre par chevauchement de date |
| `bbox` | `min_lon,min_lat,max_lon,max_lat` | Filtre géographique |
| `start_from` | `YYYY-MM-DD` | Borne inférieure de chevauchement : inclut les événements dont `COALESCE(end_date, start_date) >= start_from` |
| `start_to` | `YYYY-MM-DD` | Borne haute sur `start_date` |
| `q` | `string` | Recherche textuelle (titre, lieu, access) |
| `category` | `string` | Filtre par catégorie (champ `attributes.categories` — compatible TC et TOT) |
| `limit` | `int` 1–500 (défaut 100) | Pagination |
| `offset` | `int` (défaut 0) | Pagination |

Sans filtre de date, seuls les événements à venir sont retournés.

**`POST /scrape` :**

```
POST /scrape?source=all&region=ar0300
Authorization: Bearer <EVENTMAPS_SCRAPE_TOKEN>
```

Paramètres : `source` (`tc` | `hanabi` | `tot` | `ij` | `all`), `region` (code Hanabi Walker). Rate limité à 2 req/h.

Réponses possibles :
- `{"status": "started", "job_id": 42}` — job lancé ; utiliser `GET /scrape/status?job_id=42` pour suivre.
- `{"status": "already_running", "running_sources": ["tc"]}` — un job conflictuel est déjà actif ; pas de `job_id` retourné.

### Exemple de réponse

```json
[
  {
    "id": "4e1e4f87206f7566",
    "source": "tc",
    "title": "Dry Noodle Grand Prix",
    "url": "https://tokyocheapo.com/events/dry-noodle-grand-prix/",
    "start_date": "2026-05-11",
    "end_date": "2026-05-20",
    "times": "10:00-18:00",
    "venue": null,
    "latitude": 35.627198,
    "longitude": 139.661894,
    "price": "Free",
    "attributes": {
      "categories": ["food"],
      "tags": ["food", "noodles"],
      "official_link": null,
      "location_name": "Komazawa Olympic Park"
    },
    "created_at": "2026-05-16T12:51:25+00:00"
  }
]
```

## Base de données

Les événements sont stockés dans `data/events.db` (SQLite) avec un hash SHA-256 (16 hex) comme clé primaire. Relancer le scraper met à jour les lignes existantes sans créer de doublons.

| Table | Source | Clé de déduplication |
|---|---|---|
| `events` (TC) | tokyocheapo.com | `url` + `location_name` |
| `events` (Hanabi) | hanabi.walkerplus.com | `url` + `date` |
| `events` (TOT) | timeout.com/tokyo | `url` |
| `scrape_jobs` | — | suivi des jobs de scraping |

## Modèles de données

### TokyoCheapoEvent

| Champ | Description |
|---|---|
| `title` | Nom de l'événement |
| `start_date` / `end_date` | Dates au format `YYYY-MM-DD` |
| `times` | Horaires (`HH:MM–HH:MM`) |
| `price` | Prix (`Free`, `¥1,000`, etc.) |
| `categories` / `tags` | Listes de strings |
| `official_link` | URL du site officiel |
| `location_name` / `lat` / `lng` | Lieu et coordonnées GPS |

Les dates floues (`Mid May`, `Early Apr ~ Late Jun`) sont converties : Early=1–10, Mid=11–20, Late=21–fin du mois. Les événements multi-lieux génèrent une ligne par lieu.

### HanabiEvent

| Champ | Description |
|---|---|
| `title` | Nom du festival |
| `start_date` | Date au format `YYYY-MM-DD` |
| `times` | Horaires (`HH:MM–HH:MM`) |
| `fireworks_count` | Nombre de feux (ex. `"10000発"`) |
| `fireworks_duration` | Durée du spectacle |
| `expected_crowd` | Affluence estimée |
| `rain_policy` | Politique en cas de pluie |
| `paid_seating` / `paid_seating_details` | Places payantes |
| `food_stalls` | Stands de nourriture |
| `venue` / `access` / `parking` | Informations pratiques |
| `official_site` / `official_x` | Liens officiels |
| `lat` / `lng` | Coordonnées GPS |

Les événements multi-jours génèrent une ligne par jour.

## Configuration

Variables d'environnement préfixées `EVENTMAPS_` (fichier `.env` ou variables système) :

| Variable | Défaut | Description |
|---|---|---|
| `EVENTMAPS_ENV` | `development` | `development` \| `production` — en production, un `EVENTMAPS_ALLOWED_ORIGINS` resté au wildcard (`*`) empêche le démarrage |
| `EVENTMAPS_DB_PATH` | `data/events.db` | Chemin vers la base SQLite |
| `EVENTMAPS_PORT` | `8000` | Port d'écoute uvicorn |
| `EVENTMAPS_LOG_LEVEL` | `INFO` | Niveau de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `EVENTMAPS_REQUEST_LOGGING` | `false` | Activer le log des requêtes HTTP (timings) |
| `EVENTMAPS_ALLOWED_ORIGINS` | `*` | Origines CORS — CSV ou JSON array |
| `EVENTMAPS_SCRAPE_TOKEN` | _(vide)_ | Token Bearer pour `POST /scrape` — si vide, l'endpoint est **public** (rate limité à 2 req/h) |
| `EVENTMAPS_SCRAPE_USER_AGENT` | `EventMaps/1.0` | User-Agent HTTP des scrapers |
| `EVENTMAPS_SCRAPE_TIMEOUT_HOURS` | `2` | Durée max d'un job avant marquage stale |
| `EVENTMAPS_SCRAPE_ERROR_THRESHOLD` | `0.5` | Taux d'erreur max avant échec du job (0.0–1.0) |
| `EVENTMAPS_SCRAPE_REQUEST_TIMEOUT_SECONDS` | `10` | Timeout HTTP par requête (secondes) |
| `EVENTMAPS_SCRAPE_MAX_PAGES_TC` | `10` | Pages max scraper Tokyo Cheapo |
| `EVENTMAPS_SCRAPE_MAX_PAGES_HANABI` | `20` | Pages max scraper Hanabi Walker |
| `EVENTMAPS_SCRAPE_MAX_LISTING_PAGES_TOT` | `4` | Pages max scraper TimeoutTokyo |
| `EVENTMAPS_SCRAPE_MAX_PAGES_IJ` | `5` | Pages catégorie max scraper Ichiban Japan |
| `EVENTMAPS_SCRAPE_RETRY_ATTEMPTS` | `3` | Nombre de tentatives tenacity |
| `EVENTMAPS_SCRAPE_RETRY_WAIT_MIN` | `2` | Backoff min entre tentatives (secondes) |
| `EVENTMAPS_SCRAPE_RETRY_WAIT_MAX` | `10` | Backoff max entre tentatives (secondes) |

**Dev local :** copier `.env.example` en `.env` à la racine (chargé automatiquement).

**Production :** définir `EVENTMAPS_ENV=production` et restreindre `EVENTMAPS_ALLOWED_ORIGINS` à l'origine réelle du frontend :
```
EVENTMAPS_ENV=production
EVENTMAPS_ALLOWED_ORIGINS=https://monapp.example.com
EVENTMAPS_SCRAPE_TOKEN=un-token-secret-fort
```
Si `EVENTMAPS_ENV=production` et `EVENTMAPS_ALLOWED_ORIGINS` reste au wildcard (`*`), l'application **refuse de démarrer** (`RuntimeError`). En développement (valeur par défaut), la même situation combinée à un `EVENTMAPS_SCRAPE_TOKEN` défini n'émet qu'un avertissement.

## Docker

```bash
# Build
docker build -t eventmaps .

# Run (production, avec token de scraping)
docker run -p 8000:8000 \
  -e EVENTMAPS_ENV=production \
  -e EVENTMAPS_SCRAPE_TOKEN=mon-token \
  -e EVENTMAPS_ALLOWED_ORIGINS=https://monapp.example.com \
  -v $(pwd)/data:/app/data \
  eventmaps

# → http://localhost:8000
```

L'image utilise un utilisateur non-root (`appuser`) et inclut un healthcheck sur `/health`.

## Tests

```bash
# Tous les tests Python (avec coverage, gate CI à 80 %)
make test

# Tests frontend (Vitest)
make test-frontend

# Reproduire tous les checks CI en local (lint, format, tests, sécurité)
make ci
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — architecture, flux de données, contrat `attributes` par source, schéma DB
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, conventions, workflow PR, politique fixtures
