# Plan d'exécution de la stabilisation

[Retour à l'index](README.md)

## Baseline observée le 6 juin 2026

| Contrôle | Résultat |
|---|---|
| Tests Python | 309 réussis ; couverture totale 95,24 % ; seuil 80 % respecté |
| Ruff lint | Réussi |
| Ruff format | Réussi |
| Tests frontend | 58 réussis dans 2 fichiers |
| Audit Python | Non vérifiable localement : accès réseau à PyPI bloqué par le proxy |
| Branches GitHub | Non vérifiables : aucun remote, aucune référence distante et commande `gh` absente |

## STAB-001 — Geler les évolutions produit

- **Statut : À faire**
- **Priorité : P0**
- **Suivi :** à renseigner

**Objectif.** Empêcher de nouvelles fonctionnalités de déplacer la cible pendant la stabilisation.

**Actions.** Définir une date de début/fin, n'autoriser que les corrections, la dette technique, les tests, la documentation et l'exploitation ; étiqueter ou repousser les demandes produit.

**Critères d'acceptation.** La règle est visible dans le processus de contribution et les PR actives sont classées selon cette règle.

## STAB-002 — Définir les checks obligatoires de la branche principale

- **Statut : À faire**
- **Priorité : P0**
- **Dépendances :** CI-001, CI-002
- **Suivi :** à renseigner

**Objectif.** Faire de la baseline de qualité une règle de merge explicite.

**Critères d'acceptation.** Les noms définitifs des checks sont documentés ; la protection de branche les exige ; aucun nom de check générique ou instable n'est requis.

## STAB-003 — Créer un tableau de suivi à partir de cette roadmap

- **Statut : À faire**
- **Priorité : P1**
- **Suivi :** à renseigner

**Objectif.** Rendre l'avancement visible sans dupliquer le détail des tâches.

**Actions.** Créer les issues depuis les identifiants de cette roadmap, conserver l'identifiant dans le titre, et mettre à jour le statut et le lien `Suivi` dans le fichier concerné lors de chaque PR.

**Critères d'acceptation.** Chaque tâche P0/P1 possède une issue assignable et un statut identique entre GitHub et la roadmap.

## STAB-004 — Revue de sortie de stabilisation

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** toutes les tâches P0/P1
- **Suivi :** à renseigner

**Objectif.** Décider explicitement si la base est assez saine pour reprendre les évolutions.

**Critères d'acceptation.** Tous les P0/P1 sont terminés ou acceptés comme risques résiduels documentés ; CI verte ; tests des scrapers basés sur des fixtures réelles ; documentation vérifiée ; branches nettoyées.

## STAB-005 — Produire l'audit modulaire initial

- **Statut : Terminé**
- **Priorité : P0**
- **Suivi :** cette roadmap

**Résultat.** L'audit monolithique précédent a été remplacé par des documents thématiques et des tâches indépendantes avec statuts, priorités et critères d'acceptation.
