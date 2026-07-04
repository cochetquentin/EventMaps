# Documentation

[Retour à l'index](README.md)

## Diagnostic

La documentation est déjà répartie selon des audiences utiles : `README.md` pour démarrer, `CONTRIBUTING.md` pour contribuer, `docs/ARCHITECTURE.md` pour la conception et `CLAUDE.md` pour les consignes propres à Claude Code. Cette séparation doit être conservée tout en éliminant les divergences.

Constats précis :

- Le README annonce `247 tests Python`, alors que la baseline actuelle en exécute 309.
- Le README est détaillé sur l'utilisation, mais ne donne pas de parcours rapide permettant de choisir entre CLI, API et Docker.
- `docs/ARCHITECTURE.md` décrit l'API, mais sa table d'endpoints ne contient pas les exports ICS actuels et doit être comparée systématiquement aux routes.
- `CLAUDE.md` est court et utile pour l'agent, mais duplique des commandes présentes ailleurs et une partie des règles de `/handle-codex-review`.
- L'ancien audit monolithique mélangeait backlog terminé, fonctionnalités et stabilisation ; il a été remplacé par cette roadmap spécialisée.

## DOC-001 — Corriger les faits périssables du README

- **Statut : Terminé**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/66

**Actions.** Corriger le nombre de tests ou éviter un nombre figé ; vérifier tous les exemples de commandes, sources, endpoints, paramètres, réponses, variables d'environnement et comportement Docker contre le code actuel.

**Critères d'acceptation.** Chaque commande documentée fonctionne ; aucun nombre ou exemple connu comme obsolète ; une procédure indique comment vérifier les informations susceptibles de changer.

## DOC-002 — Clarifier le parcours d'installation et d'exploitation

- **Statut : À faire**
- **Priorité : P2**
- **Suivi :** à renseigner

**Actions.** Distinguer clairement développement local, scraping CLI, serveur API/UI et Docker ; documenter les prérequis Node pour les tests frontend, les implications d'un endpoint `/scrape` public lorsque le token est vide, et l'usage non sensible de `localStorage` pour les favoris.

**Critères d'acceptation.** Un nouveau contributeur peut installer, lancer et tester le projet sans chercher des étapes dans plusieurs fichiers.

## DOC-003 — Réduire `CLAUDE.md` à des consignes spécifiques à l'agent

- **Statut : Terminé**
- **Priorité : P1**
- **Dépendances :** TOOL-005
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/67

**Actions.** Conserver uniquement les garde-fous et liens propres à Claude Code ; pointer vers CONTRIBUTING pour les conventions générales. TOOL-005 déplace le comportement détaillé de `/handle-codex-review` hors de `CLAUDE.md` ; DOC-003 finalise ensuite la réduction en retirant les commandes générales dupliquées.

**Critères d'acceptation.** Aucune commande générale n'est maintenue en double ; supprimer `CLAUDE.md` reste possible uniquement si aucune consigne agent-spécifique utile ne subsiste.

## DOC-004 — Synchroniser la documentation d'architecture avec le code

- **Statut : Terminé**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/68

**Actions.** Comparer les routes, modèles, tables, flux de scrape et réglages avec `docs/ARCHITECTURE.md`; ajouter les exports ICS et le suivi par `job_id`; retirer les descriptions obsolètes.

**Critères d'acceptation.** Toutes les routes publiques et tous les composants structurants actuels sont représentés ; la documentation évite de recopier les détails déjà mieux exposés par OpenAPI.

## DOC-005 — Ajouter une vérification documentaire légère

- **Statut : À faire**
- **Priorité : P2**
- **Dépendances :** DOC-001, DOC-004
- **Suivi :** à renseigner

**Actions.** Ajouter un contrôle de liens/format Markdown et, si rentable, un petit test comparant la liste documentée des endpoints ou variables aux sources d'autorité.

**Critères d'acceptation.** Les liens cassés et divergences faciles à automatiser échouent avant merge sans rendre la maintenance disproportionnée.
