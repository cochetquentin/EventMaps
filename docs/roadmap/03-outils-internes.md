# Configuration locale et review Codex

[Retour à l'index](README.md)

## État observé

- `.claude/settings.local.json` est ignoré et absent de la branche courante.
- La dernière version trouvée dans l'historique autorisait surtout des commandes ponctuelles et obsolètes : suppressions de fichiers précis, chemins Windows locaux, `grep`, `iconv`, `uv add` et diverses variantes Git. Elle ne doit pas être restaurée.
- `.claude/commands/handle-codex-review.md` compte 201 lignes. Il demande à l'agent d'identifier la PR, comparer plusieurs horodatages, agréger trois API GitHub, modifier le code, gérer un rollback sélectif, tester, commit, push et relancer Codex.
- Cette logique est difficile à tester, fragile face aux noms de fichiers avec espaces, à l'interpolation shell et aux échecs intermédiaires. Les règles importantes sont dupliquées dans `CLAUDE.md`.

## TOOL-001 — Retirer l'ancienne configuration locale du contrat du dépôt

- **Statut : Terminé**
- **Priorité : P0**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/78

**Résultat.** Le fichier local n'est ni versionné ni requis par le fonctionnement de l'application. Son entrée `.gitignore` est appropriée.

## TOOL-002 — Définir une politique minimale de permissions Claude

- **Statut : Terminé**
- **Priorité : P0**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/51

**Contrainte impérative.** `/handle-codex-review` doit continuer à fonctionner sans validation manuelle pour chaque sous-commande.

**Décision recommandée.** Autoriser une seule commande de haut niveau, versionnée et testée, plutôt qu'une longue liste de commandes shell générales ou destructrices. Garder les secrets et préférences propres au poste dans `settings.local.json`.

**Critères d'acceptation.** La politique distingue les permissions partagées des préférences locales ; elle définit la commande de haut niveau qui pourra être autorisée après TOOL-003 ; la proposition ne contient ni chemins personnels, ni suppressions ponctuelles, ni jokers plus larges que nécessaire.

**Résultat.** `.claude/settings.json` créé et versionné. Politique minimale : uv (run, sync, lock), gh (PR view/list/comment, issue comment, API PR/issues/commits), git (status, log, diff, add, commit, push, stash, checkout, branch, rev-parse). Opérations destructrices (force push, git clean, reset --hard) explicitement refusées. Slot TOOL-003 documenté via clé `_comment_tool003_slot`.

## TOOL-003 — Extraire l'orchestration de review dans un programme testable

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** TOOL-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/62

**Actions.** Remplacer la majorité du document de commande par un script/module versionné ; isoler l'accès GitHub, la sélection des remarques, l'anti-boucle et le résumé ; utiliser des structures de données plutôt que des variables shell interpolées.

**Critères d'acceptation.** Le fichier de commande devient un point d'entrée court ; la logique de décision possède des tests sans appel GitHub réel ; les erreurs sont explicites et n'entraînent ni push ni commentaire involontaire ; une installation neuve peut autoriser cette seule commande de haut niveau et exécuter le cycle sans prompts répétitifs.

## TOOL-004 — Simplifier la stratégie de modification, commit et rollback

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** TOOL-003
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/63

**Actions.** Refuser proprement un working tree sale ou utiliser une stratégie Git sûre et documentée ; éviter de reconstruire des listes de fichiers avec `awk` ; rendre commit, push et relance Codex explicitement conditionnels au succès des tests et à la présence d'un diff.

**Critères d'acceptation.** Des tests couvrent au minimum : arbre sale, aucune remarque, tests en échec, aucun diff, push en échec, commentaire déjà présent et réponse Codex reçue.

## TOOL-005 — Centraliser la documentation de la commande

- **Statut : À faire**
- **Priorité : P2**
- **Dépendances :** TOOL-003, DOC-003
- **Suivi :** à renseigner

**Actions.** Garder dans `CLAUDE.md` uniquement le lien et les garde-fous essentiels ; placer le comportement détaillé près du programme et de ses tests ; documenter les prérequis `gh`, authentification et remote Git.

**Critères d'acceptation.** Une règle n'a qu'une source d'autorité ; les prérequis et modes d'échec sont découvrables.
