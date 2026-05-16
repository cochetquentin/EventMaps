# EventMaps

Scrapers d'événements géolocalisés pour alimenter une carte interactive.

## Installation

```bash
uv sync
```

## Structure

```
EventMaps/
├── scrapers/          # Scrapers Tokyo Cheapo et Hanabi Walker
├── models/            # Modèles Pydantic (TokyoCheapoEvent, HanabiEvent)
├── db/                # Persistance SQLite (EventStore)
├── api/               # API FastAPI
├── frontend/          # UI carte interactive (Leaflet.js)
├── tests/             # Tests unitaires et API
├── data/              # Base de données et exports CSV (gitignored)
└── main.py            # CLI de scraping
```

## Scraping

```bash
# Scraper Tokyo Cheapo → SQLite
uv run python main.py tc

# Scraper Hanabi Walker → SQLite (région Kantō par défaut)
uv run python main.py hanabi --region ar0300

# Scraper les deux sources
uv run python main.py all

# Exporter en CSV au lieu de SQLite
uv run python main.py tc --output csv > output.csv
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
- **Bleu** → Tokyo Cheapo · **Orange** → Hanabi
- Clustering automatique des marqueurs proches
- Popup au clic : titre, date, lieu, prix / feux d'artifice, lien
- Filtres par source et par date (sidebar gauche)

## API

```bash
uv run uvicorn api.app:app --reload
```

### Endpoints

```
GET /                                → UI carte (Leaflet.js)
GET /events                          → liste tous les événements
GET /events?source=tc                → filtre par source (tc | hanabi)
GET /events?date=2026/07/25          → filtre par date
GET /events?limit=50&offset=0        → pagination
GET /events/{id}                     → détail d'un événement
GET /docs                            → Swagger UI
```

### Exemple de réponse

```json
[
  {
    "id": "4e1e4f87206f7566",
    "source": "tc",
    "title": "Dry Noodle Grand Prix",
    "url": "https://tokyocheapo.com/events/dry-noodle-grand-prix/",
    "start_date": "2026/05/11",
    "end_date": "2026/05/20",
    "start_time": "10:00",
    "end_time": "18:00",
    "price": "Free",
    "categories": ["food"],
    "tags": ["food", "noodles"],
    "location_name": "Komazawa Olympic Park",
    "lat": 35.627198,
    "lng": 139.661894,
    "scraped_at": "2026-05-16T12:51:25+00:00"
  }
]
```

## Base de données

Les événements sont stockés dans `data/events.db` (SQLite) avec un hash SHA-256 (16 hex) comme clé primaire. Relancer le scraper met à jour les lignes existantes sans créer de doublons.

| Table | Source | Clé de déduplication |
|---|---|---|
| `tokyo_cheapo` | tokyocheapo.com | `url` + `location_name` |
| `hanabi` | hanabi.walkerplus.com | `url` + `date` |

## Modèles de données

### TokyoCheapoEvent

| Champ | Description |
|---|---|
| `title` | Nom de l'événement |
| `start_date` / `end_date` | Dates au format `YYYY/MM/DD` |
| `start_time` / `end_time` | Heures (`HH:MM`, 24h) |
| `price` | Prix (`Free`, `¥1,000`, etc.) |
| `categories` / `tags` | Listes de strings |
| `official_link` | URL du site officiel |
| `location_name` / `lat` / `lng` | Lieu et coordonnées GPS |

Les dates floues (`Mid May`, `Early Apr ~ Late Jun`) sont converties : Early=1-10, Mid=11-20, Late=21-fin du mois.
Les événements multi-lieux génèrent une ligne par lieu.

### HanabiEvent

| Champ | Description |
|---|---|
| `title` | Nom du festival |
| `start_date` | Date au format `YYYY/MM/DD` |
| `start_time` / `end_time` | Heures (`HH:MM`) |
| `fireworks_count` | Nombre de feux |
| `fireworks_duration` | Durée du spectacle |
| `expected_crowd` | Affluence estimée |
| `rain_policy` | Politique en cas de pluie |
| `paid_seating` / `paid_seating_details` | Places payantes |
| `food_stalls` | Stands de nourriture |
| `venue` / `access` / `parking` | Informations pratiques |
| `official_site` / `official_x` | Liens officiels |
| `lat` / `lng` | Coordonnées GPS |

Les événements multi-jours génèrent une ligne par jour.

## Tests

```bash
uv run pytest          # tous les tests (115)
uv run pytest tests/test_store.py   # store SQLite
uv run pytest tests/test_api.py     # API FastAPI
```
