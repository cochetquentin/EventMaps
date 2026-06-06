# Politique des fixtures de test — EventMaps

Ce document définit les règles de création, de catégorisation et de maintenance des fixtures HTML
utilisées dans la suite de tests. Il est la source d'autorité : toute fixture non conforme doit être
corrigée avant d'être mergée.

---

## 1. Deux catégories

### `real`

Capture complète d'une page telle que renvoyée par le serveur tiers (Tokyo Cheapo, Hanabi Walker,
Time Out Tokyo), enregistrée manuellement à une date donnée.

**Rôle** : couverture de régression sur des structures HTML réellement observées — vérifier que le
parseur fonctionne sur du HTML réel capturé à une date donnée.  
**Hypothèse** : la fixture est un instantané statique. Si la structure upstream change, les tests
sur la fixture continueront à passer (ils ne détectent pas les changements en production). Renouveler
la fixture manuellement lorsqu'une rupture de sélecteur est détectée en production.

### `synthetic`

HTML minimal construit à la main pour couvrir un cas unitaire précis (champ absent, format de date
particulier, régression de bug, structure multi-entrée).

**Rôle** : test unitaire ciblé — vérifier un comportement de parsing isolé sans bruit du HTML réel.  
**Hypothèse** : le fichier ne représente pas la page réelle et ne peut pas détecter une rupture de
contrat côté source.

---

## 2. Règles par dimension

### Provenance

- Toute fixture doit avoir une entrée dans `MANIFEST.yml` (même répertoire que ce fichier).
- `real` : le champ `url` dans le manifeste doit contenir l'URL canonique complète de la page capturée.
- `synthetic` : le champ `url` est `null` ; le champ `purpose` décrit précisément le cas couvert.
- Un test de conformité dans `tests/conftest.py` vérifie automatiquement que chaque `.html`
  est déclaré dans le manifeste.

### Date de capture

- `real` : le champ `captured_at` est obligatoire, au format ISO 8601 (`YYYY-MM-DD`).
- `synthetic` : `captured_at` est `null`.
- Lors d'une mise à jour d'une fixture `real`, mettre à jour `captured_at` dans le manifeste.

### Anonymisation

Supprimer ou remplacer par `REDACTED` dans les fixtures `real` :
- Tokens et clés d'API côté client (ex. `timeoutAuthClientId`, `newrelic_license_key` non publics)
- Adresses e-mail personnelles
- Toute donnée personnelle identifiable (RGPD)

**Conserver** le reste de la structure HTML intact, y compris les traceurs analytics (GTM, NewRelic,
etc.) : ils font partie du DOM réel et donc du contrat de structure testé.

Indiquer `anonymized: true` dans le manifeste une fois les données sensibles retirées.

### Taille

- `synthetic` : rester en dessous de **5 Ko**. Si le fichier grandit, diviser en cas distincts.
- `real` : pas de limite stricte — les captures réelles peuvent dépasser 100 Ko. Préférer la page
  minimale qui déclenche le cas couvert (éviter les pages paginées complètes si la section utile
  est petite).

### Mise à jour des captures réelles

Ne jamais mettre à jour une fixture `real` silencieusement. Toute mise à jour doit :

1. Être justifiée dans le message de commit (ex. : "structure de la page changée le YYYY-MM-DD").
2. Mettre à jour `captured_at` dans `MANIFEST.yml`.
3. S'accompagner d'une revue du diff HTML pour détecter les changements de sélecteurs.
4. Passer l'intégralité des tests avant merge.

### Tests réseau live

**Interdits en CI et localement.** Les tests ne font jamais de vraies requêtes HTTP vers les
sources tierces.

Cette règle est renforcée techniquement : `tests/conftest.py` bloque `requests.Session.send`
pendant chaque test. Tout appel réseau non intercepté lève une `RuntimeError` explicite.

Procédure pour renouveler une capture : voir TEST-007.

---

## 3. Nommage des fichiers

Convention : `{source}_{type}[_{variante}].html`

| Segment | Valeurs autorisées | Exemple |
|---|---|---|
| `source` | `tc` (Tokyo Cheapo), `hanabi` (Hanabi Walker), `tot` (Time Out Tokyo) | `tc` |
| `type` | `listing`, `event`, `map`, `fragment` | `event` |
| `variante` (optionnelle) | descriptif court en snake_case | `no_description`, `multi_location` |

Exemples valides : `tc_event_full.html`, `hanabi_event_map.html`, `tot_event_no_jsonld.html`.

---

## 4. Référence au manifeste

Chaque fichier `.html` dans ce répertoire doit avoir une entrée dans `MANIFEST.yml`.  
Le manifeste doit contenir au minimum : `file`, `category`, `source`, `captured_at`, `url`, `purpose`.

Un test de conformité (`pytest_sessionstart` dans `tests/conftest.py`) échoue si un `.html` est
présent sur disque sans entrée correspondante dans le manifeste.
