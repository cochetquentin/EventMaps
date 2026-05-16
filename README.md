# EventMaps

Scrapers d'événements géolocalisés pour alimenter une carte interactive.

## Installation

```bash
uv sync
```

## Scrapers disponibles

### Tokyo Cheapo

Événements de la semaine à Tokyo depuis [tokyocheapo.com](https://tokyocheapo.com).

```python
from scrapers.tokyo_cheapo import TokyoCheapo

scraper = TokyoCheapo()
events = scraper.scrape_all(max_pages=10)
```

**Champs retournés :**

| Champ | Description |
|---|---|
| `url` | URL de la page Tokyo Cheapo |
| `title` | Nom de l'événement |
| `start_date` | Date de début au format `YYYY/MM/DD` |
| `end_date` | Date de fin au format `YYYY/MM/DD` (identique à `start_date` si événement sur un seul jour) |
| `start_time` | Heure de début (`HH:MM`, 24h) |
| `end_time` | Heure de fin (`HH:MM`, 24h) |
| `price` | Prix (ex: `Free`, `¥1,000 – ¥2,500`, `¥500 (advance sales)`) |
| `categories` | Catégories séparées par des virgules |
| `tags` | Tags séparés par des virgules |
| `official_link` | URL du site officiel de l'événement |
| `locations` | Liste de lieux avec `name`, `lat`, `lng`, `address` |

**Normalisation des dates :**
- Dates précises (`Fri, May 15`, `May 16 - May 17`) → `YYYY/MM/DD`
- Plages floues (`Mid May`, `Mid ~ Late May`, `Early Apr ~ Early Jun`) → converties via Early=1-10, Mid=11-20, Late=21-fin du mois
- Dates non parsables → conservées telles quelles

---

### Hanabi Walker

Festivals de feux d'artifice japonais depuis [hanabi.walkerplus.com](https://hanabi.walkerplus.com).

```python
from scrapers.hanabi_walker import HanabiWalker

scraper = HanabiWalker(region="ar0300")  # ar0300 = Kanto (défaut)
events = scraper.scrape_all(max_pages=20)
```

Les événements sur plusieurs jours sont automatiquement dupliqués — une ligne par jour.

**Champs retournés :**

| Champ | Description |
|---|---|
| `url` | URL de l'événement |
| `title` | Nom du festival |
| `date` | Date au format `YYYY/MM/DD` |
| `start_time` | Heure de début (`HH:MM`) |
| `end_time` | Heure de fin (`HH:MM`) |
| `fireworks_count` | Nombre de feux |
| `fireworks_duration` | Durée du spectacle |
| `expected_crowd` | Affluence estimée |
| `rain_policy` | Politique en cas de pluie |
| `paid_seating` | `あり` / `なし` |
| `paid_seating_details` | Détails et tarifs des places payantes |
| `food_stalls` | Présence de stands de nourriture |
| `venue` | Lieu |
| `access` | Accès (transports) |
| `parking` | Informations parking |
| `contact` | Contact |
| `official_site` | URL du site officiel |
| `official_x` | URL du compte X (Twitter) |
| `lat` / `lng` | Coordonnées GPS |

**Codes région disponibles** (paramètre `region`) :

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

## Export CSV

### Tokyo Cheapo

```bash
uv run python main.py > output.csv
```

Colonnes : `title`, `start_date`, `end_date`, `start_time`, `end_time`, `price`, `categories`, `tags`, `official_link`, `url`, `location_name`, `lat`, `lng`

Les événements multi-lieux génèrent une ligne par lieu.

### Hanabi Walker

```python
import pandas as pd

scraper = HanabiWalker()
events = scraper.scrape_all()
pd.DataFrame(events).to_csv("output_hanabi.csv", index=False, encoding="utf-8-sig")
```
