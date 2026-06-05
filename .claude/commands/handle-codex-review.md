# handle-codex-review

Automatise le cycle de review Codex ↔ Claude Code sur la PR courante.

---

## Phase 1 — Identifier la PR et le repo

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
PR_INFO=$(gh pr view --json number,headRefName,title,state)
PR_NUMBER=$(echo "$PR_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['number'])")
STATE=$(echo "$PR_INFO" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['state'])")
HEAD_BRANCH=$(git branch --show-current)
```

Extraire depuis ces résultats : `REPO`, `PR_NUMBER`, `HEAD_BRANCH`, `STATE`.
Si `STATE != "OPEN"` → arrêter : "PR fermée ou mergée."
Mémoriser ces variables pour toutes les étapes suivantes.

---

## Phase 2 — Protection anti-boucle

```bash
gh api --paginate --slurp "repos/${REPO}/issues/${PR_NUMBER}/comments"
gh api --paginate --slurp "repos/${REPO}/pulls/${PR_NUMBER}/reviews"
git log -1 --format="%cI"
```

Logique :
1. Dans les issue comments (paginés), trouver le **dernier** dont le `body` contient `@Codex review` (insensible à la casse) → `T_trigger`.
2. Dans les reviews formelles, trouver le `submitted_at` de la **dernière** review de l'identité Codex exacte (`chatgpt-codex-connector[bot]`) → `T_codex_review`.
3. Si `T_trigger` existe ET `T_trigger > T_commit` ET (`T_codex_review` est absent ou `T_codex_review < T_trigger`) → **STOP** :
   "Anti-boucle : `@Codex review` déjà posté après le dernier commit et Codex n'a pas encore répondu."
4. Sinon → continuer.

---

## Phase 3 — Récupérer les remarques Codex

```bash
gh api --paginate --slurp "repos/${REPO}/pulls/${PR_NUMBER}/reviews"
gh api --paginate --slurp "repos/${REPO}/pulls/${PR_NUMBER}/comments"
gh api --paginate --slurp "repos/${REPO}/issues/${PR_NUMBER}/comments"
```

Filtrer uniquement les objets dont `user.login` est exactement `chatgpt-codex-connector[bot]`
(identité exacte du bot Codex — ne pas utiliser un substring match pour éviter l'usurpation).
Exclure les `body` vides ou contenant seulement `@Codex review`.

Classer par priorité :
1. Reviews formelles avec state `CHANGES_REQUESTED`
2. Commentaires inline (associés à un fichier:ligne)
3. Commentaires généraux

Si aucune remarque trouvée → afficher "Aucune remarque Codex sur cette PR." et s'arrêter.

Sinon, **afficher un résumé des points à traiter** avant toute modification.

---

## Phase 4 — Appliquer les corrections

Pour chaque remarque (dans l'ordre de priorité) :

1. Lire le fichier concerné pour comprendre le contexte actuel.
2. **Évaluer** : la remarque est-elle valide ? Déjà corrigée par un commit précédent ?
3. Si **valide** → appliquer la correction, noter : `[APPLIQUÉ] fichier:ligne — description`.
4. Si **invalide / non applicable** → ignorer avec justification courte.

Ne pas modifier les tests pour faire passer une règle de coverage — corriger le code de production.

---

## Phase 5 — Tests

```bash
uv run pytest --cov=. --cov-fail-under=80 tests/ -v
```

- **Succès** → continuer.
- **Échec** → diagnostiquer, corriger, relancer (max 2 tentatives).
  Si toujours KO après 2 tentatives : vérifier d'abord `git status` pour s'assurer
  qu'il n'y a pas de modifications non liées ; annuler uniquement les fichiers
  introduits par ce workflow (`git checkout -- <fichiers modifiés dans ce cycle>`),
  noter les corrections non appliquées, continuer sans elles.
- **Coverage < 80%** → ajouter des tests pour le code modifié.

---

## Phase 6 — Commit et push

Si des modifications ont été appliquées :

```bash
git status
git add <fichiers modifiés spécifiquement>
git commit -m "fix: appliquer corrections Codex — {résumé 1 ligne}"
git push
```

Si **aucune modification** → ne pas commiter. Passer en Phase 7 avec note explicative.

---

## Phase 7 — Relancer Codex

Re-vérifier l'anti-boucle (précaution post-push) :

```bash
git log -1 --format="%cI"
gh api --paginate --slurp "repos/${REPO}/issues/${PR_NUMBER}/comments"
```

Confirmer que `T_commit > T_comment` (ou pas de commentaire `@Codex review`), puis :

```bash
gh pr comment "${PR_NUMBER}" --body "@Codex review"
```

---

## Résumé de sortie

Afficher à la fin :

```
## /handle-codex-review — Résultat

PR : #{PR_NUMBER} — {title}
Branche : {HEAD_BRANCH}

Remarques Codex : N trouvées
Corrections : X appliquées, Y ignorées
Tests : PASS | FAIL (coverage : Z%)
Commit : {sha} — "{message}"
Push : OK | SKIPPED

@Codex review relancé : OUI / NON (raison si NON)
```
