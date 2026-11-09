# Axiom — Local Guardrail for AI Coding Agents

![Hook](https://img.shields.io/badge/hook-PreToolUse-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Agents](https://img.shields.io/badge/agents-Claude%20Code%20%7C%20Cursor%20%7C%20Aider%20%7C%20Copilot-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

Axiom is a local guardrail for AI coding agents. It runs as a pre-write hook in Claude Code and Cursor, and as a stdin/stdout filter for any agent that can pipe tool calls through a subprocess. Zero dependencies. No API keys. No tokens. Blocks before the write.

[![M8ven Score](https://m8ven.ai/badge/mcp/axiom-csc-axiom-claude-skill-5qs6l4?v=fe87bd3203fb7efc545a95c4b466b13e)](https://m8ven.ai/mcp/axiom-csc-axiom-claude-skill-5qs6l4?s=readme)

![Axiom blocking a payment limit violation](demo.gif)

> Detection is regex and AST-pattern based, not semantic. A motivated agent or attacker can bypass these checks with minor obfuscation. This tool catches the most common accidental violations, not adversarial ones. For adversarial resistance, pair it with container isolation and branch protection.

```
       [ Claude Code / AI Agent Pipeline ]
                        |
                ( PreToolUse Hook )
                        |
+───────────────────────────────────────────────────+
|                 Axiom Core Engine                  |
| +─────────────────────────────────────────────+   |
| |   Noema: Scope-Aware AST Lowering Pipeline  |   |
| +─────────────────────+───────────────────────+   |
|                       |                           |
| +─────────────────────+───────────────────────+   |
| |   Lemma: Relational Logic Solver (Python)   |   |
| +─────────────────────+───────────────────────+   |
|                       |                           |
| +─────────────────────+───────────────────────+   |
| |   Manam: Tri-State Epistemic Controller     |   |
| +─────────────────────+───────────────────────+   |
+───────────────────────────────────────────────────+
                        |
        +───────────────+───────────────+
        v                               v
  [TRUE / FALSE]                   [UNKNOWN]
  (Permit Tool Run)             (Fail-Closed Halt)
```

The fail-closed path above applies within the rule pipeline **when a valid
`.axiom/invariants.yaml` is active**. With no policy file, v1.2.3 applies a
built-in default that blocks destructive shell commands, force-push, disk
tools, and writes to credential files, and lets everything else through.
With an empty, malformed or unreadable policy file, every intercepted
operation is denied. Versions ≤1.2.2 allowed destructive operations when
no policy file existed; see the [v1.2.3 release notes][release].

[release]: https://github.com/axiom-csc/axiom-skill/releases/tag/v1.2.3

## Install

Clone the desired release tag, then install from that checkout. Until the
patch is tagged, use the local review branch and the same commands below.
The installer reads `project.version` from `pyproject.toml` and copies all
payload files from that checkout; it never downloads a different version.

```bash
git clone https://github.com/axiom-csc/axiom-skill.git
cd axiom-skill
# For a published release: git checkout v<project.version>
bash install.sh
```

Contributor setup (Python 3.10+):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -ra
```

Runtime dependencies: none. pytest and PyYAML are development-only.
When policy is missing, empty, unreadable, or unsupported, the built-in
emergency policy denies **all** intercepted tool operations (including reads
through Bash). It blocks destructive commands and auth/credential writes by
default. Generate and review `.axiom/invariants.yaml` to enable normal policy
checks. This conservative fallback is not a semantic command sandbox.

## Uninstall

```bash
bash install.sh uninstall
```

## How it works

| Pass | Component | What it does |
|------|-----------|--------------|
| 1 | **Noema** | Extracts typed constraints from task context via regex patterns |
| 2 | **Lemma** | Evaluates them against your invariants (deterministic Python logic) |
| 3 | **Manam** | Enforces 3-state logic: TRUE / FALSE / UNKNOWN |

**On UNKNOWN** — Claude halts and asks the exact right question.
**On FALSE** — Claude outputs an `AxiomConstraintViolation` and stops.

## Agent compatibility

| Agent | Mode | Blocking? |
|-------|------|-----------|
| Claude Code | PreToolUse hook via `.claude/settings.json` | Yes — blocks before write |
| Cursor | `.cursor/hooks.json` (same format) | Yes — blocks before write |
| Aider / Continue / generic | `--stdin` mode (pipe JSON tool call) | Yes — if wired manually |
| VS Code + Copilot | File-save task (`.vscode/axiom-task.json`) | No — flags after write |

**Generic `--stdin` mode** — any agent that can pipe JSON through a subprocess:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"src/auth/middleware.py","content":"if user.id==1: return True"}}' \
  | python3 .claude/skills/axiom-csc/hooks/pre_tool_use.py --stdin
# exit 1 = deny, exit 2 = ask, exit 0 = allow
```

## What it catches

| Category | What Axiom catches | Known gaps |
|----------|--------------------|------------|
| **Payments / numeric bounds** | Hardcoded limits that don't match your policy; literal math expressions like `MAX_TRANSACTION = 10000 * 8` are folded (→ 80000) | Limits stored in variables (`max = 10000; amount > max`) |
| **Auth: hardcoded ID** | `user.id == 1` checks in auth paths (AST-based); arbitrary-depth variable aliases via fixed-point taint propagation (`a = user.id; b = a; c = b; if c == 1` fires) | — |
| **Auth: unconditional return** | `if True: return True` in auth paths | Complex conditional chains |
| **Auth: role literals** | `"admin"`, `"root"` in non-config auth files (plus `"administrador"`, `"администратор"`, `"管理员"`, etc.; extend via `AXIOM_AUTH_ROLE_LITERALS` env) | Config files exempt by design |
| **Auth: commented checks** | `# check permission` and localised equivalents (`# проверка прав`, `# verificar permiso`, `# 权限 验证`, etc.; extend via `AXIOM_AUTH_COMMENT_TERMS` env) | — |
| **Dangerous Bash** | DROP TABLE, rm -rf (non-tmp), curl\|bash, writes to .axiom/, encoded payloads piped to a shell (`base64 -d \| bash`, `xxd -r \| sh`, `openssl base64 -d \| bash`, `python -c "... base64 ... os.system(...)"`) | Multi-line commands, heredocs, shelling out via spawned Python subprocess files |
| **Secrets** | AWS keys, Stripe live/test keys, OpenAI keys, PEM blocks, hardcoded passwords | Secrets stored in variables before assignment; base64-encoded secrets |
| **Dependency confusion** | Misspellings of requests, numpy, flask, django, express, react, lodash, axios | Packages not in the hardcoded known list |
| **Rate limits** | Invented req/min values | Values in separate config files |
| **File uploads** | Assumed size caps, including byte-expressed caps (`MAX_UPLOAD_BYTES = 100 * 1024 * 1024` → routes to `file_size_mb = 100`) when the identifier carries a `_bytes`, `_kb`, or `_kib` suffix | Ambiguous identifiers (`MAX_UPLOAD = 10000000` without a unit suffix) are not guessed |
| **Database** | Arbitrary LIMIT clauses | LIMIT in comments or strings |
| **API quotas** | Made-up daily call limits | Quotas in env vars |

Auth checks are **path-scoped** — they only fire in files under `auth/`, `middleware/`, `permissions/`, or `roles/`. The same pattern in `src/utils/helpers.py` is allowed.

Auth bypass detection uses Python's `ast` module, so whitespace and simple aliases don't bypass it.

## Before / after example

**Without Axiom** — agent sets MAX_TRANSACTION higher than policy allows:

```python
# Claude writes:
MAX_TRANSACTION = 75000   # raised for enterprise tier
```

**With Axiom** (hook fires immediately on the Edit call):

```
❌ [Lemma BLOCK] AxiomConstraintViolation: transaction_value = 75000.0 violates lte 50000
[axiom-csc] Invariant violation: ❌ [Lemma BLOCK] AxiomConstraintViolation: transaction_value = 75000.0 violates lte 50000
```

Claude sees the denial reason and asks for clarification instead of silently writing the bad value.

To record the demo GIF: install [vhs](https://github.com/charmbracelet/vhs) (`brew install charmbracelet/tap/vhs`), then run:

```bash
vhs scripts/demo.tape
```

Or record with asciinema: `asciinema rec demo.cast && bash scripts/record_demo.sh` — upload the `.cast` file to asciinema.org and embed the link here.

## Demo — Auth pattern detection (new)

**Without Axiom:**
```python
# Claude writes to src/auth/middleware.py:
if user.id == 1:
    return True   # hardcoded ID bypass
```

**With Axiom:**
```
❌ [Lemma BLOCK] AxiomConstraintViolation: auth_hardcoded_id = 1 violates banned true
[axiom-csc] Invariant violation: auth_hardcoded_id — hardcoded user ID check detected in auth path
```

## Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| STRICT | _(default)_ | Halt on any UNKNOWN or violation |
| AUDIT | `[AXIOM: AUDIT]` anywhere in the tool call | Log the would-be disposition to `.axiom/local_log.jsonl`, pass the call through |

AUDIT runs the full pipeline, captures what STRICT would have done
(`allow` / `ask` / `deny`), and lets the call proceed. Use it to shake a
new rule set into shape without blocking real work.

## Usage

```bash
# Check telemetry status
python3 .claude/skills/axiom-csc/scripts/axiom.py telemetry status

# Enable / disable telemetry
python3 .claude/skills/axiom-csc/scripts/axiom.py telemetry on
python3 .claude/skills/axiom-csc/scripts/axiom.py telemetry off

# Submit a false positive / false negative case
python3 .claude/skills/axiom-csc/scripts/axiom.py report
```

## Custom rules

Edit `.axiom/invariants.yaml` (auto-generated by `axiom_init.py`):

```yaml
rules:
  - concept: transaction_value
    op: lte
    value: 50000
    action_on_fail: BLOCK

  - concept: dangerous_bash
    banned: true
    action_on_fail: BLOCK

  - concept: secret_pattern
    banned: true
    action_on_fail: BLOCK

  - concept: dep_confusion
    banned: true
    action_on_fail: BLOCK

  - concept: role_assignment
    required: true
    action_on_missing: ASK
```

**Rule fields:**

| Field | Meaning |
|-------|---------|
| `op: lte` + `value: N` | Fail if extracted numeric value exceeds N |
| `banned: true` | Fail if any matching entity is found in the tool call |
| `required: true` | Ask for clarification if the entity is not found |

## Known limitations

| Limitation | Why |
|------------|-----|
| Semantic bypasses | An agent can write `50000 + 25000` or put values in variables — Noema extracts literals only |
| Container escape | Axiom runs inside the agent's process; a compromised container can bypass the hook entirely |
| Single call scope | The hook sees one tool call at a time — invariants spread across files are not checked |
| Path-scope bypass | Auth checks only cover the four named directories; a renamed auth module is not caught |
| Edit-distance coverage | Dependency confusion uses a fixed known-package list — typos against unlisted packages are missed |

Axiom is a first line of defense, not a complete security layer. Use it alongside proper code review, CI checks, secret scanning (gitleaks), and least-privilege infrastructure.

## Privacy

Telemetry is **off by default**. When enabled:

**What is sent:**
- A random install ID (uuid4, not tied to your machine or account)
- Timestamp, decision (allow/ask/deny), rule ID, tool name, latency, skill version, OS name, Python version

**What is NEVER sent:**
- Tool input, code, file paths, file names, shell commands
- Contents of `invariants.yaml`, env vars, CWD, or project names

**How to turn off:**
```bash
python3 .claude/skills/axiom-csc/scripts/axiom.py telemetry off
```
Or set `"telemetry": false` in `~/.config/axiom-csc/config.json`.

`axiom report` is always **manual**: you pick the case, review the redacted payload, and explicitly type `yes` to submit. Reports become public GitHub issues under CC-BY-4.0.

See [PRIVACY.md](PRIVACY.md) for full details.

## FAQ

**Q: Why not use Claude Code's plugin marketplace?**

Claude Code's plugin marketplace distributes MCP servers and slash-command skills — it does not currently support PreToolUse hooks, which is the hook type this tool requires to block before a write happens. Installing via this script is the only supported path until Anthropic adds marketplace support for hooks. When they do, we'll publish there.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues tagged on GitHub — S3 file size extractor, Kubernetes quota templates, Supabase RLS parser.

## License

MIT · [Axiom CSC](https://github.com/axiom-csc)
