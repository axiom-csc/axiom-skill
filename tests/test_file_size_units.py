#!/usr/bin/env python3
"""Regression tests for bytes/KB→MB routing in numeric assignments.

Backlog item 32. Closes the README Known-gaps row: `MAX_UPLOAD = 100 * 1024 * 1024`
(100 MB expressed as bytes) was being ignored by the file_size_mb rule.
Identifier-suffix hints (`_bytes`, `_kb`, `_kib`) now route the value
to `file_size_mb` with the right divisor.
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


def _vals(entities, concept):
    return [e["value"] for e in entities if e["concept"] == concept]


class ByteCapTests(unittest.TestCase):

    def test_bytes_cap_as_math_folds_to_mb(self):
        ents = lower_ast.extract("MAX_UPLOAD_BYTES = 100 * 1024 * 1024")
        vals = _vals(ents, "file_size_mb")
        self.assertIn(100.0, vals, f"100MB in bytes should route to file_size_mb=100; got {vals}")

    def test_bytes_cap_as_bare_constant_folds_to_mb(self):
        """A bare integer in bytes should still be recognised when the
        identifier carries a `_bytes` suffix."""
        ents = lower_ast.extract("MAX_UPLOAD_BYTES = 104857600")
        vals = _vals(ents, "file_size_mb")
        self.assertIn(100.0, vals, f"bare 104857600 bytes should route to 100 MB; got {vals}")

    def test_kb_cap_as_math_folds_to_mb(self):
        ents = lower_ast.extract("MAX_UPLOAD_KB = 500 * 1024")
        vals = _vals(ents, "file_size_mb")
        self.assertIn(500.0, vals, f"500 * 1024 KB should fold to 500 MB; got {vals}")

    def test_kib_cap_folds_to_mb(self):
        ents = lower_ast.extract("MAX_FILE_SIZE_KIB = 2048")
        vals = _vals(ents, "file_size_mb")
        self.assertIn(2.0, vals, f"2048 KiB should fold to 2 MB; got {vals}")

    def test_mb_identifier_still_works_as_mb(self):
        """Regression: a plain `_mb` identifier continues to route to
        file_size_mb at factor 1 via the keyword map."""
        ents = lower_ast.extract("MAX_FILE_SIZE_MB = 50 * 2")
        vals = _vals(ents, "file_size_mb")
        self.assertIn(100.0, vals, f"50 * 2 MB should stay 100 MB; got {vals}")

    def test_mb_identifier_without_math_no_duplication(self):
        """A bare `MAX_FILE_SIZE_MB = 100` (no math, no `MB` unit suffix in
        the RHS) is intentionally not picked up by the existing regex pass
        (which keys on `100 MB`, not an identifier suffix). The AST pass
        must not double-emit under `file_size_mb` either — bare constants
        without a unit hint fall through."""
        ents = lower_ast.extract("MAX_FILE_SIZE_MB = 100")
        vals = _vals(ents, "file_size_mb")
        # Keyword-path requires a computed RHS; unit-hint path requires
        # a bytes/KB/KiB substring. Neither applies → 0 entries.
        self.assertEqual(
            vals, [], f"should emit zero entries for this shape; got {vals}"
        )

    def test_name_without_hint_is_not_treated_as_bytes(self):
        """`max_upload` alone (no `_bytes`/`_kb`/`_mb`) must not be assumed
        to be in any particular unit — we skip rather than guess."""
        ents = lower_ast.extract("MAX_UPLOAD = 10000000")
        vals = _vals(ents, "file_size_mb")
        self.assertFalse(
            vals,
            f"ambiguous `MAX_UPLOAD` must not be guessed as bytes; got {vals}",
        )


if __name__ == "__main__":
    unittest.main()
