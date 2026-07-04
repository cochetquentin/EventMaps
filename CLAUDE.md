# EventMaps — Instructions Claude Code

## Stack et commandes essentielles

- **Langage** : Python 3.13, géré par `uv`
- **Tests** : `uv run pytest --cov=. --cov-fail-under=80 tests/ -v`
- **Serveur dev** : `uv run uvicorn api.app:app --reload`
- Toujours `uv run` — jamais `python` directement
- Pour les conventions de commit et les règles de contribution : voir [CONTRIBUTING.md](CONTRIBUTING.md)

## Workflow de review Codex

Ce repo utilise Codex (bot OpenAI) pour des reviews automatiques sur les PRs.

Voir `.claude/commands/handle-codex-review.md` pour le cycle complet.

### Règle anti-boucle absolue

Ne jamais poster `@Codex review` si un commentaire `@Codex review` existe déjà
et est **plus récent** que le dernier commit sur la branche.
