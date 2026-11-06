"""Offline contract checks for mobile registration (no database or SMTP needed)."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class RegistrationVerificationTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[2] / "apps/api/routers/mobile_auth.py"
        tree = ast.parse(source.read_text())
        functions = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {
                "mobile_email_register", "mobile_email_login"
            }:
                node.decorator_list = []
                functions.append(node)
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *functions], type_ignores=[])

        class HTTPException(Exception):
            def __init__(self, status_code, detail):
                self.status_code, self.detail = status_code, detail

        self.error = HTTPException
        self.sent = Mock()
        self.token = Mock(side_effect=AssertionError("Registration must not issue a session"))
        self.namespace = {
            "Depends": lambda value: None, "get_db": Mock(),
            "HTTPException": HTTPException,
            "_normalize_email": lambda value: value.strip().lower(),
            "_validate_email_format": Mock(), "_email_rate_limit": Mock(),
            "_check_password_strength": lambda value: None,
            "hash_password": lambda value: "hashed", "verify_password": lambda *args: True,
            "normalize_locale": lambda value: value,
            "User": Mock(), "UserPreference": Mock(),
            "_send_verification_email": self.sent,
            "serialize_user": lambda user: {"email": user.email},
            "create_access_token": self.token, "TOKEN_TTL_SECONDS": 2592000,
            "utcnow": Mock(),
        }
        self.namespace["User"].side_effect = lambda **values: SimpleNamespace(
            id="user-1", preference=None, email_verified_at=None, **values
        )
        exec(compile(ast.fix_missing_locations(module), str(source), "exec"), self.namespace)
        self.db = Mock()
        self.db.query.return_value.filter.return_value.one_or_none.return_value = None
        self.payload = SimpleNamespace(email="new@example.com", password="Strong123", name="New", locale="en")

    def test_registration_requires_verification_and_sends_no_session(self):
        result = self.namespace["mobile_email_register"](self.payload, Mock(), self.db)
        user = self.sent.call_args.args[0]
        self.assertIsNone(user.email_verified_at)
        self.assertTrue(result["verification_required"])
        self.assertTrue(result["email_sent"])
        self.assertNotIn("access_token", result)
        self.token.assert_not_called()
        self.db.commit.assert_called_once()

    def test_delivery_failure_rolls_back_registration(self):
        self.sent.side_effect = RuntimeError("SMTP unavailable")
        with self.assertRaises(self.error) as caught:
            self.namespace["mobile_email_register"](self.payload, Mock(), self.db)
        self.assertEqual(caught.exception.status_code, 503)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.token.assert_not_called()

    def test_existing_account_is_not_changed(self):
        self.db.query.return_value.filter.return_value.one_or_none.return_value = object()
        with self.assertRaises(self.error) as caught:
            self.namespace["mobile_email_register"](self.payload, Mock(), self.db)
        self.assertEqual(caught.exception.status_code, 409)
        self.sent.assert_not_called()
        self.db.add.assert_not_called()

    def test_unverified_user_cannot_login(self):
        self.db.query.return_value.filter.return_value.one_or_none.return_value = SimpleNamespace(
            password_hash="hashed", email_verified_at=None
        )
        with self.assertRaises(self.error) as caught:
            self.namespace["mobile_email_login"](self.payload, Mock(), self.db)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["code"], "EMAIL_NOT_VERIFIED")
        self.token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
