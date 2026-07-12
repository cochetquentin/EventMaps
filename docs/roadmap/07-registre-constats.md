# Registre des constats hérités de l'ancien audit

[Retour à l'index](README.md)

## Objectif du registre

Ce registre empêche la suppression de `REPO_ROADMAP_AUDIT.md` de faire disparaître des problèmes techniques connus. Il reprend **tous les constats BUG, SEC, ARCH, TEST, DOC et CLEAN qui n'étaient pas marqués terminés** dans cet ancien audit et leur attribue une disposition vérifiable. Les propositions `FEAT` sont conservées séparément dans l'[archive du backlog produit différé](08-backlog-produit-differe.md), car elles sont hors du périmètre de stabilisation :

- **Terminé avant cette roadmap** : le code ou la documentation actuelle contient déjà la correction attendue ;
- **Couvert** : une tâche active de la roadmap modulaire reprend explicitement le travail ;
- **Actif** : une nouvelle tâche `LEGACY-*` ci-dessous conserve le constat qui n'avait pas encore de destination.

Lorsqu'un constat classé terminé s'avère encore reproductible, il doit être rouvert sous forme de tâche active plutôt que supprimé de cette table.

## Table de migration des constats

| Ancien identifiant | Disposition | Destination ou justification actuelle |
|---|---|---|
| BUG-001 | Terminé avant cette roadmap | Les filtres `start_from` et `start_to` sont transmis par le frontend et couverts par les tests API/frontend. |
| BUG-003 | Terminé avant cette roadmap | `ScrapeReport`, le seuil d'erreur et leurs tests détectent les pertes massives. |
| BUG-004 | Terminé avant cette roadmap | Le parsing Hanabi des dates non exploitables possède désormais des cas de test dédiés. |
| BUG-005 | Terminé avant cette roadmap | Tokyo Cheapo applique un fallback de description et les variantes sont testées. |
| BUG-006 | **Actif** | [LEGACY-001](#legacy-001--filtrer-les-liens-dévénement-tokyo-cheapo) |
| BUG-007 | Terminé avant cette roadmap | `POST /scrape` retourne un `job_id` et `/scrape/status` peut filtrer dessus. |
| BUG-008 | Terminé avant cette roadmap | La génération des liens de directions est gardée lorsque les coordonnées sont absentes. |
| SEC-001 | **Actif** | [LEGACY-009](#legacy-009--décider-du-comportement-par-défaut-de-post-scrape) ; le token existe, mais l'endpoint reste public par défaut. |
| SEC-002 | Terminé avant cette roadmap | Les données externes affichées sont échappées et des tests frontend couvrent les helpers concernés. |
| SEC-003 | **Actif** | [LEGACY-002](#legacy-002--définir-la-résilience-des-assets-cdn) ; SRI est présent, mais aucun fallback n'est défini. |
| SEC-004 | **Actif** | [LEGACY-003](#legacy-003--rendre-la-configuration-cors-sûre-en-production) |
| SEC-005 | Terminé avant cette roadmap | `pip-audit` est exécuté par la CI ; CI-002 suit sa séparation en check lisible. |
| SEC-006 | **Couvert** | [DOC-002](05-documentation.md#doc-002--clarifier-le-parcours-dinstallation-et-dexploitation) doit documenter le stockage navigateur et les implications utilisateur. |
| ARCH-001 | Terminé avant cette roadmap | Les attributs par source sont modélisés par des modèles Pydantic dédiés. |
| ARCH-003 | **Actif** | [LEGACY-004](#legacy-004--réduire-le-couplage-entre-rendu-html-et-données) ; TREE-003 ne couvre que l'extraction du CSS. |
| ARCH-005 | Terminé avant cette roadmap | La génération d'identifiant vit dans `models/identity.py`, hors de la couche DB. |
| ARCH-006 | **Actif** | [LEGACY-010](#legacy-010--décider-et-valider-la-politique-des-régions-hanabi) ; les réglages réseau sont centralisés, mais pas la politique des régions autorisées. |
| ARCH-007 | **Actif** | [LEGACY-005](#legacy-005--définir-un-socle-dobservabilité) |
| ARCH-008 | **Actif** | [LEGACY-006](#legacy-006--stabiliser-le-contrat-api-consommé-par-le-frontend) |
| TEST-002 | Terminé avant cette roadmap | Les filtres de plage de dates sont couverts côté API et frontend. |
| TEST-003 | **Couvert** | [TEST-003](02-fixtures-tests.md#test-003--constituer-un-corpus-réel-tokyo-cheapo) |
| TEST-004 | **Couvert** | [TEST-004](02-fixtures-tests.md#test-004--constituer-un-corpus-réel-hanabi-walker) |
| TEST-005 | Terminé avant cette roadmap | Les routes de scrape, le `job_id` et les conflits de jobs possèdent des tests dédiés. |
| TEST-008 | **Actif** | [LEGACY-011](#legacy-011--valider-les-configurations-invalides) ; les valeurs valides, defaults et normalisations sont couverts, mais pas les valeurs invalides. |
| DOC-001 | **Couvert** | [DOC-001](05-documentation.md#doc-001--corriger-les-faits-périssables-du-readme) |
| DOC-002 | **Couvert** | [DOC-002](05-documentation.md#doc-002--clarifier-le-parcours-dinstallation-et-dexploitation) |
| DOC-003 | **Couvert** | [DOC-004](05-documentation.md#doc-004--synchroniser-la-documentation-darchitecture-avec-le-code) |
| DOC-004 | Terminé avant cette roadmap | `CONTRIBUTING.md` existe et documente setup, workflow, style et politique de fixtures. |
| DOC-005 | Terminé par cette roadmap | L'ancien audit a été remplacé par `docs/roadmap` et l'index en est la source d'autorité. |
| CLEAN-001 | Terminé avant cette roadmap | Les dépendances inutilisées citées par l'ancien audit ne figurent plus dans `pyproject.toml`. TREE-006 conserve le contrôle périodique. |
| CLEAN-002 | Terminé avant cette roadmap | `.dockerignore` exclut explicitement environnements, tooling, données, tests et documentation. |
| CLEAN-003 | **Couvert** | [TREE-003](04-arborescence.md#tree-003--réduire-progressivement-frontendindexhtml) |
| CLEAN-004 | **Actif** | [LEGACY-007](#legacy-007--définir-une-représentation-canonique-des-horaires) |
| CLEAN-005 | Terminé par cette roadmap | Il n'existe plus deux roadmaps concurrentes dans le dépôt. |
| CLEAN-006 | **Actif** | [LEGACY-008](#legacy-008--remplacer-les-valeurs-par-défaut-mutables-des-attributs) |

## Tâches actives héritées

## LEGACY-001 — Filtrer les liens d'événement Tokyo Cheapo

- **Statut : Terminé par cette roadmap**
- **Priorité : P1**
- **Origine :** BUG-006
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/72

**Problème.** `TokyoCheapo.get_event_links()` accepte encore largement les URLs sous `/events/`; une page de taxonomie ou de navigation peut donc provoquer des téléchargements inutiles et des événements ignorés.

**Critères d'acceptation.** La règle d'acceptation repose sur des structures réellement observées ; des fixtures couvrent les URLs événement valides et les URLs de navigation/taxonomie rejetées ; aucun événement réel du corpus n'est perdu.

**Résolution.** L'analyse du corpus réel a montré que `_EXCLUDE_LINKS` couvrait déjà correctement les URLs de navigation/taxonomie observées ; le vrai problème était la duplication d'un même événement sous une URL de base (`/events/{slug}/`) et une ou plusieurs URLs d'occurrence datée (`/events/{slug}/{YYYYMMDD}/`), provoquant des téléchargements redondants. `_dedupe_event_hrefs()` regroupe ces variantes sous l'URL de base quand elle est présente sur les pages parcourues, et conserve la variante datée telle quelle sinon (pour ne perdre aucun événement dont seule une occurrence datée est observée). Les 3 duplications connues du corpus réel (`ohi-racecourse-flea-market`, `geisha-ozashiki-odori-asakusa`, `shimokitazawa-flea-market`) sont verrouillées par un test de régression dédié.

## LEGACY-002 — Définir la résilience des assets CDN

- **Statut : À faire**
- **Priorité : P2**
- **Origine :** SEC-003
- **Suivi :** à renseigner

**Problème.** Les assets CDN possèdent SRI, mais l'application n'a pas de stratégie explicite lorsque le CDN est indisponible.

**Critères d'acceptation.** Le choix entre assets locaux, fallback ou dépendance assumée est documenté et testé au niveau adapté ; les hashes SRI restent vérifiés si le CDN est conservé.

## LEGACY-003 — Rendre la configuration CORS sûre en production

- **Statut : Terminé par cette roadmap**
- **Priorité : P1**
- **Origine :** SEC-004
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/73

**Problème.** Le wildcard reste la valeur par défaut ; un warning existe avec un token, mais la posture de production dépend encore d'une configuration manuelle facile à oublier.

**Critères d'acceptation.** Le comportement attendu en développement et production est explicite, testé et documenté ; une configuration sensible ne peut pas démarrer silencieusement avec un wildcard non souhaité.

**Résolution.** Ajout d'une variable explicite `EVENTMAPS_ENV` (`development` par défaut, `production` en option — toute autre valeur est rejetée au démarrage). Quand `EVENTMAPS_ENV=production` et que `EVENTMAPS_ALLOWED_ORIGINS` contient encore le wildcard `*`, l'application refuse de démarrer (`RuntimeError`) au lieu d'un simple avertissement. Le comportement précédent (warning en développement quand un `EVENTMAPS_SCRAPE_TOKEN` est défini avec un wildcard) est conservé à l'identique. Documenté dans `.env.example` et `README.md`.

## LEGACY-004 — Réduire le couplage entre rendu HTML et données

- **Statut : À faire**
- **Priorité : P3**
- **Origine :** ARCH-003
- **Suivi :** à renseigner

**Problème.** Malgré l'échappement ajouté, le rendu frontend reste fortement couplé à de grands templates HTML construits en JavaScript.

**Critères d'acceptation.** Les composants les plus risqués ou complexes sont identifiés ; une approche progressive est choisie sans introduire de framework injustifié ; les tests de rendu protègent le comportement.

## LEGACY-005 — Définir un socle d'observabilité

- **Statut : À faire**
- **Priorité : P2**
- **Origine :** ARCH-007
- **Suivi :** à renseigner

**Critères d'acceptation.** Les informations minimales nécessaires pour diagnostiquer requêtes, jobs et sources de scrape sont définies ; les logs permettent de corréler un job sans exposer de secret ; toute métrique ajoutée répond à un besoin documenté.

## LEGACY-006 — Stabiliser le contrat API consommé par le frontend

- **Statut : À faire**
- **Priorité : P3**
- **Origine :** ARCH-008
- **Suivi :** à renseigner

**Critères d'acceptation.** Une stratégie proportionnée est décidée — test de schéma, snapshot OpenAPI, versionnement ou compatibilité documentée — et une rupture involontaire des champs consommés par le frontend est détectée avant merge.

## LEGACY-007 — Définir une représentation canonique des horaires

- **Statut : À faire**
- **Priorité : P2**
- **Origine :** CLEAN-004
- **Suivi :** à renseigner

**Problème.** Plusieurs couches construisent et interprètent encore une chaîne `times`, avec des règles potentiellement divergentes.

**Critères d'acceptation.** Le contrat des horaires et des plages nocturnes est documenté ; parsing et formatage sont centralisés ou rendus cohérents ; les exports ICS et les trois sources restent couverts.


## LEGACY-008 — Remplacer les valeurs par défaut mutables des attributs

- **Statut : À faire**
- **Priorité : P2**
- **Origine :** CLEAN-006
- **Suivi :** à renseigner

**Problème.** `TokyoCheapoAttributes.categories` et `TokyoCheapoAttributes.tags` utilisent encore des listes littérales comme valeurs par défaut, contrairement au modèle Time Out Tokyo qui utilise `Field(default_factory=list)`.

**Critères d'acceptation.** Toutes les collections mutables des modèles utilisent une factory explicite ; un test démontre que deux instances ne partagent pas leur état ; la sérialisation existante reste compatible.


## LEGACY-009 — Décider du comportement par défaut de `POST /scrape`

- **Statut : À faire**
- **Priorité : P1**
- **Origine :** SEC-001
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/74

**Problème.** La protection Bearer est disponible, mais l'absence de token laisse encore l'endpoint public par défaut. Ce comportement peut être volontaire en développement, mais il ne constitue pas une posture de production sûre sans décision explicite.

**Critères d'acceptation.** Le comportement par défaut et les environnements supportés sont décidés ; un déploiement de production ne peut pas exposer involontairement le déclenchement du scraping ; l'UI, `/scrape/config`, les tests et la documentation restent cohérents avec la décision.

## LEGACY-010 — Décider et valider la politique des régions Hanabi

- **Statut : À faire**
- **Priorité : P1**
- **Origine :** ARCH-006
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/75

**Problème.** La CLI et `POST /scrape` acceptent actuellement n'importe quelle valeur `region` et `HanabiWalker` l'interpole dans l'URL de listing. L'ancien audit prévoyait une configuration `allowed_hanabi_regions`, qui n'a pas été implémentée.

**Décision attendue.** Choisir explicitement entre une liste de régions supportées et validées, ou le support assumé de codes arbitraires respectant un format sûr.

**Critères d'acceptation.** La politique est centralisée, appliquée de façon cohérente par la CLI et l'API, testée pour les valeurs valides et invalides, et documentée sans bloquer l'ajout futur d'une région légitime.

## LEGACY-011 — Valider les configurations invalides

- **Statut : À faire**
- **Priorité : P2**
- **Origine :** TEST-008
- **Dépendances :** LEGACY-003, LEGACY-010
- **Suivi :** à renseigner

**Problème.** `tests/test_config.py` couvre les valeurs par défaut, le parsing CSV/JSON des origines, la normalisation du token et des overrides valides. Il ne définit toutefois pas le comportement attendu pour les valeurs invalides. Plusieurs réglages numériques sont actuellement de simples `int` ou `float` sans bornes déclarées, et la politique des origines/régions reste à préciser.

**Cas minimaux à décider et couvrir.** Origines JSON malformées ou types inattendus ; port hors plage ; timeouts, limites de pages et tentatives nuls ou négatifs ; seuil d'erreur hors de l'intervalle retenu ; booléen invalide ; région Hanabi rejetée selon la politique issue de LEGACY-010.

**Critères d'acceptation.** Pour chaque réglage public, le comportement sur valeur invalide est explicite — rejet avec erreur compréhensible ou normalisation documentée — et testé depuis les sources réellement supportées (`env`, `.env` ou initialisation directe selon le contrat). Les tests ne doivent pas seulement figer le comportement permissif actuel : ils doivent refléter les contraintes décidées.
