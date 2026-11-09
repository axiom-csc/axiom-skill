#!/usr/bin/env python3
import json, sys, pathlib, argparse

OPS = {"lte": lambda a,b: a<=b, "gte": lambda a,b: a>=b, "lt": lambda a,b: a<b, "gt": lambda a,b: a>b, "eq": lambda a,b: a==b}

DEFAULT_RULES = {"rules": [
    {"concept": "transaction_value",  "op": "lte", "value": 10000, "action_on_fail": "BLOCK"},
    {"concept": "rate_limit_rpm",     "op": "lte", "value": 1000,  "action_on_fail": "BLOCK"},
    {"concept": "file_size_mb",       "op": "lte", "value": 100,   "action_on_fail": "BLOCK"},
    {"concept": "query_row_limit",    "op": "lte", "value": 10000, "action_on_fail": "BLOCK"},
    {"concept": "percentage_value",   "op": "lte", "value": 100,   "action_on_fail": "BLOCK"},
    {"concept": "retry_count",        "op": "lte", "value": 10,    "action_on_fail": "BLOCK"},
    # Security rules — always ban these patterns when found
    {"concept": "auth_hardcoded_id",    "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "auth_uncond_return",   "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "auth_role_literal",    "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "auth_commented_check", "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "dangerous_bash",       "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "auth_file_write",      "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "secret_pattern",       "banned": True, "action_on_fail": "BLOCK"},
    {"concept": "dep_confusion",        "banned": True, "action_on_fail": "BLOCK"},
]}

ASK_Q = {
    "role_assignment": "What explicit permissions should this role hold? (e.g., users:read, users:write)",
    "api_quota_daily": "What is the authorized daily API quota for this service?",
}

def _parse_yaml_rules(text):
    """Minimal parser for the flat rule list axiom_init generates — no PyYAML needed."""
    rules, current = [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('- ') or line == '-':
            if current.get('concept'):
                rules.append(current)
            current = {}
            line = line[2:].strip()
        if ':' in line:
            k, _, v = line.partition(':')
            k, v = k.strip(), v.strip()
            if v.lower() in ('true', 'yes'):    v = True
            elif v.lower() in ('false', 'no'): v = False
            else:
                try: v = int(v)
                except ValueError:
                    try: v = float(v)
                    except ValueError: v = v.strip('"\'')
            if k: current[k] = v
    if current.get('concept'):
        rules.append(current)
    return {"rules": rules}


def _merge_default_numeric(user_rules):
    """Merge DEFAULT_RULES op/value rules not already covered by the user's yaml.

    Banned security rules are intentionally excluded — they are opt-in via the
    generated invariants.yaml so that MINIMAL_RULES test fixtures stay predictable.

    Rules without a ``concept`` key (e.g. a user wrote ``field:`` by mistake)
    are skipped from the coverage set; they'll be dropped again downstream by
    :func:`solve`. Tolerating missing keys here keeps load_rules from
    crashing when PyYAML is installed and parses such a malformed rule.
    """
    covered = {r["concept"] for r in user_rules.get("rules", []) if "concept" in r}
    extras = [r for r in DEFAULT_RULES["rules"] if "op" in r and r["concept"] not in covered]
    if not extras:
        return user_rules
    return {"rules": list(user_rules.get("rules", [])) + extras}


def load_rules(path):
    p = pathlib.Path(path)
    if not p.exists():
        return DEFAULT_RULES
    text = p.read_text()
    # Try JSON first (superset), then PyYAML if installed, then built-in parser
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data is None:
        data = _parse_yaml_rules(text)
    return _merge_default_numeric(data)

def _disposition(rule, key, default):
    """Resolve a rule's disposition field (action_on_fail / action_on_missing).

    Only values the init template and DEFAULT_RULES emit are recognised: BLOCK
    and ASK. Anything else (including missing) falls back to ``default`` so a
    typo in the yaml cannot accidentally flip a BLOCK into an ALLOW.
    """
    raw = str(rule.get(key, "")).strip().upper()
    return raw if raw in ("BLOCK", "ASK") else default


def solve(ast_path, rules_path):
    try: ast = json.loads(pathlib.Path(ast_path).read_text())
    except FileNotFoundError:
        print("[Lemma]  ERROR: ast.json not found"); return 1
    rules = load_rules(rules_path).get("rules", [])
    nodes_by = {}
    for n in ast.get("nodes", []): nodes_by.setdefault(n["concept"], []).append(n)
    blocks, asks = [], []
    for rule in rules:
        # Silently skip malformed rules without a `concept` key. PyYAML will
        # happily parse a rule written with `field:` or any other key; we
        # treat those as "not a rule" rather than crashing on KeyError.
        if "concept" not in rule:
            continue
        concept = rule["concept"]
        nodes = nodes_by.get(concept, [])
        if rule.get("required") and not nodes:
            if "op" not in rule and not rule.get("banned"):
                # Legacy shape: `required: true` with no `op`/`banned` and no
                # entity in the ast means "ask the user about this concept".
                # Respect action_on_missing if present, defaulting to ASK.
                if _disposition(rule, "action_on_missing", "ASK") == "BLOCK":
                    blocks.append((concept, "<missing>", "required", "true"))
                else:
                    asks.append((concept, ASK_Q.get(concept, f"What is '{concept}'?")))
                continue
            # op-shaped or banned-shaped rules fall through to the normal
            # evaluation below (no nodes → nothing to compare → no violation).
        if rule.get("banned"):
            disp = _disposition(rule, "action_on_fail", "BLOCK")
            for n in nodes:
                if disp == "ASK":
                    asks.append((concept, f"'{concept}' pattern detected — confirm this is intended."))
                else:
                    blocks.append((concept, n["value"], "banned", "true"))
            continue
        if "op" in rule:
            op_fn = OPS.get(rule["op"])
            disp = _disposition(rule, "action_on_fail", "BLOCK")
            for n in nodes:
                if op_fn and not op_fn(n["value"], rule["value"]):
                    if disp == "ASK":
                        asks.append((concept, f"'{concept}' = {n['value']} violates {rule['op']} {rule['value']} — confirm this is intended."))
                    else:
                        blocks.append((concept, n["value"], rule["op"], rule["value"]))
    for concept, actual, op, bound in blocks:
        print(f"\u274c [Lemma BLOCK] AxiomConstraintViolation: {concept} = {actual} violates {op} {bound}")
    for concept, q in asks:
        print(f"\u2753 [Lemma ASK] UNKNOWN: '{concept}' — {q}")
    if blocks: return 1
    if asks: return 2
    print(f"\u2705 [Lemma ALLOW] All {len(rules)} invariant checks passed.")
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ast", default="ast.json")
    p.add_argument("--rules", default=".axiom/invariants.yaml")
    args = p.parse_args()
    sys.exit(solve(args.ast, args.rules))
