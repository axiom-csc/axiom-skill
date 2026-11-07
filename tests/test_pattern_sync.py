#!/usr/bin/env python3
"""Regression tests for the CLI redactor / hook detector pattern sync.

Closes backlog item 24. The privacy audit (docs/privacy-audit.md § 4)
flagged that `axiom.py:SECRET_PATTERNS` was a proper subset of
`lower_ast.py:SECRET_PATTERNS` — notably the redactor missed Stripe
test keys and AWS-secret assignments that the detector caught. Both
sites now read from `_secret_patterns.py`; these tests enforce that
the credential set does not drift and that the redactor is a strict
superset of the detector.
"""

import importlib.util
import pathlib
import sys
import unittest

SCRIPTS = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/axiom-csc/scripts"
)

sys.path.insert(0, str(SCRIPTS))
import _secret_patterns  # noqa: E402

spec_ax = importlib.util.spec_from_file_location("axiom_cli", SCRIPTS / "axiom.py")
axiom_cli = importlib.util.module_from_spec(spec_ax)
spec_ax.loader.exec_module(axiom_cli)

spec_la = importlib.util.spec_from_file_location("lower_ast", SCRIPTS / "lower_ast.py")
lower_ast = importlib.util.module_from_spec(spec_la)
spec_la.loader.exec_module(lower_ast)


class PatternSyncTests(unittest.TestCase):

    def test_detector_patterns_identical_to_shared_source(self):
        self.assertEqual(
            list(lower_ast.SECRET_PATTERNS),
            list(_secret_patterns.CREDENTIAL_PATTERNS),
            "lower_ast.SECRET_PATTERNS must come from _secret_patterns.CREDENTIAL_PATTERNS",
        )

    def test_redactor_is_strict_superset_of_detector(self):
        redactor = set(axiom_cli.SECRET_PATTERNS)
        detector = set(lower_ast.SECRET_PATTERNS)
        missing = detector - redactor
        self.assertFalse(
            missing,
            f"redactor must scrub everything the detector catches; missing: {missing}",
        )

    def test_redactor_scrubs_stripe_test_key(self):
        """This is the exact drift the privacy audit flagged — must not reappear."""
        blob = "payload: sk_test_abc123DEFgh456jklMNO789pqr"
        out = axiom_cli.redact_secrets(blob)
        self.assertNotIn("sk_test_abc123DEFgh456jklMNO789pqr", out)
        self.assertIn("[REDACTED]", out)

    def test_redactor_scrubs_aws_secret_assignment(self):
        blob = 'aws_secret_access_key="AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd"'
        out = axiom_cli.redact_secrets(blob)
        self.assertNotIn("AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd", out)

    def test_redactor_still_scrubs_email(self):
        """Email is redactor-only (PII) — must survive the refactor."""
        blob = "contact alice@example.com"
        out = axiom_cli.redact_secrets(blob)
        self.assertNotIn("alice@example.com", out)
        self.assertIn("[REDACTED]", out)

    def test_detector_does_not_scrub_email(self):
        """Email must NOT be in the detector set — the hook shouldn't block
        a developer from writing an email into code."""
        blob = "contact alice@example.com"
        # Compile each detector pattern and check none fire on the email
        import re
        for pat in lower_ast.SECRET_PATTERNS:
            self.assertFalse(
                re.search(pat, blob),
                f"detector pattern {pat!r} fired on a bare email; detector must not treat emails as secrets",
            )


if __name__ == "__main__":
    unittest.main()
