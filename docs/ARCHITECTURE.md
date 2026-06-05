# Architecture EventMaps

## Vue d'ensemble

EventMaps est un agrégateur d'événements géolocalisés composé de trois parties :

1. **Scrapers** — collectent les événements sur des sources tierces
2. **API FastAPI** — expose les événements via HTTP (REST + iCal)
3. **Frontend Leaflet** — affiche les événements sur une carte interactive

### Flux de données

```
Sources tierces
  tokyocheapo.com       hanabi.walkerplus.com
       │                        │
       ▼                        ▼
  TokyoCheapo            HanabiWalker
  (scrapers/)            (scrapers/)
       │                        │
       └──────────┬─────────────┘
                  ▼
           models/Event
           (Pydantic model)
                  │
                  ▼
           db/EventStore
           (SQLite WAL)
                  │
                  ▼
           api/routes/events.py
           GET /events, GET /events/{id}
                  │
                  ▼
           frontend/js/*.js
           Leaflet + clustering
```

Le scraping est déclenché manuellement (CLI `main.py`) ou via `POST /scrape` (API, protégé par token). Le résultat est persisté en SQLite, puis servi par l'API sans état.

---

## Modules principaux

### `scrapers/`

| Fichier | Rôle |
|---------|------|
| `base.py` | `BaseScraper` (interface), `ScrapeReport` (métriques) |
| `tokyo_cheapo.py` | Scraper tokyocheapo.com → `Event` avec `TokyoCheapoAttributes` |
| `hanabi_walker.py` | Scraper hanabi.walkerplus.com → `Event` avec `HanabiWalkerAttributes` |

Chaque scraper retourne `(list[Event], ScrapeReport)`. `ScrapeReport` comptabilise `links_seen`, `events_ok`, `events_skipped`, `errors[]`, `duration_s`.

Les retries HTTP sont gérés via **tenacity** (3 tentatives, backoff 2–10 s configurable).

### `models/`

| Fichier | Rôle |
|---------|------|
| `event.py` | Modèle canonical `Event` (Pydantic v2) |
| `attributes.py` | `TokyoCheapoAttributes`, `HanabiWalkerAttributes` (Pydantic BaseModel) |
| `identity.py` | `make_event_id(parts)` — génère l'ID stable SHA-256 |

### `db/`

| Fichier | Rôle |
|---------|------|
| `store.py` | `EventStore` — façade publique (context manager) |
| `events.py` | `EventRepository` — CRUD événements |
| `jobs.py` | `JobRepository` — suivi des jobs de scrape |
| `schema.py` | DDL des tables + migrations |
| `migrations.py` | Migration depuis le schéma legacy (table unique `events`) |

SQLite en mode WAL. La DB est créée automatiquement à la première connexion.

### `api/`

| Fichier | Rôle |
|---------|------|
| `app.py` | Application FastAPI, middlewares CORS et logging, montage des routes |
| `routes/events.py` | `GET /events` (filtres, pagination) + `GET /events/{id}` + `GET /events/{id}.ics` |
| `routes/scrape.py` | `POST /scrape`, `GET /scrape/status`, `GET /scrape/config` |
| `limiter.py` | Instance SlowAPI (rate limit 2 req/h sur `/scrape`) |

### `frontend/`

Modules ES (pas de bundler) chargés via `<script type="module">` :

| Fichier | Rôle |
|---------|------|
| `app.js` | État global, event listeners, orchestration |
| `api.js` | `fetchEventsByBbox()` → appels API REST |
| `markers.js` | `renderMarkers()`, clustering Leaflet |
| `popups.js` | `buildPopup()`, `escapeHtml()` (protection XSS) |
| `filters.js` | Presets de date, filtre par source |
| `events-list.js` | Liste latérale des événements |
| `favorites.js` | Favoris via `localStorage` |
| `geolocation.js` | `navigator.geolocation` |
| `utils.js` | Helpers divers, parsing `timeRange` |

---

## Modèle de données

### Event (modèle canonical)

```python
class Event(BaseModel):
    id: str               # SHA-256 16 hex chars (stable, calculé avant insertion)
    source: str           # "tc" | "hanabi"
    title: str
    url: str
    start_date: date | None
    end_date: date | None
    times: str | None     # "HH:MM–HH:MM" ou None
    venue: str | None
    latitude: float | None
    longitude: float | None
    price: str | None
    attributes: TokyoCheapoAttributes | HanabiWalkerAttributes
    created_at: datetime
```

### Contrat `attributes` par source

#### `TokyoCheapoAttributes` (source `"tc"`)

| Champ | Type | Description |
|-------|------|-------------|
| `categories` | `list[str]` | Ex. `["food", "festival"]` |
| `tags` | `list[str]` | Tags libres de l'article |
| `official_link` | `str \| None` | URL du site officiel de l'événement |
| `location_name` | `str \| None` | Nom du lieu (complète `venue`) |

`extra="allow"` : des champs supplémentaires peuvent apparaître sans casser la validation.

#### `HanabiWalkerAttributes` (source `"hanabi"`)

| Champ | Type | Description |
|-------|------|-------------|
| `fireworks_count` | `str \| None` | Nombre de feux (ex. `"10000発"`) |
| `fireworks_duration` | `str \| None` | Durée du spectacle |
| `expected_crowd` | `str \| None` | Affluence estimée |
| `rain_policy` | `str \| None` | Politique en cas de pluie |
| `paid_seating` | `str \| None` | Présence de places payantes |
| `paid_seating_details` | `str \| None` | Détails sur les places payantes |
| `food_stalls` | `str \| None` | Stands de nourriture |
| `notes` | `str \| None` | Notes diverses |
| `access` | `str \| None` | Accès transport |
| `parking` | `str \| None` | Informations parking |
| `official_site` | `str \| None` | URL site officiel |
| `official_x` | `str \| None` | URL compte X (ex-Twitter) |
| `contact` | `str \| None` | Contact principal |
| `contact2` | `str \| None` | Contact secondaire |

`extra="allow"` : idem.

### Schéma SQLite

#### Table `events`

```sql
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,   -- SHA-256 16 hex
    source      TEXT NOT NULL,      -- "tc" | "hanabi"
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    start_date  TEXT,               -- ISO 8601 YYYY-MM-DD
    end_date    TEXT,
    times       TEXT,               -- "HH:MM–HH:MM"
    venue       TEXT,
    latitude    REAL,
    longitude   REAL,
    price       TEXT,
    attributes  TEXT,               -- JSON sérialisé
    created_at  TEXT NOT NULL       -- ISO 8601 avec timezone
)
```

#### Table `scrape_jobs`

```sql
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT,            -- "tc" | "hanabi" | "all"
    status         TEXT,            -- "running" | "done" | "failed"
    started_at     TEXT,
    finished_at    TEXT,
    events_scraped INTEGER,
    error          TEXT,
    links_seen     INTEGER,
    events_ok      INTEGER,
    events_skipped INTEGER,
    error_count    INTEGER
)
```

---

## Déduplication

L'ID d'un événement est généré **avant l'insertion** dans la DB par `make_event_id(parts)` (`models/identity.py`) :

```python
def make_event_id(parts: list[str]) -> str:
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**Parties discriminantes par source :**
- Tokyo Cheapo : `[url, location_name]`
- Hanabi Walker : `[url, date_val]`

L'algorithme est stable et ne doit **jamais être modifié** : les IDs persistés en DB en dépendent.

---

## API — Référence des endpoints

| Méthode | Chemin | Auth | Description |
|---------|--------|------|-------------|
| `GET` | `/` | - | Frontend Leaflet (HTML) |
| `GET` | `/events` | - | Liste des événements (filtres, pagination) |
| `GET` | `/events/{id}` | - | Détail d'un événement |
| `GET` | `/events/{id}.ics` | - | Export iCal d'un événement |
| `POST` | `/scrape` | Bearer token | Déclenche un job de scraping (async) |
| `GET` | `/scrape/status` | - | Dernier job de scraping |
| `GET` | `/scrape/config` | - | Indique si `/scrape` est public |
| `GET` | `/health` | - | Healthcheck DB (`SELECT 1`) |
| `GET` | `/docs` | - | Swagger UI (FastAPI) |

**Paramètres `GET /events` :**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `source` | `"tc" \| "hanabi"` | Filtre par source |
| `date` | `YYYY-MM-DD` | Filtre par chevauchement de date |
| `bbox` | `min_lon,min_lat,max_lon,max_lat` | Filtre géographique |
| `start_from` | `YYYY-MM-DD` | Borne basse sur `start_date` |
| `start_to` | `YYYY-MM-DD` | Borne haute sur `start_date` |
| `limit` | `int` (1–500, défaut 100) | Pagination |
| `offset` | `int` (défaut 0) | Pagination |

Sans filtre de date, seuls les événements à venir sont retournés (`upcoming=True`).

---

## Configuration

Toutes les variables sont préfixées `EVENTMAPS_` et lues via `pydantic-settings` (fichier `.env` + variables d'environnement).

| Variable | Défaut | Description |
|----------|--------|-------------|
| `EVENTMAPS_DB_PATH` | `data/events.db` | Chemin SQLite |
| `EVENTMAPS_PORT` | `8000` | Port uvicorn |
| `EVENTMAPS_ALLOWED_ORIGINS` | `["*"]` | CORS — CSV ou JSON |
| `EVENTMAPS_LOG_LEVEL` | `INFO` | Niveau de log |
| `EVENTMAPS_REQUEST_LOGGING` | `false` | Log des requêtes HTTP (timings) |
| `EVENTMAPS_SCRAPE_TOKEN` | _(vide)_ | Token Bearer pour `POST /scrape` |
| `EVENTMAPS_SCRAPE_USER_AGENT` | `EventMaps/1.0` | User-Agent des scrapers |
| `EVENTMAPS_SCRAPE_TIMEOUT_HOURS` | `2` | Durée max avant de marquer un job stale |
| `EVENTMAPS_SCRAPE_ERROR_THRESHOLD` | `0.5` | Taux d'erreur max (0.0–1.0) |
| `EVENTMAPS_SCRAPE_REQUEST_TIMEOUT_SECONDS` | `10` | Timeout HTTP par requête |
| `EVENTMAPS_SCRAPE_MAX_PAGES_TC` | `10` | Pages max Tokyo Cheapo |
| `EVENTMAPS_SCRAPE_MAX_PAGES_HANABI` | `20` | Pages max Hanabi Walker |
| `EVENTMAPS_SCRAPE_RETRY_ATTEMPTS` | `3` | Tentatives tenacity |
| `EVENTMAPS_SCRAPE_RETRY_WAIT_MIN` | `2` | Backoff min (secondes) |
| `EVENTMAPS_SCRAPE_RETRY_WAIT_MAX` | `10` | Backoff max (secondes) |
