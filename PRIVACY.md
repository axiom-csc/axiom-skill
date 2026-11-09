# Privacy Policy — Axiom CSC

## Telemetry

Axiom CSC collects **no data by default**. Telemetry is opt-in and is disabled unless you
explicitly enable it during install or run `axiom telemetry on`.

### What is sent when telemetry is on

Events are only transmitted if you have also configured an endpoint in
`~/.config/axiom-csc/config.json`. With no endpoint set, no event is recorded at all —
the queue file stays empty. This is stricter than queue-then-hold: nothing lands on
disk under `~/.config/axiom-csc/queue.jsonl` until both telemetry is on and an
endpoint is configured.

Each event contains **exactly** these fields (strict allowlist — built by explicit field
assignment, not by copying the tool input):

| Field | Value |
|-------|-------|
| `install_id` | Random UUID generated at install time. Not tied to your machine, username, or hardware. |
| `ts` | Unix timestamp of the event |
| `decision` | `allow`, `ask`, or `deny` |
| `rule_id` | The first violated or unknown concept (e.g. `transaction_value`), or `none` |
| `tool_name` | Claude Code tool name (e.g. `Edit`, `Bash`) |
| `latency_ms` | Hook evaluation time in milliseconds |
| `skill_version` | Axiom CSC version string |
| `os` | OS name string (e.g. `darwin`, `linux`) |
| `python` | Python major.minor (e.g. `3.11`) |

### What is NEVER sent

- Tool input, shell commands, code, or file contents
- File paths or file names
- Contents of `.axiom/invariants.yaml` or `.axiom/state.json`
- Environment variables
- Working directory or project name
- Hostname, username, or any hardware identifier

### How telemetry works

Events are appended to a local queue file (`~/.config/axiom-csc/queue.jsonl`) by the
hook. A background process (detached subprocess with a 2-second timeout) sends the queue
to the configured endpoint. Any network error is silently swallowed and never affects the
hook's decision. If the queue grows past 1,000 events, the oldest are dropped.

### Turning off telemetry

```bash
python3 .claude/skills/axiom-csc/scripts/axiom.py telemetry off
```

Or edit `~/.config/axiom-csc/config.json` and set `"telemetry": false`.

---

## Case reports (`axiom report`)

Case reports are always **voluntary and manual**. The hook never submits anything
automatically.

When you run `axiom report`:

1. You choose a specific decision from your local log.
2. Axiom scans the payload for secrets (API keys, private keys, emails) and redacts them.
3. You can open the payload in `$EDITOR` to remove anything else.
4. The full redacted payload is printed for your review.
5. You must type `yes` to confirm submission.
6. Axiom opens a prefilled **public GitHub issue** page in your browser at
   `github.com/axiom-csc/axiom-skill/issues/new`, with the title, body,
   and `case-report` label already set. **You** click Submit on GitHub after
   reviewing the prefilled form — nothing is posted automatically. If the
   payload is too large for a URL (over 2 KB), it is written to
   `axiom_case_report.json` in your current directory and you attach it to a
   new issue manually.

By submitting a case report, you agree it may be included in Axiom's public benchmark
dataset under the CC-BY-4.0 license. Do not submit proprietary code or business logic.

The local decision log (`.axiom/local_log.jsonl`) is never sent automatically and is
listed in `.gitignore` by `axiom_init.py` so it is not committed to your repository.

---

## Changes

This policy applies to Axiom CSC v1.0.0 and later. Changes will be noted in the
repository's git history.
