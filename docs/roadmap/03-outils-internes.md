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
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/51 — PR : https://github.com/cochetquentin/EventMaps/pull/92

**Contrainte impérative.** `/handle-codex-review` doit continuer à fonctionner sans validation manuelle pour chaque sous-commande.

**Décision recommandée.** Autoriser une seule commande de haut niveau, versionnée et testée, plutôt qu'une longue liste de commandes shell générales ou destructrices. Garder les secrets et préférences propres au poste dans `settings.local.json`.

**Critères d'acceptation.** La politique distingue les permissions partagées des préférences locales ; elle définit la commande de haut niveau qui pourra être autorisée après TOOL-003 ; la proposition ne contient ni chemins personnels, ni suppressions ponctuelles, ni jokers plus larges que nécessaire.

**Résultat.** `.claude/settings.json` créé et versionné. Politique minimale : uv (run, sync, lock), gh (PR view/list/comment, issue comment, API PR/issues/commits), git (status, log, diff, add, commit, push, stash, checkout, branch, rev-parse). Opérations destructrices (force push, git clean, reset --hard) explicitement refusées. La permission `Bash(uv run python -c*)` est maintenue pour les snippets de normalisation d'horodatage utilisés par `/handle-codex-review`.

## TOOL-003 — Extraire l'orchestration de review dans un programme testable

- **Statut : Abandonné**
- **Priorité : P1**
- **Dépendances :** TOOL-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/62 — PR #93 fermée

**Raison d'abandon.** La commande Claude native fonctionne correctement. L'extraction dans un script Python de ~1000 lignes a généré une complexité disproportionnée (10+ cycles Codex, edge cases hypothétiques) pour une valeur marginale. On reste sur `.claude/commands/handle-codex-review.md`.

## TOOL-004 — Améliorer la robustesse de la commande handle-codex-review

- **Statut : Terminé**
- **Priorité : P1**
- **Dépendances :** TOOL-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/63 — PR : https://github.com/cochetquentin/EventMaps/pull/101

**Actions.** Dans `.claude/commands/handle-codex-review.md` : refuser proprement un working tree sale ; éviter les reconstructions de listes de fichiers avec `awk` ; rendre commit, push et relance Codex explicitement conditionnels au succès des tests et à la présence d'un diff.

**Critères d'acceptation.** La commande gère correctement : arbre sale, aucune remarque, tests en échec, aucun diff, push en échec, commentaire déjà présent et réponse Codex reçue.

## TOOL-005 — Nettoyer la duplication entre CLAUDE.md et la commande

- **Statut : Terminé**
- **Priorité : P2**
- **Dépendances :** TOOL-002
- **Suivi :** PR : https://github.com/cochetquentin/EventMaps/pull/101

**Actions.** Garder dans `CLAUDE.md` uniquement le lien vers la commande et la règle anti-boucle absolue ; placer le comportement détaillé et les prérequis (`gh`, authentification, remote Git) dans `handle-codex-review.md`.

**Critères d'acceptation.** Une règle n'a qu'une source d'autorité ; les prérequis et modes d'échec sont découvrables depuis la commande.

## TOOL-006 — Publier un compte-rendu des remarques ignorées avant de relancer Codex

- **Statut : Terminé**
- **Priorité : P2**
- **Dépendances :** TOOL-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/102 — PR : https://github.com/cochetquentin/EventMaps/pull/103

**Contexte.** Lorsque le cycle ignore certaines remarques Codex, il relance immédiatement `@Codex review` sans expliquer pourquoi. Codex les ressort au cycle suivant et l'historique de la PR ne permet pas de distinguer un point délibérément ignoré d'un point oublié.

**Actions.** Dans `.claude/commands/handle-codex-review.md`, juste avant de poster `@Codex review`, publier un commentaire GitHub via `gh pr comment` listant chaque remarque ignorée avec sa justification. Ne poster ce commentaire que si les deux conditions sont réunies : au moins une remarque est ignorée ET au moins une correction a été appliquée et pushée (c'est-à-dire que `@Codex review` est effectivement relancé). Quand toutes les remarques sont ignorées, aucun diff n'est produit, Codex n'est pas relancé et ce commentaire n'est pas créé.

**Format suggéré du commentaire :**

```
## Remarques Codex ignorées — cycle N

| Remarque | Raison |
|---|---|
| `fichier:ligne` — titre court | justification |
| ... | ... |
```

**Critères d'acceptation.** Si au moins une remarque est ignorée ET que Codex est relancé, un commentaire est posté avant `@Codex review` ; le commentaire liste chaque point avec une raison non vide ; si aucune remarque n'est ignorée, ou si le cycle ne produit aucun diff (donc ne relance pas Codex), aucun commentaire supplémentaire n'est créé.
