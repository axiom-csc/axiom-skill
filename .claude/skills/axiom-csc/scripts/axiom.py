#!/usr/bin/env python3
"""axiom - CLI for axiom-csc: telemetry control and case reporting."""

import json
import os
import pathlib
import re
import sys
import time
import uuid
import webbrowser
from urllib.parse import urlencode

# Shared pattern source — see _secret_patterns.py. Importing from a sibling
# file requires sys.path to include this directory when invoked via `python3
# .claude/.../axiom.py` (it does — Python prepends the script's dir).
from _secret_patterns import REDACTOR_PATTERNS

CONFIG_DIR = pathlib.Path.home() / ".config" / "axiom-csc"
CONFIG_FILE = CONFIG_DIR / "config.json"
QUEUE_FILE = CONFIG_DIR / "queue.jsonl"
REPO_ISSUES = "https://github.com/axiom-csc/axiom-claude-skill/issues/new"
MAX_URL_LEN = 2000

# ── Config helpers ─────────────────────────────────────────────────────────

def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    except Exception:
        return {}


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── Secret redaction ───────────────────────────────────────────────────────
# Pattern list lives in _secret_patterns.py so the hook-side detector and
# this redactor can't drift. See that module's docstring.

SECRET_PATTERNS = REDACTOR_PATTERNS


def redact_secrets(text):
    for pat in SECRET_PATTERNS:
        text = re.sub(pat, '[REDACTED]', text)
    return text


# ── Local log helpers ──────────────────────────────────────────────────────

def find_local_log():
    """Walk up from CWD looking for .axiom/local_log.jsonl"""
    p = pathlib.Path.cwd()
    for _ in range(10):
        candidate = p / ".axiom" / "local_log.jsonl"
        if candidate.exists():
            return candidate
        parent = p.parent
        if parent == p:
            break
        p = parent
    return None


def load_local_log(log_file):
    entries = []
    for line in log_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries


# ── Subcommands ────────────────────────────────────────────────────────────

def cmd_telemetry(args):
    if not args:
        print("Usage: axiom telemetry on|off|status")
        sys.exit(1)
    sub = args[0].lower()
    cfg = load_config()
    if "install_id" not in cfg:
        cfg["install_id"] = str(uuid.uuid4())
    if sub == "on":
        cfg["telemetry"] = True
        save_config(cfg)
        print("Telemetry enabled.")
        print(f"Install ID: {cfg['install_id']}")
        endpoint = cfg.get("endpoint", "")
        if not endpoint:
            print("No endpoint configured — events will be queued but not sent.")
            print(f"Set endpoint in {CONFIG_FILE} to start sending.")
    elif sub == "off":
        cfg["telemetry"] = False
        save_config(cfg)
        print("Telemetry disabled.")
    elif sub == "status":
        enabled = cfg.get("telemetry", False)
        endpoint = cfg.get("endpoint", "")
        queue_count = 0
        if QUEUE_FILE.exists():
            try:
                queue_count = sum(1 for l in QUEUE_FILE.read_text().splitlines() if l.strip())
            except Exception:
                pass
        print(f"Telemetry:  {'ON' if enabled else 'OFF'}")
        print(f"Install ID: {cfg.get('install_id', '(not set)')}")
        print(f"Endpoint:   {endpoint or '(none — events not sent even if telemetry is on)'}")
        print(f"Queue:      {queue_count} event(s) pending in {QUEUE_FILE}")
        print(f"Config:     {CONFIG_FILE}")
    else:
        print(f"Unknown subcommand: {sub}. Use on, off, or status.")
        sys.exit(1)


def cmd_report(args):
    log_file = find_local_log()
    if not log_file:
        print("No .axiom/local_log.jsonl found. Run axiom_init and make some edits first.")
        sys.exit(1)

    entries = load_local_log(log_file)
    if not entries:
        print("No decisions logged yet.")
        sys.exit(0)

    # Show last 10
    recent = entries[-10:]
    print("\nRecent decisions:")
    for i, e in enumerate(recent):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("ts", 0)))
        print(f"  [{i+1}] {ts}  {e.get('decision','?').upper():5}  {e.get('tool_name','?'):12}  {e.get('rule','?')}")

    try:
        raw = input("\nPick a number (or Enter to cancel): ").strip()
        if not raw:
            sys.exit(0)
        idx = int(raw) - 1
        if not (0 <= idx < len(recent)):
            print("Invalid choice.")
            sys.exit(1)
    except (ValueError, EOFError, KeyboardInterrupt):
        sys.exit(0)

    entry = recent[idx]

    print("\n  (1) False positive — blocked something fine")
    print("  (2) False negative — allowed something risky")
    try:
        kind_raw = input("Which? [1/2]: ").strip()
        kind = "false_positive" if kind_raw == "1" else "false_negative" if kind_raw == "2" else None
        if not kind:
            print("Cancelled.")
            sys.exit(0)
        note = input("Optional note (press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)

    # Redact secrets from the payload
    redacted_entry = json.loads(redact_secrets(json.dumps(entry)))

    payload = {
        "axiom_version": "1.2.2",
        "report_type": kind,
        "note": note,
        "decision": redacted_entry.get("decision"),
        "tool_name": redacted_entry.get("tool_name"),
        "rule": redacted_entry.get("rule"),
        "reason": redacted_entry.get("reason"),
        "tool_input_redacted": redacted_entry.get("tool_input"),
        "ts": redacted_entry.get("ts"),
    }

    # Open in $EDITOR for review
    editor = os.environ.get("EDITOR", "")
    payload_text = json.dumps(payload, indent=2)
    if editor:
        import tempfile, subprocess
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write(payload_text)
            tmpfile = f.name
        subprocess.run([editor, tmpfile])
        try:
            payload_text = pathlib.Path(tmpfile).read_text()
            payload = json.loads(payload_text)
            pathlib.Path(tmpfile).unlink(missing_ok=True)
        except Exception as ex:
            print(f"Could not read edited file: {ex}")
            sys.exit(1)
    else:
        print("\n--- Review payload (edit .axiom/local_log.jsonl to change, $EDITOR not set) ---")
        print(payload_text)
        print("---")

    print("\nThe following will be submitted as a public GitHub issue:")
    print(json.dumps(payload, indent=2))
    print()
    print("By submitting, you agree this case may be included in Axiom's public")
    print("benchmark under CC-BY-4.0. Don't submit proprietary code.")
    print()

    try:
        confirm = input("Type 'yes' to submit (anything else cancels): ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    if confirm.lower() != "yes":
        print("Cancelled.")
        sys.exit(0)

    # Build GitHub issue URL
    body = f"```json\n{json.dumps(payload, indent=2)}\n```"
    title = f"[Case] {kind.replace('_', ' ').title()} — {entry.get('tool_name','?')} / {entry.get('rule','?')}"
    params = urlencode({"title": title, "labels": "case-report", "body": body})
    url = f"{REPO_ISSUES}?{params}"

    if len(url) > MAX_URL_LEN:
        out = pathlib.Path.cwd() / "axiom_case_report.json"
        out.write_text(json.dumps(payload, indent=2))
        print(f"\nPayload too large for a URL. Saved to: {out}")
        print(f"Open a new issue at {REPO_ISSUES} and attach the file.")
    else:
        print(f"\nOpening browser: {url}")
        webbrowser.open(url)


# ── Main ───────────────────────────────────────────────────────────────────

USAGE = """axiom - Axiom CSC CLI

Commands:
  axiom telemetry on|off|status   Manage anonymous usage telemetry
  axiom report                    Submit a false positive / false negative case

Usage:
  python3 .claude/skills/axiom-csc/scripts/axiom.py <command> [args]
"""

COMMANDS = {"telemetry": cmd_telemetry, "report": cmd_report}

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)
    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}\n")
        print(USAGE)
        sys.exit(1)
    COMMANDS[cmd](argv[1:])
