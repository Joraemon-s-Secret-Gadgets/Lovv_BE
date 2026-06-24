import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shared.auth import create_access_token
from shared.authorization import (
    AuthorizationError,
    ROLE_ADMIN,
    ROLE_DATA_PROVIDER,
    authenticated_principal,
    normalize_roles,
    require_admin_access,
    require_roles,
)


AUTH_ENV = {
    "AUTH_TOKEN_SIGNING_SECRET": "unit-test-signing-secret-with-enough-length",
    "AUTH_TOKEN_TTL_SECONDS": "900",
    "AUTH_ISSUER": "lovv-test-auth",
    "AUTH_AUDIENCE": "lovv-test-api",
}


def make_event(authorizer_context=None, headers=None):
    event = {
        "headers": headers or {},
        "requestContext": {"http": {"method": "GET"}},
    }
    if authorizer_context is not None:
        event["requestContext"]["authorizer"] = {"lambda": authorizer_context}
    return event


class AuthorizationTest(unittest.TestCase):
    def test_normalize_roles_accepts_authorizer_string_and_arrays(self):
        self.assertEqual(normalize_roles("R-USER, R-DATA-PROVIDER, R-USER"), ["R-USER", "R-DATA-PROVIDER"])
        self.assertEqual(normalize_roles(["R-USER", "R-ADMIN", "R-ADMIN"]), ["R-USER", "R-ADMIN"])
        self.assertEqual(normalize_roles({"not": "valid"}), [])

    def test_authenticated_principal_normalizes_roles_and_scopes(self):
        principal = authenticated_principal(
            make_event(
                {
                    "userId": "provider-1",
                    "sub": "provider-1",
                    "sessionId": "session-1",
                    "roles": "R-USER, R-DATA-PROVIDER",
                    "organization_ids": "org-1, org-2, org-1",
                    "regionIds": ["KR-42-150", "KR-42-150", "KR-42-170"],
                    "provider": "cognito",
                }
            )
        )

        self.assertEqual(principal["userId"], "provider-1")
        self.assertEqual(principal["sessionId"], "session-1")
        self.assertEqual(principal["roles"], ["R-USER", "R-DATA-PROVIDER"])
        self.assertEqual(principal["organizationIds"], ["org-1", "org-2"])
        self.assertEqual(principal["regionIds"], ["KR-42-150", "KR-42-170"])
        self.assertEqual(principal["provider"], "cognito")

    def test_require_roles_returns_principal_when_any_allowed_role_matches(self):
        principal = require_roles(
            make_event({"userId": "provider-1", "roles": ["R-USER", "R-DATA-PROVIDER"]}),
            {ROLE_ADMIN, ROLE_DATA_PROVIDER},
        )

        self.assertEqual(principal["userId"], "provider-1")
        self.assertEqual(principal["roles"], ["R-USER", "R-DATA-PROVIDER"])

    def test_require_roles_accepts_single_allowed_role_string(self):
        principal = require_roles(
            make_event({"userId": "admin-1", "roles": "R-ADMIN"}),
            ROLE_ADMIN,
        )

        self.assertEqual(principal["userId"], "admin-1")
        self.assertEqual(principal["roles"], ["R-ADMIN"])

    def test_require_roles_raises_role_forbidden_when_role_does_not_match(self):
        with self.assertRaises(AuthorizationError) as context:
            require_roles(
                make_event({"userId": "user-1", "roles": "R-USER"}),
                {ROLE_DATA_PROVIDER},
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.code, "ROLE_FORBIDDEN")

    def test_require_admin_access_uses_admin_access_error_code(self):
        with self.assertRaises(AuthorizationError) as context:
            require_admin_access(make_event({"userId": "provider-1", "roles": "R-DATA-PROVIDER"}))

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.code, "ADMIN_ACCESS_REQUIRED")

    def test_bearer_token_principal_is_supported_without_authorizer_context(self):
        with patch.dict(os.environ, AUTH_ENV, clear=True):
            token = create_access_token(user_id="admin-1", session_id="session-1", roles=[ROLE_ADMIN]).token
            principal = require_admin_access(make_event(headers={"Authorization": f"Bearer {token}"}))

        self.assertEqual(principal["userId"], "admin-1")
        self.assertEqual(principal["sessionId"], "session-1")
        self.assertEqual(principal["roles"], [ROLE_ADMIN])


if __name__ == "__main__":
    unittest.main()
