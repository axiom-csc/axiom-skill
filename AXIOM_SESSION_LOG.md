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
