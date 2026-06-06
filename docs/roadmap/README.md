# Roadmap de stabilisation EventMaps

Cette roadmap transforme l'audit du dépôt en tâches indépendantes, priorisées et vérifiables. Elle ne contient volontairement aucune nouvelle fonctionnalité produit.

## Comment l'utiliser

- Une tâche est l'unité de travail : elle possède un identifiant stable, un statut, une priorité, un résultat attendu et des critères d'acceptation.
- Statuts autorisés : **À faire**, **En cours**, **Terminé**.
- Lorsqu'une tâche démarre, remplacer son statut par **En cours** dans son fichier. Lorsqu'elle est validée, passer à **Terminé** et ajouter le lien de la PR ou du commit dans la ligne `Suivi`.
- Une PR de stabilisation devrait traiter une seule tâche, ou un petit groupe explicitement indiqué comme lié.
- Les constats datés décrivent l'état observé le **6 juin 2026** ; ils doivent être réévalués si le dépôt évolue.

## Priorités

| Priorité | Interprétation |
|---|---|
| **P0** | Prérequis immédiat de la phase de stabilisation |
| **P1** | Risque important pour la fiabilité ou la maintenabilité |
| **P2** | Amélioration utile après les risques P1 |
| **P3** | Opportunité non bloquante |

## Vue d'ensemble

| Domaine | Document | Tâches à faire | En cours | Terminées |
|---|---|---:|---:|---:|
| Pilotage | [Plan d'exécution](00-plan-execution.md) | 4 | 0 | 1 |
| CI/CD | [CI/CD et contrôles qualité](01-ci-cd.md) | 5 | 0 | 0 |
| Tests | [Fixtures et stratégie de test](02-fixtures-tests.md) | 7 | 0 | 0 |
| Outils internes | [Configuration locale et review Codex](03-outils-internes.md) | 4 | 0 | 1 |
| Structure | [Arborescence et maintenabilité](04-arborescence.md) | 6 | 0 | 0 |
| Documentation | [Documentation](05-documentation.md) | 5 | 0 | 0 |
| GitHub | [Branches et gouvernance Git](06-git-gouvernance.md) | 4 | 0 | 0 |

## Ordre recommandé

1. **Geler les fonctionnalités et établir la baseline** : [STAB-001 à STAB-003](00-plan-execution.md).
2. **Rendre les contrôles fiables et lisibles** : [CI-001 à CI-005](01-ci-cd.md).
3. **Sécuriser le contrat des scrapers avec des pages réelles** : [TEST-001 à TEST-007](02-fixtures-tests.md).
4. **Simplifier l'automatisation de review sans réintroduire de validations manuelles** : [TOOL-002 à TOOL-005](03-outils-internes.md).
5. **Nettoyer l'arborescence et remettre la documentation en cohérence** : [TREE-001 à TREE-006](04-arborescence.md), puis [DOC-001 à DOC-005](05-documentation.md).
6. **Finaliser la gouvernance GitHub et clôturer la stabilisation** : [GIT-001 à GIT-004](06-git-gouvernance.md), puis STAB-004.

## Constats majeurs de l'audit

- La baseline locale est saine : **309 tests Python** passent avec **95,24 %** de couverture, **58 tests frontend** passent, et Ruff ne signale rien.
- La CI est regroupée dans un seul workflow nommé `CI`. Ses jobs frontend et Docker sont explicites, mais le job backend générique `Tests` mélange audit de dépendances, lint, format et pytest.
- Les fixtures Tokyo Cheapo et Hanabi Walker sont de très petits HTML manifestement reconstruits ; elles ne représentent pas suffisamment les pages réelles. Time Out Tokyo possède déjà plusieurs captures volumineuses qui semblent réelles, mais leur provenance n'est pas documentée.
- `.claude/settings.local.json` n'est plus versionné et est ignoré. Sa dernière version historique contenait des permissions ponctuelles et obsolètes ; elle ne doit pas être restaurée telle quelle.
- `/handle-codex-review` est décrit par un document de 201 lignes qui confie une orchestration complexe et un rollback fragile à l'agent. Une commande testable doit remplacer cette logique textuelle.
- Le README annonce encore `247 tests Python`, alors que la baseline en exécute 309. `docs/ARCHITECTURE.md` ne documente pas tous les endpoints actuels, notamment les exports ICS.
- L'ancien `REPO_ROADMAP_AUDIT.md` monolithique, long de 1 328 lignes et partiellement obsolète, a été remplacé par le présent ensemble modulaire.
- L'audit des branches GitHub n'a pas pu être réalisé depuis cette copie : aucun remote Git n'est configuré, aucune référence distante n'est disponible et `gh` n'est pas installé.
