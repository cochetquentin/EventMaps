# Branches et gouvernance Git

[Retour à l'index](README.md)

## Limite de l'audit

La copie auditée ne contient qu'une branche locale nommée `work`. Aucun remote Git n'est configuré, aucune référence distante n'est disponible et la commande `gh` n'est pas installée. Il est donc impossible de déterminer honnêtement quelles branches GitHub existent, sont mergées, protégées ou supprimables. Les suppressions doivent être décidées depuis GitHub, jamais à partir de cette seule copie.

L'historique local montre de nombreuses branches de fonctionnalités mergées via PR jusqu'à la PR #45. Cela justifie un inventaire des branches distantes et une politique de suppression automatique après merge.

## GIT-001 — Inventorier les branches GitHub

- **Statut : À faire**
- **Priorité : P1**
- **Suivi :** à renseigner

**Actions.** Exporter nom, date du dernier commit, auteur, PR associée, état de merge, protection et divergence avec la branche par défaut ; identifier les branches sans PR et celles déjà mergées.

**Critères d'acceptation.** L'inventaire est daté et revu par un mainteneur ; aucune branche n'est supprimée seulement parce qu'elle paraît ancienne.

## GIT-002 — Supprimer les branches mergées et abandonnées confirmées

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** GIT-001
- **Suivi :** à renseigner

**Actions.** Supprimer d'abord les branches entièrement mergées ; obtenir confirmation pour les branches non mergées ; conserver tags/releases et branches protégées.

**Critères d'acceptation.** Chaque suppression est traçable ; aucune branche contenant un travail unique n'est perdue.

## GIT-003 — Définir une stratégie de branches simple

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** CI-001, STAB-002
- **Suivi :** à renseigner

**Décision recommandée.** Utiliser une branche principale protégée et des branches courtes liées à une issue ; imposer PR + checks ; éviter une branche de développement longue tant qu'elle n'est pas nécessaire.

**Critères d'acceptation.** La stratégie, les conventions de nommage, les règles de merge et les exceptions sont documentées dans CONTRIBUTING.

## GIT-004 — Activer l'hygiène automatique après merge

- **Statut : À faire**
- **Priorité : P2**
- **Dépendances :** GIT-003
- **Suivi :** à renseigner

**Actions.** Activer la suppression automatique des branches de head après merge si compatible avec les pratiques ; définir une revue périodique des branches non mergées et des protections.

**Critères d'acceptation.** Les branches de PR mergées ne s'accumulent plus ; les exceptions sont explicites.
