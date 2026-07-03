import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.app import handle_request
from admin.audit_logs_repository import InMemoryAuditLogRepository
from admin.mfa_repository import InMemoryAdminMfaRepository
from admin.mfa_service import AdminMfaService, PlaintextSecretCipher


FIXED_NOW = datetime(2026, 6, 30, 2, 0, 0, tzinfo=timezone.utc)


def make_event(method, path, body=None, session_id="session-1"):
    event = {
        "rawPath": path,
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "lambda": {
                    "userId": "admin-1",
                    "roles": "R-ADMIN",
                    "sessionId": session_id,
                    "email": "admin@example.com",
                }
            },
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


class FakeAdminUserRepository:
    def list_users(self):
        return [{"userId": "admin-1", "email": "admin@example.com", "roles": ["R-ADMIN"]}]


class AdminMfaAppTest(unittest.TestCase):
    def setUp(self):
        self.now = FIXED_NOW
        self.repository = InMemoryAdminMfaRepository()
        self.service = AdminMfaService(
            self.repository,
            PlaintextSecretCipher(),
            now_provider=lambda: self.now,
        )
        self.audit = InMemoryAuditLogRepository()

    def request(self, method, path, body=None, session_id="session-1"):
        return handle_request(
            make_event(method, path, body=body, session_id=session_id),
            repository=FakeAdminUserRepository(),
            audit_repository=self.audit,
            mfa_service=self.service,
            enforce_mfa=True,
        )

    def enroll_and_confirm(self):
        enrolled = self.request("POST", "/api/v1/admin/security/mfa/enroll", {})
        enrollment = json.loads(enrolled["body"])["enrollment"]
        code = pyotp.TOTP(enrollment["secret"]).at(self.now)
        confirmed = self.request("POST", "/api/v1/admin/security/mfa/confirm", {"code": code})
        return enrollment, json.loads(confirmed["body"])

    def test_admin_read_routes_need_role_only_and_mfa_status_is_accessible(self):
        # Per ADMIN_RBAC_SPEC, MFA is required only for high-risk approve/reject,
        # not for read/other admin routes. A role-authorized read succeeds
        # without an MFA session; high-risk approval MFA is covered elsewhere.
        users = self.request("GET", "/api/v1/admin/users")
        status = self.request("GET", "/api/v1/admin/security/mfa/status")

        self.assertEqual(users["statusCode"], 200)
        self.assertEqual(status["statusCode"], 200)
        self.assertFalse(json.loads(status["body"])["mfa"]["enrolled"])

    def test_enroll_confirm_and_access_protected_admin_route(self):
        enrollment, confirmed = self.enroll_and_confirm()
        allowed = self.request("GET", "/api/v1/admin/users")

        self.assertTrue(enrollment["provisioningUri"].startswith("otpauth://totp/"))
        self.assertEqual(len(confirmed["recoveryCodes"]), 8)
        self.assertTrue(confirmed["status"]["sessionVerified"])
        self.assertEqual(allowed["statusCode"], 200)
        self.assertEqual(
            [entry["action"] for entry in self.audit.entries],
            ["admin_mfa.enroll", "admin_mfa.confirm"],
        )

    def test_same_totp_code_cannot_be_reused(self):
        enrollment, _ = self.enroll_and_confirm()
        reused = self.request(
            "POST",
            "/api/v1/admin/security/mfa/verify",
            {"code": pyotp.TOTP(enrollment["secret"]).at(self.now)},
            session_id="session-2",
        )

        self.assertEqual(reused["statusCode"], 409)
        self.assertEqual(json.loads(reused["body"])["error"]["code"], "ADMIN_MFA_CODE_REUSED")
        audit = self.audit.entries[-1]
        self.assertEqual((audit["action"], audit["result"], audit["reasonCode"]), (
            "admin_mfa.verify", "denied", "ADMIN_MFA_CODE_REUSED"
        ))

    def test_admin_read_routes_do_not_require_new_mfa_session(self):
        enrollment, _ = self.enroll_and_confirm()
        readable_before_mfa = self.request("GET", "/api/v1/admin/users", session_id="session-2")
        self.now += timedelta(seconds=30)
        verified = self.request(
            "POST",
            "/api/v1/admin/security/mfa/verify",
            {"code": pyotp.TOTP(enrollment["secret"]).at(self.now)},
            session_id="session-2",
        )
        readable_after_mfa = self.request("GET", "/api/v1/admin/users", session_id="session-2")

        self.assertEqual(readable_before_mfa["statusCode"], 200)
        self.assertEqual(verified["statusCode"], 200)
        self.assertEqual(readable_after_mfa["statusCode"], 200)

    def test_five_invalid_codes_lock_mfa_temporarily(self):
        self.enroll_and_confirm()
        self.now += timedelta(seconds=30)
        for _ in range(5):
            response = self.request(
                "POST", "/api/v1/admin/security/mfa/verify", {"code": "000000"}, session_id="session-2"
            )
            self.assertEqual(response["statusCode"], 403)

        locked = self.request(
            "POST", "/api/v1/admin/security/mfa/verify", {"code": "000000"}, session_id="session-2"
        )
        self.assertEqual(locked["statusCode"], 429)
        self.assertEqual(json.loads(locked["body"])["error"]["code"], "ADMIN_MFA_LOCKED")
        denied = [entry for entry in self.audit.entries if entry["action"] == "admin_mfa.verify"]
        self.assertEqual(len(denied), 6)
        self.assertTrue(all(entry["result"] == "denied" for entry in denied))

    def test_recovery_code_is_single_use(self):
        _, confirmed = self.enroll_and_confirm()
        recovery_code = confirmed["recoveryCodes"][0]
        recovered = self.request(
            "POST",
            "/api/v1/admin/security/mfa/recover",
            {"recoveryCode": recovery_code},
            session_id="session-2",
        )
        reused = self.request(
            "POST",
            "/api/v1/admin/security/mfa/recover",
            {"recoveryCode": recovery_code},
            session_id="session-3",
        )

        self.assertEqual(recovered["statusCode"], 200)
        self.assertEqual(reused["statusCode"], 403)
        self.assertEqual(json.loads(reused["body"])["error"]["code"], "ADMIN_MFA_CODE_INVALID")


if __name__ == "__main__":
    unittest.main()
