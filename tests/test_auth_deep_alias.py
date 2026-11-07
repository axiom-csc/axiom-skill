#!/usr/bin/env python3
"""Regression tests for N-hop user.id alias detection.

Backlog item 30. Closes the README Known-gaps row: "Aliased variables
more than one hop deep". The AST auth walker previously caught a single
alias (`uid = user.id; if uid == 1`) but gave up at two or more
indirections (`a = user.id; b = a; if b == 1`). Now resolved via
fixed-point iteration over single-Name assignments.
"""

import importlib.util
import pathlib
import unittest

LOWER_AST = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/axiom-csc/scripts/lower_ast.py"
)

spec = importlib.util.spec_from_file_location("lower_ast", LOWER_AST)
lower_ast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lower_ast)


def _auth_hits(text, file_path="src/auth/middleware.py"):
    return [
        e for e in lower_ast.extract_auth_patterns(text, file_path)
        if e["concept"] == "auth_hardcoded_id"
    ]


class DeepAliasTests(unittest.TestCase):

    def test_one_hop_still_works(self):
        """Regression: the pre-existing one-hop case stays caught."""
        ents = _auth_hits("uid = user.id\nif uid == 1:\n    return True")
        self.assertTrue(ents, f"one-hop alias should fire; got {ents}")

    def test_two_hop_alias(self):
        ents = _auth_hits(
            "a = user.id\n"
            "b = a\n"
            "if b == 1:\n"
            "    return True"
        )
        self.assertTrue(ents, f"two-hop alias should fire; got {ents}")

    def test_three_hop_alias(self):
        ents = _auth_hits(
            "a = user.id\n"
            "b = a\n"
            "c = b\n"
            "if c == 1:\n"
            "    return True"
        )
        self.assertTrue(ents, f"three-hop alias should fire; got {ents}")

    def test_long_chain_alias(self):
        chain = ["a0 = user.id"] + [f"a{i} = a{i-1}" for i in range(1, 10)]
        chain.append("if a9 == 1:\n    return True")
        ents = _auth_hits("\n".join(chain))
        self.assertTrue(ents, f"10-hop alias should fire; got {ents}")

    def test_alias_chain_from_current_user(self):
        """Transitive chain also resolves when the root is one of the other
        user-root names (current_user, request_user)."""
        ents = _auth_hits(
            "uid = current_user.id\n"
            "cached = uid\n"
            "if cached == 1:\n"
            "    return True"
        )
        self.assertTrue(ents, f"chain from current_user must fire; got {ents}")

    def test_unrelated_assignment_not_tainted(self):
        """A chain that starts from an unrelated variable must NOT be
        tagged — the fixed-point must only propagate from user.id."""
        ents = _auth_hits(
            "a = some_counter\n"
            "b = a\n"
            "if b == 1:\n"
            "    return True"
        )
        self.assertFalse(
            ents, f"chain not rooted in user.id must not fire; got {ents}"
        )

    def test_alias_assigned_from_name_but_not_tainted_root(self):
        """`b = a` where `a` is not an alias must not add `b`."""
        ents = _auth_hits(
            "a = 42\n"
            "b = a\n"
            "if b == 1:\n"
            "    return True"
        )
        self.assertFalse(
            ents, f"untainted chain must not fire; got {ents}"
        )

    def test_cycle_does_not_loop_forever(self):
        """A pathological cycle `a = b; b = a` must not infinite-loop the
        fixed-point. Neither is rooted in user.id, so no alias added."""
        ents = _auth_hits(
            "a = b\n"
            "b = a\n"
            "if a == 1:\n"
            "    return True"
        )
        # Just reaching this assertion means we didn't hang.
        self.assertFalse(ents)

    def test_cycle_with_tainted_entry(self):
        """A cycle that includes a tainted source — all cycle members
        become aliases at fixed point."""
        ents = _auth_hits(
            "a = user.id\n"
            "b = a\n"
            "a = b\n"      # redefines a from b (still tainted)
            "if a == 1:\n"
            "    return True\n"
            "if b == 1:\n"
            "    return True"
        )
        self.assertTrue(ents, f"tainted cycle should fire; got {ents}")

    def test_builtin_aliases_still_direct(self):
        """`user_id` and `userid` are pre-seeded aliases — no assignment
        chain needed."""
        ents = _auth_hits("if user_id == 1:\n    return True")
        self.assertTrue(ents)


if __name__ == "__main__":
    unittest.main()
