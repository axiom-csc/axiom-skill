# Privacy Audit — `axiom report` submit flow

Audit performed 2026-11-07 against commits up to `0c93bf0`. Scope: every
claim in `PRIVACY.md`, traced to code. Each claim is marked:

- **VERIFIED** — code backs the claim end-to-end.
- **BROKEN** — code contradicts the claim as written.
- **NOT TESTABLE BY READING** — needs a live network trace.

## 1. Telemetry — `PRIVACY.md` "Telemetry" section

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 1.1 | "Collects no data by default" | **VERIFIED** | `install.sh` writes `telemetry: false` in `~/.config/axiom-csc/config.json` on both the explicit-N and non-TTY paths; `record_telemetry()` early-returns when `cfg.get("telemetry")` is falsy (`pre_tool_use.py:165`). |
| 1.2 | "Opt-in via install prompt or `axiom telemetry on`" | **VERIFIED** | `install.sh` prompts only when TTY; `cmd_telemetry("on")` sets `telemetry: True` (`axiom.py:91–95`). |
| 1.3 | "Events are only transmitted if you have also configured an endpoint" | **VERIFIED** | `record_telemetry()` returns before any network path when `endpoint` is empty (`pre_tool_use.py:167–169`). |
| 1.4 | "With no endpoint set, events are queued locally but never sent" | **BROKEN** | With no endpoint, `record_telemetry()` returns *before* `queue_event()` is called. Nothing is queued; the queue file stays empty. The claim implies local inspection is possible without an endpoint, but it isn't. |
| 1.5 | Event field allowlist (install_id, ts, decision, rule_id, tool_name, latency_ms, skill_version, os, python) | **VERIFIED** | `build_event()` (`pre_tool_use.py:121–133`) constructs the dict by explicit field assignment, nine keys exactly. Covered by `test_telemetry.test_event_contains_only_allowlisted_fields`. |
| 1.6 | "Not tied to machine, username, or hardware" (install_id) | **VERIFIED** | Install_id is `uuid.uuid4()` generated at install time (`install.sh` telemetry-consent block, `cmd_telemetry` fallback). No system identifiers participate. |
| 1.7 | "Never sent: tool_input, commands, code, file contents, paths, filenames" | **VERIFIED** | `build_event()` has no reference to any of these; fields are copied from a fixed call signature, not from the payload. Covered by `test_telemetry.test_event_does_not_contain_tool_input`. |
| 1.8 | "Never sent: contents of invariants.yaml / state.json" | **VERIFIED** | Those files are only read by the pipeline scripts; `build_event()` never touches them. |
| 1.9 | "Never sent: env vars, CWD, project name, hostname, username, hardware id" | **VERIFIED** | `os` field is `platform.system().lower()` — the OS *name* (`darwin`/`linux`), not hostname. `python` is `sys.version_info.major.minor`. Nothing else system-derived. |
| 1.10 | "Events appended to `~/.config/axiom-csc/queue.jsonl`" | **VERIFIED** | `queue_event()` writes to `QUEUE_FILE = CONFIG_DIR / "queue.jsonl"` (`pre_tool_use.py:56, 143`). |
| 1.11 | "Background detached subprocess with 2-second timeout" | **VERIFIED** | `fire_flush()` uses `subprocess.Popen(..., start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)` (`pre_tool_use.py:148–159`); `axiom_flush.py` sets `TIMEOUT = 2` on `urllib.request.urlopen`. |
| 1.12 | "Any network error is silently swallowed and never affects the hook's decision" | **VERIFIED** | `record_telemetry()` wraps everything in `try/except Exception: pass` (`pre_tool_use.py:173`); `axiom_flush.py` wraps the send in its own blanket except. Covered by `test_telemetry.test_network_failure_does_not_affect_decision`. |
| 1.13 | "Queue cap at 1,000 events, oldest dropped" | **VERIFIED** | `QUEUE_MAX = 1000` + `lines = lines[-QUEUE_MAX:]` (`pre_tool_use.py:57, 141–142`). Covered by `test_telemetry.test_queue_capped_at_1000`. |
| 1.14 | `axiom telemetry off` disables | **VERIFIED** | `cmd_telemetry("off")` sets `telemetry: False` and persists (`axiom.py:100–102`). |

## 2. Case reports — `PRIVACY.md` "Case reports (`axiom report`)" section

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 2.1 | "Always voluntary and manual. The hook never submits anything automatically" | **VERIFIED** | Hook (`pre_tool_use.py`) never calls `cmd_report` or any GitHub endpoint; case submission lives only in `axiom.py` and requires interactive input. |
| 2.2 | "Choose a specific decision from your local log" | **VERIFIED** | `cmd_report()` enumerates the last 10 entries of `.axiom/local_log.jsonl` and requires `input()` of an index (`axiom.py:124–150`). |
| 2.3 | "Scans the payload for secrets and redacts them" | **VERIFIED** | `redact_secrets()` runs on `json.dumps(entry)` before payload construction (`axiom.py:167`). Patterns: AWS access keys, OpenAI keys, Stripe live keys, generic api_key/token/secret assignments, PEM PRIVATE KEY blocks, emails. Covered by `test_telemetry.RedactorTests` (6 tests). |
| 2.4 | "You can open the payload in `$EDITOR` to remove anything else" | **VERIFIED** | When `$EDITOR` is set, payload is written to a tempfile, opened, and re-read before preview (`axiom.py:182–196`). |
| 2.5 | "The full redacted payload is printed for your review" | **VERIFIED** | Payload is printed verbatim before confirmation (`axiom.py:202–203`). |
| 2.6 | "You must type `yes` to confirm submission" | **VERIFIED** | `if confirm.lower() != "yes": sys.exit(0)` (`axiom.py:210–215`). |
| 2.7 | "The payload is submitted as a public GitHub issue" | **BROKEN** | The script does not submit anything — it opens a GitHub "new issue" URL with the title/labels/body pre-filled via `urlencode` + `webbrowser.open()` (`axiom.py:217–230`). The user must still click **Submit** inside GitHub, after reviewing the prefilled form. "Submitted" overstates the automation; "opens a prefilled GitHub issue for the user to submit" is accurate. (Also: if the URL exceeds `MAX_URL_LEN = 2000`, the payload is written to `axiom_case_report.json` in CWD and the user is told to attach it manually.) |
| 2.8 | "CC-BY-4.0 notice" | **VERIFIED** | Shown before confirmation (`axiom.py:205–206`). |
| 2.9 | "`.axiom/local_log.jsonl` is never sent automatically and is listed in `.gitignore` by `axiom_init.py`" | **VERIFIED** | `axiom_init.py:96` adds `.axiom/local_log.jsonl` (plus audit.log, ast.json, state.json) to the project `.gitignore`. Hook writes the local log on every call but no code sends it anywhere — only an interactive `axiom report` can surface a single selected entry. |

## 3. "Changes" section

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 3.1 | "Policy applies to Axiom CSC v1.0.0 and later" | **VERIFIED (historical)** | Current version is 1.2.2 (`SKILL_VERSION`, SKILL.md frontmatter, axiom.py); "from v1.0.0 onward" stays accurate as a historical statement. |

## 4. Not covered by the doc but worth noting

- **Flush retry semantics.** `axiom_flush.py` clears only events that round-tripped successfully — on a failed send, nothing is dropped, so the next flush retries the same events. Combined with the 1000-cap, this means a long offline window silently drops the oldest beyond 1000; no doc claim is wrong, but users may want this surfaced in a FAQ.
- **Secret-pattern coverage vs the hook.** _Closed._ Both sites now
  read from `_secret_patterns.py` (backlog item 24): the redactor is a
  strict superset of the detector. `tests/test_pattern_sync.py` pins the
  invariant. Prior gap — redactor missed Stripe `sk_test_` and
  `aws_secret_access_key=` assignments that the detector caught — would
  be caught by the two regression tests there.
- **`$EDITOR` round-trip.** If the user edits the payload and introduces invalid JSON, `cmd_report` exits with "Could not read edited file" and does not fall back. Acceptable, just noting.
- **Repo name reference.** PRIVACY.md says reports become issues "in the axiom-csc repository". The actual URL target is `github.com/axiom-csc/axiom-skill/issues/new`. The org is `axiom-csc`; the repo is `axiom-claude-skill`. Mildly ambiguous; PRIVACY.md should name the repo, not the org.

## 5. Fix plan

Both BROKEN claims are doc-wording, not privacy regressions. The code is
more conservative than the doc:

- **1.4 fix** — Re-word to "If telemetry is enabled but no endpoint is set, events are not recorded at all" (which is what the code does and is the stronger privacy posture).
- **2.7 fix** — Re-word submission step to describe opening a prefilled GitHub issue URL for the user to submit, and mention the large-payload fallback to `axiom_case_report.json`.

Also:

- **4 (repo name)** — Clarify "axiom-csc/axiom-skill" where the doc currently says "axiom-csc".

No code changes required. Fixes land in a follow-up commit after this audit lands.
