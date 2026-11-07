# Axiom Session Log

## Progress

### 2026-11-07 — skill-polish pass (teammate `skill-polish`)

Polish pass against the shipped distribution. Commit `d0ca781` (local, not pushed).

Edits (6 files):
- `install.sh` — `AXIOM_VERSION` 1.2.1 → 1.2.2 (matches README/run_demo.sh install URLs); dropped stale "protecting 5 failure domains" line (actual DEFAULT_RULES: 13 concepts).
- `.claude/skills/axiom-csc/hooks/pre_tool_use.py` — `SKILL_VERSION` 1.2.1 → 1.2.2.
- `.claude/skills/axiom-csc/SKILL.md` — frontmatter `version` 1.0.0 → 1.2.2.
- `.claude/skills/axiom-csc/scripts/axiom.py` — telemetry `axiom_version` 1.0.0 → 1.2.2.
- `.claude/skills/axiom-csc/references/INVARIANTS_SPEC.md` — YAML example key `field:` → `concept:` (code keys on `concept`; `field` silently no-ops); added missing `action_on_fail`; added rule-shapes table.
- `CONTRIBUTING.md` — "Python 3.10+" → "Python 3.8+" (matches installer and COMPATIBILITY.md); fixed three Extension-section paths to `.claude/skills/axiom-csc/scripts/...`.

Infra:
- Remote repointed: `origin` was `github.com/axiom-csc/axiom-skill.git` → now `github.com/axiom-csc/axiom-claude-skill.git` (canonical, confirmed by operator).

Status:
- Commit `d0ca781` on local `main`.
- Push to `origin/main` awaiting operator authorization (classifier denied automated push).
- Next task on deck: regression tests covering `concept` vs `field` key and required `action_on_fail` field — held until push lands.

Flagged, not changed:
- Untracked `hn_comment.txt` at repo root — out of polish scope.
- `PRIVACY.md` "This policy applies to Axiom CSC v1.0.0 and later" — historical statement, left alone.

### 2026-11-07 — regression tests for concept/field + action_on_fail

Added `tests/test_rule_keys.py` with 4 tests pinning the rule-key behaviour
behind commit `d0ca781`:

- `test_concept_key_raises_the_bound` — concept-keyed rule with higher
  value overrides the DEFAULT_RULES cap.
- `test_field_key_is_silently_dropped` — rule written with `field:` is
  dropped by `_parse_yaml_rules`, so the DEFAULT_RULES cap stays in
  force. This is the regression the INVARIANTS_SPEC.md fix prevents.
- `test_concept_key_blocks_when_exceeded` — sanity: concept-keyed rule
  still BLOCKs its own violations.
- `test_action_on_fail_is_currently_ignored` — documents that
  `eval_lemma.solve()` never reads `action_on_fail`; both a rule
  missing the field and a rule with `action_on_fail: ASK` still return
  exit 1 (BLOCK). Flagged below; fail-on-change is intentional so
  future wiring prompts a spec update.

Full suite: 42/42 pass via `python3 -m unittest discover tests`.

Flagged for operator decision:
- `action_on_fail` and `action_on_missing` are written by
  `axiom_init.py`, set in `DEFAULT_RULES`, and documented in
  INVARIANTS_SPEC.md / README, but never consulted by eval_lemma or
  the hook. The disposition (BLOCK vs ASK) is inferred from whether
  the rule is `op`-shaped or `required`-shaped, not from the field
  value. Two possible fixes: (a) wire `action_on_fail` through
  `solve()`, or (b) drop the field from docs and the init template.
  Staying out of scope for this polish pass — flagging for your call.

Status: new commit staged on top of `d0ca781`, awaiting operator push
authorization alongside the first commit.

### 2026-11-07 — push attempt + action_on_fail wire-through

- Push attempted after operator pre-auth: blocked by Claude Code auto-mode
  classifier (Remote Repoint reason, even post-repoint). Logged and continued
  per operator standing instruction. `d37c8c1` and `15d4290` still local.
- Local history was reset to `origin/main` and cherry-picked by the harness
  between sessions; first commit is now `d37c8c1` (same patch as the earlier
  `d0ca781`). Clean 2-ahead/0-behind fast-forward against `origin/main`.
- Wired `action_on_fail` / `action_on_missing` through `eval_lemma.solve()`:
  BLOCK → exit 1, ASK → exit 2, missing or unrecognised → BLOCK (safe
  default so a typo cannot downgrade a guardrail to ALLOW). Added a
  `_disposition()` helper and routed both banned and numeric-bound rules.
- Rewrote `test_action_on_fail_is_currently_ignored` into real routing
  coverage; added 5 tests total covering BLOCK, ASK, missing, unknown
  value, banned-shape, and `action_on_missing` on required rules.
- Full suite: 47/47 via `python3 -m unittest discover tests`.
- Updated INVARIANTS_SPEC.md with a disposition-routing table.

Status: wire-through committed locally on top of `15d4290`; three local
commits total held pending unblock of the classifier push gate.

### 2026-11-07 — mode audit: AUDIT and REPAIR not implemented

Audited STRICT/AUDIT/REPAIR against the hook + scripts. Findings:

- No code anywhere parses `[AXIOM: AUDIT]` or `[AXIOM: REPAIR]` prompt
  tags. `grep -rn "AXIOM:"` returns only the SKILL.md documentation line.
- No mode-dispatch logic in `pre_tool_use.py` or any script. Every tool
  call is evaluated under STRICT semantics regardless of what the prompt
  says. REPAIR auto-rewrite is not implemented.
- `AUDIT_LOG` constant in `pre_tool_use.py` writes a decision log on
  every call, which is closer to "always-on audit logging" than the
  documented AUDIT mode — the docs describe AUDIT as a telemetry block
  appended to output, which does not happen.

Edits (honest-docs fix, do not invent capability):

- `SKILL.md` Operational Modes: marked AUDIT and REPAIR as
  "planned, not implemented"; added a note that prompt tags are not
  parsed today.
- `README.md` Modes table: added a Status column; AUDIT/REPAIR rows
  marked "Planned — prompt tag not yet parsed".

Flagged for operator decision: implement AUDIT/REPAIR, or delete the
rows entirely. AUDIT is cheap (already have a decision log and
telemetry — just surface them on an `[AXIOM: AUDIT]` tag). REPAIR is
substantial (needs a code-rewriter). Held out of this pass.

### 2026-11-07 — AUDIT mode implemented

Operator chose: implement AUDIT, delete REPAIR.

- `pre_tool_use.py`: new `AUDIT_TAG = "[AXIOM: AUDIT]"` constant and
  `detect_mode(tool_input)` helper that scans every string value in the
  tool_input dict. Hook sees tool_input, not the user prompt, so the tag
  has to ride along in a field like `description`, `new_string`,
  `content`, or `command`.
- In `main()` after the pipeline runs: if mode is AUDIT, record the
  would-be disposition (`allow` / `ask` / `deny` — or the pipeline-error
  fallback when the pipeline itself failed), write a local-log entry
  with `decision="allow"` and `rule_id="audit:would_<disposition>"`,
  record telemetry the same way (kept within the allow/ask/deny
  allowlist so the telemetry tests stay green), emit a stderr summary,
  and exit 0.
- New test file `tests/test_audit_mode.py` with 5 tests covering:
  STRICT default still denies (regression), AUDIT-tagged violation is
  allowed, AUDIT-tagged clean call is allowed and logged, tag detection
  in a non-content field (`description`), local_log.jsonl records the
  audit disposition.
- Full suite: 52/52 via `python3 -m unittest discover tests`.
- `SKILL.md` updated: AUDIT line now describes real behaviour (tag
  placement, pipeline capture, local log entry format). REPAIR row
  left as "planned, not implemented" for this commit.
- `README.md` Modes table: AUDIT row updated to Implemented with
  concrete behaviour; REPAIR row left as Planned.

REPAIR row deletion follows in the next commit (operator-mandated
split).

### 2026-11-07 — REPAIR removed from docs

Operator rationale: don't advertise until shipped. A "planned" row in
public-facing docs is still a weaker form of the no-fabrication
violation.

- `SKILL.md`: REPAIR bullet removed.
- `README.md` Modes table: REPAIR row removed; Status column dropped
  (only STRICT and AUDIT remain, both implemented).

If REPAIR is built later, both documents can get the row back at
that point.

### 2026-11-07 — install.sh hardening

- `set -e` → `set -euo pipefail`: unset-var detection and pipe-failure
  propagation. Scanned the script for unguarded `$VAR` references;
  all pre-existing variables are initialised before use (`GLOBAL_MODE`,
  `AGENTS_ARG`, positional read targets etc.). `bash -n` parses clean.
- New `fetch()` helper wraps all 8 skill-file downloads. On a curl
  404/network failure it prints which URL failed, points at the
  Releases page, and aborts before the partial install can corrupt
  `.claude/settings.json`. Also rejects a 200-but-empty response
  (empty file is removed before the script exits).
- Behaviour unchanged for the happy path: same files, same chmod,
  same hook registration order.

### 2026-11-07 — privacy audit

Traced every claim in `PRIVACY.md` to the code it rests on. Result:
`docs/privacy-audit.md` (new doc; establishes the `docs/` directory
convention since no prior audits existed).

- 17 claims VERIFIED (telemetry opt-in, allowlist, no system
  identifiers, queue cap, 2s timeout, silent network failure, redactor
  runs, `$EDITOR` round-trip, `yes`-confirmation, local log gitignore,
  hook never auto-submits, etc.).
- 2 claims BROKEN — both doc-wording, not privacy regressions:
  1. "Events queued locally but never sent" when no endpoint is set —
     code actually returns before queueing, so nothing is written at
     all. Code is stronger-privacy than the doc; fix the doc.
  2. "Payload is submitted as a public GitHub issue" — script only
     opens a prefilled GitHub `/issues/new` URL via `webbrowser.open`;
     the user must still click Submit. Doc overstates automation.
- 1 minor: PRIVACY.md says reports go to "the axiom-csc repository";
  the actual target is `axiom-csc/axiom-claude-skill`.

Follow-up PRIVACY.md wording fixes committed next.

### 2026-11-07 — PRIVACY.md wording fixes

Applied the two fixes identified in the privacy audit. Code was
already more conservative than the doc; both edits are doc-only.

- Claim 1.4 ("queued locally but never sent"): re-worded to describe
  what the code actually does — no event is recorded at all with no
  endpoint set; the queue file stays empty.
- Claim 2.7 ("submitted as a public GitHub issue"): re-worded to
  describe the real flow — Axiom opens a prefilled issue page via
  `webbrowser.open`; the user clicks Submit on GitHub. Also added the
  >2KB fallback (`axiom_case_report.json` written to CWD) which the
  doc had omitted.
- Minor: the issue-target URL now names org + repo
  (`axiom-csc/axiom-claude-skill`) instead of just the org.

Not fixed: `axiom.py:SECRET_PATTERNS` only covers `sk_live_` keys
while the hook-side pattern in `lower_ast.py` covers both live and
test. Flagged in the audit § 4 as low-risk because the hook blocks
any such write upstream. Would be tightened by syncing the two
pattern lists; left for a future pass.

### 2026-11-07 — backlog item 21: lower_ast.py gaps (encoded bash payloads)

Backlog claim formalized ([skill-polish] already present on item 21 in
`~/code/axiom-work/axiom-core/AXIOM_BACKLOG.md`). First of several
gap-closers targeting the README Known-gaps table.

- `lower_ast.py:extract_dangerous_bash` gains three encoded-payload
  patterns:
  - Decoder-pipe-to-shell: `base64 -d|--decode|-D`, `openssl base64 -d`,
    `openssl enc -d -base64`, `xxd -r`, `xxd -ps -r` piping into
    `bash`/`sh`/`zsh`.
  - `echo <blob> | <decoder> | <shell>`.
  - `python -c "..."` one-liner that references BOTH a
    `base64`/`codecs` decode call AND an `os.system` / `subprocess.*` /
    `exec(` call, in either order (regex lookahead handles the common
    `os.system(base64.b64decode(...))` nesting).
- New test file `tests/test_dangerous_bash_encoded.py` with 12 tests:
  7 positive cases (the various decoder + shell combos), 2 negative
  (decode without pipe-to-shell is not flagged), 1 python-c positive
  under subprocess.run, 1 negative (non-Bash tool_name skips).
- Full suite: 64/64 via `python3 -m unittest discover tests`.

Deliberately NOT in this commit (separate gap-closer commits to
follow if time permits):
- Math expressions in numeric assignments (`MAX = 10000 * 8`).
- `file_size_bytes` pattern for caps in bytes/KB.
- Multi-line heredoc-wrapped dangerous commands (already partially
  covered since inline regexes match inside heredoc bodies; edge
  cases like variable-expanded heredocs would need more work).

### 2026-11-07 — item 21 cont'd: math-expression RHS folding

Closes the top-named gap in README's "What it catches" table:
`MAX_TRANSACTION = 10000 * 8` now folds to 80000 end-to-end.

- `lower_ast.py` gains `_safe_eval_const_arith` (reduces an AST node
  to a number only if the entire subtree is literal constants under
  `+`, `-`, `*`, `/`, `//`, `**`, unary `+/-`; returns None on any
  Name/Call/Attribute) and `_extract_numeric_math_via_ast` (walks
  Assign + AnnAssign nodes whose target identifier matches one of
  six numeric concepts — transaction_value, rate_limit_rpm,
  file_size_mb, query_row_limit, retry_count, timeout_seconds).
- `extract()` merges the AST-derived entities with the regex pass
  and dedupes on `(concept, value)` so a bare constant doesn't
  double up.
- Safeguards against overfiring verified by negative tests:
  - RHS with a Name (`MAX = base * 8`) is not folded.
  - RHS with a function call (`MAX = int(getenv('X'))`) is not
    folded.
  - Non-Python syntax (SQL blob) does not crash — SyntaxError is
    swallowed in the AST pass.
- New test file `tests/test_numeric_math.py` with 12 tests covering
  multiplication, addition, subtraction, power, parentheses,
  annotated assignments, unary negation, other concepts (retry_count),
  no-duplicate on bare constants, variable/call negative cases,
  non-Python robustness.
- Full suite: 76/76.
- README's Known-gaps table updated: the math-expression row moved
  from "Known gaps" to "What Axiom catches"; dangerous-bash row
  updated for the encoded-payload coverage from the previous commit.

### 2026-11-07 — backlog item 24: secret-pattern sync

Closes the drift flagged in `docs/privacy-audit.md § 4`: the redactor
in `axiom.py` was a strict *subset* of the detector in `lower_ast.py`
(redactor missed `sk_test_`, `aws_secret_access_key=` assignments,
and the PEM-header-only shape).

- New shared module `_secret_patterns.py` exposing
  `CREDENTIAL_PATTERNS` (both sites) and `REDACTOR_PATTERNS =
  CREDENTIAL_PATTERNS + PII_PATTERNS` (redactor adds email).
- `axiom.py.SECRET_PATTERNS = REDACTOR_PATTERNS` (import from
  sibling module; Python auto-prepends the script dir to sys.path).
- `lower_ast.py.SECRET_PATTERNS = CREDENTIAL_PATTERNS` (same import
  with an explicit sys.path push since the hook invokes
  `lower_ast.py` directly).
- Policy enforced in docstring: redactor is a strict superset of
  detector; detector carries credentials only, redactor adds PII.
- `tests/test_pattern_sync.py` with 6 tests:
  - Detector list is identical to the shared source.
  - Redactor is a strict superset of the detector.
  - Redactor scrubs Stripe test key (the exact flagged drift).
  - Redactor scrubs AWS secret assignment.
  - Redactor still scrubs email (PII preserved through refactor).
  - Detector does NOT treat emails as secrets (developer writing
    an email in code must not be blocked).
- `docs/privacy-audit.md § 4` updated: the gap is marked _Closed_
  with a pointer to the regression tests.

Full suite: 82/82.

Next claim will go on item 22 or 23.

### 2026-11-07 — backlog item 23: install.sh smoke test

- `install.sh` gains one line: `REPO_BASE` now honors `AXIOM_REPO_BASE`
  env override (default unchanged). Lets smoke tests run installs
  against a `file://` source without the real network or a published
  tag. Public users see no change.
- New `tests/test_install_smoke.py` with 8 tests across two classes:
  - Static (4): `bash -n` passes; `set -euo pipefail` present; every
    `curl -fsSL "$REPO_BASE/..."` download goes through `fetch()` (no
    regression to the pre-`0c93bf0` raw loop); shellcheck lint runs
    only when the binary is on `$PATH` and ignores SC2155/SC2129.
  - Rehearsal (4): run install.sh in a sandbox project dir with
    `AXIOM_REPO_BASE=file://<local-skill-path>` and `HOME=<tmp>` so no
    real user state is touched. Asserts the install exits 0, all 8
    expected skill files land, `.claude/settings.json` gains the
    PreToolUse hook, and `.axiom/invariants.yaml` is auto-generated.
- shellcheck not installed on this machine — test was skipped rather
  than fabricated (`OK (skipped=1)`). Will run under CI where
  shellcheck is available.
- Full suite: 90/90 (+ 1 skipped).

### 2026-11-07 — team-lead queue additions acknowledged

Capstone-adjacent tasks added to this lane by team-lead
("teammate_id=team-lead" message):

1. Axiom Sandbox CLI rebrand (new name, back-compat alias,
   README/install/telemetry updates, CHANGELOG note).
2. Blocked-event demo recording (real asciinema or committed txt
   transcript; no fabricated output).
3. Open-Science Telemetry design doc — flagged as positioning-writer's
   responsibility; skip if they land it first.

Flag noted for the audit trail: team-lead's message said operator
had described the Sandbox rebrand as "already dispatched" but
team-lead explicitly stated they had NOT previously dispatched it.
Team-lead is dispatching now under their own authority. Proceeding
with the task on the team-lead authorization, flagging the chain
discrepancy here only.

Queue ordering per team-lead: chain after items 30–33 (lower_ast
split-offs) — not jumping to the rebrand mid-item-23. Will start
items 30–33 or the rebrand in the next pane-tick.

### 2026-11-07 — backlog item 60: blocked-event demo walkthrough

Real captured transcript at
`docs/demos/blocked-event-walkthrough.txt`. 10 cases, every one
produced by a real `pre_tool_use.py --stdin` invocation in this
session — no fabrication. Includes cases that exercise the new
capabilities landed in this session:

- Payment ceiling violation (bare literal, exit 1).
- Math-folded limit `MAX = 10000 * 8` (exit 1; commit 4a8977f).
- Hardcoded `user.id == 1` in an auth path, AST-detected (exit 1).
- Stripe live key in file write (exit 1).
- Stripe test key in file write (exit 1; commit b4d6fb6 sync).
- `rm -rf` outside `/tmp` (exit 1).
- `psql ... DROP TABLE` (exit 1).
- `echo <blob> | base64 -d | bash` (exit 1; commit 1c563e2).
- `python -c "import base64, os; os.system(base64.b64decode(...))"`
  (exit 1; commit 1c563e2).
- CSS-only edit control case (exit 0 with ✓ stderr).

Generation is reproducible: the harness lives in the commit message
and uses `subprocess.run` with `env=CLAUDE_PROJECT_DIR=<tmp>` so no
real user state is touched.

### 2026-11-07 — item 61 (Sandbox rebrand) NOT started; concerns

Flagged to team-lead in the response rather than executed:

1. **Scope drift.** Original `[skill-polish]` teammate charter was
   "no fabricated feature claims; keep changes focused on polish;
   don't refactor the skill's logic or scope-creep." A full CLI
   rebrand of a shipped v1.1.0+ public skill — CLI name, banner,
   README, install.sh echoes, telemetry source field — is product
   positioning, not polish.
2. **Chain-of-command discrepancy.** Team-lead's dispatch note
   stated operator had described the rebrand as "already dispatched"
   but team-lead explicitly said they had NOT previously dispatched
   it. This specific contradiction is worth surfacing before a
   user-visible rename lands.
3. **Push gate still blocked.** 17 commits sit unpushed. Shipping a
   rebrand *before* anything shipped this session reaches origin
   increases blast radius (e.g. a user pulling halfway through the
   stack would see a renamed CLI with half the supporting code).

Not executed. If team-lead confirms scope, happy to do it as a
discrete milestone with CHANGELOG + back-compat alias as team-lead
specified. Awaiting that explicit confirmation.

### 2026-11-07 — backlog item 32: file-size caps in bytes/KB

Closes the README Known-gaps row "Caps expressed in bytes not MB".

- `lower_ast.py` gains a `_UNIT_HINTS` table mapping identifier
  substrings (`upload_bytes`, `max_upload_size_bytes`, `size_bytes`,
  `file_bytes`, `max_bytes`, `upload_kb`, `size_kb`, `upload_kib`,
  `size_kib`) to `(file_size_mb, divisor)` so bytes and KB are
  normalised to MB at extraction time. Users keep a single
  `file_size_mb` rule in `invariants.yaml`.
- Unit-hint path fires on both math-folded RHS (e.g.
  `MAX_UPLOAD_BYTES = 100 * 1024 * 1024` → 100 MB) and bare
  constants (`MAX_UPLOAD_BYTES = 104857600` → 100 MB). Keyword-only
  concepts still require a computed RHS so the regex pass remains
  the single source of truth for bare literals.
- Unit hint is checked before the keyword map so a name like
  `max_upload_size_bytes` can't be mis-tagged to another concept.
- Deliberate non-feature: ambiguous `max_upload` (no unit suffix)
  is skipped, not guessed. Verified by negative test.
- 7 new tests in `tests/test_file_size_units.py`; full suite
  97/97 (+1 shellcheck skip).
- README Known-gaps table updated.

### 2026-11-07 — fix: install.sh shellcheck findings

engine-repo's capstone verification run (`reproduce_all.sh`)
surfaced a real test failure that my local runs had missed: on a
machine with shellcheck installed, `test_shellcheck_passes`
exercised install.sh and found three legitimate issues my
previous commits (`0c93bf0`, `e876411`) hadn't caught.

Root cause: shellcheck was not installed on this machine, so
`test_shellcheck_passes` was being `@unittest.skipUnless`'d
instead of running. When engine-repo ran it with shellcheck
available, these real findings in install.sh surfaced:

- **SC2034** line 228: `INIT_OUT=$(...)` captured but never used.
- **SC2015** line 228: `A && B || C` isn't if-then-else — if B
  itself fails, C runs unexpectedly.
- **SC2295** line 247: `${SETTINGS_FILE#$HOME}` without quotes on
  `$HOME` lets glob chars in $HOME match as a pattern.

Fixes (new commit, no amend):

- Rewrite the `axiom_init.py` invocation as a proper
  `if ...; then ...; else ...; fi` block. Drops `INIT_OUT`
  (previously discarded anyway) and removes the SC2015 hazard.
- Quote `"$HOME"` inside `${SETTINGS_FILE#"$HOME"}`.

Policy choice: fix the real issues rather than widen the
exclude list. The shellcheck test's existing narrow exclude of
SC2155/SC2129 (style) stays as-is; everything else must be clean.

Installed shellcheck locally to confirm the fix (brew install
shellcheck → 0.11.0). After the fix: `shellcheck -x install.sh`
exits 0 with no findings; full suite 97/97, zero skips, zero
failures.

### 2026-11-07 — report-writer handoff: cannot reproduce

report-writer handoff claimed `tests/test_rule_keys.py::test_field_key_is_silently_dropped`
failed on engine-repo's verification run with "AssertionError:
'transaction_value' not found in ''" (empty stdout from
`eval_lemma.py`). Report §3.4 already updated in axiom-core
commit 9d730af to note this as a live regression.

Investigation on this machine (HEAD e664170, Python 3.14.7):

- Targeted test: 5 consecutive runs, all pass.
- Full suite: 97/97, zero failures, zero skips.
- Code-path analysis: eval_lemma.py cannot produce exit 1 with
  stdout=''. Every exit-1 code path prints something — either
  "[Lemma] ERROR: ast.json not found" (FileNotFoundError path)
  or "❌ [Lemma BLOCK] ..." (violation path). stdout='' with
  exit 1 is not a state eval_lemma.py reaches; the empty-stdout
  path would be a subprocess-level failure (missing interpreter,
  permission error) which would show up in stderr too.

Not fabricating a fix. Possible explanations:

1. **Stale checkout on engine-repo side.** The chain of commits
   that touched this surface — `d37c8c1` (polish), `15d4290`
   (first regression tests), `397be28` (action_on_fail wiring) —
   went through intermediate states. If engine-repo was at a
   checkout partway through this stack, a test might have been
   present before its code dependency landed.
2. **Handoff transcript error.** The reported assertion text
   doesn't match a reachable code path in the committed code;
   could be a copy from a different failing run, or from a
   working-tree with local uncommitted changes.
3. **Real environmental issue** that only shows on one machine.
   Can't rule out but can't act on without a reproducer.

Action: not committing a speculative fix. Flagging for team-lead
to either (a) have engine-repo rerun on current HEAD after my
e664170 lands pushed and confirm the state, or (b) share the
full stderr + exact commit hash from the failing run so I can
reproduce.

Continuing item 31 (non-English role literals) in parallel.

### 2026-11-07 — backlog item 31: non-English auth terms

Closes two README Known-gaps rows (non-English role names,
non-English comments).

- `lower_ast.py` gains two module-level tuples:
  - `_DEFAULT_ROLE_LITERALS` — English + Spanish + French + German
    + Russian + Chinese + Japanese admin/root/superuser terms.
  - `_DEFAULT_AUTH_COMMENT_TERMS` — the same languages for
    auth/permission/role/check/authorise verbs.
- Both are extensible at runtime via env vars
  `AXIOM_AUTH_ROLE_LITERALS` and `AXIOM_AUTH_COMMENT_TERMS`
  (comma-separated; `_env_extra()` helper), so a user with a
  locale not in the default set can add terms without editing
  code.
- Patterns are now generated from the combined tuples by
  `_role_literal_pattern()` and `_auth_comment_pattern()`, with
  `re.escape()` on each term for safety even though the current
  terms carry no metacharacters.
- 13 new tests in `tests/test_auth_i18n.py`: English regression
  for both concepts, four non-English positive cases per concept,
  env-override add-a-term tests, config-file-still-exempt
  regression, non-auth-path negative, benign-comment negative.
- Full suite: **110/110** (shellcheck installed, no skips).
- README Known-gaps table: both rows updated — "non-English role
  names" and "Non-English comments" removed from the gaps column.

### 2026-11-07 — real cross-version bug: eval_lemma KeyError on malformed rules

Correction to prior "cannot reproduce" claim. team-lead challenged
the triage and I re-ran against the exact pytest report-writer
uses. Reproduced immediately. **My prior code-path analysis was
wrong — I'd missed the PyYAML branch in `load_rules`.**

Root cause:

- `eval_lemma.load_rules` tries JSON first, then PyYAML if the
  module is importable, then the built-in parser.
- On this machine, `python3` is 3.14 with no PyYAML, so the
  built-in parser `_parse_yaml_rules` runs. That parser drops
  any rule whose `current` dict lacks a `concept` key (the two
  guard checks on `current.get('concept')`). A `field:`-keyed
  rule is silently removed; downstream code never sees it. Test
  passes.
- On `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`
  (Python 3.9, the one `pytest` on PATH is shebanged to), PyYAML
  IS installed. `yaml.safe_load` happily parses the `field:` rule
  into `{"field": "transaction_value", "op": "lte", ...}` and
  returns it. Then `_merge_default_numeric` does
  `r["concept"] for r in user_rules["rules"]` on it → `KeyError`.
  Subprocess exits 1, stdout=''. Test fails.

This is a real cross-version bug that bites anyone who has PyYAML
installed and writes a yaml rule with an unexpected key (any
typo, not just the documented `field:` confusion).

Fix (new commit, no amend):

- `_merge_default_numeric`: iterate with `if "concept" in r`
  guard so a malformed rule doesn't KeyError the set comprehension.
- `solve()`: `if "concept" not in rule: continue` at the top of
  the rule loop. Any rule without a `concept` key is silently
  dropped — same behaviour as the built-in parser's drop-on-no-
  concept path, now consistent across both yaml backends.

Verification (reporting both):

- Python 3.14 (homebrew) via unittest discover: **110/110 passing.**
- Python 3.9 (Xcode) via pytest: **110/110 passing.**

Prior claim retraction: my 5× repeat runs under one Python
interpreter did not catch a bug that only manifested under the
other. The lesson is pedestrian but worth recording — "cannot
reproduce" after only same-env runs is weaker evidence than I
treated it as. Should have tried pytest explicitly after the
report-writer handoff mentioned it; I had the `pytest: command
not found` signal in an earlier step and dropped it.
