# Arborescence et maintenabilité

[Retour à l'index](README.md)

## Diagnostic

L'organisation applicative est globalement cohérente : `api/`, `db/`, `models/`, `scrapers/`, `frontend/` et `tests/` ont des responsabilités compréhensibles. Le découpage récent de `db/store.py` en repositories spécialisés est sain. Le nettoyage doit donc rester ciblé et éviter une réorganisation massive sans bénéfice mesurable.

Les principaux candidats observés sont l'ancien audit monolithique désormais supprimé, les fixtures à réorganiser, le très grand `frontend/index.html` (845 lignes, incluant beaucoup de présentation), les métadonnées génériques du package Python, et un `Makefile` qui ne propose que `run` alors que la documentation énumère plusieurs commandes qualité.

Les répertoires locaux `.venv/` et `node_modules/` sont présents dans la copie de travail mais correctement ignorés et non versionnés : ils ne constituent pas des éléments à supprimer du dépôt Git.

## TREE-001 — Maintenir un inventaire des fichiers racine

- **Statut : Terminé**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/64

**Actions.** Pour chaque fichier racine, confirmer propriétaire, rôle et audience ; supprimer ou déplacer uniquement les éléments sans rôle actuel ; vérifier les fichiers générés et les ignores Git/Docker.

**Résultat.** Tous les fichiers racine sont justifiés et documentés (voir tableau ci-dessous). Aucun artefact temporaire n'est versionné. `.ruff_cache/` et `.pytest_cache/` ajoutés au `.gitignore` pour expliciter les exclusions déjà effectives en pratique.

| Fichier / dossier | Rôle | Audience |
|---|---|---|
| `main.py` | CLI scraper (entry point `scrape`) | Développeurs, ops |
| `config.py` | Configuration centralisée | Modules backend |
| `pyproject.toml` | Manifeste Python | Python tooling |
| `uv.lock` | Lock file uv | CI/CD |
| `package.json` + `package-lock.json` | Manifeste npm (vitest frontend) | Devs frontend |
| `vitest.config.js` | Config tests frontend | CI/CD |
| `Makefile` | Cible `run` (serveur API dev) | Développeurs |
| `Dockerfile` + `.dockerignore` | Image container | Ops / CI |
| `.env.example` | Template variables d'environnement | Onboarding |
| `.python-version` | Ancrage Python 3.13 | uv / pyenv |
| `.gitattributes` | EOL LF forcé | Git |
| `.gitignore` | Exclusions Git | Git |
| `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` | Documentation racine | Tous |
| `api/`, `db/`, `models/`, `scrapers/`, `frontend/`, `tests/`, `tools/`, `scripts/`, `docs/`, `data/` | Modules applicatifs | Développeurs |

**Critères d'acceptation.** Aucun document d'audit temporaire ou artefact généré n'est versionné à la racine ; chaque fichier racine est justifié.

## TREE-002 — Corriger les métadonnées et points d'entrée du package

- **Statut : Terminé**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/65

**Constat.** `pyproject.toml` contenait la description générique `Add your description here`. Le script `scrape = "main:main"` était déjà testé (`tests/test_main.py::test_main_dispatch_tc`) et documenté (README, CONTRIBUTING, ARCHITECTURE) — il est conservé.

**Résultat.** Description remplacée par `"API et scrapers pour cartographier les événements autour de Tokyo"`. Point d'entrée `scrape` conservé : contrat validé par les tests et la documentation existante.

**Critères d'acceptation.** Les métadonnées décrivent réellement EventMaps ; le point d'entrée installé est testé et documenté, ou retiré s'il n'est pas supporté.

## TREE-003 — Réduire progressivement `frontend/index.html`

- **Statut : Terminé**
- **Priorité : P2**
- **Suivi :** https://github.com/cochetquentin/EventMaps/pull/108

**Résultat.** Le bloc `<style>` de 727 lignes a été extrait vers `frontend/css/style.css`. FastAPI sert le fichier via un mount `/css` (même pattern que `/js`). `index.html` est passé de 845 à ~115 lignes purement structurelles.

**Critères d'acceptation.** `index.html` redevient principalement structurel ; aucun changement visuel ou fonctionnel involontaire.

## TREE-004 — Fournir une interface unique pour les commandes courantes

- **Statut : À faire**
- **Priorité : P2**
- **Suivi :** à renseigner

**Actions.** Décider si `Makefile` reste l'interface commune ; si oui, ajouter des cibles cohérentes pour tests, lint, format, frontend et CI locale ; sinon le supprimer et documenter l'alternative.

**Critères d'acceptation.** README, CONTRIBUTING et CI utilisent ou référencent les mêmes commandes canoniques.

## TREE-005 — Vérifier les frontières et imports internes

- **Statut : À faire**
- **Priorité : P2**
- **Suivi :** à renseigner

**Actions.** Examiner les imports de symboles privés entre modules, notamment `_today_jst`, `_EVENTS_HEADERS` et les alias `_make_id`; décider lesquels doivent devenir API interne explicite ; éviter une refonte sans test de bénéfice.

**Critères d'acceptation.** Les imports privés inter-modules sont supprimés ou justifiés ; les contrats internes importants sont testés.

## TREE-006 — Examiner les fichiers et dépendances devenus inutiles

- **Statut : À faire**
- **Priorité : P3**
- **Suivi :** à renseigner

**Actions.** Rechercher imports, fichiers de package vides, tests orphelins, dépendances runtime/dev inutilisées et exclusions obsolètes ; traiter chaque suppression dans une PR petite avec CI verte.

**Critères d'acceptation.** Toute suppression est accompagnée d'une preuve d'absence d'usage et n'altère pas les points d'entrée supportés.
