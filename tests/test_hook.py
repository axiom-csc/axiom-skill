#!/usr/bin/env python3
"""Tests for pre_tool_use.py — asserts full hook JSON output and exit code."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import pathlib
import unittest

HOOK = pathlib.Path(__file__).parent.parent / ".claude/skills/axiom-csc/hooks/pre_tool_use.py"

MINIMAL_RULES = textwrap.dedent("""\
    rules:
      - concept: transaction_value
        op: lte
        value: 10000
        action_on_fail: BLOCK
      - concept: rate_limit_rpm
        op: lte
        value: 1000
        action_on_fail: BLOCK
""")


def run_hook(tool_name: str, tool_input: dict, project_dir: str) -> tuple[int, dict, str]:
    """Run the hook with the given payload; return (exit_code, stdout_json, stderr)."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": project_dir}
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, capture_output=True, text=True, env=env,
    )
    stdout = result.stdout.strip()
    try:
        out_json = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        out_json = {"_raw": stdout}
    return result.returncode, out_json, result.stderr


class HookTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        axiom_dir = pathlib.Path(self.tmp) / ".axiom"
        axiom_dir.mkdir()
        (axiom_dir / "invariants.yaml").write_text(MINIMAL_RULES)

    # 1. CSS-only edit — no matching entities → ALLOW
    def test_css_edit_allows(self):
        code, out, stderr = run_hook(
            "Edit",
            {"file_path": "src/CheckoutButton.tsx", "new_string": "color: red; font-size: 14px;"},
            self.tmp,
        )
        self.assertEqual(code, 0, f"Expected exit 0, got {code}. stderr={stderr}")
        self.assertEqual(out, {}, f"Expected no JSON on stdout for allow, got: {out}")
        self.assertIn("✓", stderr, f"Expected pass message in stderr, got: {stderr}")

    # 2. Payment $75,000 → DENY (transaction_value 75000 > lte 10000)
    def test_payment_violation_denies(self):
        code, out, stderr = run_hook(
            "Edit",
            {"new_string": "Set transaction limit to $75,000 for enterprise customers"},
            self.tmp,
        )
        self.assertEqual(code, 0, f"Expected exit 0 with JSON deny, got exit {code}")
        decision = out.get("hookSpecificOutput", {}).get("permissionDecision")
        self.assertEqual(decision, "deny", f"Expected deny, got: {out}")
        reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        self.assertIn("transaction_value", reason, f"Reason should mention rule: {reason}")

    # 3. Auth bypass: if user.id == 1 without an auth-path file_path → ALLOW (scope respected)
    def test_auth_bypass_id_check_no_path_allows(self):
        code, out, stderr = run_hook(
            "Write",
            {"content": "if user.id == 1:\n    return grant_admin_access()"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, "Scope respected: auth checks only fire in auth-related paths")

    # 4. DB constraint drop via Bash — MINIMAL_RULES has no dangerous_bash rule → ALLOW
    def test_db_constraint_drop_no_rule_allows(self):
        code, out, stderr = run_hook(
            "Bash",
            {"command": "psql $DB_URL -c 'ALTER TABLE payments DROP CONSTRAINT chk_amount'"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, "dangerous_bash rule not in MINIMAL_RULES — no block")

    # 5. README edit — no matching entities → ALLOW
    def test_readme_edit_allows(self):
        code, out, stderr = run_hook(
            "Edit",
            {"file_path": "README.md", "new_string": "Update heading from Installation to Getting Started"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {})
        self.assertIn("✓", stderr)

    # Missing policy: built-in default policy is active. A harmless Edit
    # passes; the stderr notice points at axiom_init for customization.
    def test_no_invariants_uses_builtin_default_with_hint(self):
        empty_dir = tempfile.mkdtemp()
        code, out, stderr = run_hook("Edit", {"new_string": "anything"}, empty_dir)
        self.assertEqual(code, 0)
        self.assertIn("Built-in default policy", stderr)
        self.assertIn("axiom_init", stderr)

    # 7. Non-intercepted tool passes through immediately
    def test_non_intercepted_tool_passthrough(self):
        code, out, stderr = run_hook("Read", {"file_path": "README.md"}, self.tmp)
        self.assertEqual(code, 0)
        self.assertEqual(out, {})

    # 8. NotebookEdit is intercepted
    def test_notebook_edit_intercepted(self):
        code, out, stderr = run_hook(
            "NotebookEdit",
            {"new_source": "Set payment cap to $99,999"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        decision = out.get("hookSpecificOutput", {}).get("permissionDecision")
        self.assertEqual(decision, "deny", f"NotebookEdit should be intercepted: {out}")


SECURITY_RULES = textwrap.dedent("""\
    rules:
      - concept: auth_hardcoded_id
        banned: true
        action_on_fail: BLOCK
      - concept: auth_uncond_return
        banned: true
        action_on_fail: BLOCK
      - concept: auth_role_literal
        banned: true
        action_on_fail: BLOCK
      - concept: auth_commented_check
        banned: true
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
""")


class HookSecurityTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        axiom_dir = pathlib.Path(self.tmp) / ".axiom"
        axiom_dir.mkdir()
        (axiom_dir / "invariants.yaml").write_text(SECURITY_RULES)

    def _decision(self, out):
        return out.get("hookSpecificOutput", {}).get("permissionDecision")

    # ── A. Auth pattern detection ──────────────────────────────────────────

    # A1. Hardcoded user.id == 1 in an auth path → DENY
    def test_auth_hardcoded_id_in_auth_path_denies(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/auth/middleware.py",
             "content": "if user.id == 1:\n    return True"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"auth_hardcoded_id in auth path must DENY: {out}")

    # A2. Same pattern in a non-auth path → ALLOW (scope respected)
    def test_auth_pattern_outside_auth_path_allows(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/utils/helpers.py",
             "content": "if user.id == 1:\n    return True"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, f"auth check must not fire outside auth paths: {out}")

    # A3. Commented-out auth check in auth path → DENY
    def test_auth_commented_check_in_auth_path_denies(self):
        code, out, stderr = run_hook(
            "Edit",
            {"file_path": "src/auth/middleware.py",
             "new_string": "# check permission before proceeding\ndef process(): pass"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"commented-out auth check must DENY: {out}")

    # ── B. Dangerous Bash commands ─────────────────────────────────────────

    # B1. DROP TABLE in Bash → DENY
    def test_dangerous_bash_drop_table_denies(self):
        code, out, stderr = run_hook(
            "Bash",
            {"command": "psql $DB_URL -c 'DROP TABLE payments'"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"DROP TABLE must DENY: {out}")

    # B2. Safe SELECT → ALLOW
    def test_dangerous_bash_safe_select_allows(self):
        code, out, stderr = run_hook(
            "Bash",
            {"command": "psql $DB_URL -c 'SELECT * FROM users LIMIT 10'"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, f"Safe SELECT must ALLOW: {out}")

    # B3. rm -rf on a non-tmp path → DENY
    def test_dangerous_bash_rm_rf_non_tmp_denies(self):
        code, out, stderr = run_hook(
            "Bash",
            {"command": "rm -rf /home/user/project_data"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"rm -rf on non-tmp path must DENY: {out}")

    # B4. git commit -m with dangerous words in message → ALLOW (string arg, not shell)
    def test_dangerous_bash_git_commit_msg_allows(self):
        code, out, stderr = run_hook(
            "Bash",
            {"command": "git commit -m \"fix rm -rf bug\""},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, f"git commit -m with 'rm -rf' in message must ALLOW: {out}")

    # B5. git commit -m "rm -rf /" — still a string, still must ALLOW
    def test_dangerous_bash_git_commit_literal_rm_allows(self):
        code, out, stderr = run_hook(
            "Bash",
            {"command": "git commit -m \"rm -rf /\""},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, f"git commit -m 'rm -rf /' must ALLOW (string, not command): {out}")

    # ── C. Secret / credential patterns ───────────────────────────────────

    # C1. Stripe live key → DENY
    def test_secret_stripe_key_denies(self):
        # Key split to avoid triggering GitHub push-protection on the literal
        fake_key = "sk_live_" + "abcdef1234567890xyz"
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/payments/checkout.py",
             "content": f"STRIPE_KEY = '{fake_key}'"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"Stripe live key must DENY: {out}")

    # C2. Env-var reference — no hardcoded value → ALLOW
    def test_secret_env_var_allows(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/app.py",
             "content": "api_key = os.environ.get('API_KEY')"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, f"env-var reference must ALLOW: {out}")

    # C3. AWS access key literal → DENY
    def test_secret_aws_key_denies(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/config.py",
             "content": "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"AWS access key must DENY: {out}")

    # ── D. Dependency confusion ────────────────────────────────────────────

    # D1. Typo 'reqeusts' (transposition of 'requests') → DENY
    def test_dep_confusion_reqeusts_typo_denies(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "requirements.txt",
             "content": "reqeusts==2.28.0\nflask==2.3.0\n"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"'reqeusts' typo must DENY: {out}")

    # D2. Exact known package name → ALLOW
    def test_dep_exact_match_allows(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "requirements.txt",
             "content": "requests==2.28.0\nnumpy==1.24.0\nflask==2.3.0\n"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {}, f"Exact known packages must ALLOW: {out}")

    # D3. Typo 'numpyy' (extra letter) → DENY
    def test_dep_confusion_numpyy_typo_denies(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "requirements.txt",
             "content": "numpyy==1.24.0\n"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"'numpyy' typo must DENY: {out}")

    # ── Addition 1: AST-based auth detection ──────────────────────────────

    # AST-1. Obfuscated spacing `user . id == 1` — AST ignores spaces → DENY
    def test_auth_ast_obfuscated_spacing_denies(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/auth/middleware.py",
             "content": "if user . id == 1:\n    return True\n"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"Obfuscated 'user . id == 1' must DENY via AST: {out}")

    # AST-2. Aliased comparison: uid = user.id; if uid == 1 → DENY
    def test_auth_ast_aliased_id_denies(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/auth/middleware.py",
             "content": "uid = user.id\nif uid == 1:\n    return True\n"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._decision(out), "deny",
                         f"Aliased 'uid = user.id; if uid == 1' must DENY via AST: {out}")

    # AST-3. True negative: comparing to another id attribute → ALLOW
    def test_auth_ast_legitimate_id_comparison_allows(self):
        code, out, stderr = run_hook(
            "Write",
            {"file_path": "src/auth/middleware.py",
             "content": "if user.id == session.user_id:\n    grant_access()\n"},
            self.tmp,
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, {},
                         f"Comparison to another id attribute must ALLOW: {out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
