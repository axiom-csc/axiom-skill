#!/usr/bin/env python3
"""Regression tests for encoded-payload execution patterns in extract_dangerous_bash.

Closes the README Known-gaps row: `base64 -d | bash`, xxd, hex decode patterns
piped to a shell. Also covers the subcase of Python `-c` one-liners that
decode-and-exec via os.system / subprocess / exec."""

import importlib.util
import pathlib
import sys
import unittest

LOWER_AST = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/axiom-csc/scripts/lower_ast.py"
)

spec = importlib.util.spec_from_file_location("lower_ast", LOWER_AST)
lower_ast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lower_ast)


def extract(command):
    return lower_ast.extract_dangerous_bash(command, tool_name="Bash")


class EncodedPayloadTests(unittest.TestCase):

    def test_base64_decode_piped_to_bash(self):
        ents = extract("base64 -d payload.b64 | bash")
        self.assertTrue(ents, "base64 -d | bash must be flagged")
        self.assertEqual(ents[0]["concept"], "dangerous_bash")

    def test_base64_long_flag_piped_to_sh(self):
        ents = extract("cat blob | base64 --decode | sh")
        self.assertTrue(ents, "base64 --decode | sh must be flagged")

    def test_openssl_base64_decode_piped_to_bash(self):
        ents = extract("cat blob | openssl base64 -d | bash")
        self.assertTrue(ents, "openssl base64 -d | bash must be flagged")

    def test_openssl_enc_d_base64(self):
        ents = extract("openssl enc -d -base64 -in blob | bash")
        self.assertTrue(ents, "openssl enc -d -base64 | bash must be flagged")

    def test_xxd_reverse_piped_to_bash(self):
        ents = extract("xxd -r hex.txt | bash")
        self.assertTrue(ents, "xxd -r | bash must be flagged")

    def test_xxd_plain_reverse_piped(self):
        ents = extract("xxd -ps -r hex.txt | sh")
        self.assertTrue(ents, "xxd -ps -r | sh must be flagged")

    def test_echo_blob_pipe_base64_pipe_bash(self):
        ents = extract("echo 'ZWNobyBoZWxsbw==' | base64 -d | bash")
        self.assertTrue(ents, "echo <blob> | base64 -d | bash must be flagged")

    def test_python_dash_c_base64_os_system(self):
        cmd = (
            "python3 -c \"import base64, os; "
            "os.system(base64.b64decode('ZWNobyBoZWxsbw==').decode())\""
        )
        ents = extract(cmd)
        self.assertTrue(ents, f"python -c with base64 + os.system must be flagged; got {ents}")

    def test_python_dash_c_codecs_decode_subprocess(self):
        cmd = (
            "python -c \"import codecs, subprocess; "
            "subprocess.run(codecs.decode('abcd', 'hex'))\""
        )
        ents = extract(cmd)
        self.assertTrue(ents, f"python -c with codecs + subprocess must be flagged; got {ents}")

    def test_plain_base64_decode_without_pipe_not_flagged(self):
        """A bare `base64 -d file > out` (no pipe to shell) must not fire.

        Guards against overfiring: decoding is only dangerous when piped to
        execution.
        """
        ents = extract("base64 -d payload.b64 > decoded.txt")
        self.assertFalse(
            ents, f"base64 -d without pipe-to-shell must not be flagged; got {ents}"
        )

    def test_plain_echo_pipe_base64_without_bash_not_flagged(self):
        ents = extract("echo 'YWJjZA==' | base64 -d > out")
        self.assertFalse(
            ents, f"echo | base64 -d without pipe-to-shell must not be flagged; got {ents}"
        )

    def test_tool_name_not_bash_skips(self):
        ents = lower_ast.extract_dangerous_bash(
            "base64 -d | bash", tool_name="Edit"
        )
        self.assertFalse(ents, "Non-Bash tool_name must skip these checks")


if __name__ == "__main__":
    unittest.main()
