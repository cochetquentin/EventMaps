# Arborescence et maintenabilité

[Retour à l'index](README.md)

## Diagnostic

L'organisation applicative est globalement cohérente : `api/`, `db/`, `models/`, `scrapers/`, `frontend/` et `tests/` ont des responsabilités compréhensibles. Le découpage récent de `db/store.py` en repositories spécialisés est sain. Le nettoyage doit donc rester ciblé et éviter une réorganisation massive sans bénéfice mesurable.

Les principaux candidats observés sont l'ancien audit monolithique désormais supprimé, les fixtures à réorganiser, le très grand `frontend/index.html` (845 lignes, incluant beaucoup de présentation), les métadonnées génériques du package Python, et un `Makefile` qui ne propose que `run` alors que la documentation énumère plusieurs commandes qualité.

Les répertoires locaux `.venv/` et `node_modules/` sont présents dans la copie de travail mais correctement ignorés et non versionnés : ils ne constituent pas des éléments à supprimer du dépôt Git.

## TREE-001 — Maintenir un inventaire des fichiers racine

- **Statut : À faire**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/64

**Actions.** Pour chaque fichier racine, confirmer propriétaire, rôle et audience ; supprimer ou déplacer uniquement les éléments sans rôle actuel ; vérifier les fichiers générés et les ignores Git/Docker.

**Critères d'acceptation.** Aucun document d'audit temporaire ou artefact généré n'est versionné à la racine ; chaque fichier racine est justifié.

## TREE-002 — Corriger les métadonnées et points d'entrée du package

- **Statut : À faire**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/65

**Constat.** `pyproject.toml` contient encore la description générique `Add your description here` et expose le script `scrape = "main:main"` sans que ce contrat soit clairement vérifié dans la documentation.

**Critères d'acceptation.** Les métadonnées décrivent réellement EventMaps ; le point d'entrée installé est testé et documenté, ou retiré s'il n'est pas supporté.

## TREE-003 — Réduire progressivement `frontend/index.html`

- **Statut : À faire**
- **Priorité : P2**
- **Suivi :** à renseigner

**Actions.** Extraire en priorité les styles statiques vers un fichier dédié ; ne pas introduire de framework ; conserver le comportement et ajouter les contrôles nécessaires au chargement des assets.

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
