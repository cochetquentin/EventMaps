# Branches et gouvernance Git

[Retour à l'index](README.md)

## Limite de l'audit

La copie auditée ne contient qu'une branche locale nommée `work`. Aucun remote Git n'est configuré, aucune référence distante n'est disponible et la commande `gh` n'est pas installée. Il est donc impossible de déterminer honnêtement quelles branches GitHub existent, sont mergées, protégées ou supprimables. Les suppressions doivent être décidées depuis GitHub, jamais à partir de cette seule copie.

L'historique local montre de nombreuses branches de fonctionnalités mergées via PR jusqu'à la PR #45. Cela justifie un inventaire des branches distantes et une politique de suppression automatique après merge.

## GIT-001 — Inventorier les branches GitHub

- **Statut : Terminé**
- **Priorité : P1**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/69
- **Livrable :** [docs/branches-inventory-2026-07-05.md](../branches-inventory-2026-07-05.md)

**Actions.** Exporter nom, date du dernier commit, auteur, PR associée, état de merge, protection et divergence avec la branche par défaut ; identifier les branches sans PR et celles déjà mergées.

**Résultat (2026-07-05).** 56 branches non-main auditées via `gh api` :
- 48 `behind` main (PR mergées) → supprimées par GIT-002
- 7 `diverged` avec PR ouverte (Dependabot actif) → conservées
- 1 `diverged` avec PR fermée (`feat/tool-003`, TOOL-003 abandonné) → supprimée par GIT-002

**Critères d'acceptation.** L'inventaire est daté et revu par un mainteneur ; aucune branche n'est supprimée seulement parce qu'elle paraît ancienne.

## GIT-002 — Supprimer les branches mergées et abandonnées confirmées

- **Statut : Terminé**
- **Priorité : P1**
- **Dépendances :** GIT-001
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/70

**Actions.** Supprimer d'abord les branches entièrement mergées ; obtenir confirmation pour les branches non mergées ; conserver tags/releases et branches protégées.

**Résultat (2026-07-05).** 49 branches supprimées (48 `behind` + `feat/tool-003` confirmée), 0 erreur.
Les 7 branches Dependabot avec PR ouvertes ont été conservées.

**Critères d'acceptation.** Chaque suppression est traçable ; aucune branche contenant un travail unique n'est perdue.

## GIT-003 — Définir une stratégie de branches simple

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** CI-001, STAB-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/71

**Décision recommandée.** Utiliser une branche principale protégée et des branches courtes liées à une issue ; imposer PR + checks ; éviter une branche de développement longue tant qu'elle n'est pas nécessaire.

**Critères d'acceptation.** La stratégie, les conventions de nommage, les règles de merge et les exceptions sont documentées dans CONTRIBUTING.

## GIT-004 — Activer l'hygiène automatique après merge

- **Statut : À faire**
- **Priorité : P2**
- **Dépendances :** GIT-003
- **Suivi :** à renseigner

**Actions.** Activer la suppression automatique des branches de head après merge si compatible avec les pratiques ; définir une revue périodique des branches non mergées et des protections.

**Critères d'acceptation.** Les branches de PR mergées ne s'accumulent plus ; les exceptions sont explicites.
