# Architecture EventMaps

## Vue d'ensemble

EventMaps est un agrégateur d'événements géolocalisés composé de trois parties :

1. **Scrapers** — collectent les événements sur des sources tierces
2. **API FastAPI** — expose les événements via HTTP (REST + iCal)
3. **Frontend Leaflet** — affiche les événements sur une carte interactive

### Flux de données

```
Sources tierces
  tokyocheapo.com   hanabi.walkerplus.com   timeout.com/tokyo   ichiban-japan.com
       │                     │                    │                    │
       ▼                     ▼                    ▼                    ▼
  TokyoCheapo          HanabiWalker         TimeoutTokyo         IchibanJapan
  (scrapers/)          (scrapers/)          (scrapers/)          (scrapers/)
       │                     │                    │                    │
       └──────────────┬───────────────────────────────────────────────┘
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
| `timeout_tokyo.py` | Scraper timeout.com/tokyo → `Event` avec `TimeoutTokyoAttributes` |
| `ichiban_japan.py` | Scraper ichiban-japan.com → `Event` avec `IchibanJapanAttributes` |

Chaque scraper retourne `(list[Event], ScrapeReport)`. `ScrapeReport` comptabilise `links_seen`, `events_ok`, `events_skipped`, `errors[]`, `duration_s`.

Les retries HTTP sont gérés via **tenacity** (3 tentatives, backoff 2–10 s configurable).

> **Spécificité Ichiban Japan** : contrairement aux autres sources (1 URL = 1 événement), un article Ichiban agrège **plusieurs** événements. Le scraper découvre les URLs d'articles depuis les pages catégorie paginées, puis émet **un événement par bloc « Lieu : »** de l'article (les `<h2>` ne sont que des titres de section). Les coordonnées sont extraites des liens Google Maps du lieu (`!3d!4d` ou `@lat,lng`), avec résolution des liens courts `maps.app.goo.gl`.
>
> Les articles mensuels étant archivistiques, le scraper ne garde que les événements **à venir** (`scrape(upcoming_only=True)` par défaut) : les articles de mois révolus sont sautés d'après leur slug (`festivals-tokyo-<mois>-<année>`), les pages spéciales sans mois (marchés, Tohoku, yuki-matsuri…) sont toujours parcourues, et chaque événement passé (date de fin < aujourd'hui) est écarté.

### `models/`

| Fichier | Rôle |
|---------|------|
| `event.py` | Modèle canonical `Event` (Pydantic v2) |
| `attributes.py` | `TokyoCheapoAttributes`, `HanabiWalkerAttributes`, `TimeoutTokyoAttributes`, `IchibanJapanAttributes` (Pydantic BaseModel) |
| `identity.py` | `make_event_id(parts)` — génère l'ID stable SHA-256 |

### `db/`

| Fichier | Rôle |
|---------|------|
| `store.py` | `EventStore` — façade publique (context manager) |
| `events.py` | `EventRepository` — CRUD événements |
| `jobs.py` | `JobRepository` — suivi des jobs de scrape |
| `schema.py` | DDL des tables + migrations |
| `migrations.py` | Migration depuis le schéma legacy (tables `tokyo_cheapo` + `hanabi` → `events`) |

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
    source: str           # "tc" | "hanabi" | "tot" | "ij"
    title: str
    url: str
    start_date: date | None
    end_date: date | None
    times: str | None     # "HH:MM–HH:MM" ou None
    venue: str | None
    latitude: float | None
    longitude: float | None
    price: str | None
    attributes: TokyoCheapoAttributes | HanabiWalkerAttributes | TimeoutTokyoAttributes | IchibanJapanAttributes
    created_at: datetime
    canonical_id: str | None  # représentant du cluster de doublons (None = canonique)
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

#### `TimeoutTokyoAttributes` (source `"tot"`)

| Champ | Type | Description |
|-------|------|-------------|
| `categories` | `list[str]` | Catégories de l'événement |
| `venue_name` | `str \| None` | Nom du lieu |
| `venue_address` | `str \| None` | Adresse du lieu |
| `image_url` | `str \| None` | URL de l'image |
| `description` | `str \| None` | Description courte |

`extra="allow"` : idem.

#### `IchibanJapanAttributes` (source `"ij"`)

| Champ | Type | Description |
|-------|------|-------------|
| `description` | `str \| None` | Description de l'événement |
| `official_link` | `str \| None` | URL du site officiel (dernier lien du bloc « Lieu : ») |
| `neighbourhood` | `str \| None` | Quartier (ex. `"Monzen-Nakacho"`) |
| `venue_name` | `str \| None` | Nom du lieu (complète `venue`) |
| `zone` | `str \| None` | Zone déduite du slug (`"Tokyo"`, `"Tohoku"`) |
| `image_url` | `str \| None` | URL de l'image de l'événement |
| `image_caption` | `str \| None` | Légende de l'image (crédit photo retiré) |
| `dates_text` | `str \| None` | Texte de date brut (ex. `"Du 3 au 5 mai 2026"`) |
| `article_url` | `str \| None` | URL de l'article source (sans ancre) |
| `article_title` | `str \| None` | Titre de l'article source |

`extra="allow"` : idem. `venue` (top-level) porte le nom du lieu pour la dédup et les popups.

### Schéma SQLite

#### Table `events`

```sql
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,   -- SHA-256 16 hex
    source      TEXT NOT NULL,      -- "tc" | "hanabi" | "tot" | "ij"
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    start_date  TEXT,               -- ISO 8601 YYYY-MM-DD
    end_date    TEXT,
    times       TEXT,               -- "HH:MM–HH:MM"
    venue       TEXT,
    latitude    REAL,
    longitude   REAL,
    price        TEXT,
    attributes   TEXT,              -- JSON sérialisé
    created_at   TEXT NOT NULL,     -- ISO 8601 avec timezone
    canonical_id TEXT               -- représentant du cluster de doublons (index idx_events_canonical)
)
```

#### Table `scrape_jobs`

```sql
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT,            -- "tc" | "hanabi" | "tot" | "ij" | "all"
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

Deux niveaux complémentaires : la déduplication **exacte** (identité) et la déduplication **floue cross-source** (clustering).

### 1. Déduplication exacte (par ID)

L'ID d'un événement est généré **avant l'insertion** dans la DB par `make_event_id(parts)` (`models/identity.py`) :

```python
def make_event_id(parts: list[str]) -> str:
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**Parties discriminantes par source :**
- Tokyo Cheapo : `[url, location_name]`
- Hanabi Walker : `[url, date_val]`
- Timeout Tokyo : `[url]`
- Ichiban Japan : `[url]` — l'URL inclut une ancre `#slug` par événement (un article agrège plusieurs événements), ce qui garantit un ID distinct par festival

L'algorithme est stable et ne doit **jamais être modifié** : les IDs persistés en DB en dépendent. Combiné à l'`ON CONFLICT(id) DO UPDATE` de `upsert_events`, il rend un re-scrape de la même URL idempotent. Il ne rapproche **pas** deux sources différentes (URLs différentes → IDs différents).

### 2. Déduplication floue cross-source (colonne `canonical_id`)

Le package **`dedup/`** (pur, sans I/O) rapproche le *même* événement listé sur plusieurs sites. Il n'écrit rien et ne supprime rien : la couche DB matérialise le résultat dans la colonne `events.canonical_id` (représentant du cluster ; `NULL` = non encore dédupliqué, traité comme canonique).

Un pin sur la carte = **un événement à un lieu donné**. Le clustering (`dedup/cluster.py`) applique **deux régimes disjoints** selon que les deux événements viennent de la même source ou non (`dedup/matching.py`) :

**(a) Même source → identité par (URL + nom de lieu)** — `same_source_same_event`. Fusion si même `source` ET même **URL canonique** (le suffixe d'occurrence daté `/YYYYMMDD/` est retiré par `canonical_url`) ET même **nom de lieu** (`location_name`/`venue` normalisé, égalité exacte). **La date n'est pas exigée** (l'URL fait foi) : c'est le cas Tokyo Cheapo qui publie une page par date d'occurrence, et Hanabi qui éclate un feu multi-nuits en une ligne par jour. Le lieu se juge sur le **nom**, pas sur la distance : au sein d'une source, le `location_name` est l'identité que le scraper utilise pour distinguer les rangs, donc un événement multi-lieux (même URL, plusieurs musées) reste **un pin par lieu**, même si deux venues sont à quelques centaines de mètres.

**(b) Sources différentes → similarité floue** — `classify_pair` (logique **ET** conservatrice, pensée pour zéro faux positif). Doublon **seulement si** :
1. leurs **plages de dates se chevauchent** (un même titre à deux dates disjointes = événement récurrent, jamais fusionné) ;
2. leurs **titres normalisés** ont un `rapidfuzz.token_set_ratio ≥ 90` (`TITLE_MIN_RATIO`) ;
3. le **lieu est confirmé** : **si les coordonnées sont présentes des deux côtés, la distance fait autorité** (`≤ 0.75 km`, `GEO_MAX_KM`) et les noms de lieu ne sont pas consultés — deux lieux éloignés aux noms proches ne fusionnent pas. Sinon (coordonnées manquantes — cas Time Out Tokyo, ou événement Ichiban dont le lien de lieu n'a pas fourni de coordonnées) on se rabat sur la similarité des noms de lieu (`≥ 88`, `VENUE_MIN_RATIO`).

Toute donnée manquante fait échouer sa porte → pas de fusion. `classify_pair` court-circuite dès que les dates ne se chevauchent pas (la partie fuzzy coûteuse n'est évaluée que sur des paires plausibles).

**Clustering** — `dedup/cluster.py::assign_canonical_ids` fait un union-find sur les paires jugées doublons puis élit un représentant déterministe par cluster (priorité à l'événement **avec coordonnées**, pour garder un point sur la carte).

**Points d'exécution :**
- **Ingestion** : `EventsRepository.upsert_with_dedup` (appelé par `api/routes/scrape.py` et `main.py`) clusterise les nouveaux événements **avec** les événements à venir déjà en base — un doublon peut provenir d'un scrape antérieur d'une autre source — puis met à jour le `canonical_id` des nouveaux et des lignes existantes concernées.
- **Backfill** : `uv run python -m tools.backfill_canonical [--db PATH] [--all]` recalcule les `canonical_id` sur une base existante (idempotent, ne touche à aucun autre champ).

**Affichage** — le paramètre `?collapse=true` de `GET /events` ne renvoie qu'un représentant par cluster (`WHERE canonical_id IS NULL OR canonical_id = id`). Le frontend l'active pour la carte afin d'éviter les amas d'événements identiques ; les autres lignes restent en base et accessibles avec `collapse=false`.

---

## API — Référence des endpoints

| Méthode | Chemin | Auth | Description |
|---------|--------|------|-------------|
| `GET` | `/` | - | Frontend Leaflet (HTML) |
| `GET` | `/events` | - | Liste des événements (filtres, pagination) |
| `GET` | `/events/{id}` | - | Détail d'un événement |
| `GET` | `/events/{id}.ics` | - | Export iCal d'un événement |
| `GET` | `/events.ics` | - | Export iCal des événements filtrés (max 5 000 ; tronqué via `X-ICS-Truncated`) |
| `POST` | `/scrape` | Bearer token (si `SCRAPE_TOKEN` configuré, sinon public) | Déclenche un job de scraping (async) |
| `GET` | `/scrape/status` | - | Dernier job de scraping |
| `GET` | `/scrape/config` | - | Indique si `/scrape` est public |
| `GET` | `/health` | - | Healthcheck DB (`SELECT 1`) |
| `GET` | `/docs` | - | Swagger UI (FastAPI) |

**Paramètres `GET /events` :**

| Paramètre | Type | Description |
|-----------|------|-------------|
| `source` | `"tc" \| "hanabi" \| "tot" \| "ij"` | Filtre par source |
| `date` | `YYYY-MM-DD` | Filtre par chevauchement de date |
| `bbox` | `min_lon,min_lat,max_lon,max_lat` | Filtre géographique |
| `start_from` | `YYYY-MM-DD` | Borne basse sur `start_date` |
| `start_to` | `YYYY-MM-DD` | Borne haute sur `start_date` |
| `q` | `string` | Recherche textuelle (titre, lieu, access) |
| `category` | `string` | Filtre par catégorie (`attributes.categories` — TC et TOT) |
| `limit` | `int` (1–500, défaut 100) | Pagination |
| `offset` | `int` (défaut 0) | Pagination |
| `collapse` | `bool` (défaut `false`) | Regroupe les doublons cross-source : un seul représentant par cluster |

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
| `EVENTMAPS_SCRAPE_MAX_LISTING_PAGES_TOT` | `4` | Pages max scraper TimeoutTokyo |
| `EVENTMAPS_SCRAPE_MAX_PAGES_IJ` | `5` | Pages catégorie max scraper Ichiban Japan |
| `EVENTMAPS_SCRAPE_RETRY_ATTEMPTS` | `3` | Tentatives tenacity |
| `EVENTMAPS_SCRAPE_RETRY_WAIT_MIN` | `2` | Backoff min (secondes) |
| `EVENTMAPS_SCRAPE_RETRY_WAIT_MAX` | `10` | Backoff max (secondes) |
