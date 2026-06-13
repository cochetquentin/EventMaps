# handle-codex-review

Lance le cycle de review Codex sur la PR courante.

```bash
uv run --locked python scripts/handle_codex_review.py
```

Le script orchestre les 7 phases : identification PR, anti-boucle, récupération
des remarques Codex, affichage des corrections à appliquer, tests, commit/push,
relance Codex.

Voir [scripts/handle_codex_review.py](../../scripts/handle_codex_review.py) pour
la logique complète et les structures de données.

## Règle anti-boucle absolue

Ne jamais poster `@Codex review` si un commentaire `@Codex review` existe déjà
et est **plus récent** que le dernier commit sur la branche. Le script vérifie
cette condition automatiquement (phase 2 et phase 7).