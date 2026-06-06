# CI/CD et contrôles qualité

[Retour à l'index](README.md)

## État observé

Le dépôt possède un unique workflow `.github/workflows/ci.yml`, nommé `CI`, déclenché sur les pull requests vers `main`, les push vers `main` et manuellement. Six jobs sont exposés : `Python / Lint`, `Python / Format`, `Python / Tests`, `Python / Security`, `Frontend / Tests` et `Docker / Build and smoke test`.

Chaque responsabilité Python dispose de son propre job : Ruff lint, Ruff format, pytest et pip-audit sont séparés, ce qui rend chaque échec attribuable sans ouvrir le log. Le smoke test Docker utilise une boucle bornée (15 × 2s) avec nettoyage garanti et affichage des logs en cas d'échec. Stratégie de pinning : version tags + Dependabot (voir `.github/dependabot.yml`).

## CI-001 — Donner des noms stables et explicites aux checks

- **Statut : ✅ Done**
- **Priorité : P0**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/49

**Actions.** Renommer les jobs selon leur responsabilité, par exemple `Python / Tests`, `Frontend / Tests`, `Docker / Build and smoke test`; éviter `Tests` seul ; documenter les noms retenus avant de configurer la protection de branche.

**Critères d'acceptation.** Depuis l'onglet Checks d'une PR, chaque échec est attribuable sans ouvrir le log ; les noms requis par la protection de branche sont stables.

## CI-002 — Séparer qualité Python, tests Python et audit de dépendances

- **Statut : ✅ Done**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/54

**Décision recommandée.** Garder un seul fichier de workflow tant que le dépôt reste petit, mais séparer les jobs. Plusieurs fichiers n'apporteraient pas encore de gain suffisant et dupliqueraient le setup.

**Actions.** Créer des jobs distincts pour Ruff, pytest et `pip-audit`, ou justifier explicitement leur regroupement ; mutualiser l'installation avec le cache `uv` si possible.

**Critères d'acceptation.** Un audit réseau indisponible ne masque pas le résultat des tests ; lint, format, tests et sécurité apparaissent comme checks distincts.

## CI-003 — Durcir le workflow GitHub Actions

- **Statut : ✅ Done**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/55

**Actions.** Ajouter des permissions minimales explicites (`contents: read`), des `timeout-minutes`, et une concurrence annulant les runs obsolètes d'une même PR. Évaluer le pinning des actions par SHA, en conservant Dependabot pour les mises à jour.

**Critères d'acceptation.** Les permissions et timeouts sont visibles dans le YAML ; un nouveau push annule le run précédent de la PR ; la stratégie de pinning est documentée.

## CI-004 — Fiabiliser le smoke test Docker

- **Statut : ✅ Done**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/56

**Actions.** Remplacer le `sleep 8` fixe par une boucle bornée ; garantir le nettoyage avec un mécanisme exécuté aussi en cas d'échec ; afficher les logs du conteneur quand `/health` ne répond pas.

**Critères d'acceptation.** Le job échoue avec un diagnostic utile, ne laisse pas de conteneur actif et tolère un démarrage légèrement plus lent sans devenir flaky.

## CI-005 — Définir les déclencheurs hors pull request

- **Statut : ✅ Done**
- **Priorité : P2**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/57

**Décision retenue.** Trois déclencheurs :
- `pull_request` vers `main` — vérification avant merge
- `push` vers `main` — signal de santé après merge
- `workflow_dispatch` — exécution manuelle pour déboguer ou valider une branche

Pas de `schedule` : l'audit pip-audit peut échouer sur des dépendances réseau sans action possible, générant du bruit inutile.

**Actions.** Décider si la CI doit aussi tourner sur push vers `main`, manuellement, et/ou selon un calendrier pour détecter les dérives externes des dépendances et du build Docker.

**Critères d'acceptation.** Les déclencheurs retenus et leur objectif sont documentés ; la branche principale possède un signal de santé après merge.
