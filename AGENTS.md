# EventMaps — Instructions Codex

## Stack et commandes essentielles

- **Langage** : Python 3.13, géré par `uv`
- **Tests** : `uv run pytest --cov=. --cov-fail-under=80 tests/ -v`
- **Serveur dev** : `uv run uvicorn api.app:app --reload`
- Toujours `uv run` — jamais `python` directement

## Workflow de review Codex

Ce repo utilise Codex (bot OpenAI) pour des reviews automatiques sur les PRs.

La commande `/handle-codex-review` automatise le cycle complet :
1. Récupérer les remarques Codex sur la PR courante
2. Analyser et appliquer les corrections valides
3. Lancer les tests (`uv run pytest`)
4. Commiter et pusher les correctifs
5. Relancer Codex avec `@Codex review`

Voir `.claude/commands/handle-codex-review.md` pour les instructions d'exécution.

### Règle anti-boucle absolue

Ne jamais poster `@Codex review` si un commentaire `@Codex review` existe déjà
et est **plus récent** que le dernier commit sur la branche.

## Conventions de commit

Format : `type(scope): message`
Types : `fix`, `feat`, `test`, `refactor`, `chore`, `docs`, `ci`
Exemple : `fix(scraper): corriger la validation des dates`
