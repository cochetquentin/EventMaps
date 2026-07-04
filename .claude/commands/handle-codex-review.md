# handle-codex-review

Automatise le cycle de review Codex ↔ Claude Code sur la PR courante.

---

## Prérequis

Conditions à réunir avant de lancer (vérification humaine — la commande ne les exécute pas) :
- gh authentifié et autorisé (`gh auth status`)
- remote Git configuré (`git remote -v`)
- PR ouverte sur la branche courante

---

## Phase 1 — Identifier la PR et le repo

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
PR_NUMBER=$(gh pr view --json number -q .number)
STATE=$(gh pr view --json state -q .state)
TITLE=$(gh pr view --json title -q .title)
HEAD_BRANCH=$(git branch --show-current)
```

Extraire depuis ces résultats : `REPO`, `PR_NUMBER`, `HEAD_BRANCH`, `STATE`.
Si `STATE != "OPEN"` → arrêter : "PR fermée ou mergée."
Vérifier que l'arbre de travail est propre — si `git status --porcelain` retourne une sortie
non vide → **STOP** : "Working tree non propre. Committez ou stashez vos changements avant
de lancer la commande."
Mémoriser ces variables pour toutes les étapes suivantes.

---

## Phase 2 — Protection anti-boucle

```bash
# T_TRIGGER : dernier commentaire dont le body est EXACTEMENT "@Codex review" (trim)
# Évite que des mentions incidentes (ex: "j'ai posté @Codex review hier") deviennent le trigger
T_TRIGGER=$(gh api --paginate "repos/${REPO}/issues/${PR_NUMBER}/comments" \
  --jq '.[] | select(.body | ltrimstr("\n") | rtrimstr("\n") | ltrimstr("\r") | rtrimstr("\r") | ascii_downcase | . == "@codex review") | .created_at' | tail -1)

# T_CODEX : dernière réponse Codex parmi les 3 endpoints (reviews formelles, inline, issue comments)
T_CODEX_R=$(gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/reviews" \
  --jq '.[] | select(.user.login == "chatgpt-codex-connector[bot]") | .submitted_at' | tail -1)
T_CODEX_C=$(gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/comments" \
  --jq '.[] | select(.user.login == "chatgpt-codex-connector[bot]") | .created_at' | tail -1)
T_CODEX_I=$(gh api --paginate "repos/${REPO}/issues/${PR_NUMBER}/comments" \
  --jq '.[] | select(.user.login == "chatgpt-codex-connector[bot]") | .created_at' | tail -1)

# T_COMMIT : via l'API commits sur le headRefOid (pas de limite 100 commits)
HEAD_SHA=$(gh pr view --json headRefOid -q .headRefOid)
T_COMMIT=$(gh api "repos/${REPO}/commits/${HEAD_SHA}" --jq '.commit.committer.date' 2>/dev/null \
  || git log -1 --format="%cI")

# Normaliser en epoch UTC pour comparaison cross-timezone (GitHub = UTC Z, git = offset local)
T_TRIGGER_E=$(uv run python -c "
from datetime import datetime,timezone
s='$T_TRIGGER'
print(int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()) if s else 0)
")
T_CODEX_E=$(uv run python -c "
from datetime import datetime,timezone
def e(s): return int(datetime.fromisoformat(s.strip().replace('Z','+00:00')).timestamp()) if s.strip() else 0
print(max(e('$T_CODEX_R'), e('$T_CODEX_C'), e('$T_CODEX_I')))
")
T_COMMIT_E=$(uv run python -c "
from datetime import datetime,timezone
s='$T_COMMIT'
print(int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()))
")
```

Logique :
1. `T_TRIGGER_E` = epoch UTC du dernier commentaire contenant `@Codex review`.
2. `T_CODEX_E` = epoch UTC de la dernière réponse Codex (reviews formelles **+ inline + issue comments**).
3. `T_COMMIT_E` = epoch UTC du dernier commit du PR (remote).
4. Si `T_TRIGGER_E > 0` ET `T_TRIGGER_E > T_COMMIT_E` ET `T_CODEX_E < T_TRIGGER_E` → **STOP** :
   "Anti-boucle : `@Codex review` déjà posté après le dernier commit et Codex n'a pas encore répondu."
5. Sinon → continuer.

---

## Phase 3 — Récupérer les remarques Codex

```bash
# --paginate --jq applique le filtre à chaque page et concatène les résultats
# Filtrer sur le cycle courant uniquement (depuis T_TRIGGER) pour éviter de retraiter
# des remarques déjà corrigées dans des cycles précédents.
gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/reviews" \
  --jq ".[] | select(.user.login == \"chatgpt-codex-connector[bot]\") | select(.submitted_at > \"${T_TRIGGER}\")"
gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/comments" \
  --jq ".[] | select(.user.login == \"chatgpt-codex-connector[bot]\") | select(.created_at > \"${T_TRIGGER}\")"
gh api --paginate "repos/${REPO}/issues/${PR_NUMBER}/comments" \
  --jq ".[] | select(.user.login == \"chatgpt-codex-connector[bot]\") | select(.created_at > \"${T_TRIGGER}\")"
```

Filtrer uniquement les objets dont `user.login` est exactement `chatgpt-codex-connector[bot]`
(identité exacte du bot Codex — ne pas utiliser un substring match pour éviter l'usurpation).
Exclure les `body` vides ou contenant seulement `@Codex review`.
Seules les remarques postées **après `T_TRIGGER`** sont traitées (cycle courant).

Classer par priorité :
1. Reviews formelles avec state `CHANGES_REQUESTED`
2. Commentaires inline (associés à un fichier:ligne)
3. Commentaires généraux

Si aucune remarque trouvée → afficher "Aucune remarque Codex sur cette PR." et s'arrêter.

Sinon, **afficher un résumé des points à traiter** avant toute modification.

---

## Phase 4 — Appliquer les corrections

L'arbre est garanti propre (vérifié en Phase 1) : toute modification présente ici est issue du workflow.

Pour chaque remarque (dans l'ordre de priorité) :

1. Lire le fichier concerné pour comprendre le contexte actuel.
2. **Évaluer** : la remarque est-elle valide ? Déjà corrigée par un commit précédent ?
3. Si **valide** → appliquer la correction, noter : `[APPLIQUÉ] fichier:ligne — description`.
4. Si **invalide / non applicable** → ignorer avec justification courte.

Ne pas modifier les tests pour faire passer une règle de coverage — corriger le code de production.

---

## Phase 5 — Tests

```bash
uv run --locked python -m pytest --cov=. --cov-fail-under=80 tests/ -v
```

- **Succès** → continuer.
- **Échec** → diagnostiquer, corriger, relancer (max 2 tentatives).
  Si toujours KO après 2 tentatives : annuler les changements de ce cycle :
  - `git checkout -- <fichiers trackés modifiés dans ce cycle>`
  - `rm <fichiers non-trackés créés dans ce cycle>`
  noter les corrections non appliquées, continuer sans elles.
- **Coverage < 80%** → ajouter des tests pour le code modifié.

---

## Phase 6 — Commit et push

```bash
git add <fichiers modifiés spécifiquement>
STAGED=$(git diff --cached --name-only)
```

Si `STAGED` est vide → ne pas commiter, **ne pas relancer Codex** (même SHA = review inutile).
Afficher le résumé final avec `@Codex review relancé : NON (aucun diff stagé)` et s'arrêter.

Sinon :

```bash
git commit -m "fix: appliquer corrections Codex — {résumé 1 ligne}"
```

Puis tenter le push :

```bash
git push
```

Si **`git push` échoue** → noter `Push : ÉCHEC` dans le résumé final, ne pas passer en Phase 7
(même SHA en remote = review inutile + risque de boucle).
Afficher : "Commit local préservé ({sha}). Récupération : `git push` pour retenter, ou
`git reset HEAD~1` pour annuler et réappliquer lors du prochain cycle."
S'arrêter.

---

## Phase 7 — Relancer Codex

Re-vérifier l'anti-boucle (précaution post-push) :

```bash
HEAD_SHA=$(gh pr view --json headRefOid -q .headRefOid)
T_COMMIT=$(gh api "repos/${REPO}/commits/${HEAD_SHA}" --jq '.commit.committer.date' 2>/dev/null \
  || git log -1 --format="%cI")
T_TRIGGER=$(gh api --paginate "repos/${REPO}/issues/${PR_NUMBER}/comments" \
  --jq '.[] | select(.body | ltrimstr("\n") | rtrimstr("\n") | ltrimstr("\r") | rtrimstr("\r") | ascii_downcase | . == "@codex review") | .created_at' | tail -1)
T_COMMIT_E=$(uv run python -c "from datetime import datetime,timezone; s='$T_COMMIT'; print(int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()))")
T_TRIGGER_E=$(uv run python -c "from datetime import datetime,timezone; s='$T_TRIGGER'; print(int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()) if s else 0)")
```

Confirmer que `T_COMMIT_E > T_TRIGGER_E` (ou `T_TRIGGER_E == 0`), puis :

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
Push : OK | SKIPPED | ÉCHEC

@Codex review relancé : OUI / NON (raison si NON)
```
