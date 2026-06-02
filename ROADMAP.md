# EventMaps — Roadmap & Guidelines de développement

> Document de référence pour prioriser les travaux sur ce repo.
> Synthèse de l'analyse du codebase + avis croisés de 5 LLMs (ChatGPT, Claude, DeepSeek, Gemini, Kimi).
> Rédigé le 2026-06-01.

---

## Philosophie générale

Plusieurs LLMs ont recommandé des migrations prématurées (Redis, Celery, PostgreSQL, Elasticsearch, microservices). C'est du **over-engineering** pour un projet à cette échelle. La règle ici : on ne migre que quand ça craque, pas par anticipation.

Ce qui craque **maintenant** : le flag de scraping global et l'absence d'indexes SQL.  
Ce qui craquera **bientôt** : la limite 1000 côté frontend, le schéma à deux tables si on ajoute des sources.  
Ce qui craquera **un jour** : SQLite si on dépasse 500k événements et/ou plusieurs writers concurrents.

**SQLite reste le bon choix** jusqu'à preuve du contraire. WAL est déjà activé, c'est bien.

---

## Vue d'ensemble des phases

```
Phase 0 ─── Correctifs immédiats (< 1 jour)
Phase 1 ─── Architecture core (dépendances entre elles, dans l'ordre)
Phase 2 ─── Production readiness
Phase 3 ─── Features à valeur utilisateur réelle
Phase 4 ─── Nice-to-have / scalabilité future
```

---

## Phase 0 — Correctifs immédiats ✅ DONE (PR #3, mergé 2026-06-02)

> Aucune dépendance entre eux. Peuvent être faits dans n'importe quel ordre ou en parallèle.

### 0.1 — Indexes SQL ✅

5 indexes ajoutés dans `EventStore.__init__` (`db/store.py`) :

```sql
CREATE INDEX IF NOT EXISTS idx_tc_start_date ON tokyo_cheapo(start_date);
CREATE INDEX IF NOT EXISTS idx_tc_end_date   ON tokyo_cheapo(end_date);   -- ajouté (prédicat OR dans _query_tc)
CREATE INDEX IF NOT EXISTS idx_tc_coords     ON tokyo_cheapo(lat, lng);   -- colonnes réelles : lat/lng, pas latitude/longitude
CREATE INDEX IF NOT EXISTS idx_hanabi_date   ON hanabi(date);
CREATE INDEX IF NOT EXISTS idx_hanabi_coords ON hanabi(lat, lng);
```

---

### 0.2 — Timeout HTTP sur les scrapers ✅ (déjà fait)

Les deux scrapers utilisaient déjà `requests.Session()` avec `timeout=10`. Aucun changement nécessaire.

---

### 0.3 — Remplacer `print()` par `logging` ✅

- `scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py` : `print([SKIP])` → `logger.warning`
- `main.py` : 5 `print(..., file=sys.stderr)` → `logger.info` ; `logging.basicConfig` ajouté dans `main()` (pas dans `api/app.py` — le CLI n'importe jamais `api.app`)
- `api/app.py` : `logging.basicConfig` ajouté au démarrage de l'API

---

### 0.4 — Endpoint `GET /health` ✅

Ajouté dans `api/app.py`. Notes d'implémentation :
- `store.db` n'existe pas — utiliser `store._conn.execute("SELECT 1")`
- `EventStore.__init__` crée maintenant le répertoire parent avec `os.makedirs` avant d'ouvrir la connexion (sinon 500 sur fresh checkout où `data/` n'existe pas)

---

## Phase 1 — Architecture core ✅ DONE (PR #4, mergé 2026-06-02)

> **Ordre important.** 1.1 et 1.2 sont liés et doivent être faits ensemble ou dans cet ordre.  
> 1.3 dépend de 1.1+1.2. 1.4 est indépendant.

### 1.1 — Schéma unifié : 2 tables → 1 table `events` ✅

**Le changement le plus impactant du projet. Consensus fort : 5/5 LLMs.**

Aujourd'hui deux tables séparées `tokyo_cheapo` et `hanabi` veulent dire que :
- Ajouter une 3ème source implique modifier l'API, la DB, et le frontend
- `GET /events/{id}` fait 2 requêtes SQL pour un lookup par PK
- Les requêtes de filtrage croisé sont impossibles

**Migration cible :**

```sql
CREATE TABLE events (
    id          TEXT PRIMARY KEY,          -- SHA256[:16] de (source + url + discriminant)
    source      TEXT NOT NULL,             -- 'tc' | 'hanabi' | future sources
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    start_date  TEXT,                      -- YYYY-MM-DD
    end_date    TEXT,                      -- YYYY-MM-DD
    times       TEXT,
    venue       TEXT,
    latitude    REAL,
    longitude   REAL,
    price       TEXT,
    attributes  TEXT,                      -- JSON pour les champs spécifiques à chaque source
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_events_start_date ON events(start_date);
CREATE INDEX idx_events_source     ON events(source);
CREATE INDEX idx_events_coords     ON events(latitude, longitude);
```

Le champ `attributes` en JSON stocke tout ce qui est source-spécifique : `categories`, `tags` pour TC ; `fireworks_count`, `crowd_size`, `access`, `parking` pour Hanabi. SQLite gère le JSON nativement (`json_extract`) depuis la version 3.38.

**Bénéfice immédiat :** l'API `GET /events` devient une seule requête propre. L'ajout d'une source = écrire un scraper, pas toucher l'API.

---

### 1.2 — Modèle canonique `Event` en Python ✅

**Dépend de 1.1. À faire en même temps.**

Aujourd'hui le code a `TokyoCheapoEvent` et `HanabiEvent` comme modèles "terminaux". Le frontend lui veut juste un `Event` avec `source`, `title`, `coordinates`, `dates`.

```python
# models/event.py — nouveau modèle canonique
class Event(BaseModel):
    id: str
    source: Literal["tc", "hanabi"]
    title: str
    url: str
    start_date: date | None
    end_date: date | None
    times: str | None
    venue: str | None
    latitude: float | None
    longitude: float | None
    price: str | None
    attributes: dict  # champs spécifiques à la source
```

Les scrapers deviennent des transformateurs : `TokyoCheapoScraper → list[Event]`, `HanabiScraper → list[Event]`.

L'interface commune à respecter :
```python
class BaseScraper(ABC):
    @abstractmethod
    def scrape(self) -> list[Event]: ...
```

---

### 1.3 — Découpler le scraping de l'API ✅

**Dépend de 1.1+1.2. Consensus fort : tous les LLMs l'ont mentionné.**

Actuellement `POST /scrape` lance le scraping dans le même process FastAPI avec un flag global `_scraping` non thread-safe. En production avec `--workers N`, chaque worker a son propre flag, donc la protection ne fonctionne plus.

**Solution recommandée pour ce projet :** un **cron job indépendant** qui appelle directement `main.py`, pas un endpoint HTTP.

```
# cron (ou Makefile target)
0 6 * * * cd /app && uv run python main.py all
```

Ce que l'API garde :
- `GET /scrape/status` → lire un fichier `data/scrape.lock` ou une entrée en DB
- `POST /scrape` → optionnel, peut rester pour trigger manuel, mais avec un vrai lock

**Implémentation du lock :**
```python
# db/store.py — ajouter une table jobs
CREATE TABLE scrape_jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    status     TEXT,  -- 'running' | 'done' | 'failed'
    started_at TEXT,
    finished_at TEXT,
    events_scraped INTEGER,
    error      TEXT
)
```

Le scraper insère un job au début, le met à jour à la fin. L'API lit le dernier job pour `/scrape/status`. Pas de race condition, persistant au restart.

---

### 1.4 — Retry + backoff sur les scrapers ✅

**Indépendant de 1.1-1.3.**

Les sites japonais peuvent être capricieux, retourner des 503 transitoires, ou rate-limiter.

```python
# Utiliser tenacity (1 dep à ajouter)
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_page(url: str, session: requests.Session) -> str:
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.text
```

Logger les tentatives de retry. Loguer les URLs qui échouent après toutes les tentatives (dead letter log).

---

## Phase 2 — Production readiness

> Peut être fait après la Phase 1, indépendamment entre items.

### 2.1 — Dockerfile

```dockerfile
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Le volume `/app/data` doit être monté sur le host, sinon la DB est perdue au redeploy.

---

### 2.2 — Variables d'environnement

Utiliser `pydantic-settings` pour centraliser la config :

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_path: str = "data/events.db"
    port: int = 8000
    allowed_origins: list[str] = ["*"]
    log_level: str = "INFO"
    scrape_user_agent: str = "EventMaps/1.0"

settings = Settings()
```

Ne jamais hardcoder de chemins ou de valeurs dans le code.

---

### 2.3 — Rate limiting sur l'API

`POST /scrape` sans rate limiting = n'importe qui peut spammer les scrapers et faire blacklister l'IP par TokyoCheapo/HanabiWalker.

```bash
uv add slowapi
```

```python
# api/app.py
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@router.post("/scrape")
@limiter.limit("2/hour")
async def trigger_scrape(request: Request): ...
```

---

### 2.4 — CORS en production

Actuellement `allow_origins=["*"]`. En production :

```python
allow_origins=settings.allowed_origins  # configuré via env var
```

---

### 2.5 — Validation des paramètres API

FastAPI valide automatiquement si on déclare les types correctement :

```python
@router.get("/events")
def get_events(
    source: Literal["tc", "hanabi"] | None = None,
    date: date | None = None,          # FastAPI parse et valide YYYY-MM-DD
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
```

`limit=-1` et `date=n'importe quoi` retourneront automatiquement un 422.

---

### 2.6 — Alerte sur scraping vide

**Point soulevé uniquement par Claude — et c'est probablement le plus important pour la fiabilité.**

Si un scraper retourne 0 événements, c'est presque certainement un parser cassé (structure HTML changée), pas une vraie absence d'événements. Logger un WARNING niveau CRITICAL dans ce cas.

```python
if len(events) == 0:
    logger.critical("Scraper %s returned 0 events — likely a parser failure", source)
```

C'est la fragilité principale de tout projet de scraping, et elle n'est couverte par aucun test actuel.

---

### 2.7 — Backup SQLite

SQLite = un fichier unique. Un redeploy sans volume monté = tout perdu.

```bash
# Cron quotidien
0 3 * * * cp /app/data/events.db /backups/events_$(date +%Y%m%d).db
# Garder 30 jours
find /backups -name "events_*.db" -mtime +30 -delete
```

---

## Phase 3 — Features à valeur utilisateur

> À faire après la Phase 1. Indépendantes entre elles.

### 3.1 — Filtre "événements à venir" par défaut

**Point soulevé par Claude uniquement — mais évident une fois dit.**

Aujourd'hui l'app affiche par défaut TOUS les événements, y compris les passés. Un agrégateur d'événements qui montre des choses passées est inutilisable. Le filtre `start_date >= today` devrait être le défaut, pas une option.

- Côté API : `start_date >= today` par défaut si aucun filtre de date
- Côté frontend : le picker de date devrait pré-sélectionner aujourd'hui

---

### 3.2 — Bounding box API + chargement progressif

**Le vrai fix pour le `limit=1000` — consensus fort.**

Au lieu de charger 1000 events au démarrage, charger uniquement ce qui est visible sur la carte :

```
GET /events?bbox=min_lon,min_lat,max_lon,max_lat&start_date=2026-06-01
```

Le frontend déclenche un nouveau fetch à chaque fin de déplacement de la carte (`map.on('moveend', ...)`). Ça règle le problème de performance frontend ET l'arbitraire du limit=1000.

Requiert les indexes lat/lng de la Phase 0.

---

### 3.3 — Géolocalisation + filtre par distance

```javascript
// Frontend
navigator.geolocation.getCurrentPosition(pos => {
    filterByDistance(pos.coords.latitude, pos.coords.longitude, radiusKm=5)
})
```

Côté API, avec les indexes coords en place, le filtrage par bounding box approximate (latitude ± delta, longitude ± delta) est déjà efficace sans PostGIS.

---

### 3.4 — Export iCal

Très faible effort, très haute valeur utilisateur. Un événement sur une carte sans possibilité de l'ajouter au calendrier est un one-shot.

```bash
uv add icalendar
```

```python
@router.get("/events/{event_id}.ics")
def export_ical(event_id: str):
    event = store.get_event(event_id)
    cal = Calendar()
    e = ICSEvent()
    e.add("summary", event.title)
    e.add("dtstart", date.fromisoformat(event.start_date))
    e.add("url", event.url)
    cal.add_component(e)
    return Response(content=cal.to_ical(), media_type="text/calendar")
```

---

### 3.5 — Liens Google/Apple Maps dans les popups

Deux lignes de HTML par événement. Valeur énorme pour l'utilisateur qui veut naviguer jusqu'à l'événement.

```javascript
const gmapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`
const appleMapsUrl = `https://maps.apple.com/?daddr=${lat},${lng}`
```

---

### 3.6 — Scheduler automatique pour le scraping

Après avoir découpé le scraping de l'API (Phase 1.3), ajouter APScheduler dans le process FastAPI pour lancer le scraping automatiquement :

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(run_scraping, "cron", hour=6, timezone="Asia/Tokyo")
scheduler.start()
```

Ou rester sur un cron système si le projet est déployé sur un VPS simple.

---

## Phase 4 — Nice-to-have / scalabilité future

> Ne pas faire avant les phases précédentes. Évaluer si vraiment nécessaire.

### 4.1 — SQLite FTS5 pour la recherche texte

Avant de migrer vers PostgreSQL ou Elasticsearch (overkill), SQLite FTS5 donne une vraie recherche plein texte :

```sql
CREATE VIRTUAL TABLE events_fts USING fts5(title, venue, content="events");
```

À faire si le `LIKE %term%` devient lent (> 50k events).

---

### 4.2 — Modulariser le JS frontend

600 lignes inline dans `index.html`. À découper si on veut :
- Tester le JS
- Ajouter des features UI complexes
- Collaborer à plusieurs

Sinon, c'est fonctionnel tel quel. **Ne pas refactorer pour refactorer.**

---

### 4.3 — Coverage minimum en CI

```yaml
# .github/workflows/ci.yml
- run: uv run pytest --cov=. --cov-fail-under=80 tests/
```

À ajouter seulement si on a l'intention de maintenir la couverture. Un seuil non tenu devient du bruit.

---

### 4.4 — PostgreSQL + PostGIS

**Quand y migrer :** uniquement si :
- Plusieurs writers concurrents (API + scraper en continu)
- Requêtes géospatiales avancées (ST_DWithin en natif)
- Volume > 200-300k events

SQLite avec WAL + indexes tient très bien jusqu'à 500k events en lecture majoritaire. Ne pas migrer par anticipation.

---

### 4.5 — Favoris / bookmarks

Simple à faire en localStorage d'abord (aucun backend nécessaire), puis optionnellement persister côté serveur avec une vraie auth.

---

## Résumé : ordre d'exécution recommandé

```
Aujourd'hui (rapide) :
  ├── 0.1 Indexes SQL             [5 min]
  ├── 0.2 Timeout HTTP            [15 min]
  ├── 0.3 Logging stdlib          [1h]
  └── 0.4 GET /health             [15 min]

Semaine 1 (architectural) :
  ├── 1.1 Schéma unifié events    [2-4h] ← le plus impactant
  ├── 1.2 Modèle canonique Event  [1-2h] ← avec 1.1
  ├── 1.3 Découpler scraping/API  [2h]   ← après 1.1
  └── 1.4 Retry/backoff scrapers  [1h]   ← indépendant

Semaine 2 (production) :
  ├── 2.1 Dockerfile              [1h]
  ├── 2.2 Env vars (pydantic-settings) [30 min]
  ├── 2.3 Rate limiting           [30 min]
  ├── 2.5 Validation API params   [30 min]
  └── 2.6 Alerte scraping vide    [15 min]  ← critique

Features (priorité décroissante) :
  ├── 3.1 Filtre upcoming par défaut  [30 min]
  ├── 3.5 Liens Google/Apple Maps     [30 min]
  ├── 3.4 Export iCal                 [2h]
  ├── 3.2 Bounding box API            [3-4h]
  ├── 3.3 Géolocalisation utilisateur [2h]
  └── 3.6 Scheduler automatique       [1h]
```

---

## Ce qu'il ne faut PAS faire (red flags LLMs)

Plusieurs LLMs ont recommandé des choses qui seraient contre-productives à ce stade :

| Recommandation | Pourquoi l'ignorer |
|----------------|-------------------|
| Redis + Celery | Overkill pour un scraper qui tourne 1x/jour |
| Elasticsearch | SQLite FTS5 suffit jusqu'à 500k events |
| Microservices | Un seul dev, un seul processus, pas de justification |
| Prometheus + Grafana | Un logger + UptimeRobot suffit |
| Auth utilisateur en priorité | Zéro valeur sans base d'utilisateurs |
| User-Agent rotation + proxies | Seulement si effectivement bloqué |
| SCD Type 2 (historique des changements) | Complexité astronomique pour une valeur incertaine |
| Migration PostgreSQL "par précaution" | SQLite tient 500k events, WAL déjà actif |

---

## Dépendances entre tâches (graphe)

```
0.1 Indexes
0.2 Timeout HTTP          ─┐
0.3 Logging               ─┤─→  1.3 Découpler scraping  ─→  2.1 Dockerfile
0.4 Health endpoint        │                             ─→  2.3 Rate limiting
                           │
1.1 Schéma unifié    ──────┤
1.2 Modèle Event     ──────┘─→  3.2 Bounding box API  ─→  3.3 Géolocalisation
                              ─→  3.4 Export iCal
                              ─→  3.1 Filtre upcoming

(indépendants de tout)
  0.2 Timeout HTTP
  1.4 Retry/backoff
  2.6 Alerte scraping vide
  3.5 Liens maps
```

---

*Ce document doit être mis à jour au fur et à mesure que les tâches avancent. Une tâche complétée = un item barré ou supprimé.*
