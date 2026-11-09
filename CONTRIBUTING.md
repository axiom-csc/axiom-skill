# Contributing to Axiom CSC

Thank you for helping build a deterministic safety layer for autonomous AI agents.

## Architecture (read before submitting code)

- **Noema** — AST lowering & entity extraction. Must use scope-aware parsing, never naive regex. `const MAX_RETRIES = 3` must NOT trigger a boundary event.
- **Lemma** — Relational logic solver. Optimized for <0.09ms execution. Any change that pushes cumulative `PreToolUse` runtime above 1.5ms fails CI.
- **Manam** — Tri-state epistemic controller (`TRUE | FALSE | UNKNOWN`). UNKNOWN is not an error — it is a missing-value signal that triggers fail-closed within the rule pipeline when a valid `.axiom/invariants.yaml` is active. Missing-policy behavior is a separate concern handled in the hook entry point (v1.2.3: built-in default policy applied; empty/malformed/unreadable policy: deny-all).

## Setup

```bash
git clone https://github.com/axiom-csc/axiom-skill
cd axiom-claude-skill
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Standards

- Python 3.8+ (matches the installer's minimum); use type annotations
- All PRs must include tests covering all three epistemic states: TRUE, FALSE, UNKNOWN
- Update `.axiom/invariants.yaml` schema docs when adding new entity types
- Hook latency regression: cumulative `PreToolUse` runtime must stay under 1.5ms

## Pull Request Process

1. Fork, branch from `main`
2. Add tests for TRUE / FALSE / UNKNOWN cases
3. Run `python -m pytest` -- all green
4. Submit PR with description of what domain/entity type you are adding and why

## Good First Issues

See GitHub Issues tagged `good-first-issue`:

- **S3 file size extractor** -- Terraform/CDK AWS S3 upload size boundary detection
- **Kubernetes pod quota template** -- `resources.limits.cpu/memory` invariant schema
- **Supabase RLS parser** -- detect missing Row Level Security policies in SQL migrations

## Extension: Adding a New Domain

1. Add extraction patterns to `.claude/skills/axiom-csc/scripts/lower_ast.py` under `PATTERNS`
2. Add a matching rule template to `.claude/skills/axiom-csc/scripts/axiom_init.py` under `HEURISTICS`
3. Add a domain block to `.claude/skills/axiom-csc/references/INVARIANTS_SPEC.md`
4. Open a PR with before/after examples of what Claude would have guessed vs. what Axiom catches
