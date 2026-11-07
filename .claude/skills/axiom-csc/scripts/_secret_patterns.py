"""Shared secret patterns for the hook (write-time detector) and the CLI
(case-report redactor).

The two sites had drifted — the detector in `lower_ast.py` caught
Stripe test keys and AWS-secret assignment forms that the redactor in
`axiom.py` did not. Since a case report may carry content the detector
didn't fire on (e.g. an allowed context, or a pattern added here
later), the redactor must be a strict superset of the detector.

Rule for future edits:
    CREDENTIAL_PATTERNS lists credential/secret-shaped tokens — both
    sites use this.
    PII_PATTERNS lists things we scrub only on submission (not on
    write). Redactor-only.
"""

CREDENTIAL_PATTERNS = [
    # AWS
    r'AKIA[0-9A-Z]{16}',
    r'(?:aws_secret_access_key|AWS_SECRET)[^\n]*?["\']([A-Za-z0-9/+=]{40})["\']',
    # Stripe (live and test — both can be sensitive in dev-chat contexts)
    r'sk_live_[a-zA-Z0-9]+',
    r'sk_test_[a-zA-Z0-9]+',
    # OpenAI
    r'sk-[A-Za-z0-9]{48}',
    # PEM private key — both the bare header and the full block are
    # treated as a secret marker.
    r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
    # Generic password/token/secret assignment to a non-trivial literal.
    r'(?:password|passwd|secret|api_key)\s*=\s*["\'][^"\'${\s]{4,}["\']',
    # Generic api_key/token/secret in header-style form: `token: abc123...`.
    # Overlaps with the assignment form but catches YAML/HTTP header shapes.
    r'(?i)(api[_-]?key|token|secret)["\s:=]+[\'"]?([a-zA-Z0-9+/]{20,})[\'"]?',
]

# Redactor-only: things to scrub from a case report before it hits GitHub,
# but we don't block code from being written that mentions them.
PII_PATTERNS = [
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',  # email
]

# Full redactor pattern set.
REDACTOR_PATTERNS = CREDENTIAL_PATTERNS + PII_PATTERNS
