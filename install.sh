#!/usr/bin/env bash
set -euo pipefail
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

AXIOM_VERSION="v1.2.2"
# Default remote source. Can be overridden for smoke tests and offline installs
# via AXIOM_REPO_BASE — e.g. `AXIOM_REPO_BASE=file:///path/to/skill install.sh`.
# curl handles file:// natively, so the override works with no other changes.
REPO_BASE="${AXIOM_REPO_BASE:-https://raw.githubusercontent.com/axiom-csc/axiom-claude-skill/${AXIOM_VERSION}/.claude/skills/axiom-csc}"

# Download one file, fail loudly with a hint if the server 404s or the file
# comes back empty. A silent curl failure or partial fetch leaves a broken
# skill install, which is worse than no install.
fetch() {
  local url="$1" dest="$2"
  if ! curl -fsSL "$url" -o "$dest"; then
    echo -e "${RED}Error: failed to download ${url}.${NC}" >&2
    echo "  Check that tag ${AXIOM_VERSION} exists at" >&2
    echo "  https://github.com/axiom-csc/axiom-claude-skill/releases" >&2
    echo "  and that you have network access." >&2
    return 1
  fi
  if [[ ! -s "$dest" ]]; then
    echo -e "${RED}Error: ${dest} downloaded but is empty (from ${url}).${NC}" >&2
    rm -f "$dest"
    return 1
  fi
}

# ── Argument parsing ───────────────────────────────────────────────────────
GLOBAL_MODE=false
AGENTS_ARG=""
for arg in "$@"; do
  case "$arg" in
    --global)   GLOBAL_MODE=true ;;
    --agents=*) AGENTS_ARG="${arg#--agents=}" ;;
  esac
done

if [[ "$GLOBAL_MODE" == "true" ]]; then
  SKILL_DIR="$HOME/.claude/skills/axiom-csc"
  SETTINGS_FILE="$HOME/.claude/settings.json"
  HOOK_CMD="python3 $HOME/.claude/skills/axiom-csc/hooks/pre_tool_use.py"
else
  SKILL_DIR=".claude/skills/axiom-csc"
  SETTINGS_FILE=".claude/settings.json"
  HOOK_CMD="python3 .claude/skills/axiom-csc/hooks/pre_tool_use.py"
fi

# ── Uninstall ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "uninstall" ]]; then
  echo -e "${BLUE}==> Uninstalling Axiom CSC...${NC}"
  AXIOM_SETTINGS_FILE="$SETTINGS_FILE" python3 - <<'PYEOF'
import json, pathlib, os, sys
p = pathlib.Path(os.environ["AXIOM_SETTINGS_FILE"]).expanduser()
if p.exists():
    try:
        s = json.loads(p.read_text())
        pre = s.get("hooks", {}).get("PreToolUse", [])
        filtered = [e for e in pre if "axiom-csc" not in e.get("hooks", [{}])[0].get("command", "")]
        if len(filtered) < len(pre):
            s["hooks"]["PreToolUse"] = filtered
            p.write_text(json.dumps(s, indent=2))
            print(f"  Hook entry removed from {p}")
        else:
            print(f"  No axiom-csc entry found in {p}")
    except Exception as e:
        print(f"  Could not update {p}: {e}", file=sys.stderr)
else:
    print(f"  No {p} found")
PYEOF
  if [[ -d "$SKILL_DIR" ]]; then
    rm -rf "$SKILL_DIR"
    echo -e "${GREEN}  Removed $SKILL_DIR${NC}"
  fi
  CFG="$HOME/.config/axiom-csc/config.json"
  if [[ -f "$CFG" ]]; then
    read -r -p "  Remove telemetry config at $CFG? [y/N] " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
      rm -f "$CFG"
      echo -e "${GREEN}  Removed telemetry config${NC}"
    fi
  fi
  echo -e "${GREEN}✓ Uninstall complete${NC}"
  exit 0
fi

# ── Python version check ───────────────────────────────────────────────────
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null || {
  echo -e "${RED}Error: Python 3.8 or higher is required (found $(python3 --version 2>&1)).${NC}"
  exit 1
}

# ── Project root check ─────────────────────────────────────────────────────
if [[ "$GLOBAL_MODE" == "false" ]]; then
  if [[ ! -e ".git" && ! -f "package.json" && ! -f "pyproject.toml" && ! -f "Cargo.toml" ]]; then
    echo -e "${YELLOW}Warning: This doesn't look like a project root (no .git, package.json, pyproject.toml, or Cargo.toml found).${NC}"
    echo "Run install.sh from your project directory, or pass --global to install to ~/.claude/settings.json."
    if [[ -t 0 ]]; then
      echo ""
      read -r -p "Continue anyway? [y/N] " _yn
      [[ "$_yn" =~ ^[Yy]$ ]] || exit 1
    fi
  fi
fi

echo -e "${BLUE}==> Installing Axiom CSC ${AXIOM_VERSION}...${NC}"
mkdir -p "$SKILL_DIR/scripts" "$SKILL_DIR/references" "$SKILL_DIR/hooks"

fetch "$REPO_BASE/SKILL.md"                      "$SKILL_DIR/SKILL.md"
fetch "$REPO_BASE/hooks/pre_tool_use.py"         "$SKILL_DIR/hooks/pre_tool_use.py"
fetch "$REPO_BASE/scripts/lower_ast.py"          "$SKILL_DIR/scripts/lower_ast.py"
fetch "$REPO_BASE/scripts/eval_lemma.py"         "$SKILL_DIR/scripts/eval_lemma.py"
fetch "$REPO_BASE/scripts/axiom_init.py"         "$SKILL_DIR/scripts/axiom_init.py"
fetch "$REPO_BASE/scripts/axiom.py"              "$SKILL_DIR/scripts/axiom.py"
fetch "$REPO_BASE/scripts/axiom_flush.py"        "$SKILL_DIR/scripts/axiom_flush.py"
fetch "$REPO_BASE/references/INVARIANTS_SPEC.md" "$SKILL_DIR/references/INVARIANTS_SPEC.md"
chmod +x "$SKILL_DIR/hooks/"*.py "$SKILL_DIR/scripts/"*.py

# ── Register PreToolUse hook in settings.json ──────────────────────────────
AXIOM_SETTINGS_FILE="$SETTINGS_FILE" AXIOM_HOOK_CMD="$HOOK_CMD" python3 - <<'PYEOF'
import json, pathlib, os
p = pathlib.Path(os.environ["AXIOM_SETTINGS_FILE"]).expanduser()
p.parent.mkdir(parents=True, exist_ok=True)
try:
    s = json.loads(p.read_text()) if p.exists() else {}
except Exception:
    s = {}
cmd = os.environ["AXIOM_HOOK_CMD"]
entry = {"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
         "hooks": [{"type": "command", "command": cmd}]}
h = s.setdefault("hooks", {})
pre = h.setdefault("PreToolUse", [])
h["PreToolUse"] = [e for e in pre if "axiom-csc" not in e.get("hooks",[{}])[0].get("command","")] + [entry]
p.write_text(json.dumps(s, indent=2))
print(f"  Hook registered in {p}")
PYEOF

# ── Telemetry consent (TTY only, default No) ───────────────────────────────
python3 - <<'PYEOF'
import sys, json, pathlib, uuid
cfg_dir = pathlib.Path.home() / ".config" / "axiom-csc"
cfg_file = cfg_dir / "config.json"
try:
    cfg = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
except Exception:
    cfg = {}
if "telemetry" not in cfg:
    if sys.stdin.isatty():
        try:
            ans = input("\nShare anonymous usage stats to help improve Axiom?\n"
                        "Code, file paths and commands are never sent. (y/N): ").strip().lower()
            cfg["telemetry"] = ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            cfg["telemetry"] = False
    else:
        cfg["telemetry"] = False
if "install_id" not in cfg:
    cfg["install_id"] = str(uuid.uuid4())
if "endpoint" not in cfg:
    cfg["endpoint"] = ""
cfg_dir.mkdir(parents=True, exist_ok=True)
cfg_file.write_text(json.dumps(cfg, indent=2))
status = "enabled" if cfg["telemetry"] else "disabled (default)"
print(f"  Telemetry: {status}")
print(f"  Config: {cfg_file}")
PYEOF

# ── Agent compatibility (project mode only) ────────────────────────────────
if [[ "$GLOBAL_MODE" == "false" ]]; then
  if [[ -z "$AGENTS_ARG" ]] && [[ -t 0 ]]; then
    echo ""
    echo -e "${BLUE}==> Agent compatibility${NC}"
    echo "Which additional agents do you want to configure?"
    echo "Options: cursor  vscode  (space-separated, or press Enter to skip)"
    echo -e "${YELLOW}Default: Claude Code only (non-interactive install always skips):${NC} "
    read -r AGENTS_ARG || AGENTS_ARG=""
  fi

  if [[ "$AGENTS_ARG" == *"cursor"* ]]; then
    mkdir -p .cursor
    AXIOM_HOOK_CMD="$HOOK_CMD" python3 - <<'PYEOF'
import json, pathlib, os
p = pathlib.Path(".cursor/hooks.json")
p.parent.mkdir(parents=True, exist_ok=True)
cmd = os.environ["AXIOM_HOOK_CMD"]
entry = {"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
         "hooks": [{"type": "command", "command": cmd}]}
try:
    s = json.loads(p.read_text()) if p.exists() else {}
except Exception:
    s = {}
h = s.setdefault("PreToolUse", [])
s["PreToolUse"] = [e for e in h if "axiom-csc" not in e.get("hooks",[{}])[0].get("command","")] + [entry]
p.write_text(json.dumps(s, indent=2))
print(f"  Cursor hook registered in {p}")
PYEOF
  fi

  if [[ "$AGENTS_ARG" == *"vscode"* ]]; then
    mkdir -p .vscode
    AXIOM_HOOK_CMD="$HOOK_CMD" python3 - <<'PYEOF'
import json, pathlib, os
p = pathlib.Path(".vscode/axiom-task.json")
p.parent.mkdir(parents=True, exist_ok=True)
cmd = os.environ["AXIOM_HOOK_CMD"]
task = {
  "version": "2.0.0",
  "tasks": [{
    "label": "axiom-csc: check file on save",
    "type": "shell",
    "command": "echo '{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"${file}\",\"content\":\"\"}}' | " + cmd + " --stdin",
    "presentation": {"reveal": "silent", "panel": "shared"},
    "runOptions": {"runOn": "folderOpen"},
    "problemMatcher": []
  }]
}
p.write_text(json.dumps(task, indent=2))
print(f"  VS Code task written to {p}")
PYEOF
  fi
fi

# ── Auto-generate invariants (project mode only) ───────────────────────────
RULES_COUNT=0
INIT_NOTE=""
if [[ "$GLOBAL_MODE" == "false" ]]; then
  INIT_OUT=$(python3 "$SKILL_DIR/scripts/axiom_init.py" . 2>&1) && {
    # Count rules generated
    RULES_COUNT=$(python3 -c "
import pathlib, sys
try:
    import re
    text = pathlib.Path('.axiom/invariants.yaml').read_text()
    print(len(re.findall(r'^  - concept:', text, re.MULTILINE)))
except Exception:
    print(0)
" 2>/dev/null || echo 0)
  } || {
    INIT_NOTE="ℹ  Run \`python3 $SKILL_DIR/scripts/axiom_init.py .\` to generate rules from your codebase."
  }
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
SETTINGS_SHORT="$SETTINGS_FILE"
[[ "$SETTINGS_FILE" == "$HOME"* ]] && SETTINGS_SHORT="~${SETTINGS_FILE#$HOME}"
echo -e "${GREEN}  ✓ Hook registered in ${SETTINGS_SHORT}${NC}"
if [[ "$GLOBAL_MODE" == "false" && -z "$INIT_NOTE" ]]; then
  echo -e "${GREEN}  ✓ .axiom/invariants.yaml generated (${RULES_COUNT} rules)${NC}"
fi
echo -e "${GREEN}  ✓ Axiom ${AXIOM_VERSION} armed${NC}"
echo ""
if [[ -n "$INIT_NOTE" ]]; then
  echo -e "${YELLOW}  ${INIT_NOTE}${NC}"
  echo ""
fi
echo "  Test it: ask Claude to set a payment limit above your ceiling."
echo "  Docs:    https://github.com/axiom-csc/axiom-claude-skill"
echo ""
echo "Found a bypass? Open an issue: https://github.com/axiom-csc/axiom-claude-skill/issues"
echo "Built something with it? Drop a star: https://github.com/axiom-csc/axiom-claude-skill"
