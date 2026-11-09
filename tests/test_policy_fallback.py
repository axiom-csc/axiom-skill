import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / '.claude/skills/axiom-csc/hooks/pre_tool_use.py'

DESTRUCTIVE = (
    [('Bash', {'command': x}) for x in (
        'rm -rf /outside-project', 'git push --force origin main',
        'psql -c "DROP TABLE users"', 'psql -c "TRUNCATE TABLE users"',
        'dd if=/dev/zero of=/dev/disk0', 'mkfs.ext4 /dev/disk0',
        'echo bad >> /etc/passwd', 'echo key >> ~/.ssh/authorized_keys')]
    + [('Write', {'file_path': x, 'content': 'overwrite'}) for x in
       ('/home/u/.aws/credentials', '/home/u/.ssh/authorized_keys',
        '/etc/shadow', '/srv/app/.env')]
)

HARMLESS = (
    [('Bash', {'command': x}) for x in (
        'ls', 'ls -la src/', 'pwd', 'git status', 'echo hello',
        'cat README.md', 'python -m pytest tests/test_foo.py')]
    + [('Write', {'file_path': x, 'content': 'print("hi")'}) for x in
       ('src/new_module.py', 'docs/notes.md', 'tests/test_x.py')]
)


def _run(tool, tool_input, project_dir, stdin=False):
    return subprocess.run(
        [sys.executable, str(HOOK)] + (['--stdin'] if stdin else []),
        input=json.dumps({'tool_name': tool, 'tool_input': tool_input}),
        text=True, capture_output=True,
        env={**os.environ, 'CLAUDE_PROJECT_DIR': project_dir})


class MissingPolicyFirstRunTests(unittest.TestCase):
    """With no .axiom/invariants.yaml, built-in default policy is active:
    destructive ops blocked, harmless ops allowed, one-line notice printed."""

    def test_destructive_payloads_are_blocked_with_no_policy(self):
        for tool, tool_input in DESTRUCTIVE:
            for stdin in (True, False):
                with tempfile.TemporaryDirectory() as tmp:
                    with self.subTest(tool=tool, payload=tool_input, stdin=stdin):
                        proc = _run(tool, tool_input, tmp, stdin=stdin)
                        if stdin:
                            self.assertNotEqual(
                                proc.returncode, 0,
                                f'expected deny, got allow\nstderr={proc.stderr}')
                        else:
                            decision = json.loads(proc.stdout)['hookSpecificOutput']['permissionDecision']
                            self.assertEqual(
                                decision, 'deny',
                                f'expected deny\nstdout={proc.stdout}\nstderr={proc.stderr}')

    def test_harmless_operations_pass_with_no_policy(self):
        for tool, tool_input in HARMLESS:
            with tempfile.TemporaryDirectory() as tmp:
                with self.subTest(tool=tool, payload=tool_input):
                    proc = _run(tool, tool_input, tmp, stdin=True)
                    self.assertEqual(
                        proc.returncode, 0,
                        f'expected allow, got deny\nstderr={proc.stderr}')

    def test_notice_identifies_default_policy_and_how_to_customize(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run('Bash', {'command': 'ls'}, tmp, stdin=True)
            self.assertIn('Built-in default policy', proc.stderr)
            self.assertIn('axiom_init.py', proc.stderr)


class BadPolicyStateDenyAllTests(unittest.TestCase):
    """An EMPTY, MALFORMED, UNREADABLE or INVALID policy still denies
    every intercepted operation — the 1.2.3 patch's original guarantee."""

    BAD_STATES = {
        'empty': '',
        'malformed': 'rules: [broken',
        'invalid_json': '{"rules":[{"concept":"dangerous_bash","banned":"false"}]}',
        'unreadable': 'rules:\n  - concept: dangerous_bash\n    banned: true\n',
    }

    PAYLOADS = DESTRUCTIVE + HARMLESS

    def test_bad_policies_deny_everything(self):
        for state, content in self.BAD_STATES.items():
            for tool, tool_input in self.PAYLOADS:
                for stdin in (True, False):
                    with tempfile.TemporaryDirectory() as tmp:
                        policy = Path(tmp) / '.axiom/invariants.yaml'
                        policy.parent.mkdir()
                        policy.write_text(content)
                        if state == 'unreadable':
                            policy.chmod(0)
                        try:
                            with self.subTest(state=state, tool=tool, payload=tool_input, stdin=stdin):
                                proc = _run(tool, tool_input, tmp, stdin=stdin)
                                self.assertNotEqual(proc.returncode, 0,
                                                    proc.stdout + proc.stderr)
                                self.assertIn('Create a policy', proc.stderr)
                                if not stdin:
                                    decision = json.loads(proc.stdout)['hookSpecificOutput']['permissionDecision']
                                    self.assertEqual(decision, 'deny')
                        finally:
                            if policy.exists():
                                policy.chmod(0o600)
