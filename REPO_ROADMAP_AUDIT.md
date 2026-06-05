# Repo Roadmap Audit

## 1. Executive Summary

EventMaps est une application Python/FastAPI + frontend statique Leaflet qui scrape des événements géolocalisés Tokyo Cheapo et Hanabi Walker, les normalise dans un modèle `Event`, les persiste dans SQLite, puis les expose via une API et une carte interactive. Le repo est petit, cohérent et déjà orienté produit : CLI de scraping, API, UI, persistance, Dockerfile, CI et tests existent.

**Niveau de maturité estimé :** prototype avancé / early beta. Le cœur fonctionne et les tests backend sont bons, mais plusieurs choix sont encore fragiles pour un déploiement public : endpoint de scraping exposé, HTML injecté côté frontend, dépendance forte aux DOMs de sites tiers, peu de tooling qualité, documentation d'exploitation limitée.

**Points forts observés :**

* Modèle canonique unique `Event` utilisé par l'API et les scrapers (`models/event.py`).
* Store SQLite simple avec WAL, indexes de base, upsert idempotent et migration depuis les anciennes tables (`db/store.py`).
* API FastAPI lisible avec filtres `source`, `date`, `bbox`, pagination et export ICS (`api/routes/events.py`).
* Scrapers encapsulés par source avec retries `tenacity`, user-agent configurable et alerting log si zéro événement (`scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py`).
* Couverture de tests backend solide : 146 tests passent, couverture totale 88.37% avec `--cov-fail-under=80`.
* Frontend modulaire en ES modules, avec filtres, favoris locaux, géolocalisation, clustering et pagination bbox (`frontend/js/*.js`).

**Points faibles principaux :**

* Le bouton frontend et `POST /scrape` permettent de déclencher un scraping serveur sans authentification ; la rate limit est seulement par process/IP et ne protège pas contre des coûts réseau répétés ou un usage non désiré (`api/routes/scrape.py`, `frontend/js/app.js`).
* Plusieurs champs issus de sites externes sont injectés via `innerHTML`/templates sans escaping (`frontend/js/popups.js`, `frontend/js/events-list.js`, `frontend/js/markers.js`), ce qui crée un risque XSS stocké si une source scrapée contient du HTML malveillant.
* Les presets de date côté UI ne transmettent pas `filter-date-to` à l'API bbox : le backend peut charger trop large et le filtrage de fin est seulement client-side (`frontend/js/api.js`, `frontend/js/app.js`).
* Le parsing de dates Tokyo Cheapo utilise l'année locale courante par défaut, ce qui peut mal classer des événements autour du Nouvel An (`scrapers/tokyo_cheapo.py`).
* Le Dockerfile copie `.venv`, `tests` et Markdown à cause d'une `.dockerignore` trop agressive/incohérente qui ignore aussi `tests/` et `*.md` pour le contexte Docker (`.dockerignore`).
* Tooling incomplet : pas de formatter/linter/type checker déclaré, pas de pre-commit, pas de audit supply-chain, pas de tests frontend automatisés.

**Risques bloquants :**

1. **Sécurité P0/P1 :** XSS stocké par données scrapées affichées en HTML et endpoint de scraping non authentifié.
2. **Fiabilité P1 :** scrapers dépendants de DOMs externes, erreurs par événement silencieuses, absence de snapshots HTML de contrat.
3. **Produit P1 :** dates/presets et pagination bbox peuvent donner des résultats incohérents ou trop chargés.
4. **Ops P1/P2 :** absence de stratégie de seed/scrape initial, pas de health/readiness différencié, pas de logs structurés.

**Recommandations prioritaires :**

* Sécuriser ou désactiver `POST /scrape` en production avec un token/admin flag et masquer le bouton si non configuré.
* Échapper toute donnée externe avant injection HTML ou construire les DOM nodes via `textContent`.
* Ajouter tests de contrat pour les scrapers avec fixtures HTML réalistes et cas de DOM manquant.
* Clarifier la stratégie de dates et utiliser une référence JST/source-aware pour Tokyo Cheapo.
* Ajouter Ruff + typos/mypy ou pyright minimal, Dependabot/Renovate, audit de dépendances et CI multi-checks.

## 2. Repository Map

### Principaux dossiers et rôles

* `api/` — Application FastAPI, middleware CORS, static files, routes événements/scrape, rate limiter.
  * `api/app.py` : point d'entrée ASGI `app`, configuration logging/CORS, mount `/js`, routes `/`, `/health`.
  * `api/routes/events.py` : endpoints `GET /events`, `GET /events/{id}`, `GET /events/{id}.ics`.
  * `api/routes/scrape.py` : endpoints `POST /scrape`, `GET /scrape/status`, orchestration background scraping.
  * `api/limiter.py` : instance SlowAPI.
* `scrapers/` — Scrapers synchrones par source.
  * `scrapers/base.py` : interface abstraite `BaseScraper`.
  * `scrapers/tokyo_cheapo.py` : extraction Tokyo Cheapo, parsing dates/prix/lieux, conversion canonique.
  * `scrapers/hanabi_walker.py` : extraction Hanabi Walker, parsing japonais dates/tables/map, conversion canonique.
* `db/` — Persistance SQLite.
  * `db/store.py` : DDL, migration legacy, upsert/query events, suivi jobs de scraping.
* `models/` — Modèles de données.
  * `models/event.py` : modèle Pydantic `Event`.
* `frontend/` — UI carte statique.
  * `frontend/index.html` : HTML + CSS + imports CDN/ES modules.
  * `frontend/js/` : modules API, état, filtres, markers, popups, favoris, géolocalisation, liste.
* `tests/` — Tests pytest backend/scrapers/store/API.
* `.github/workflows/ci.yml` — CI pull request vers `main`, Python 3.13, `uv sync`, pytest + coverage.
* Racine : `main.py` CLI, `config.py` settings, `pyproject.toml` dépendances, `Dockerfile`, `Makefile`, `README.md`, `ROADMAP.md`.

### Fichiers de configuration importants

* `pyproject.toml` : projet Python >=3.13, dépendances runtime et dev, script `scrape = "main:main"`.
* `uv.lock` : lockfile uv.
* `.python-version` : `3.13`.
* `.gitignore` : ignore `.venv`, `data`, DB/CSV générés.
* `.dockerignore` : ignore plusieurs éléments dont `tests/` et `*.md`, mais inclut potentiellement des fichiers non nécessaires selon Docker build context.
* `config.py` : variables `EVENTMAPS_DB_PATH`, `EVENTMAPS_PORT`, `EVENTMAPS_ALLOWED_ORIGINS`, `EVENTMAPS_LOG_LEVEL`, `EVENTMAPS_SCRAPE_USER_AGENT`, `EVENTMAPS_SCRAPE_TIMEOUT_HOURS`.

### Points d'entrée

* API/UI : `uv run uvicorn api.app:app --reload` ou `make run`.
* Docker : `CMD uv run --no-sync uvicorn api.app:app --host 0.0.0.0 --port ${EVENTMAPS_PORT}`.
* CLI scraping : `uv run python main.py tc|hanabi|all` ou script `uv run scrape ...`.
* UI : `GET /` sert `frontend/index.html`, JS sous `/js`.
* API principale : `GET /events`.
* Scraping distant : `POST /scrape`.

### Scripts disponibles

* `make run` — lance Uvicorn sur `0.0.0.0:8000`.
* `uv run python main.py tc` — scrape Tokyo Cheapo vers SQLite par défaut.
* `uv run python main.py hanabi --region ar0300` — scrape Hanabi Walker.
* `uv run python main.py all` — scrape les deux sources.
* `uv run python main.py tc --output csv > output.csv` — export CSV.
* `uv run pytest` — tests.
* CI : `uv run --locked python -m pytest --cov=. --cov-fail-under=80 tests/ -v`.

### Zones critiques

* `frontend/js/popups.js` et `frontend/js/events-list.js` : rendu HTML de données externes.
* `api/routes/scrape.py` : déclenchement scraping réseau + état concurrent.
* `scrapers/tokyo_cheapo.py` et `scrapers/hanabi_walker.py` : parsing fragile de HTML tiers.
* `db/store.py` : migration destructive des anciennes tables, requêtes de listing, JSON attributes.
* `frontend/js/api.js` + `frontend/js/markers.js` : cohérence filtres date/bbox entre client et serveur.

## 3. Technology & Tooling Assessment

| Élément | État actuel | Problème éventuel | Recommandation |
|---|---|---|---|
| Python | Python `>=3.13`, `.python-version` 3.13, CI setup Python 3.13 | Version récente, réduit compatibilité environnements ; OK si assumé | Documenter clairement Python 3.13 comme requis et tester Docker/CI uniquement dessus ou ajouter matrice si support élargi souhaité |
| FastAPI | API simple et typed, response models Pydantic | Pas de versioning API, pas de auth pour `/scrape` | Ajouter auth/feature flag pour routes mutantes, envisager `/api/v1` avant API publique |
| Pydantic | `Event` très simple | `attributes: dict = {}` mutable default, typage peu précis | Utiliser `Field(default_factory=dict)` et types d'attributs par source si le modèle grandit |
| SQLite | WAL, indexes source/date/coords, upsert | Pas de busy timeout, pas d'index composite pour filtres fréquents, migration legacy destructive | Ajouter `PRAGMA busy_timeout`, indexes composites (`source,start_date`, bbox/date si besoin), sauvegarde/transaction migration |
| Scraping | `requests` + BeautifulSoup + tenacity | Synchrone, fragile au DOM, erreurs événement seulement loggées | Ajouter fixtures HTML, compte d'erreurs, seuil d'échec, user-agent contact, tests contrat |
| Frontend | HTML/CSS/JS vanilla ES modules, Leaflet CDN | Pas de bundling ni tests ; XSS par template strings ; dépendance CDN sans SRI | Ajouter escaping/sanitization, SRI ou vendoring, tests JS légers avec Vitest/Playwright si nécessaire |
| Dépendances | `uv.lock` présent | Contraintes très larges (`>=`) et pas d'audit vulnérabilités | Dependabot/Renovate + `pip-audit`/`uv pip audit` si disponible + pinning via lock conservé |
| Tests | 146 tests, coverage 88% | `main.py` 0%, `api/routes/scrape.py` 31%, aucun test frontend | Ajouter tests CLI/scrape route et tests JS critiques |
| CI/CD | PR vers main, install/test coverage | Pas de lint/format/type/security, pas de push main, pas de Docker build | Ajouter jobs Ruff, type check minimal, audit deps, Docker build smoke |
| Lint/format | Aucun outil déclaré | Style manuel, imports non ordonnés, bugs détectables manqués | Ajouter Ruff format+check, config dans `pyproject.toml`, CI |
| Typage | Hints présents mais pas checkés | `dict` libre, types `tuple[float,float]|tuple[None,None]`, imports privés | Ajouter mypy/pyright progressif avec exclusions initiales |
| Packaging | `project.scripts.scrape` | Module racine `main.py` peut être fragile en packaging | Envisager package `eventmaps/` à moyen terme, pas P0 |
| Docker | Image uv + python slim | `.dockerignore` exclut README/tests mais pas forcément optimal ; pas de non-root user ; pas de healthcheck | Corriger `.dockerignore`, ajouter user non-root, `HEALTHCHECK`, build CI |
| Config | Pydantic settings, env prefix | CORS `[*]` par défaut, pas de config auth scrape | Restreindre CORS par défaut en prod ou documenter ; ajouter `SCRAPE_TOKEN`/`ENABLE_SCRAPE_ENDPOINT` |

## 4. Bugs & Correctness Risks

### BUG-001 — Preset date `to` non transmis à l'API bbox

**Sévérité :** Medium
**Confiance :** High
**Zone concernée :** `frontend/js/api.js`, `frontend/js/app.js`, `api/routes/events.py`, `db/store.py`
**Symptôme probable :** les presets `today`, `weekend`, `week`, etc. chargent côté serveur tous les événements depuis `filter-date-from`, puis filtrent `filter-date-to` uniquement côté client. Sur une base grandissante, l'UI peut charger trop d'événements et la pagination bbox peut masquer des événements dans la fenêtre voulue si des pages sont remplies par des dates ultérieures ou non pertinentes.
**Cause suspectée :** `fetchEventsByBbox()` ajoute seulement `start_from` depuis `filter-date-from` et ignore `filter-date-to`; le backend ne supporte pas de filtre range `start_to`.
**Comment vérifier :** créer >500 événements futurs avec dates étalées, appliquer preset `today`, observer les requêtes `/events` et le nombre d'éléments chargés avant filtrage.
**Correction proposée :** ajouter paramètres API `start_to` ou `end_to` avec logique overlap `start_date <= to AND COALESCE(end_date,start_date) >= from`, puis transmettre les deux bornes depuis `frontend/js/api.js`.
**Dépendances :** TEST-002 recommandé.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### ~~BUG-002 — Année Tokyo Cheapo calculée avec l'année locale courante~~ **[DONE]**

**Sévérité :** Medium
**Confiance :** Medium
**Zone concernée :** `scrapers/tokyo_cheapo.py`
**Symptôme probable :** autour de décembre/janvier, un événement listé pour janvier peut être stocké avec l'année de scraping incorrecte, ou une plage franchissant l'année peut avoir `end_date < start_date`.
**Cause suspectée :** `_parse_date_range()` prend `_date.today().year` par défaut et `_parse_date_part()` ne gère pas l'inférence d'année entre mois de fin/début.
**Comment vérifier :** tests unitaires avec date de référence `2026-12-30`, input `Jan 2`, `Dec 31 - Jan 2`.
**Correction proposée :** injecter une date de référence JST/source-aware, inférer l'année suivante si le mois parsé est nettement avant le mois courant pour des pages futures, et gérer les ranges cross-year.
**Dépendances :** TEST-003.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### BUG-003 — Scrapers peuvent réussir avec une perte massive silencieuse

**Sévérité :** High
**Confiance :** High
**Zone concernée :** `scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py`, `api/routes/scrape.py`, `main.py`
**Symptôme probable :** si le DOM change pour une partie des événements, le scraper log `SKIP` et retourne une liste partielle ; l'API/CLI upsert cette liste comme succès, sans signaler un taux d'erreur anormal.
**Cause suspectée :** `scrape_all()` catch toutes les exceptions par événement, ne retourne pas de compteur d'échecs, et seul le cas `not events` est loggé en critical.
**Comment vérifier :** monkeypatcher `scrape_event` pour échouer sur 80% des URLs et constater que `scrape()` retourne les 20% restants sans exception.
**Correction proposée :** collecter `scrape_errors`, logger un résumé, exposer dans job status, et échouer si taux d'échec > seuil configurable ou si liens trouvés >0 mais événements valides trop faibles.
**Dépendances :** ARCH-002.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### BUG-004 — `_extract_dates` Hanabi retourne du texte brut non parseable

**Sévérité :** Medium
**Confiance :** Medium
**Zone concernée :** `scrapers/hanabi_walker.py`
**Symptôme probable :** certains événements Hanabi avec format de date inattendu sont convertis en `Event(start_date=None)` mais gardent un ID basé sur le texte brut ; ils ne remontent pas dans les filtres upcoming/date et deviennent invisibles par défaut.
**Cause suspectée :** `_extract_dates()` retourne `[raw]` quand aucun format connu n'est trouvé ; `scrape()` passe ensuite par `_parse_iso_date()` qui renvoie `None`.
**Comment vérifier :** test unitaire avec un format japonais non couvert, vérifier que l'événement final a `start_date is None`.
**Correction proposée :** distinguer explicitement `parse_failed` de date inconnue, ne pas générer d'Event sans date pour Hanabi sauf décision produit, et inclure l'erreur dans un rapport de scraping.
**Dépendances :** BUG-003.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### BUG-005 — `parse_description` Tokyo Cheapo peut faire échouer un événement sans fallback

**Sévérité :** Low
**Confiance :** High
**Zone concernée :** `scrapers/tokyo_cheapo.py`
**Symptôme probable :** une page sans `div.entry-content__text` est skip entièrement même si les données essentielles sont disponibles.
**Cause suspectée :** `soup.find(...).text.strip()` sans vérification `None`.
**Comment vérifier :** test `scrape_event` avec fixture sans `entry-content__text`.
**Correction proposée :** rendre description optionnelle avec fallback `""`; ne pas bloquer l'événement sur champ non essentiel.
**Dépendances :** Aucune.
**Taille estimée :** XS
**Candidat PR indépendante :** Oui

### BUG-006 — `get_event_links` Tokyo Cheapo peut collecter des URLs hors événement

**Sévérité :** Low
**Confiance :** Medium
**Zone concernée :** `scrapers/tokyo_cheapo.py`
**Symptôme probable :** liens de taxonomies/pagination non exclus, doublons, ou URLs relatives sans slash final peuvent déclencher des fetch inutiles puis `SKIP`.
**Cause suspectée :** filtre par `href.startswith("/events/")` avec liste d'exclusion statique, sans vérification de structure article/card.
**Comment vérifier :** fixture de page listing avec catégories `/events/foo/` et vrais événements, vérifier la liste finale.
**Correction proposée :** cibler les cartes événement ou patterns permalink connus, normaliser et dédupliquer l'ordre.
**Dépendances :** TEST-003.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### BUG-007 — Status scraping global ambigu pour jobs concurrents/source

**Sévérité :** Medium
**Confiance :** Medium
**Zone concernée :** `api/routes/scrape.py`, `db/store.py`, `frontend/js/app.js`
**Symptôme probable :** le frontend poll `/scrape/status` sans source ; si un ancien job ou un autre source est le dernier, le bouton peut arrêter de tourner trop tôt ou recharger au mauvais moment.
**Cause suspectée :** `scrape_status(source=None)` renvoie le dernier job global ; `startScrape()` ne transmet pas de source/job id et ignore la réponse `already_running`.
**Comment vérifier :** créer deux jobs source différents en DB, déclencher un scrape, poller sans source.
**Correction proposée :** faire retourner `job_id` par `POST /scrape`, ajouter `GET /scrape/status?job_id=...`, et adapter le frontend.
**Dépendances :** SEC-001 si auth ajoutée.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### BUG-008 — Liens directions générés avec coordonnées nulles

**Sévérité :** Low
**Confiance :** High
**Zone concernée :** `frontend/js/popups.js`, `frontend/js/markers.js`
**Symptôme probable :** si un événement sans coordonnées est rendu ailleurs ou si le filtre change, les liens Google/Apple peuvent pointer vers `null,null` ou `undefined,undefined`. Actuellement `renderMarkers()` ignore les événements sans coordonnées, mais le popup n'est pas défensif.
**Cause suspectée :** `buildPopup()` suppose `ev.latitude`/`ev.longitude` disponibles.
**Comment vérifier :** appeler `buildPopup()` en test JS avec lat/lng null.
**Correction proposée :** masquer les actions direction si coordonnées absentes.
**Dépendances :** TEST-006.
**Taille estimée :** XS
**Candidat PR indépendante :** Oui

## 5. Security Review

### SEC-001 — Endpoint `POST /scrape` exposé sans authentification

**Sévérité :** High
**Confiance :** High
**Zone concernée :** `api/routes/scrape.py`, `frontend/js/app.js`, `config.py`
**Risque :** n'importe quel visiteur pouvant atteindre l'application peut déclencher des requêtes réseau vers Tokyo Cheapo et Hanabi Walker, consommer CPU/I/O, remplir les logs/jobs et potentiellement faire bannir l'IP serveur.
**Scénario d'exploitation :** un bot appelle `POST /scrape` toutes les heures/IP ou depuis plusieurs IPs ; SlowAPI limite par process mais ne fournit pas de contrôle admin durable.
**Correction proposée :** ajouter `EVENTMAPS_SCRAPE_TOKEN` ou désactiver l'endpoint par défaut en production (`EVENTMAPS_ENABLE_SCRAPE_ENDPOINT=false`), vérifier header `Authorization: Bearer`, masquer/désactiver le bouton frontend si non autorisé, documenter l'usage.
**Comment vérifier :** tests API : sans token => 401/403 ou 404 selon config ; avec token => 200 ; bouton non rendu/non actif sans config publique.
**Dépendances :** DOC-002.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### SEC-002 — XSS stocké via données scrapées injectées en HTML

**Sévérité :** High
**Confiance :** High
**Zone concernée :** `frontend/js/popups.js`, `frontend/js/events-list.js`, `frontend/js/markers.js`, `frontend/js/filters.js`
**Risque :** titres, lieux, prix, catégories, access et URLs viennent de sites externes ou de la DB, puis sont interpolés dans des templates HTML avec `innerHTML`/Leaflet popup.
**Scénario d'exploitation :** une page source contient un titre `</div><img onerror=...>` ; le scraper stocke la chaîne ; la carte l'insère dans `.innerHTML` et exécute du JS chez les utilisateurs.
**Correction proposée :** créer helpers `escapeHtml`, `safeUrl` ou construire via DOM `textContent`; limiter URLs aux protocoles `http/https`; ajouter tests JS/unitaires ou tests Python de snapshot frontend si outillage minimal.
**Comment vérifier :** fixture événement avec `<img onerror>` et `javascript:` URL ; ouvrir popup/liste, vérifier rendu textuel et lien neutralisé.
**Dépendances :** TEST-006.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### SEC-003 — Dépendances CDN sans SRI ni fallback

**Sévérité :** Medium
**Confiance :** High
**Zone concernée :** `frontend/index.html`
**Risque :** compromission ou altération d'un CDN tiers (`unpkg.com`, Google Fonts, Stadia tiles pour ressources) peut injecter du code ou casser l'UI.
**Scénario d'exploitation :** un CDN ou chemin package sert une version altérée de Leaflet/markercluster ; le navigateur l'exécute avec l'origine de l'application.
**Correction proposée :** ajouter `integrity` + `crossorigin` pour scripts/styles versionnés quand possible, ou vendoriser Leaflet/markercluster sous `frontend/vendor/`; documenter choix.
**Comment vérifier :** inspecter HTML, CSP/SRI, et charger l'UI hors réseau CDN si vendorisé.
**Dépendances :** DOC-003 si politique assets.
**Taille estimée :** S/M
**Candidat PR indépendante :** Oui

### SEC-004 — CORS wildcard par défaut

**Sévérité :** Medium
**Confiance :** Medium
**Zone concernée :** `config.py`, `api/app.py`, README
**Risque :** toute origine peut lire l'API si elle est exposée publiquement. Pour des événements publics ce n'est pas critique, mais combiné à routes mutantes ou futures données privées, le défaut est risqué.
**Scénario d'exploitation :** un site tiers interroge massivement `/events` depuis les navigateurs d'utilisateurs ou exploite une future route auth mal configurée.
**Correction proposée :** conserver `*` en dev mais documenter/proposer `EVENTMAPS_ALLOWED_ORIGINS` en prod ; éventuellement refuser `*` si `SCRAPE_TOKEN`/admin activé.
**Comment vérifier :** tests config pour string CSV/JSON et doc env.
**Dépendances :** SEC-001.
**Taille estimée :** XS/S
**Candidat PR indépendante :** Oui

### SEC-005 — Pas d'audit automatique supply-chain

**Sévérité :** Medium
**Confiance :** High
**Zone concernée :** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`
**Risque :** vulnérabilités dans FastAPI/Starlette/requests/aiofiles/etc. non détectées en PR.
**Scénario d'exploitation :** dépendance transitive vulnérable lockée dans `uv.lock`, jamais remontée par CI.
**Correction proposée :** ajouter Dependabot/Renovate et job `pip-audit` compatible uv, ou GitHub dependency review.
**Comment vérifier :** CI échoue sur vulnérabilité connue dans une branche test ; Dependabot ouvre des PRs.
**Dépendances :** Aucune.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### SEC-006 — Cookies/localStorage favoris non sensibles mais non documentés

**Sévérité :** Low
**Confiance :** High
**Zone concernée :** `frontend/js/favorites.js`, README
**Risque :** les favoris sont stockés en `localStorage`; ce n'est pas sensible, mais couplé à XSS cela devient un canal de persistance/exfiltration mineur.
**Scénario d'exploitation :** XSS lit/altère les favoris.
**Correction proposée :** traiter via SEC-002 ; documenter que les favoris restent locaux.
**Comment vérifier :** lire README/UI.
**Dépendances :** SEC-002.
**Taille estimée :** XS
**Candidat PR indépendante :** Oui

### SEC-007 — Image Docker lancée en root sans hardening minimal

**Sévérité :** Low
**Confiance :** High
**Zone concernée :** `Dockerfile`, `.dockerignore`
**Risque :** si l'application ou une dépendance est compromise, le process tourne en root dans le conteneur.
**Scénario d'exploitation :** RCE future via dépendance ; l'attaquant a privilèges root dans container.
**Correction proposée :** créer user non-root, ownership `/app`/`data`, healthcheck, réduire contexte Docker.
**Comment vérifier :** `docker run ... id` ou endpoint health ; build CI.
**Dépendances :** CLEAN-002.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

## 6. Architecture & Maintainability

### ARCH-001 — Modèle `Event.attributes` trop libre

**Impact :** Medium
**Zone concernée :** `models/event.py`, `scrapers/*.py`, `frontend/js/*.js`, `db/store.py`
**Problème :** les champs source-specific sont enfouis dans un `dict` non typé (`categories`, `tags`, `location_name`, `fireworks_count`, etc.). Le frontend connaît implicitement ces clés.
**Pourquoi c'est important :** toute nouvelle source ou renommage casse silencieusement l'UI/tests ; impossible de valider les attributs par source.
**Refactor proposé :** définir schémas Pydantic optionnels `TokyoCheapoAttributes`, `HanabiAttributes`, ou au minimum constantes de clés + TypedDict côté Python ; documenter le contrat JSON.
**Plan de migration :** (1) ajouter types sans changer DB ; (2) valider dans scrapers ; (3) adapter tests ; (4) éventuellement exposer `source_details` versionné.
**Dépendances :** TEST-001.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### ARCH-002 — Résultat de scraping sans métadonnées de qualité

**Impact :** High
**Zone concernée :** `scrapers/base.py`, `scrapers/*.py`, `api/routes/scrape.py`, `db/store.py`
**Problème :** l'interface `scrape() -> list[Event]` ne transporte ni nombre de liens trouvés, ni erreurs, ni warnings, ni source/region effective.
**Pourquoi c'est important :** impossible de distinguer “0 événement réel” de “parser cassé”, ou succès partiel de succès complet.
**Refactor proposé :** introduire `ScrapeResult(events, source, links_seen, skipped, errors, started_at, finished_at)` et stocker les métriques dans `scrape_jobs`.
**Plan de migration :** garder `scrape()` pour compatibilité, ajouter `scrape_with_report()`, migrer API/CLI, puis déprécier l'ancien.
**Dépendances :** BUG-003.
**Taille estimée :** L
**Candidat PR indépendante :** Non, à découper

### ARCH-003 — Couplage frontend direct au HTML template strings

**Impact :** High
**Zone concernée :** `frontend/js/popups.js`, `frontend/js/events-list.js`, `frontend/index.html`
**Problème :** UI générée avec templates HTML inline, styles inline et données externes mélangées.
**Pourquoi c'est important :** sécurité XSS, maintenabilité CSS, tests difficiles, duplication des actions popup/cards.
**Refactor proposé :** extraire helpers de rendu sûrs, composants DOM (`createElement`) et classes CSS dédiées.
**Plan de migration :** commencer par escaping central (SEC-002), puis déplacer styles inline vers CSS, puis composants DOM.
**Dépendances :** SEC-002.
**Taille estimée :** L
**Candidat PR indépendante :** Non, découper par composant

### ~~ARCH-004 — `db.store` mélange DDL, migration, queries et jobs~~ **[DONE]**

**Impact :** Medium
**Zone concernée :** `db/store.py`
**Problème :** un seul fichier porte schéma, migration legacy, repository events, repository jobs, helpers ID/date.
**Pourquoi c'est important :** le fichier reste lisible aujourd'hui, mais chaque nouvelle table/source augmentera la complexité et les risques de migration.
**Refactor proposé :** extraire `db/schema.py`, `db/migrations.py`, `db/events_repository.py`, `db/jobs_repository.py` ou garder `EventStore` façade.
**Plan de migration :** ajouter modules sans changer API publique, déplacer DDL/tests progressivement.
**Dépendances :** TEST-001.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### ARCH-005 — Import d'un helper privé `_make_id` depuis `db.store`

**Impact :** Low
**Zone concernée :** `scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py`, `tests/*.py`, `db/store.py`
**Problème :** les scrapers dépendent d'une fonction privée du module DB pour générer les IDs.
**Pourquoi c'est important :** l'identité événement est une règle métier, pas une responsabilité DB ; changement DB peut casser scraping/tests.
**Refactor proposé :** déplacer vers `models/event_identity.py` ou `utils/identity.py` avec fonctions explicites `make_event_id`.
**Plan de migration :** créer nouveau module, remplacer imports, garder alias temporaire dans `db.store` si besoin.
**Dépendances :** Aucune.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### ARCH-006 — Configuration de scraping partiellement centralisée

**Impact :** Medium
**Zone concernée :** `config.py`, `scrapers/*.py`, `main.py`, `api/routes/scrape.py`
**Problème :** user-agent et timeout job sont configurables, mais max pages, retry count, request timeout, regions autorisées et thresholds ne le sont pas.
**Pourquoi c'est important :** ops et tests ont besoin d'ajuster le comportement sans modifier le code.
**Refactor proposé :** ajouter settings `scrape_request_timeout_seconds`, `scrape_max_pages_tc`, `scrape_max_pages_hanabi`, `scrape_failure_threshold`, `allowed_hanabi_regions`.
**Plan de migration :** settings + docs + tests config, puis injection dans scrapers.
**Dépendances :** BUG-003.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### ARCH-007 — Pas d'observabilité structurée

**Impact :** Medium
**Zone concernée :** `api/app.py`, `api/routes/scrape.py`, `scrapers/*.py`, `main.py`
**Problème :** logs texte simples, pas de request id, pas de métriques scrape, pas de timings par source.
**Pourquoi c'est important :** difficile de diagnostiquer parser cassé, lenteur ou abus `/scrape`.
**Refactor proposé :** ajouter logs structurés minimalistes (source, job_id, counts, duration), middleware request logging optionnel, timings scraper.
**Plan de migration :** commencer par logs job/scraper sans dépendance externe ; envisager Prometheus plus tard seulement si besoin.
**Dépendances :** ARCH-002.
**Taille estimée :** S/M
**Candidat PR indépendante :** Oui

### ARCH-008 — Frontend sans contrat API versionné

**Impact :** Medium
**Zone concernée :** `api/routes/events.py`, `models/event.py`, `frontend/js/*.js`
**Problème :** le frontend consomme directement les noms Pydantic actuels ; aucun OpenAPI client/schema snapshot ou version.
**Pourquoi c'est important :** refactors backend peuvent casser l'UI sans tests.
**Refactor proposé :** ajouter tests de contrat JSON pour `/events`, documenter le schema, éventuellement générer types TS/JSDoc.
**Plan de migration :** snapshot JSON minimal + JSDoc typedef `Event` côté JS.
**Dépendances :** TEST-006.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

## 7. Testing Strategy

### État des tests existants

* `tests/test_store.py` couvre fortement SQLite, migration, filtres, jobs, indexes et date upcoming.
* `tests/test_api.py` couvre listing, filtres, pagination, bbox, health, ICS et quelques cas d'erreur.
* `tests/test_tokyo_cheapo.py` couvre de nombreux parseurs Tokyo Cheapo.
* `tests/test_hanabi_walker.py` couvre de nombreux parseurs Hanabi.
* `tests/test_scraper_alerts.py` couvre l'alerte zéro événement.
* Commandes vérifiées pendant l'audit : `uv run --locked python -m pytest -q` => 146 passed ; `uv run --locked python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=80 tests/ -q` => 88.37%.

### Couverture apparente et zones non testées

* Bon niveau backend global mais trous importants : `main.py` 0%, `api/routes/scrape.py` 31%, plusieurs branches réseau scrapers non testées.
* Aucun test automatisé frontend : filtres, XSS escaping, favoris, popups, bbox pagination, presets non couverts.
* Pas de test Docker build, pas de test CLI, pas de test de sécurité headers/CORS/auth.
* Pas de fixtures HTML complètes versionnées pour détecter un changement de DOM tiers.

### ~~TEST-001 — Couvrir CLI `main.py`~~ **[DONE]**

**Priorité :** P1
**Zone concernée :** `main.py`, `tests/`
**But :** éviter régressions sur commandes `tc`, `hanabi`, `all`, sortie CSV et DB path.
**Tests à ajouter :** monkeypatch scrapers pour retourner événements synthétiques ; vérifier upsert appelé/DB remplie ; vérifier CSV header/rows ; vérifier `--region`.
**Données ou fixtures nécessaires :** factory `Event` partagée.
**Dépendances :** Aucune.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### TEST-002 — Tester filtres date range backend + frontend contract

**Priorité :** P1
**Zone concernée :** `api/routes/events.py`, `db/store.py`, `frontend/js/api.js`
**But :** sécuriser la correction BUG-001.
**Tests à ajouter :** API avec événements multi-days, `start_from`, futur `start_to`; vérifier overlap ; pagination avec >500 events.
**Données ou fixtures nécessaires :** événements synthétiques avec dates avant/pendant/après.
**Dépendances :** BUG-001.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### TEST-003 — Fixtures HTML contrat pour Tokyo Cheapo

**Priorité :** P1
**Zone concernée :** `scrapers/tokyo_cheapo.py`, `tests/fixtures/`
**But :** détecter les changements DOM sur listing/page détail et les cas Nouvel An.
**Tests à ajouter :** listing fixture, detail fixture complète, missing optional description, cross-year dates, multi-location.
**Données ou fixtures nécessaires :** HTML anonymisé/minimal reproduisant structure source.
**Dépendances :** Aucune.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### TEST-004 — Fixtures HTML contrat pour Hanabi Walker

**Priorité :** P1
**Zone concernée :** `scrapers/hanabi_walker.py`, `tests/fixtures/`
**But :** sécuriser parsing tables japonaises, data/map pages, formats dates inconnus.
**Tests à ajouter :** listing page, data table complète, map iframe, format date non couvert, paid seating/access links.
**Données ou fixtures nécessaires :** HTML minimal `list`, `data.html`, `map.html`.
**Dépendances :** BUG-004.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### TEST-005 — Couvrir `POST /scrape` et concurrence jobs

**Priorité :** P0
**Zone concernée :** `api/routes/scrape.py`, `db/store.py`, `tests/test_api.py` ou nouveau `tests/test_scrape_api.py`
**But :** éviter abus/régression sur route mutante et statut jobs.
**Tests à ajouter :** auth requise (après SEC-001), already_running, stale job, failure marks job failed, source conflicts (`all` vs `tc`).
**Données ou fixtures nécessaires :** monkeypatch scrapers/background task synchrone.
**Dépendances :** SEC-001, BUG-007.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### ~~TEST-006 — Ajouter tests frontend minimaux~~ [DONE]

**Priorité :** P1
**Zone concernée :** `frontend/js/*.js`, `pyproject.toml` ou package JS si choisi
**But :** couvrir escaping XSS, filtres date, favoris, `buildPopup`, `renderMarkers` logique pure.
**Tests à ajouter :** Vitest/jsdom ou Playwright smoke ; au minimum tests de helpers `escapeHtml`, `safeUrl`, `parseTimes`, `computePresets`.
**Données ou fixtures nécessaires :** événements JSON synthétiques.
**Dépendances :** SEC-002.
**Taille estimée :** M
**Candidat PR indépendante :** Oui

### TEST-007 — Smoke test Docker/production start

**Priorité :** P2
**Zone concernée :** `Dockerfile`, `.github/workflows/ci.yml`, `api/app.py`
**But :** garantir que l'image build et `/health` répond.
**Tests à ajouter :** CI `docker build`, optionnel `docker run` + curl `/health`.
**Données ou fixtures nécessaires :** DB temporaire vide.
**Dépendances :** CLEAN-002.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### TEST-008 — Tests config env

**Priorité :** P2
**Zone concernée :** `config.py`
**But :** sécuriser parsing `EVENTMAPS_ALLOWED_ORIGINS`, futurs tokens/flags.
**Tests à ajouter :** CSV origins, JSON origins, defaults, invalid values.
**Données ou fixtures nécessaires :** monkeypatch env + reload settings class.
**Dépendances :** SEC-001, SEC-004.
**Taille estimée :** XS/S
**Candidat PR indépendante :** Oui

## 8. Documentation & Developer Experience

### DOC-001 — README à mettre à jour avec l'état réel

**Priorité :** P1
**Problème :** README annonce `uv run pytest # tous les tests (115)` alors que 146 tests passent ; il décrit surtout les endpoints de base mais pas `/scrape`, `/health`, bbox, `start_from`, ICS, env vars.
**Amélioration proposée :** actualiser commandes, endpoints, variables d'environnement, sécurité `/scrape`, Docker, workflow dev/test.
**Fichiers concernés :** `README.md`
**Dépendances :** SEC-001 pour doc token si implémenté.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### DOC-002 — Documenter configuration production et sécurité

**Priorité :** P1
**Problème :** pas de guide prod pour CORS, DB path, scraping token, user-agent, rate limiting, persistance `data/`.
**Amélioration proposée :** ajouter section “Production deployment checklist” dans README ou `docs/DEPLOYMENT.md`.
**Fichiers concernés :** `README.md`, éventuellement `docs/DEPLOYMENT.md` (attention `.gitignore` ignore actuellement `docs/`).
**Dépendances :** SEC-001, SEC-004, SEC-007.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### DOC-003 — Documenter architecture et contrat de données

**Priorité :** P2
**Problème :** le contrat `Event.attributes` par source n'est décrit que partiellement dans README ancien format ; le frontend dépend de clés implicites.
**Amélioration proposée :** ajouter `docs/ARCHITECTURE.md` ou section README : flux scraper -> Event -> SQLite -> API -> frontend, schema attributes par source.
**Fichiers concernés :** `README.md`, `models/event.py`, `scrapers/*.py` comme références.
**Dépendances :** ARCH-001.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### DOC-004 — Ajouter CONTRIBUTING / conventions de PR

**Priorité :** P2
**Problème :** pas de guide contribution, pas de conventions de tests/lint, pas de politique fixtures/scraping live.
**Amélioration proposée :** ajouter `CONTRIBUTING.md` avec setup uv, commandes, style, tests offline, règles de scrape respectueux.
**Fichiers concernés :** `CONTRIBUTING.md`, README.
**Dépendances :** TOOL-001/Ruff recommandé.
**Taille estimée :** S
**Candidat PR indépendante :** Oui

### DOC-005 — Roadmap existante à synchroniser ou archiver

**Priorité :** P2
**Problème :** `ROADMAP.md` contient une roadmap datée 2026-06-01 et des statuts “DONE” potentiellement divergents de ce nouvel audit.
**Amélioration proposée :** soit fusionner les décisions encore valides dans `REPO_ROADMAP_AUDIT.md`, soit ajouter en tête que `REPO_ROADMAP_AUDIT.md` est la source pour les prochains tickets.
**Fichiers concernés :** `ROADMAP.md`, `REPO_ROADMAP_AUDIT.md`
**Dépendances :** Aucune.
**Taille estimée :** XS
**Candidat PR indépendante :** Oui

### DOC-006 — Ajouter `.env.example`

**Priorité :** P2
**Problème :** variables env discoverables seulement via `config.py`.
**Amélioration proposée :** créer `.env.example` avec DB path, port, allowed origins, log level, user-agent, scrape timeout, futurs flags/token.
**Fichiers concernés :** `.env.example`, README.
**Dépendances :** SEC-001.
**Taille estimée :** XS
**Candidat PR indépendante :** Oui

## 9. Product & Feature Opportunities

### FEAT-001 — Recherche et filtres serveur complets

**Valeur utilisateur :** High
**Complexité :** M
**Description :** ajouter recherche `q`, filtres catégories/source/date range côté API pour éviter de charger puis filtrer uniquement en JS.
**Pourquoi maintenant :** la roadmap mentionne déjà la limite frontend ; bbox pagination existe mais reste incomplète pour les filtres.
**Approche MVP :** `GET /events?q=&category=&start_from=&start_to=` avec `LIKE` simple et filtre JSON basique.
**Approche complète :** FTS5 SQLite, index catégories normalisées, UI URL-shareable.
**Fichiers probablement concernés :** `api/routes/events.py`, `db/store.py`, `frontend/js/api.js`, `frontend/js/filters.js`, `frontend/js/markers.js`.
**Risques :** requêtes JSON peu performantes si attributes restent texte.
**Dépendances :** BUG-001, ARCH-001.
**Candidat PR indépendante :** Non, découper MVP

### FEAT-002 — URLs partageables pour filtres et vue carte

**Valeur utilisateur :** Medium
**Complexité :** S/M
**Description :** synchroniser recherche, dates, catégories actives, favoris-only, bbox/zoom dans query params.
**Pourquoi maintenant :** utile pour partager une sélection d'événements et tester manuellement.
**Approche MVP :** encoder `from`, `to`, `q`, `source/cats` dans URL sans reload.
**Approche complète :** deep-link avec map center/zoom, bouton “copy link”.
**Fichiers probablement concernés :** `frontend/js/app.js`, `frontend/js/filters.js`, `frontend/js/api.js`.
**Risques :** état UI déjà mutable global ; éviter complexité excessive.
**Dépendances :** BUG-001.
**Candidat PR indépendante :** Oui

### FEAT-003 — Mode “événements à proximité de moi”

**Valeur utilisateur :** High
**Complexité :** M
**Description :** après géolocalisation, trier/filtrer par distance et afficher distance dans cartes/popups.
**Pourquoi maintenant :** la géolocalisation existe déjà mais ne sert qu'à recentrer la carte.
**Approche MVP :** calcul Haversine client-side sur événements chargés, tri “nearest”.
**Approche complète :** endpoint `near=lat,lng&radius_km`, index spatial approximatif.
**Fichiers probablement concernés :** `frontend/js/geolocation.js`, `frontend/js/events-list.js`, `frontend/js/markers.js`, `db/store.py`.
**Risques :** vie privée ; garder calcul local par défaut.
**Dépendances :** SEC-002.
**Candidat PR indépendante :** Oui pour MVP

### FEAT-004 — Import/export calendrier par liste filtrée

**Valeur utilisateur :** Medium
**Complexité :** S/M
**Description :** l'export ICS existe par événement ; ajouter export ICS de tous les événements visibles/filtrés.
**Pourquoi maintenant :** cohérent avec la carte d'événements et l'endpoint ICS existant.
**Approche MVP :** bouton frontend générant un ICS client-side pour événements visibles.
**Approche complète :** endpoint `/events.ics` acceptant mêmes filtres que `/events`.
**Fichiers probablement concernés :** `api/routes/events.py`, `frontend/js/app.js`, `frontend/index.html`.
**Risques :** gros fichiers ICS ; bien filtrer.
**Dépendances :** FEAT-001 si endpoint filtré.
**Candidat PR indépendante :** Oui pour MVP client

### FEAT-005 — Source metadata et page détail événement

**Valeur utilisateur :** Medium
**Complexité :** M
**Description :** ajouter panneau détail riche avec description, liens officiels, access, parking, rain policy, etc.
**Pourquoi maintenant :** ces données sont déjà scrapées mais sous-utilisées en popup.
**Approche MVP :** drawer latéral au clic carte/liste.
**Approche complète :** route `/event/{id}` partageable, images si disponibles, traduction automatique non nécessaire.
**Fichiers probablement concernés :** `frontend/index.html`, `frontend/js/events-list.js`, `frontend/js/popups.js`, `frontend/js/app.js`.
**Risques :** XSS si rendu HTML non sécurisé.
**Dépendances :** SEC-002, ARCH-001.
**Candidat PR indépendante :** Oui après sécurité

### FEAT-006 — Ajout d'une nouvelle source d'événements

**Valeur utilisateur :** High
**Complexité :** L
**Description :** ajouter une troisième source Tokyo/Japon (ex. Time Out Tokyo, Peatix public, municipal open data si disponible).
**Pourquoi maintenant :** à faire après stabilisation architecture source-specific.
**Approche MVP :** nouvelle classe `BaseScraper`, mapping vers `Event`, tests fixtures, filtre source.
**Approche complète :** pipeline source registry, normalisation catégories, scheduling.
**Fichiers probablement concernés :** `scrapers/`, `models/event.py`, `db/store.py`, `frontend/js/config.js`, `frontend/js/filters.js`, tests.
**Risques :** droits/ToS scraping, duplication schéma attributes.
**Dépendances :** ARCH-001, ARCH-002, TEST-003/004.
**Candidat PR indépendante :** Non avant refactors

## 10. Cleanup Candidates

### CLEAN-001 — Supprimer dépendances runtime inutilisées

**Zone concernée :** `pyproject.toml`, `uv.lock`
**Pourquoi c'est supprimable ou simplifiable :** `pandas` et `aiofiles` ne semblent pas utilisés dans le code actuel (`rg` ne trouve pas d'import applicatif). `icalendar` est utilisé.
**Risque de suppression :** Medium, car dépendances peut-être prévues pour futures features non visibles.
**Comment vérifier avant suppression :** `rg "import pandas|from pandas|aiofiles"`, tests complets, build Docker, vérifier ROADMAP.
**Plan proposé :** retirer une dépendance à la fois, `uv lock`, tests, mentionner en PR.
**Candidat PR indépendante :** Oui

### CLEAN-002 — Corriger `.dockerignore`

**Zone concernée :** `.dockerignore`, `Dockerfile`
**Pourquoi c'est supprimable ou simplifiable :** `.dockerignore` ignore `tests/` et `*.md` mais le Dockerfile copie tout après `uv sync`; il faut être explicite sur ce qui est exclu pour image légère sans casser docs/build.
**Risque de suppression :** Low
**Comment vérifier avant suppression :** `docker build .`, inspecter contexte/image, vérifier README pas requis runtime.
**Plan proposé :** ignorer `.venv`, `.git`, `data`, caches, coverage ; décider si `tests/`/Markdown exclus volontairement ; ajouter commentaires.
**Candidat PR indépendante :** Oui

### CLEAN-003 — Déplacer CSS inline hors `frontend/index.html`

**Zone concernée :** `frontend/index.html`, futur `frontend/css/`
**Pourquoi c'est supprimable ou simplifiable :** le HTML contient un gros bloc CSS, difficile à relire et à citer ; séparer CSS améliore maintenance et cache.
**Risque de suppression :** Medium, risque visuel.
**Comment vérifier avant suppression :** screenshot avant/après, test manuel UI responsive.
**Plan proposé :** créer `frontend/css/app.css`, mount `/css` dans FastAPI, déplacer sans changement fonctionnel.
**Candidat PR indépendante :** Oui

### CLEAN-004 — Centraliser parsing `times`

**Zone concernée :** `scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py`, `frontend/js/utils.js`, `api/routes/events.py`
**Pourquoi c'est supprimable ou simplifiable :** plusieurs endroits construisent/splittent `"start-end"`; tiret ambigu si format contient hyphen.
**Risque de suppression :** Medium
**Comment vérifier avant suppression :** tests fixtures times, ICS.
**Plan proposé :** ajouter `start_time`/`end_time` au modèle ou helper canonique ; pour petit changement, standardiser séparateur et parser robuste.
**Candidat PR indépendante :** Non, nécessite migration contrat

### CLEAN-005 — Clarifier `ROADMAP.md` vs audit

**Zone concernée :** `ROADMAP.md`, `REPO_ROADMAP_AUDIT.md`
**Pourquoi c'est supprimable ou simplifiable :** deux roadmaps peuvent diverger ; `ROADMAP.md` est historique et long.
**Risque de suppression :** Medium, peut contenir décisions produit importantes.
**Comment vérifier avant suppression :** demander au mainteneur quelle roadmap fait foi.
**Plan proposé :** garder mais ajouter statut “historique” ou fusionner décisions validées.
**Candidat PR indépendante :** Oui

### CLEAN-006 — Remplacer mutable default `attributes: dict = {}`

**Zone concernée :** `models/event.py`
**Pourquoi c'est supprimable ou simplifiable :** Pydantic v2 gère souvent les defaults, mais `Field(default_factory=dict)` exprime mieux l'intention et évite mauvaises surprises.
**Risque de suppression :** Low
**Comment vérifier avant suppression :** test deux `Event()` sans attributes ne partagent pas l'état.
**Plan proposé :** importer `Field`, changer le champ, ajouter test.
**Candidat PR indépendante :** Oui

## 11. Prioritized Roadmap

### Phase 0 — Stabilisation immédiate

Objectif : corriger les risques bloquants.

Tâches :

1. ~~`SEC-001` — protéger/désactiver `POST /scrape` — évite abus serveur et scraping non autorisé~~ **[DONE]**
2. ~~`SEC-002` — neutraliser XSS frontend — données externes actuellement injectées en HTML~~ **[DONE]**
3. ~~`TEST-005` — couvrir `/scrape` — sécurise auth/concurrence/stale jobs~~ **[DONE — auth + config endpoint couverts]**
4. ~~`BUG-001` — ajouter filtre date range serveur/client — corrige incohérence presets/pagination — dépendances : TEST-002.~~ **[DONE]**
5. ~~`BUG-003` — signaler succès partiels scraper — évite données silencieusement incomplètes — dépendances : ARCH-002 partiel.~~ **[DONE]**

### Phase 1 — Qualité & sécurité

1. ~~`SEC-005` — ajouter audit dépendances/Dependabot — supply-chain — dépendances : aucune.~~ **[DONE]**
2. ~~`SEC-003` — SRI/vendor assets CDN — réduit risque tiers — dépendances : aucune.~~ **[DONE]**
3. ~~`SEC-004` — documenter/restreindre CORS prod — hardening — dépendances : SEC-001.~~ **[DONE]**
4. ~~`TEST-003` — fixtures Tokyo Cheapo — protège parser — dépendances : aucune.~~ **[DONE]**
5. ~~`TEST-004` — fixtures Hanabi — protège parser — dépendances : BUG-004.~~ **[DONE]**
6. ~~`BUG-005` — fallback description Tokyo Cheapo — petite robustesse — dépendances : aucune.~~ **[DONE]**
7. ~~`CLEAN-006` — default factory attributes — hygiène modèle — dépendances : aucune.~~ **[DONE]**

### Phase 2 — Maintenabilité & architecture

1. `ARCH-002` — introduire `ScrapeResult` — observabilité et qualité scraping — dépendances : BUG-003.
2. ~~`ARCH-001` — typer attributes par source — contrat plus stable — dépendances : TEST-001.~~ **[DONE]**
3. ~~`ARCH-005` — déplacer génération ID hors DB — découplage métier — dépendances : aucune.~~ **[DONE]**
4. ~~`ARCH-004` — scinder `db.store` — maintenabilité — dépendances : TEST-001.~~ **[DONE]**
5. ~~`ARCH-006` — centraliser config scraping — ops — dépendances : BUG-003.~~ **[DONE]**
6. ~~`ARCH-007` — logs structurés scrape/job — diagnostic — dépendances : ARCH-002.~~ **[DONE]**

### Phase 3 — Tests & documentation

1. ~~`TEST-001` — couvrir CLI — ferme trou coverage 0% — dépendances : aucune.~~ **[DONE]**
2. ~~`TEST-006` — tests frontend — protège XSS/filtres — dépendances : SEC-002.~~ **[DONE]**
3. ~~`TEST-007` — Docker smoke CI — production readiness — dépendances : CLEAN-002.~~ **[DONE]**
4. ~~`TEST-008` — tests config env — évite régressions ops — dépendances : SEC-001/SEC-004.~~ **[DONE]**
5. ~~`DOC-001` — README actuel — onboarding — dépendances : SEC-001.~~ **[DONE]**
6. ~~`DOC-003` — architecture/contrat data — facilite LLM/devs — dépendances : ARCH-001.~~ **[DONE]**
7. ~~`DOC-004` — CONTRIBUTING — DX — dépendances : tooling.~~ **[DONE]**

### Phase 4 — Features produit

1. ~~`FEAT-001` — filtres/recherche serveur complets — scalabilité UX — dépendances : BUG-001, ARCH-001.~~ **[DONE]**
2. ~~`FEAT-003` — événements à proximité — valeur mobile — dépendances : SEC-002.~~ **[DONE]**
3. `FEAT-005` — drawer détail événement — valorise données existantes — dépendances : SEC-002, ARCH-001.
4. `FEAT-002` — URLs partageables — UX/support — dépendances : BUG-001.
5. `FEAT-004` — export calendrier liste filtrée — productivité utilisateur — dépendances : FEAT-001 si endpoint.
6. `FEAT-006` — nouvelle source — croissance contenu — dépendances : ARCH-001/002, fixtures.

## 12. Dependency Graph Between Tasks

```text
SEC-001
  -> TEST-005
  -> SEC-004
  -> DOC-001
  -> DOC-002
  -> DOC-006

SEC-002
  -> TEST-006
  -> ARCH-003
  -> FEAT-003
  -> FEAT-005

BUG-001
  -> TEST-002
  -> FEAT-001
  -> FEAT-002

BUG-003
  -> ARCH-002
  -> ARCH-006
  -> ARCH-007
  -> BUG-004

ARCH-001
  -> DOC-003
  -> FEAT-001
  -> FEAT-005
  -> FEAT-006

ARCH-002
  -> ARCH-007
  -> FEAT-006

CLEAN-002
  -> TEST-007
  -> SEC-007

SEC-005
  -> no downstream mandatory

TEST-001
  -> ARCH-001
  -> ARCH-004
```

**Tâches sans dépendances idéales pour un premier PR :**

* `BUG-005` — fallback description Tokyo Cheapo.
* `CLEAN-006` — `Field(default_factory=dict)` pour `Event.attributes`.
* `ARCH-005` — déplacer `make_id` hors `db.store`.
* `SEC-005` — Dependabot/audit dépendances.
* `TEST-001` — tests CLI.
* `TEST-003` — fixtures Tokyo Cheapo.
* `CLEAN-001` — vérifier/supprimer dépendances inutilisées.
* ~~`CLEAN-002` — `.dockerignore`.~~ **[DONE]**

## 13. PR-Ready Task Breakdown

### PR-001 — Protéger l'endpoint de scraping ✅ DONE

**Source :** SEC-001, TEST-005, DOC-002
**Objectif :** empêcher le déclenchement anonyme de scraping en production.
**Contexte nécessaire :** `POST /scrape` lance des requêtes réseau en background et est appelé par le bouton `#scrape-btn`.
**Fichiers à lire d'abord :** `api/routes/scrape.py`, `frontend/js/app.js`, `config.py`, `tests/test_api.py`.
**Fichiers probablement à modifier :** `config.py`, `api/routes/scrape.py`, `frontend/js/app.js`, `README.md`, tests.
**Étapes recommandées :**

1. Ajouter settings `enable_scrape_endpoint` et/ou `scrape_token`.
2. Vérifier un header `Authorization` ou `X-EventMaps-Admin-Token` avant `background_tasks.add_task`.
3. Retourner 403/404 clair quand désactivé/non autorisé.
4. Adapter le frontend : gérer erreurs, ne pas spinner indéfiniment, éventuellement masquer bouton via config endpoint.
5. Ajouter tests sans token/avec token/already running.

**Critères d'acceptation :**

* Sans configuration admin, un utilisateur anonyme ne peut pas déclencher un scrape en production.
* Les tests couvrent succès et refus.
* README documente la variable et l'usage local.

**Commandes de validation :**

```bash
uv run --locked python -m pytest tests/test_api.py tests/test_scraper_alerts.py -q
uv run --locked python -m pytest --cov=. --cov-fail-under=80 tests/ -q
```

**Risques :** casser le bouton local ; prévoir default dev documenté.
**Dépendances :** Aucune stricte.
**Peut être fait en parallèle avec :** PR-002, PR-006, PR-007.
**Ne pas faire dans cette PR :** refactor complet des jobs ou scheduler.

### PR-002 — Échapper les données externes dans le frontend ✅ DONE

**Source :** SEC-002, ARCH-003
**Objectif :** supprimer le risque XSS stocké par les données scrapées.
**Contexte nécessaire :** titres, lieux, prix et attributs viennent du scraping et sont interpolés en HTML.
**Fichiers à lire d'abord :** `frontend/js/popups.js`, `frontend/js/events-list.js`, `frontend/js/filters.js`, `frontend/js/markers.js`.
**Fichiers probablement à modifier :** `frontend/js/utils.js`, `frontend/js/popups.js`, `frontend/js/events-list.js`, `frontend/js/filters.js`.
**Étapes recommandées :**

1. Ajouter helpers `escapeHtml(value)` et `safeHttpUrl(value)`.
2. Appliquer escaping à tous les champs interpolés dans `buildPopup()` et `card.innerHTML`.
3. Neutraliser liens non `http:`/`https:`.
4. Masquer directions si coordonnées absentes.
5. Ajouter tests frontend si outillage disponible, sinon isoler helpers purs et tester via Node minimal.

**Critères d'acceptation :**

* Une valeur `<img onerror=alert(1)>` s'affiche comme texte, jamais comme balise.
* Une URL `javascript:...` n'est pas utilisée dans `href`.
* Les popups/listes gardent le même rendu pour données normales.

**Commandes de validation :**

```bash
uv run --locked python -m pytest -q
# si tests JS ajoutés
npm test
```

**Risques :** double escaping ou rendu visuel altéré.
**Dépendances :** Aucune stricte.
**Peut être fait en parallèle avec :** PR-001, PR-003, PR-006.
**Ne pas faire dans cette PR :** réécrire toute l'UI en framework.

### PR-003 — Corriger le filtre date range serveur/client ✅ DONE

**Source :** BUG-001, TEST-002, FEAT-001 MVP
**Objectif :** transmettre et appliquer les bornes `from` et `to` côté API pour les chargements bbox.
**Contexte nécessaire :** le frontend ignore actuellement `filter-date-to` dans les requêtes `/events`.
**Fichiers à lire d'abord :** `frontend/js/api.js`, `frontend/js/app.js`, `frontend/js/markers.js`, `api/routes/events.py`, `db/store.py`, `tests/test_api.py`, `tests/test_store.py`.
**Fichiers probablement à modifier :** `api/routes/events.py`, `db/store.py`, `frontend/js/api.js`, tests.
**Étapes recommandées :**

1. Ajouter paramètre API `start_to` ou `date_to` avec description OpenAPI.
2. Implémenter overlap en DB : `start_date <= to AND COALESCE(end_date,start_date) >= from`.
3. Envoyer `filter-date-to` depuis `fetchEventsByBbox()`.
4. Garder filtrage client comme sécurité visuelle.
5. Ajouter tests pagination/range.

**Critères d'acceptation :**

* Preset `today` ne charge que les événements chevauchant aujourd'hui.
* Les événements multi-jours sont inclus si la période chevauche le range.
* Pagination reste stable.

**Commandes de validation :**

```bash
uv run --locked python -m pytest tests/test_store.py tests/test_api.py -q
uv run --locked python -m pytest -q
```

**Risques :** changement de comportement API pour clients existants ; utiliser nouveau paramètre optionnel.
**Dépendances :** Aucune stricte.
**Peut être fait en parallèle avec :** PR-001, PR-002.
**Ne pas faire dans cette PR :** recherche plein texte/catégories serveur.

### PR-004 — Ajouter un rapport de scraping et seuil d'échec partiel

**Source :** BUG-003, ARCH-002, ARCH-007
**Objectif :** rendre visibles les scrapes partiels et éviter les succès silencieux.
**Contexte nécessaire :** `scrape_all()` skip par événement et `scrape()` retourne seulement une liste.
**Fichiers à lire d'abord :** `scrapers/base.py`, `scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py`, `api/routes/scrape.py`, `db/store.py`, `main.py`.
**Fichiers probablement à modifier :** `scrapers/base.py`, `scrapers/*.py`, `api/routes/scrape.py`, `db/store.py`, tests.
**Étapes recommandées :**

1. Créer dataclass `ScrapeReport`/`ScrapeResult` sans casser `scrape()` public.
2. Compter liens vus, events ok, events skipped, erreurs échantillonnées.
3. Ajouter colonnes ou JSON `metadata` à `scrape_jobs` si nécessaire.
4. Échouer au-delà d'un seuil configurable.
5. Ajouter tests avec monkeypatch d'erreurs partielles.

**Critères d'acceptation :**

* Un scrape avec taux d'échec élevé marque le job failed.
* Le status expose au moins counts ok/skipped.
* CLI log un résumé actionnable.

**Commandes de validation :**

```bash
uv run --locked python -m pytest tests/test_scraper_alerts.py tests/test_api.py -q
uv run --locked python -m pytest -q
```

**Risques :** PR trop grosse ; découper si nécessaire en “compteurs sans DB” puis “job metadata”.
**Dépendances :** Aucune stricte, mais mieux après PR-001.
**Peut être fait en parallèle avec :** PR-006, PR-007.
**Ne pas faire dans cette PR :** migration vers Celery/Redis.

### PR-005 — Fixer l'inférence d'année Tokyo Cheapo

**Source :** BUG-002, TEST-003
**Objectif :** éviter dates incorrectes autour du Nouvel An.
**Contexte nécessaire :** `_parse_date_range()` utilise `_date.today().year`.
**Fichiers à lire d'abord :** `scrapers/tokyo_cheapo.py`, `tests/test_tokyo_cheapo.py`.
**Fichiers probablement à modifier :** `scrapers/tokyo_cheapo.py`, `tests/test_tokyo_cheapo.py`.
**Étapes recommandées :**

1. Ajouter paramètre `reference_date` à `_parse_date_range()` ou au scraper.
2. Ajouter tests Dec -> Jan et Jan scraping.
3. Inférer année suivante si mois parsé < mois de référence et source liste des événements futurs.
4. Gérer range où `end < start` en ajoutant un an à `end`.

**Critères d'acceptation :**

* `Dec 31 - Jan 2` produit une fin l'année suivante.
* Les dates normales de l'année courante restent inchangées.
* Tests existants restent verts.

**Commandes de validation :**

```bash
uv run --locked python -m pytest tests/test_tokyo_cheapo.py -q
uv run --locked python -m pytest -q
```

**Risques :** hypothèses sur Tokyo Cheapo “this week”; documenter l'inférence.
**Dépendances :** Aucune.
**Peut être fait en parallèle avec :** PR-001, PR-002, PR-006.
**Ne pas faire dans cette PR :** refactor complet dates Hanabi.

### ~~PR-006 — Ajouter Ruff format/check en CI~~ ✅ DONE

**Source :** Technology & Tooling, DOC-004
**Objectif :** standardiser lint/format sans gros refactor.
**Contexte nécessaire :** aucun linter/formatter déclaré.
**Fichiers à lire d'abord :** `pyproject.toml`, `.github/workflows/ci.yml`.
**Fichiers probablement à modifier :** `pyproject.toml`, `.github/workflows/ci.yml`, éventuellement fichiers Python si auto-fix minimal.
**Étapes recommandées :**

1. Ajouter `ruff` au groupe dev.
2. Configurer règles de base dans `pyproject.toml`.
3. Lancer `uv run ruff format` et `uv run ruff check --fix` si l'équipe accepte le formatage.
4. Ajouter job CI ou étapes avant pytest.
5. Documenter commandes.

**Critères d'acceptation :**

* `uv run ruff check .` passe.
* `uv run ruff format --check .` passe.
* CI exécute ces checks.

**Commandes de validation :**

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m pytest -q
```

**Risques :** diff volumineux si formatage complet ; peut d'abord ajouter config sans reformater.
**Dépendances :** Aucune.
**Peut être fait en parallèle avec :** PR-001, PR-003.
**Ne pas faire dans cette PR :** ajouter mypy strict.

### ~~PR-007 — Couvrir le CLI `main.py`~~ ✅ DONE

**Source :** TEST-001
**Objectif :** réduire trou coverage et sécuriser commandes utilisateurs.
**Contexte nécessaire :** `main.py` est à 0% de couverture.
**Fichiers à lire d'abord :** `main.py`, `tests/test_api.py` factories.
**Fichiers probablement à modifier :** `tests/test_main.py`, éventuellement petites adaptations testability dans `main.py`.
**Étapes recommandées :**

1. Créer factories Event partagées ou locales.
2. Monkeypatch `TokyoCheapo`/`HanabiWalker` pour éviter réseau.
3. Tester `tc --output csv`, `hanabi --region`, `all --db tmp`.
4. Tester erreurs argparse si utile.

**Critères d'acceptation :**

* `main.py` a une couverture significative.
* Les commandes n'accèdent pas au réseau en tests.
* CSV contient header attendu.

**Commandes de validation :**

```bash
uv run --locked python -m pytest tests/test_main.py -q
uv run --locked python -m pytest --cov=. --cov-fail-under=80 tests/ -q
```

**Risques :** besoin de refactor léger pour injecter scrapers ; rester minimal.
**Dépendances :** Aucune.
**Peut être fait en parallèle avec :** PR-001, PR-002, PR-006.
**Ne pas faire dans cette PR :** changer comportement CLI.

### PR-008 — Corriger `.dockerignore` et hardening Docker minimal

**Source :** CLEAN-002, SEC-007, TEST-007
**Objectif :** produire une image plus propre et moins risquée.
**Contexte nécessaire :** Dockerfile copie le repo complet après install deps.
**Fichiers à lire d'abord :** `Dockerfile`, `.dockerignore`, `pyproject.toml`.
**Fichiers probablement à modifier :** `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`.
**Étapes recommandées :**

1. Nettoyer `.dockerignore` avec commentaires.
2. Ajouter user non-root et répertoire data writable.
3. Ajouter `HEALTHCHECK` sur `/health` si curl/wget disponible ou Python one-liner.
4. Ajouter CI `docker build`.

**Critères d'acceptation :**

* Image build sans inclure `.venv`/data/git.
* Process tourne non-root.
* `/health` fonctionne dans container.

**Commandes de validation :**

```bash
docker build -t eventmaps:test .
docker run --rm -p 8000:8000 eventmaps:test
uv run --locked python -m pytest -q
```

**Risques :** environnement CI sans Docker run possible ; build seul acceptable initialement.
**Dépendances :** Aucune.
**Peut être fait en parallèle avec :** PR-006, PR-007.
**Ne pas faire dans cette PR :** changer base image ou orchestration complète.

### PR-009 — Supprimer dépendances inutilisées ✅ DONE

**Source :** CLEAN-001, SEC-005
**Objectif :** réduire surface supply-chain et taille install.
**Contexte nécessaire :** `pandas` et `aiofiles` semblent inutilisés.
**Fichiers à lire d'abord :** `pyproject.toml`, `uv.lock`, code via `rg`.
**Fichiers probablement à modifier :** `pyproject.toml`, `uv.lock`.
**Étapes recommandées :**

1. Confirmer absence d'import avec `rg`.
2. Retirer une dépendance à la fois.
3. `uv lock`/`uv sync --locked` selon workflow.
4. Lancer tests et Docker build si possible.

**Critères d'acceptation :**

* Tests passent.
* Lockfile cohérent.
* README/roadmap ne promet pas une feature dépendante cassée.

**Commandes de validation :**

```bash
rg "pandas|aiofiles" . -g '!uv.lock'
uv lock
uv run python -m pytest -q
```

**Risques :** dépendance prévue mais non utilisée ; mentionner dans PR.
**Dépendances :** Aucune.
**Peut être fait en parallèle avec :** PR-006, PR-008.
**Ne pas faire dans cette PR :** upgrades massifs.

### PR-010 — Déplacer génération d'ID hors DB ✅ DONE

**Source :** ARCH-005
**Objectif :** découpler règle métier d'identité événement de `db.store`.
**Contexte nécessaire :** scrapers importent `_make_id` depuis `db.store`.
**Fichiers à lire d'abord :** `db/store.py`, `scrapers/tokyo_cheapo.py`, `scrapers/hanabi_walker.py`, `tests/*.py`.
**Fichiers probablement à modifier :** nouveau `models/identity.py` ou `utils/identity.py`, imports scrapers/tests, `db/store.py`.
**Étapes recommandées :**

1. Créer `make_id(parts: list[str])` public dans un module métier.
2. Remplacer imports `_make_id`.
3. Garder alias `_make_id = make_id` temporaire si beaucoup de tests l'utilisent, ou migrer tests.
4. Lancer tests.

**Critères d'acceptation :**

* Aucun scraper n'importe un symbole privé de `db.store`.
* IDs générés inchangés.
* Tests existants passent.

**Commandes de validation :**

```bash
rg "_make_id|make_id" scrapers tests db models
uv run --locked python -m pytest -q
```

**Risques :** casser IDs si séparateur/hash change ; ne pas modifier l'algorithme.
**Dépendances :** Aucune.
**Peut être fait en parallèle avec :** PR-001, PR-002.
**Ne pas faire dans cette PR :** changer clés de déduplication.

### PR-011 — Ajouter fixtures HTML Hanabi et gérer dates non parseables ✅ DONE

**Source :** BUG-004, TEST-004
**Objectif :** éviter événements Hanabi invisibles à cause de `start_date=None`.
**Contexte nécessaire :** `_extract_dates()` retourne parfois `[raw]`; `_parse_iso_date()` renvoie ensuite `None`.
**Fichiers à lire d'abord :** `scrapers/hanabi_walker.py`, `tests/test_hanabi_walker.py`.
**Fichiers probablement à modifier :** `scrapers/hanabi_walker.py`, `tests/test_hanabi_walker.py`, `tests/fixtures/hanabi_*`.
**Étapes recommandées :**

1. Ajouter test format date inconnu.
2. Décider comportement : skip explicite avec erreur ou event `date_parse_failed` non visible.
3. Préférer skip + compteur erreur si PR-004 existe ; sinon log warning et ne pas créer Event sans date.
4. Ajouter fixtures data/map réalistes.

**Critères d'acceptation :**

* Aucun Hanabi Event sans `start_date` n'est créé par défaut.
* Format inconnu est visible dans logs/tests.
* Fixtures couvrent table + map.

**Commandes de validation :**

```bash
uv run --locked python -m pytest tests/test_hanabi_walker.py -q
uv run --locked python -m pytest -q
```

**Risques :** perte d'événements avec formats inconnus ; compenser par reporting.
**Dépendances :** PR-004 recommandé mais pas strict.
**Peut être fait en parallèle avec :** PR-005.
**Ne pas faire dans cette PR :** refactor complet ScrapeResult si non dépendant.

### PR-012 — Mettre à jour README et `.env.example`

**Source :** DOC-001, DOC-002, DOC-006
**Objectif :** améliorer onboarding et exploitation.
**Contexte nécessaire :** README ne couvre pas toutes les routes/env vars et nombre de tests obsolète.
**Fichiers à lire d'abord :** `README.md`, `config.py`, `api/routes/events.py`, `api/routes/scrape.py`, `Dockerfile`.
**Fichiers probablement à modifier :** `README.md`, `.env.example`.
**Étapes recommandées :**

1. Lister variables depuis `config.py`.
2. Documenter setup, scrape, API, frontend, tests, Docker.
3. Corriger nombre de tests ou éviter nombre fixe.
4. Ajouter `.env.example`.

**Critères d'acceptation :**

* Un nouveau dev peut lancer app/tests sans lire le code.
* Les endpoints actuels sont listés.
* Les risques prod (`/scrape`, CORS, DB path) sont visibles.

**Commandes de validation :**

```bash
uv run --locked python -m pytest -q
```

**Risques :** docs peuvent devancer une feature non merge ; aligner avec code actuel.
**Dépendances :** PR-001 si token documenté.
**Peut être fait en parallèle avec :** PR-006, PR-007.
**Ne pas faire dans cette PR :** changer code applicatif.

## 14. Suggested Labels

* `bug`
* `security`
* `tests`
* `docs`
* `refactor`
* `frontend`
* `backend`
* `scraper`
* `database`
* `api`
* `ci`
* `docker`
* `dependencies`
* `performance`
* `developer experience`
* `good first issue`
* `needs investigation`
* `breaking change`
* `product`
* `observability`
* `xss`
* `rate limiting`
* `roadmap`

## 15. Open Questions

* **L'application est-elle destinée à être publique sur Internet ou seulement locale/admin ?**
  Pourquoi : influence fortement `SEC-001`, CORS, rate limiting, Docker hardening et auth.
  Qui peut répondre : mainteneur produit/ops.
  Tâches dépendantes : SEC-001, SEC-004, DOC-002, FEAT-001.

* **Le bouton “scrape” doit-il rester visible pour tous les utilisateurs ?**
  Pourquoi : si non, il faut le masquer ou créer une interface admin.
  Qui peut répondre : product owner.
  Tâches dépendantes : PR-001, BUG-007.

* **Quelle est la politique acceptable vis-à-vis des sites scrapés ?**
  Pourquoi : user-agent, fréquence, max pages, robots/ToS, backoff et seuils dépendent de cette politique.
  Qui peut répondre : mainteneur légal/produit.
  Tâches dépendantes : ARCH-006, BUG-003, DOC-004.

* **Faut-il conserver les événements sans coordonnées ?**
  Pourquoi : la carte les ignore, mais une liste pourrait les afficher ; impact DB/API/UI.
  Qui peut répondre : product owner.
  Tâches dépendantes : FEAT-005, BUG-008, ARCH-001.

* **Faut-il conserver l'historique des événements passés ?**
  Pourquoi : `GET /events` filtre upcoming par défaut, mais DB accumule potentiellement les anciens événements. Rétention/cleanup non définie.
  Qui peut répondre : product/ops.
  Tâches dépendantes : FEAT-001, CLEAN futur, DB indexes.

* **`ROADMAP.md` reste-t-il source de vérité ?**
  Pourquoi : deux roadmaps peuvent produire des priorités contradictoires.
  Qui peut répondre : mainteneur repo.
  Tâches dépendantes : DOC-005.

* **Les dépendances CDN sont-elles acceptables en production ?**
  Pourquoi : SRI/vendorisation dépend du niveau de sécurité/offline attendu.
  Qui peut répondre : ops/security.
  Tâches dépendantes : SEC-003, CLEAN-003.

* **Quelle nouvelle source d'événements est prioritaire ?**
  Pourquoi : influence normalisation attributes/catégories et architecture scrapers.
  Qui peut répondre : product owner.
  Tâches dépendantes : FEAT-006, ARCH-001, ARCH-002.

## 16. Final Recommendations

### Les 5 actions les plus importantes

1. Protéger ou désactiver `POST /scrape` pour éviter l'abus serveur.
2. Corriger le rendu HTML frontend pour neutraliser XSS stocké.
3. Corriger le contrat de filtre date range entre UI et API.
4. Ajouter reporting de scraping partiel et fixtures HTML de contrat.
5. Ajouter tooling qualité/supply-chain en CI : Ruff + audit dépendances + Docker build.

### Les 5 PRs à faire en premier

1. `PR-001` — Protéger l'endpoint de scraping.
2. `PR-002` — Échapper les données externes dans le frontend.
3. `PR-003` — Corriger le filtre date range serveur/client.
4. `PR-007` — Couvrir le CLI `main.py`.
5. `PR-006` — Ajouter Ruff format/check en CI.

### Risques à ne pas ignorer

* XSS : le contenu scrapé est une entrée non fiable même si les sources semblent légitimes.
* Abuse `/scrape` : un endpoint mutateur anonyme est risqué dès que l'app est publique.
* Succès partiels silencieux : une carte “vide” ou incomplète peut sembler normale alors que le parser est cassé.
* Dates autour du Nouvel An : erreurs difficiles à détecter après coup car elles affectent IDs/upcoming.
* Dépendances/CDN : absence d'audit et SRI laisse des risques supply-chain évitables.

### Améliorations à plus fort retour sur investissement

* **Ruff + CI étendue** : faible coût, gains continus de qualité.
* **Tests CLI/scrape route** : couvre les zones les moins testées avec beaucoup de valeur.
* **Escaping frontend centralisé** : corrige un risque sécurité majeur sans changer le produit.
* **Fixtures HTML scrapers** : réduit fortement le coût de maintenance des parsers.
* **Documentation env/production** : accélère onboarding et évite mauvaises configurations.
