# handle-codex-review

Automatise le cycle de review Codex sur la PR courante en deux étapes.

## Étape 1 — Planification (phases 1-4)

```bash
uv run --locked python scripts/handle_codex_review.py
```

Identifie la PR, vérifie l'anti-boucle, récupère les remarques Codex et les affiche.
Le script s'arrête ici et enregistre l'état dans `.hcr_state.json`.

**Appliquer ensuite les corrections** via les outils natifs (Edit, Write…).

## Étape 2 — Exécution (phases 5-7)

```bash
uv run --locked python scripts/handle_codex_review.py --finish
```

Lance les tests, commite les fichiers modifiés depuis l'étape 1, pousse et relance Codex.

Voir [scripts/handle_codex_review.py](../../scripts/handle_codex_review.py) pour
la logique complète et les structures de données.

## Règle anti-boucle absolue

Ne jamais poster `@Codex review` si un commentaire `@Codex review` existe déjà
et est **plus récent** que le dernier commit sur la branche. Le script vérifie
cette condition automatiquement (phase 2 et phase 7).