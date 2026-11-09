#!/usr/bin/env python3
import ast as _ast
import json, os, re, argparse, pathlib, sys

# Shared secret pattern source — see _secret_patterns.py. Keeps the hook
# detector and the CLI redactor from drifting.
_THIS_DIR = pathlib.Path(__file__).parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
from _secret_patterns import CREDENTIAL_PATTERNS

PATTERNS = [
    ("transaction_value", r'\$([0-9,]+(?:\.[0-9]{2})?)', "currency_usd", float),
    ("transaction_value", r'(?:max_?transaction|transaction_?(?:limit|cap|value|amount)|max_?(?:payment|charge|amount))\s*[=:]\s*(\d[\d,]*(?:\.\d+)?)', "assignment", float),
    ("rate_limit_rpm",    r'(\d+)\s*(?:req|requests|calls)\s*/\s*min', "rate_rpm", float),
    ("rate_limit_rps",    r'(\d+)\s*(?:req|requests|calls)\s*/\s*sec', "rate_rps", float),
    ("rate_limit_rpd",    r'(\d+)\s*(?:req|requests|calls)\s*/\s*day', "rate_rpd", float),
    ("file_size_mb",      r'(\d+(?:\.\d+)?)\s*MB', "size_mb", float),
    ("file_size_gb",      r'(\d+(?:\.\d+)?)\s*GB', "size_gb", float),
    ("query_row_limit",   r'LIMIT\s+(\d+)', "db_rows", int),
    ("timeout_seconds",   r'timeout[=:\s]+(\d+)\s*s', "seconds", int),
    ("role_assignment",   r'(?:role|permission|scope)\s*[:=]\s*["\']?(\w+)["\']?', "role_string", str),
    ("api_quota_daily",   r'(\d+)\s*(?:calls?|requests?)\s*(?:per|/)\s*day', "api_calls_day", int),
    ("percentage_value",  r'(\d+(?:\.\d+)?)\s*%', "percentage", float),
    ("retry_count",       r'(?:retries?|retry)\s*[:=]?\s*(\d+)', "count", int),
]

AUTH_DIRS = {"auth", "middleware", "permissions", "roles"}
DEP_FILES = {"requirements.txt", "package.json", "pyproject.toml", "go.mod"}

# Role literals the hook treats as suspicious in non-config auth paths.
# Extend via env `AXIOM_AUTH_ROLE_LITERALS` (comma-separated). Non-English
# entries cover the most common localisations — these are quoted-string
# literals, so "admin" and "администратор" both appear as `"admin"` or
# `"администратор"` in the code being written.
_DEFAULT_ROLE_LITERALS = (
    "admin", "superuser", "root",
    "administrador",                         # Spanish
    "administrateur",                        # French
    "administrator",                         # German, Dutch
    "администратор", "админ",                # Russian (Cyrillic)
    "管理员", "超级用户",                     # Chinese (simplified)
    "管理者",                                 # Japanese
)

# Comment terms treated as suspicious-check markers in auth paths. Extend
# via env `AXIOM_AUTH_COMMENT_TERMS` (comma-separated).
_DEFAULT_AUTH_COMMENT_TERMS = (
    "auth", "permission", "role", "check",
    "autorización", "permiso", "rol",        # Spanish
    "autorisation", "rôle",                  # French
    "berechtigung", "rolle",                 # German
    "авторизация", "проверка", "права", "роль",  # Russian
    "授权", "权限", "角色", "验证",            # Chinese
    "認証", "権限",                           # Japanese
)


def _env_extra(name):
    raw = os.environ.get(name, "")
    return tuple(t.strip() for t in raw.split(",") if t.strip())


def _role_literal_pattern():
    terms = _DEFAULT_ROLE_LITERALS + _env_extra("AXIOM_AUTH_ROLE_LITERALS")
    escaped = "|".join(re.escape(t) for t in terms)
    return rf'["\']({escaped})["\']'


def _auth_comment_pattern():
    terms = _DEFAULT_AUTH_COMMENT_TERMS + _env_extra("AXIOM_AUTH_COMMENT_TERMS")
    escaped = "|".join(re.escape(t) for t in terms)
    return rf'#[^\n]*(?:{escaped})[^\n]*'

KNOWN_PACKAGES = {
    "requests", "numpy", "flask", "django", "express", "react", "lodash", "axios",
    "pandas", "pytest", "fastapi", "uvicorn", "pillow", "typescript", "vue", "jest",
}

SECRET_PATTERNS = CREDENTIAL_PATTERNS


_NUMERIC_CONCEPT_KEYWORDS = {
    "transaction_value": ("max_transaction", "transaction_limit", "transaction_cap",
                          "transaction_value", "transaction_amount",
                          "max_payment", "max_charge", "max_amount"),
    "rate_limit_rpm": ("rate_limit_rpm", "max_rpm"),
    "file_size_mb": ("max_file_size_mb", "max_upload_mb", "max_size_mb"),
    "query_row_limit": ("max_rows", "row_limit", "query_row_limit"),
    "retry_count": ("max_retries", "retry_count"),
    "timeout_seconds": ("timeout_seconds", "timeout_s"),
}

# Unit-aware routing: identifiers that strongly imply bytes or KB get routed
# to `file_size_mb` with the value normalised to MB. Checked before the
# generic keyword map so `upload_bytes` isn't mis-tagged.
#
# (substring_hint, concept, divisor_to_normalise)
_UNIT_HINTS = [
    ("upload_bytes", "file_size_mb", 1024 * 1024),
    ("max_upload_size_bytes", "file_size_mb", 1024 * 1024),
    ("size_bytes", "file_size_mb", 1024 * 1024),
    ("file_bytes", "file_size_mb", 1024 * 1024),
    ("max_bytes", "file_size_mb", 1024 * 1024),
    ("upload_kb", "file_size_mb", 1024),
    ("size_kb", "file_size_mb", 1024),
    ("upload_kib", "file_size_mb", 1024),
    ("size_kib", "file_size_mb", 1024),
]


def _safe_eval_const_arith(node):
    """Reduce an ast expression to a number if it's a literal arithmetic over
    int/float constants. Returns None for anything else (names, calls,
    attribute access, etc.). Prevents RHS-with-variable from being folded."""
    if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, _ast.UnaryOp) and isinstance(node.op, (_ast.UAdd, _ast.USub)):
        inner = _safe_eval_const_arith(node.operand)
        if inner is None:
            return None
        return +inner if isinstance(node.op, _ast.UAdd) else -inner
    if isinstance(node, _ast.BinOp):
        left = _safe_eval_const_arith(node.left)
        right = _safe_eval_const_arith(node.right)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, _ast.Add): return left + right
            if isinstance(node.op, _ast.Sub): return left - right
            if isinstance(node.op, _ast.Mult): return left * right
            if isinstance(node.op, _ast.Div) and right != 0: return left / right
            if isinstance(node.op, _ast.FloorDiv) and right != 0: return left // right
            if isinstance(node.op, _ast.Pow) and abs(right) < 20: return left ** right
        except Exception:
            return None
    return None


def _extract_numeric_math_via_ast(text):
    """Pick up numeric assignments whose RHS is an arithmetic expression over
    literal constants, e.g. `MAX_TRANSACTION = 10000 * 8` → 80000.

    Scoped to target names in `_NUMERIC_CONCEPT_KEYWORDS`, matched
    case-insensitively against the identifier. Skips RHS values with Names,
    Calls, or Attributes — anything not computable from the literal alone.
    """
    try:
        tree = _ast.parse(text)
    except SyntaxError:
        return []

    entities = []
    # Walk Assign and AnnAssign nodes
    for node in _ast.walk(tree):
        targets, value = [], None
        if isinstance(node, _ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, _ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        folded = _safe_eval_const_arith(value)
        if folded is None:
            continue
        # Unit-hinted identifiers emit for bare constants too (a byte cap
        # is just as risky written as `104857600` as `100 * 1024 * 1024`).
        # Keyword-only matches require a computed RHS — bare constants
        # under those concepts are already caught by the regex pass.
        is_computed_rhs = isinstance(value, (_ast.BinOp, _ast.UnaryOp))
        for tgt in targets:
            name = getattr(tgt, "id", None)
            if not name:
                continue
            lname = name.lower()
            # Unit hint wins over the generic keyword map — a name like
            # `max_upload_size_bytes` should route to file_size_mb with a
            # bytes→MB conversion, not be left out.
            hinted = False
            for hint, concept, divisor in _UNIT_HINTS:
                if hint in lname:
                    converted = float(folded) / divisor
                    entities.append({
                        "id": f"ent_math_{concept}_{len(entities)}",
                        "concept": concept,
                        "value": converted,
                        "type": "assignment_math",
                        "source": f"{name} = <expr> → {folded} / {divisor} = {converted} MB",
                    })
                    hinted = True
                    break
            if hinted or not is_computed_rhs:
                continue
            for concept, keys in _NUMERIC_CONCEPT_KEYWORDS.items():
                if any(k in lname for k in keys):
                    entities.append({
                        "id": f"ent_math_{concept}_{len(entities)}",
                        "concept": concept,
                        "value": float(folded),
                        "type": "assignment_math",
                        "source": f"{name} = <expr> → {folded}",
                    })
                    break
    return entities


def extract(text):
    entities, seen = [], set()
    for concept, pattern, type_label, cast in PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            raw = m.group(1).replace(',', '')
            try: val = cast(raw)
            except ValueError: val = raw
            key = (concept, str(val))
            if key in seen: continue
            seen.add(key)
            entities.append({"id": f"ent_{concept}_{len(entities)}", "concept": concept, "value": val, "type": type_label, "source": m.group(0).strip()})
    for ent in _extract_numeric_math_via_ast(text):
        key = (ent["concept"], str(ent["value"]))
        if key in seen: continue
        seen.add(key)
        entities.append(ent)
    return entities


def _in_auth_path(file_path):
    if not file_path:
        return False
    parts = set(pathlib.Path(file_path).parts)
    return bool(parts & AUTH_DIRS)


def _levenshtein(a, b):
    if a == b: return 0
    if len(a) < len(b): a, b = b, a
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j] + (ca != cb), prev[j + 1] + 1, curr[j] + 1))
        prev = curr
    return prev[-1]


def _ast_extract_auth_violations(text):
    """Use Python's ast module to detect auth bypass patterns structurally.

    Catches obfuscated spacing (user . id == 1) and simple variable aliases
    (uid = user.id; if uid == 1:) that regex cannot reliably detect.
    Returns a list of entity dicts — empty on SyntaxError or non-Python content.
    """
    try:
        tree = _ast.parse(text)
    except SyntaxError:
        return []

    entities = []
    _USER_ROOTS = {"user", "current_user", "request_user"}

    # Pass 1: collect direct aliases — `uid = user.id`.
    id_aliases = {"user_id", "userid"}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Assign):
            for target in node.targets:
                if isinstance(target, _ast.Name) and isinstance(node.value, _ast.Attribute):
                    attr = node.value
                    if (isinstance(attr.value, _ast.Name) and
                            attr.attr == "id" and
                            attr.value.id in _USER_ROOTS):
                        id_aliases.add(target.id)

    # Pass 1b: transitive aliases — `b = a` where `a` is already an alias.
    # Fixed-point iteration so arbitrary-depth chains (`a = user.id; b = a;
    # c = b; d = c; if d == 1: …`) are all resolved. Bounded by alias count,
    # so termination is guaranteed on any valid AST. Each iteration stops
    # once no new alias was added.
    assigns = [n for n in _ast.walk(tree) if isinstance(n, _ast.Assign)]
    while True:
        changed = False
        for node in assigns:
            for target in node.targets:
                if (isinstance(target, _ast.Name) and
                        isinstance(node.value, _ast.Name) and
                        node.value.id in id_aliases and
                        target.id not in id_aliases):
                    id_aliases.add(target.id)
                    changed = True
        if not changed:
            break

    def _is_id_node(n):
        if isinstance(n, _ast.Attribute):
            return (isinstance(n.value, _ast.Name) and
                    n.attr == "id" and n.value.id in _USER_ROOTS)
        if isinstance(n, _ast.Name):
            return n.id in id_aliases
        return False

    # Pass 2: flag comparisons like `user.id == 1` or `uid == 1`
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Compare) and _is_id_node(node.left):
            for cmp in node.comparators:
                if isinstance(cmp, _ast.Constant) and isinstance(cmp.value, int):
                    entities.append({
                        "id": f"auth_hid_{len(entities)}", "concept": "auth_hardcoded_id",
                        "value": 1, "type": "auth_violation",
                        "source": f"id comparison to literal {cmp.value}",
                    })

    # Pass 3: flag `if <trivial_literal>: return True`
    for node in _ast.walk(tree):
        if isinstance(node, _ast.If):
            has_return_true = any(
                isinstance(s, _ast.Return) and
                isinstance(s.value, _ast.Constant) and s.value.value is True
                for s in node.body
            )
            if has_return_true:
                test = node.test
                is_trivial = (
                    isinstance(test, _ast.Constant) and test.value in (True, 1)
                )
                if is_trivial:
                    entities.append({
                        "id": f"auth_ucr_{len(entities)}", "concept": "auth_uncond_return",
                        "value": 1, "type": "auth_violation",
                        "source": "if <trivial>: return True",
                    })

    return entities


def extract_auth_patterns(text, file_path):
    """Flag suspicious auth patterns in auth-related files."""
    if not _in_auth_path(file_path):
        return []
    entities = []

    # auth_hardcoded_id and auth_uncond_return: AST-based (catches obfuscated spacing + aliases)
    entities.extend(_ast_extract_auth_violations(text))

    # Role string literals in non-config .py files. Multi-language via
    # _DEFAULT_ROLE_LITERALS + env override; see module-level constants.
    fname = pathlib.Path(file_path).name.lower()
    if fname.endswith('.py') and 'config' not in fname and 'setting' not in fname:
        for m in re.finditer(_role_literal_pattern(), text, re.IGNORECASE):
            entities.append({"id": f"auth_rol_{len(entities)}", "concept": "auth_role_literal",
                             "value": 1, "type": "auth_violation", "source": m.group(0).strip()})

    # Commented-out auth checks. Multi-language via _DEFAULT_AUTH_COMMENT_TERMS
    # + env override.
    for m in re.finditer(_auth_comment_pattern(), text, re.IGNORECASE):
        entities.append({"id": f"auth_cmt_{len(entities)}", "concept": "auth_commented_check",
                         "value": 1, "type": "auth_violation", "source": m.group(0).strip()[:80]})

    return entities


def extract_dangerous_bash(text, tool_name):
    """Flag dangerous shell patterns in Bash tool calls."""
    if tool_name.lower() != "bash":
        return []
    entities = []
    # Force-push: a destructive git operation whose string arg IS parsed by git,
    # not the shell, so the git short-circuit below would mask it. Check first.
    if re.search(r'\bgit\s+push\b[^|&;]*?\s(?:--force(?:-with-lease)?\b|-f\b|\+\S)', text):
        entities.append({"id": f"dbash_{len(entities)}", "concept": "dangerous_bash",
                         "value": 1, "type": "force_push", "source": "git push --force"})
    # git subcommands don't execute their string arguments (e.g. -m "...") as shell
    if re.match(r'\s*git\s+', text):
        return entities
    patterns = [
        r'(?:DROP\s+(?:TABLE|COLUMN|CONSTRAINT)|TRUNCATE\s+TABLE|ALTER\s+TABLE\s+\S+\s+DROP)',
        r'rm\s+-[^\s]*r[^\s]*\s+(?!/tmp|/var/tmp)\S+',
        # Disk-level commands: operate on raw block devices or partition tables
        # and can wipe a whole disk. The `\b.*/(?:dev|disk)` suffix limits
        # false positives on values like `dd=1`.
        r'\b(?:dd|mkfs(?:\.[a-z0-9]+)?|fdisk|parted|wipefs|sgdisk|shred)\b(?=[^|\n]*(?:/dev/|\sof=))',
        # Shell redirects writing to auth/credential files anywhere on the
        # system. Paired with extract_auth_file_write for Write/Edit tools.
        r'(?:>|>>|tee\s+(?:-a\s+)?)\s*(?:/etc/(?:passwd|shadow|sudoers(?:\.d/\S+)?)|'
        r'(?:[^\s]*/)?\.ssh/(?:authorized_keys|id_[a-z0-9]+|config)|'
        r'(?:[^\s]*/)?\.aws/credentials|'
        r'(?:[^\s]*/)?\.netrc|'
        r'(?:[^\s]*/)?\.docker/config\.json|'
        r'(?:[^\s]*/)?\.env(?:\.[a-z0-9_.-]+)?)',
        r'curl\s+[^\|\n]+\|\s*(?:bash|sh)\b',
        r'wget\s+[^\|\n]+\|\s*(?:bash|sh)\b',
        r'(?:>|>>|tee\s+)\.claude/settings\.json',
        r'(?:>|>>|tee\s+)\.axiom/',
        # Encoded-payload execution: a decoder (base64/xxd/openssl) piping
        # into a shell. Covers the obvious `base64 -d | bash`, `xxd -r | sh`
        # and the openssl variant. Closes the README "encoded payloads piped
        # to bash" known-gap row.
        r'(?:base64\s+(?:-d|--decode|-D)|openssl\s+(?:base64\s+-d|enc\s+-d\s+-base64)|xxd\s+-r|xxd\s+-ps\s+-r)[^\|\n]*\|\s*(?:bash|sh|zsh)\b',
        # `echo "<blob>" | base64 -d | bash` — decoder is downstream of echo.
        r'echo\s+["\']?[A-Za-z0-9+/=]{16,}["\']?\s*\|\s*(?:base64\s+(?:-d|--decode|-D)|xxd\s+-r|xxd\s+-ps\s+-r)\s*\|\s*(?:bash|sh|zsh)\b',
        # Python one-liners that execute a base64/hex-decoded blob via os.system,
        # subprocess.run, or exec(). Catches the "commands via Python
        # subprocess" known-gap row for the decode-and-run subcase. Lookaheads
        # match in either order — e.g. `os.system(base64.b64decode(...))` has
        # the exec call before the decoder.
        r'python3?\s+-c\s+["\'](?=.*(?:base64|codecs)\.[a-zA-Z_][a-zA-Z0-9_]*\()(?=.*(?:os\.system|subprocess\.[A-Za-z_]+|exec\s*)\()',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            entities.append({"id": f"dbash_{len(entities)}", "concept": "dangerous_bash",
                             "value": 1, "type": "dangerous_command", "source": m.group(0).strip()[:80]})
    return entities


AUTH_FILE_PATTERNS = (
    r'(?:^|/)\.ssh/(?:authorized_keys|id_[a-z0-9]+|config)$',
    r'(?:^|/)\.aws/credentials$',
    r'(?:^|/)\.netrc$',
    r'(?:^|/)\.docker/config\.json$',
    r'(?:^|/)\.env(?:\.[a-z0-9_.-]+)?$',
    r'^/etc/(?:passwd|shadow|sudoers(?:\.d/.+)?)$',
)


def extract_auth_file_write(file_path, tool_name):
    """Flag Write/Edit tools targeting auth/credential files.

    extract_dangerous_bash covers shell-redirect writes; this handles direct
    file-write tool calls that never pass through bash.
    """
    if tool_name.lower() not in ("write", "edit", "multiedit", "notebookedit"):
        return []
    if not file_path:
        return []
    for pat in AUTH_FILE_PATTERNS:
        if re.search(pat, file_path, re.IGNORECASE):
            return [{"id": "authw_0", "concept": "auth_file_write",
                     "value": 1, "type": "auth_file", "source": file_path[:80]}]
    return []


def extract_secret_patterns(text, tool_name):
    """Flag secret/credential patterns in file writes."""
    if tool_name.lower() not in ("write", "edit", "multiedit", "notebookedit"):
        return []
    entities = []
    for pat in SECRET_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            entities.append({"id": f"sec_{len(entities)}", "concept": "secret_pattern",
                             "value": 1, "type": "credential", "source": m.group(0).strip()[:40]})
    return entities


def extract_dep_confusion(text, file_path):
    """Flag close misspellings of known packages in dependency files."""
    fname = pathlib.Path(file_path).name.lower() if file_path else ""
    if fname not in DEP_FILES:
        return []
    entities = []
    candidates = set()
    if fname == "requirements.txt":
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            pkg = re.split(r'[><=!;@\s\[]', line)[0].strip().lower()
            if pkg:
                candidates.add(pkg)
    elif fname == "package.json":
        for m in re.finditer(r'"([a-zA-Z0-9@/_-]+)"\s*:', text):
            pkg = m.group(1).lstrip('@').lower()
            if pkg:
                candidates.add(pkg)
    elif fname in ("pyproject.toml", "go.mod"):
        for m in re.finditer(r'["\']?([a-zA-Z][a-zA-Z0-9_-]+)["\']?\s*[><=!]', text):
            candidates.add(m.group(1).lower())

    for pkg in candidates:
        if pkg in KNOWN_PACKAGES:
            continue
        for known in KNOWN_PACKAGES:
            if abs(len(pkg) - len(known)) > 2:
                continue
            dist = _levenshtein(pkg, known)
            threshold = 1 if len(known) <= 5 else 2
            if 0 < dist <= threshold:
                entities.append({
                    "id": f"dep_{len(entities)}", "concept": "dep_confusion",
                    "value": 1, "type": "dep_typosquatt",
                    "source": f"{pkg!r} ~= {known!r} (dist={dist})",
                })
                break
    return entities


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", default="ast.json")
    p.add_argument("--tool-name", default="")
    p.add_argument("--file-path", default="")
    args = p.parse_args()
    nodes = extract(args.input)
    nodes += extract_auth_patterns(args.input, args.file_path)
    nodes += extract_dangerous_bash(args.input, args.tool_name)
    nodes += extract_auth_file_write(args.file_path, args.tool_name)
    nodes += extract_secret_patterns(args.input, args.tool_name)
    nodes += extract_dep_confusion(args.input, args.file_path)
    pathlib.Path(args.out).write_text(json.dumps({"nodes": nodes}, indent=2))
    for n in nodes: print(f"[Noema]  {n['concept']} = {n['value']} ({n['type']})")
    print(f"[Noema]  {len(nodes)} Base Entities -> {args.out}")
