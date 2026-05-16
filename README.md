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

**Champs retournés :** `url`, `title`, `date`, `time`, `price`, `description`, `categories`, `tags`, `official_link`, `locations` (liste avec `name`, `lat`, `lng`, `address`)

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

```python
import pandas as pd

events = scraper.scrape_all()
pd.DataFrame(events).to_csv("output.csv", index=False, encoding="utf-8-sig")
```
