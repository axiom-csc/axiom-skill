#!/usr/bin/env python3
"""Regression tests for math-expression RHS in numeric assignments.

Closes the README Known-gaps row:
`MAX_TRANSACTION = 10000 * 8` was being read as `10000`, not `80000`.
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


def extract(text):
    return lower_ast.extract(text)


def _concept_values(entities, concept):
    return [e["value"] for e in entities if e["concept"] == concept]


class NumericMathTests(unittest.TestCase):

    def test_multiplication_is_folded(self):
        ents = extract("MAX_TRANSACTION = 10000 * 8")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(80000.0, vals, f"10000 * 8 should fold to 80000; got {vals}")

    def test_addition_is_folded(self):
        ents = extract("max_payment = 50000 + 25000")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(75000.0, vals, f"50000 + 25000 should fold to 75000; got {vals}")

    def test_subtraction_is_folded(self):
        ents = extract("transaction_cap = 100000 - 1")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(99999.0, vals, f"100000 - 1 should fold to 99999; got {vals}")

    def test_power_is_folded(self):
        ents = extract("max_charge = 10 ** 5")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(100000.0, vals, f"10 ** 5 should fold to 100000; got {vals}")

    def test_parenthesized_mixed_ops(self):
        ents = extract("MAX_TRANSACTION = (1000 + 500) * 10")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(15000.0, vals, f"(1000 + 500) * 10 should fold to 15000; got {vals}")

    def test_annotated_assign_folded(self):
        ents = extract("MAX_TRANSACTION: int = 10000 * 2")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(20000.0, vals, f"AnnAssign should fold; got {vals}")

    def test_rhs_with_variable_not_folded(self):
        """A variable on the RHS cannot be folded safely — must not fire."""
        ents = extract("base = 10000\nMAX_TRANSACTION = base * 8")
        vals = _concept_values(ents, "transaction_value")
        # The regex path may still see `base = 10000` as 10000, but the
        # math-fold path must NOT emit 80000 (since `base` is a Name).
        self.assertNotIn(80000.0, vals, f"Variable RHS must not be folded; got {vals}")

    def test_rhs_with_function_call_not_folded(self):
        ents = extract("MAX_TRANSACTION = int(getenv('X'))")
        vals = _concept_values(ents, "transaction_value")
        self.assertFalse(
            vals, f"Function-call RHS must not emit; got {vals}"
        )

    def test_other_concepts_fold_too(self):
        """Math fold applies to retry_count, rate_limit_rpm, etc."""
        ents = extract("MAX_RETRIES = 3 * 4")
        vals = _concept_values(ents, "retry_count")
        self.assertIn(12.0, vals, f"retry_count math must fold; got {vals}")

    def test_bare_constant_only_once(self):
        """A bare `MAX_TRANSACTION = 10000` (no math) stays caught by the
        regex path and is not duplicated by the AST pass."""
        ents = extract("MAX_TRANSACTION = 10000")
        vals = _concept_values(ents, "transaction_value")
        self.assertEqual(
            vals.count(10000.0),
            1,
            f"Bare constant should emit exactly once; got {vals}",
        )

    def test_non_python_syntax_does_not_crash(self):
        """A non-Python blob (e.g. SQL) must not raise; AST pass returns []."""
        ents = extract("DROP TABLE users; -- MAX_TRANSACTION = 99 * 99")
        # Regex pattern still won't match this exact form (no `=` after
        # the keyword), so we just assert no crash.
        self.assertIsInstance(ents, list)

    def test_unary_negation_is_folded(self):
        ents = extract("MAX_TRANSACTION = -10 * 5")
        vals = _concept_values(ents, "transaction_value")
        self.assertIn(-50.0, vals, f"Unary negation should fold; got {vals}")


if __name__ == "__main__":
    unittest.main()
