# Inventaire des branches GitHub — 2026-07-05

Audit réalisé le **2026-07-05** sur `cochetquentin/EventMaps`.
Outil : GitHub API (`gh api`) + comparaison `main...branch`.

## Synthèse

| Catégorie | Nb | Décision |
|-----------|-----|----------|
| `behind` main (travail dans main) | 48 | Supprimer |
| `diverged` — PR ouverte (travail actif) | 7 | **Conserver** |
| `diverged` — PR fermée sans merge (abandonné) | 1 | Supprimer (confirmé) |
| `main` | 1 | Conserver (protégée) |
| **Total** | **57** | — |

---

## Branches à supprimer — statut `behind` (48)

Toutes ces branches sont entièrement incluses dans `main` (comparaison `main...branche` = `behind`).
Leurs PR respectives sont fermées/mergées.

| Branche | Dernier commit | Auteur | PR | PR état |
|---------|---------------|--------|----|---------|
| `chore/abandon-tool-003` | 2026-06-13 | COCHET Quentin | #94 | MERGED |
| `chore/tool-002-claude-settings` | 2026-06-13 | COCHET Quentin | #92 | MERGED |
| `ci/PR-006-ruff-lint-format` | 2026-06-05 | COCHET Quentin | #28 | MERGED |
| `ci/ci-001-ci-002-noms-checks` | 2026-06-06 | COCHET Quentin | #79 | MERGED |
| `ci/ci-003-ci-004-ci-005-durcissement` | 2026-06-06 | COCHET Quentin | #81 | MERGED |
| `codex/audit-repository-and-create-roadmap-report` | 2026-06-04 | COCHET Quentin | #8 | MERGED |
| `codex/create-stabilization-roadmap-for-the-project` | 2026-06-06 | COCHET Quentin | #46 | MERGED |
| `deps/consolidate-dependabot-june2026` | 2026-06-05 | COCHET Quentin | #29 | MERGED |
| `docs/doc-001-003-004` | 2026-06-05 | COCHET Quentin | #37 | MERGED |
| `docs/stab-001-stab-003-stabilisation` | 2026-06-06 | COCHET Quentin | #76 | MERGED |
| `docs/sync-roadmap-statuses` | 2026-06-08 | COCHET Quentin | #90 | MERGED |
| `feat/arch-004-split-db-store` | 2026-06-05 | COCHET Quentin | #31 | MERGED |
| `feat/arch-006-centralize-scrape-config` | 2026-06-05 | COCHET Quentin | #33 | MERGED |
| `feat/arch-007-structured-logs` | 2026-06-05 | COCHET Quentin | #34 | MERGED |
| `feat/bug-003-scrape-report` | 2026-06-04 | COCHET Quentin | #12 | MERGED |
| `feat/bug-007-scrape-job-id` | 2026-06-06 | COCHET Quentin | #44 | MERGED |
| `feat/clean-001-sec-005-deps-audit` | 2026-06-04 | COCHET Quentin | #13 | MERGED |
| `feat/clean-002-test-007-docker` | 2026-06-05 | COCHET Quentin | #36 | MERGED |
| `feat/doc-012-readme-env-example` | 2026-06-06 | COCHET Quentin | #45 | MERGED |
| `feat/feat-001-server-search-filters` | 2026-06-05 | COCHET Quentin | #38 | MERGED |
| `feat/feat-002-shareable-urls` | 2026-06-05 | COCHET Quentin | #41 | MERGED |
| `feat/feat-003-proximity-mode` | 2026-06-05 | COCHET Quentin | #39 | MERGED |
| `feat/feat-004-ics-export` | 2026-06-06 | COCHET Quentin | #42 | MERGED |
| `feat/feat-005-event-detail-drawer` | 2026-06-05 | COCHET Quentin | #40 | MERGED |
| `feat/feat-006-timeout-tokyo` | 2026-06-06 | COCHET Quentin | #43 | MERGED |
| `feat/pr-011-hanabi-fixtures-bug004` | 2026-06-05 | COCHET Quentin | #23 | MERGED |
| `feat/sec-003-sri-cdn-assets` | 2026-06-04 | COCHET Quentin | #20 | MERGED |
| `feat/sec-004-cors-docs` | 2026-06-04 | COCHET Quentin | #21 | MERGED |
| `feat/test-003-tc-fixtures` | 2026-06-04 | COCHET Quentin | #22 | MERGED |
| `feat/test-006-frontend-vitest` | 2026-06-05 | COCHET Quentin | #35 | MERGED |
| `fix/bug-001-date-range-filter` | 2026-06-04 | COCHET Quentin | #11 | MERGED |
| `fix/bug-002-cross-year-dates` | 2026-06-05 | COCHET Quentin | #32 | MERGED |
| `fix/clean-006-attributes-field` | 2026-06-05 | COCHET Quentin | #25 | MERGED |
| `fix/sec-002-xss-frontend` | 2026-06-04 | COCHET Quentin | #10 | MERGED |
| `phase1/sec-001-protect-scrape-endpoint` | 2026-06-04 | COCHET Quentin | #9 | MERGED |
| `phase-2/production-readiness` | 2026-06-02 | COCHET Quentin | #5 | MERGED |
| `phase-3/user-features` | 2026-06-02 | COCHET Quentin | #6 | MERGED |
| `phase-4/nice-to-have` | 2026-06-02 | COCHET Quentin | #7 | MERGED |
| `refactor/arch-005-move-make-id` | 2026-06-05 | COCHET Quentin | #26 | MERGED |
| `stab/stab-002-branch-protection` | 2026-06-06 | COCHET Quentin | #80 | MERGED |
| `test/TEST-001-cover-main-cli` | 2026-06-05 | COCHET Quentin | #27 | MERGED |
| `test/test-001-fixture-policy` | 2026-06-06 | COCHET Quentin | #82 | MERGED |
| `test/test-002-reorganize-fixtures` | 2026-06-06 | COCHET Quentin | #83 | MERGED |
| `test/test-003-004-corpus-tc-hanabi` | 2026-06-08 | COCHET Quentin | #87 | MERGED |
| `test/test-003-004-real-corpus` | 2026-06-08 | COCHET Quentin | #91 | MERGED |
| `test/test-005-qualify-tot-corpus` | 2026-06-08 | COCHET Quentin | #84 | MERGED |
| `test/test-006-contract-assertions` | 2026-06-08 | COCHET Quentin | #88 | MERGED |
| `test/test-007-fixture-renewal` | 2026-06-08 | COCHET Quentin | #89 | MERGED |

---

## Branches à conserver — `diverged`, PR ouverte (7)

Ces branches ont des commits uniques hors de `main` **et** une PR encore ouverte.
Elles représentent du travail actif (mises à jour Dependabot en attente de review).

| Branche | Dernier commit | Auteur | PR | PR état |
|---------|---------------|--------|----|---------|
| `dependabot/github_actions/actions/checkout-7` | 2026-06-22 | dependabot[bot] | #100 | **OPEN** |
| `dependabot/github_actions/actions/setup-node-6` | 2026-06-08 | dependabot[bot] | #85 | **OPEN** |
| `dependabot/uv/beautifulsoup4-4.15.0` | 2026-07-04 | dependabot[bot] | #86 | **OPEN** |
| `dependabot/uv/httpx2-2.4.0` | 2026-07-04 | dependabot[bot] | #99 | **OPEN** |
| `dependabot/uv/pytest-9.1.0` | 2026-07-04 | dependabot[bot] | #98 | **OPEN** |
| `dependabot/uv/ruff-0.15.17` | 2026-07-04 | dependabot[bot] | #96 | **OPEN** |
| `dependabot/uv/slowapi-0.1.10` | 2026-07-04 | dependabot[bot] | #97 | **OPEN** |

---

## Branches à supprimer — `diverged`, PR fermée sans merge (1)

| Branche | Dernier commit | Auteur | PR | PR état | Motif |
|---------|---------------|--------|----|---------|-------|
| `feat/tool-003-handle-codex-review-script` | 2026-06-13 | COCHET Quentin | #93 | **CLOSED** | TOOL-003 abandonné (voir #94) |

---

## Méthode de vérification

Statut de comparaison obtenu via :
```bash
gh api "repos/cochetquentin/EventMaps/compare/main...BRANCHE" --jq '.status'
```

- `behind` = tous les commits de la branche sont dans `main` (merge régulier)
- `diverged` = la branche a des commits uniques hors de `main`
- `ahead` = la branche a des commits uniques, `main` n'a pas avancé depuis le fork

Aucune branche n'a été modifiée durant cet audit.
