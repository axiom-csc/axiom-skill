#!/usr/bin/env python3
"""Regression tests for non-English role literals + auth-comment terms.

Backlog item 31. Previously the detector hardcoded English-only
patterns (`admin|superuser|root`, `auth|permission|role|check`), so a
codebase using localised role names or commented-out check prose in
another language silently bypassed detection.
"""

import importlib.util
import os
import pathlib
import unittest

LOWER_AST = (
    pathlib.Path(__file__).parent.parent
    / ".claude/skills/axiom-csc/scripts/lower_ast.py"
)


def _load():
    """Reload the module so env-var overrides take effect per test."""
    spec = importlib.util.spec_from_file_location("lower_ast", LOWER_AST)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class RoleLiteralI18NTests(unittest.TestCase):

    def test_english_admin_still_flagged(self):
        """Regression: English `"admin"` continues to fire."""
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            'role = "admin"', "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_role_literal", kinds)

    def test_russian_administrator_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            'role = "администратор"', "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_role_literal", kinds, f"got entities: {ents}")

    def test_spanish_administrador_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            'rol = "administrador"', "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_role_literal", kinds, f"got entities: {ents}")

    def test_chinese_admin_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            'role = "管理员"', "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_role_literal", kinds, f"got entities: {ents}")

    def test_config_file_still_exempt(self):
        """Regression: the config-file exemption survives the refactor —
        a role literal in `settings.py` or `config.py` is not flagged."""
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            'ADMIN_ROLE = "admin"', "src/auth/config.py"
        )
        self.assertFalse(
            [e for e in ents if e["concept"] == "auth_role_literal"],
            "config.py must be exempt for role_literal",
        )

    def test_non_auth_path_not_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            'role = "администратор"', "src/utils/helpers.py"
        )
        self.assertEqual(ents, [], "non-auth-path must not fire")

    def test_env_override_adds_custom_term(self):
        try:
            os.environ["AXIOM_AUTH_ROLE_LITERALS"] = "custodian,владелец"
            lower_ast = _load()
            ents = lower_ast.extract_auth_patterns(
                'role = "custodian"', "src/auth/middleware.py"
            )
            kinds = [e["concept"] for e in ents]
            self.assertIn("auth_role_literal", kinds, f"custom term from env missed; ents={ents}")
        finally:
            os.environ.pop("AXIOM_AUTH_ROLE_LITERALS", None)


class AuthCommentI18NTests(unittest.TestCase):

    def test_english_check_still_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            "# check permission here", "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_commented_check", kinds)

    def test_russian_check_phrase_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            "# проверка прав пользователя", "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_commented_check", kinds, f"got entities: {ents}")

    def test_spanish_check_phrase_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            "# verificar permiso del usuario", "src/auth/middleware.py"
        )
        # "permiso" is in the Spanish list
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_commented_check", kinds, f"got entities: {ents}")

    def test_chinese_check_phrase_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            "# 权限 验证", "src/auth/middleware.py"
        )
        kinds = [e["concept"] for e in ents]
        self.assertIn("auth_commented_check", kinds, f"got entities: {ents}")

    def test_env_override_adds_custom_comment_term(self):
        try:
            os.environ["AXIOM_AUTH_COMMENT_TERMS"] = "gatekeeper,санкция"
            lower_ast = _load()
            ents = lower_ast.extract_auth_patterns(
                "# санкция not yet implemented", "src/auth/middleware.py"
            )
            kinds = [e["concept"] for e in ents]
            self.assertIn("auth_commented_check", kinds, f"custom term missed; ents={ents}")
        finally:
            os.environ.pop("AXIOM_AUTH_COMMENT_TERMS", None)

    def test_unrelated_comment_not_flagged(self):
        lower_ast = _load()
        ents = lower_ast.extract_auth_patterns(
            "# TODO: tidy up this file", "src/auth/middleware.py"
        )
        self.assertFalse(
            [e for e in ents if e["concept"] == "auth_commented_check"],
            f"benign comment must not fire; ents={ents}",
        )


if __name__ == "__main__":
    unittest.main()
