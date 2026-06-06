# Roadmap de stabilisation EventMaps

Cette roadmap transforme l'audit du dépôt en tâches indépendantes, priorisées et vérifiables. Elle ne contient volontairement aucune nouvelle fonctionnalité produit.

## Comment l'utiliser

- Une tâche est l'unité de travail : elle possède un identifiant stable, un statut, une priorité, un résultat attendu et des critères d'acceptation.
- Statuts autorisés : **À faire**, **En cours**, **Terminé**.
- Lorsqu'une tâche démarre, remplacer son statut par **En cours** dans son fichier. Lorsqu'elle est validée, passer à **Terminé** et ajouter le lien de la PR ou du commit dans la ligne `Suivi`. L'index ne duplique volontairement pas les compteurs de statuts : les fichiers thématiques sont la source d'autorité.
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

| Domaine | Document | Périmètre |
|---|---|---|
| Pilotage | [Plan d'exécution](00-plan-execution.md) | Gel, baseline, suivi et sortie de stabilisation |
| CI/CD | [CI/CD et contrôles qualité](01-ci-cd.md) | Checks, sécurité du workflow et smoke test |
| Tests | [Fixtures et stratégie de test](02-fixtures-tests.md) | Corpus HTML réels et contrats des scrapers |
| Outils internes | [Configuration locale et review Codex](03-outils-internes.md) | Permissions locales et automatisation de review |
| Structure | [Arborescence et maintenabilité](04-arborescence.md) | Nettoyage et frontières internes |
| Documentation | [Documentation](05-documentation.md) | README, architecture et documentation agent |
| GitHub | [Branches et gouvernance Git](06-git-gouvernance.md) | Inventaire, suppression et stratégie de branches |
| Constats hérités | [Registre des constats hérités](07-registre-constats.md) | Traçabilité de tous les constats techniques non terminés de l'ancien audit |
| Backlog produit différé | [Archive du backlog produit](08-backlog-produit-differe.md) | Décisions produit conservées hors stabilisation |

## Ordre recommandé compatible avec les dépendances

Chaque ligne ne doit démarrer qu'après les dépendances déclarées dans les tâches concernées.

1. **Démarrer la stabilisation** : STAB-001 et STAB-003. STAB-005 est déjà terminé.
2. **Stabiliser les noms des checks** : CI-001 et CI-002.
3. **Configurer la protection de branche** : STAB-002, désormais débloqué par CI-001 et CI-002 ; poursuivre avec CI-003 à CI-005.
4. **Renforcer les contrats des scrapers** : TEST-001 à TEST-007 dans l'ordre de leurs dépendances.
5. **Simplifier le cœur de l'automatisation de review** : TOOL-002 à TOOL-004.
6. **Traiter la structure, la documentation et les constats hérités** : TREE-001 à TREE-006, DOC-001 à DOC-004, et les tâches actives de [LEGACY-001 à LEGACY-011](07-registre-constats.md), selon leurs priorités.
7. **Finaliser la documentation de l'outil** : TOOL-005, uniquement après TOOL-003 et DOC-003 ; puis DOC-005.
8. **Nettoyer et gouverner les branches** : GIT-001 et GIT-002 ; GIT-003 après CI-001 et STAB-002 ; enfin GIT-004.
9. **Clôturer la stabilisation** : STAB-004 après résolution ou acceptation explicite de toutes les autres tâches P0/P1.

## Constats majeurs de l'audit

- La baseline locale est saine : **309 tests Python** passent avec **95,24 %** de couverture, **58 tests frontend** passent, et Ruff ne signale rien.
- La CI est regroupée dans un seul workflow nommé `CI`. Ses jobs frontend et Docker sont explicites, mais le job backend générique `Tests` mélange audit de dépendances, lint, format et pytest.
- Les fixtures Tokyo Cheapo et Hanabi Walker sont de très petits HTML manifestement reconstruits ; elles ne représentent pas suffisamment les pages réelles. Time Out Tokyo possède déjà plusieurs captures volumineuses qui semblent réelles, mais leur provenance n'est pas documentée.
- `.claude/settings.local.json` n'est plus versionné et est ignoré. Sa dernière version historique contenait des permissions ponctuelles et obsolètes ; elle ne doit pas être restaurée telle quelle.
- `/handle-codex-review` est décrit par un document de 201 lignes qui confie une orchestration complexe et un rollback fragile à l'agent. Une commande testable doit remplacer cette logique textuelle.
- Le README annonce encore `247 tests Python`, alors que la baseline en exécute 309. `docs/ARCHITECTURE.md` ne documente pas tous les endpoints actuels, notamment les exports ICS.
- L'ancien `REPO_ROADMAP_AUDIT.md` monolithique, long de 1 328 lignes et partiellement obsolète, a été remplacé par le présent ensemble modulaire ; ses propositions produit non terminées sont conservées dans une archive différée, hors du périmètre de stabilisation.
- L'audit des branches GitHub n'a pas pu être réalisé depuis cette copie : aucun remote Git n'est configuré, aucune référence distante n'est disponible et `gh` n'est pas installé.
