# @file tests/test_admin_high_risk_app.py
# @description Verifies high-risk admin approval routes, MFA gates, and audit outcomes.
# @author JJonyeok2
# @lastModified 2026-07-15

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.app import HIGH_RISK_MFA_MAX_AGE_SECONDS, handle_request
from admin.audit_logs_repository import InMemoryAuditLogRepository
from admin.high_risk_repository import InMemoryHighRiskChangeRepository
from admin.mfa_repository import InMemoryAdminMfaRepository
from admin.mfa_service import AdminMfaService, PlaintextSecretCipher


HIGH_RISK = "/api/v1/admin/high-risk-requests"
FIXED_NOW = datetime(2026, 6, 30, 2, 0, 0, tzinfo=timezone.utc)


def make_event(method, path, body=None, context=None, query=None):
    event = {
        "rawPath": path,
        "headers": {"content-type": "application/json"},
        "queryStringParameters": query,
        "requestContext": {"http": {"method": method}},
    }
    if context is not None:
        event["requestContext"]["authorizer"] = {"lambda": context}
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def admin_context(user_id="admin-1", session_id="sess-admin"):
    return {"userId": user_id, "roles": "R-ADMIN", "sessionId": session_id}


def super_admin_context(user_id="super-1", session_id="sess-super"):
    return {"userId": user_id, "roles": "R-SUPER-ADMIN", "sessionId": session_id}


def _iso(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class FailExecutionAuditRepository(InMemoryAuditLogRepository):
    def record(self, entry, transaction=None, strict=False):
        if entry.get("action", "").endswith(".execute"):
            raise RuntimeError("audit insert failed")
        return super().record(entry, transaction=transaction, strict=strict)


class FailOnPublishDestination(dict):
    def __setitem__(self, key, value):
        if key == "status" and value == "published":
            raise RuntimeError("forced destination update failure")
        return super().__setitem__(key, value)


class AdminHighRiskAppTests(unittest.TestCase):
    def setUp(self):
        self.now = FIXED_NOW
        self.audit = InMemoryAuditLogRepository()
        self.destinations = {}
        self.high_risk = InMemoryHighRiskChangeRepository(
            audit_repository=self.audit,
            destinations=self.destinations,
        )
        self.mfa_repository = InMemoryAdminMfaRepository()
        self.mfa_service = AdminMfaService(
            self.mfa_repository,
            PlaintextSecretCipher(),
            now_provider=lambda: self.now,
        )

    def _call(self, method, path, body=None, context=None, query=None):
        return handle_request(
            make_event(method, path, body=body, context=context, query=query),
            audit_repository=self.audit,
            high_risk_repository=self.high_risk,
            mfa_service=self.mfa_service,
            enforce_mfa=True,
        )

    def _record_mfa_session(self, user_id, session_id, method="totp", verified_at=None):
        verified = verified_at or self.now
        self.mfa_repository.record_session(
            user_id,
            session_id,
            _iso(verified),
            _iso(self.now + timedelta(hours=1)),
            method,
        )

    def _role_grant_payload(self):
        return {
            "operationType": "role_grant",
            "targetUserId": "target-1",
            "roleCode": "R-LOCAL-OPERATOR",
            "reason": "운영 담당자 권한 부여",
        }

    def _create_role_grant(self, context=None):
        context = context or admin_context()
        self._record_mfa_session(context["userId"], context["sessionId"])
        response = self._call("POST", HIGH_RISK, body=self._role_grant_payload(), context=context)
        self.assertEqual(response["statusCode"], 201)
        return json.loads(response["body"])["request"]

    def test_admin_creates_and_lists_high_risk_request(self):
        request = self._create_role_grant()
        listed = self._call("GET", HIGH_RISK, context=admin_context(), query={"status": "pending"})

        self.assertEqual(listed["statusCode"], 200)
        items = json.loads(listed["body"])["items"]
        self.assertEqual([item["id"] for item in items], [request["id"]])
        self.assertIn("high_risk_request.create", [entry["action"] for entry in self.audit.entries])

    def test_super_admin_can_create_and_list_high_risk_request(self):
        request = self._create_role_grant(context=super_admin_context())
        listed = self._call("GET", HIGH_RISK, context=super_admin_context(), query={"status": "pending"})

        self.assertEqual(listed["statusCode"], 200)
        self.assertEqual([item["id"] for item in json.loads(listed["body"])["items"]], [request["id"]])

    def test_regular_admin_cannot_approve_high_risk_request(self):
        request = self._create_role_grant()
        self._record_mfa_session("admin-2", "sess-admin-2")
        denied = self._call(
            "POST",
            f"{HIGH_RISK}/{request['id']}/approve",
            body={},
            context=admin_context("admin-2", "sess-admin-2"),
        )

        self.assertEqual(denied["statusCode"], 403)
        self.assertEqual(json.loads(denied["body"])["error"]["code"], "SUPER_ADMIN_REQUIRED")
        audit = self.audit.entries[-1]
        self.assertEqual((audit["action"], audit["result"], audit["reasonCode"]), (
            "high_risk_request.approve", "denied", "SUPER_ADMIN_REQUIRED"
        ))

    def test_super_admin_approval_requires_recent_totp_session(self):
        request = self._create_role_grant()
        no_mfa = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())
        self._record_mfa_session("super-1", "sess-super", method="recovery_code")
        recovery_session = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())

        self.assertEqual(no_mfa["statusCode"], 403)
        self.assertEqual(json.loads(no_mfa["body"])["error"]["code"], "ADMIN_MFA_REQUIRED")
        self.assertEqual(recovery_session["statusCode"], 403)
        self.assertEqual(json.loads(recovery_session["body"])["error"]["code"], "ADMIN_MFA_TOTP_REQUIRED")
        denied = [entry for entry in self.audit.entries if entry["action"] == "high_risk_request.approve"]
        self.assertEqual([entry["result"] for entry in denied], ["denied", "denied"])

    def test_super_admin_approval_rejects_expired_recent_mfa_and_audits_denial(self):
        request = self._create_role_grant()
        self._record_mfa_session(
            "super-1", "sess-super", verified_at=self.now - timedelta(seconds=HIGH_RISK_MFA_MAX_AGE_SECONDS + 1)
        )

        denied = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())

        self.assertEqual(json.loads(denied["body"])["error"]["code"], "ADMIN_MFA_REQUIRED")
        self.assertEqual((self.audit.entries[-1]["result"], self.audit.entries[-1]["reasonCode"]), (
            "denied", "ADMIN_MFA_REQUIRED"
        ))

    def test_super_admin_approves_role_grant_and_audits_execution(self):
        request = self._create_role_grant()
        self._record_mfa_session("super-1", "sess-super")
        approved = self._call(
            "POST",
            f"{HIGH_RISK}/{request['id']}/approve",
            body={"decisionReason": "승인"},
            context=super_admin_context(),
        )

        body = json.loads(approved["body"])["request"]
        actions = [entry["action"] for entry in self.audit.entries]
        self.assertEqual(approved["statusCode"], 200)
        self.assertEqual(body["status"], "executed")
        self.assertIn(("target-1", "R-LOCAL-OPERATOR", None), self.high_risk.role_assignments)
        self.assertIn("role_grant.execute", actions)
        self.assertIn("high_risk_request.approve", actions)

    def test_requester_cannot_approve_own_high_risk_request(self):
        request = self._create_role_grant(context=super_admin_context())
        blocked = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())

        self.assertEqual(blocked["statusCode"], 409)
        self.assertEqual(json.loads(blocked["body"])["error"]["code"], "SELF_APPROVAL_FORBIDDEN")
        self.assertEqual(self.audit.entries[-1]["result"], "denied")

    def test_super_admin_rejects_high_risk_request_and_audits_decision(self):
        request = self._create_role_grant()
        self._record_mfa_session("super-1", "sess-super")
        rejected = self._call(
            "POST",
            f"{HIGH_RISK}/{request['id']}/reject",
            body={"decisionReason": "근거 부족"},
            context=super_admin_context(),
        )

        body = json.loads(rejected["body"])["request"]
        self.assertEqual(rejected["statusCode"], 200)
        self.assertEqual(body["status"], "rejected")
        audit = next(entry for entry in self.audit.entries if entry["action"] == "high_risk_request.reject")
        self.assertEqual((audit["result"], audit["reasonCode"]), ("denied", "OPERATOR_REJECTED"))

    def test_region_grant_and_bulk_publish_execution_are_audited(self):
        self._record_mfa_session("admin-1", "sess-admin")
        region_created = self._call(
            "POST",
            HIGH_RISK,
            body={
                "operationType": "region_grant",
                "targetUserId": "target-1",
                "regionId": "KR-42-150",
                "reason": "지역 운영 범위 부여",
            },
            context=admin_context(),
        )
        for index in range(10):
            destination_id = f"monthly-{index + 1}"
            self.destinations[destination_id] = {"id": destination_id, "status": "candidate"}
        bulk_created = self._call(
            "POST",
            HIGH_RISK,
            body={
                "operationType": "bulk_publish",
                "destinationIds": list(self.destinations.keys()),
                "reason": "월간 추천 일괄 게시",
            },
            context=admin_context(),
        )
        self._record_mfa_session("super-1", "sess-super")

        region_request = json.loads(region_created["body"])["request"]
        bulk_request = json.loads(bulk_created["body"])["request"]
        region_approved = self._call("POST", f"{HIGH_RISK}/{region_request['id']}/approve", body={}, context=super_admin_context())
        bulk_approved = self._call("POST", f"{HIGH_RISK}/{bulk_request['id']}/approve", body={}, context=super_admin_context())

        actions = [entry["action"] for entry in self.audit.entries]
        bulk_body = json.loads(bulk_approved["body"])["request"]
        self.assertEqual(region_approved["statusCode"], 200)
        self.assertEqual(bulk_approved["statusCode"], 200)
        self.assertIn(("target-1", "KR-42-150", None), self.high_risk.region_assignments)
        self.assertTrue(all(destination["status"] == "published" for destination in self.destinations.values()))
        self.assertEqual(bulk_body["executionSummary"]["publishedCount"], 10)
        self.assertEqual(bulk_body["executionSummary"]["reflectionJobCount"], 40)
        self.assertIn("region_grant.execute", actions)
        self.assertIn("bulk_publish.execute", actions)

    def test_role_and_region_revoke(self):
        self.high_risk.role_assignments.add(("target-1", "R-LOCAL-OPERATOR", None))
        self.high_risk.region_assignments.add(("target-1", "KR-42-150", None))
        self._record_mfa_session("admin-1", "sess-admin")
        role = self._call("POST", HIGH_RISK, body={
            "operationType": "role_revoke", "targetUserId": "target-1",
            "roleCode": "R-LOCAL-OPERATOR", "reason": "담당 종료",
        }, context=admin_context())
        region = self._call("POST", HIGH_RISK, body={
            "operationType": "region_revoke", "targetUserId": "target-1",
            "regionId": "KR-42-150", "reason": "담당 지역 변경",
        }, context=admin_context())
        self._record_mfa_session("super-1", "sess-super")

        role_result = self._call("POST", f"{HIGH_RISK}/{json.loads(role['body'])['request']['id']}/approve", body={}, context=super_admin_context())
        region_result = self._call("POST", f"{HIGH_RISK}/{json.loads(region['body'])['request']['id']}/approve", body={}, context=super_admin_context())

        self.assertEqual((role_result["statusCode"], region_result["statusCode"]), (200, 200))
        self.assertFalse(self.high_risk.role_assignments)
        self.assertFalse(self.high_risk.region_assignments)

    def test_last_super_admin_revoke_is_denied_and_audited(self):
        self.high_risk.role_assignments.add(("target-super", "R-SUPER-ADMIN", None))
        self._record_mfa_session("admin-1", "sess-admin")
        created = self._call("POST", HIGH_RISK, body={
            "operationType": "role_revoke", "targetUserId": "target-super",
            "roleCode": "R-SUPER-ADMIN", "reason": "권한 회수",
        }, context=admin_context())
        request_id = json.loads(created["body"])["request"]["id"]
        self._record_mfa_session("super-1", "sess-super")

        denied = self._call("POST", f"{HIGH_RISK}/{request_id}/approve", body={}, context=super_admin_context())

        self.assertEqual(json.loads(denied["body"])["error"]["code"], "LAST_SUPER_ADMIN_REQUIRED")
        self.assertIn(("target-super", "R-SUPER-ADMIN", None), self.high_risk.role_assignments)
        self.assertEqual((self.audit.entries[-1]["result"], self.audit.entries[-1]["reasonCode"]), (
            "denied", "LAST_SUPER_ADMIN_REQUIRED"
        ))

    def test_duplicate_role_grant_and_reapproval_are_denied(self):
        request = self._create_role_grant()
        self.high_risk.role_assignments.add(("target-1", "R-LOCAL-OPERATOR", None))
        self._record_mfa_session("super-1", "sess-super")
        duplicate = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())
        self.high_risk.role_assignments.clear()
        approved = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())
        repeated = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())

        self.assertEqual(json.loads(duplicate["body"])["error"]["code"], "DUPLICATE_ACTIVE_ASSIGNMENT")
        self.assertEqual(approved["statusCode"], 200)
        self.assertEqual(json.loads(repeated["body"])["error"]["code"], "HIGH_RISK_REQUEST_ALREADY_DECIDED")
        self.assertEqual(self.audit.entries[-1]["result"], "denied")

    def test_bulk_publish_validation_failure_rolls_back_all_destinations(self):
        for index in range(10):
            destination_id = f"monthly-{index + 1}"
            self.destinations[destination_id] = {"id": destination_id, "status": "candidate"}
        self.destinations["monthly-10"]["status"] = "published"
        self._record_mfa_session("admin-1", "sess-admin")
        created = self._call("POST", HIGH_RISK, body={
            "operationType": "bulk_publish", "destinationIds": list(self.destinations),
            "reason": "일괄 게시",
        }, context=admin_context())
        request_id = json.loads(created["body"])["request"]["id"]
        self._record_mfa_session("super-1", "sess-super")

        failed = self._call("POST", f"{HIGH_RISK}/{request_id}/approve", body={}, context=super_admin_context())

        self.assertEqual(json.loads(failed["body"])["error"]["code"], "MONTHLY_TRANSITION_FORBIDDEN")
        self.assertTrue(all(self.destinations[f"monthly-{index}"]["status"] == "candidate" for index in range(1, 10)))
        self.assertFalse(self.high_risk.publish_jobs)
        self.assertEqual(self.audit.entries[-1]["result"], "failed")

    def test_bulk_publish_mid_update_failure_rolls_back_all_destinations(self):
        for index in range(10):
            destination_id = f"monthly-{index + 1}"
            row = {"id": destination_id, "status": "candidate"}
            self.destinations[destination_id] = FailOnPublishDestination(row) if index == 9 else row
        self._record_mfa_session("admin-1", "sess-admin")
        created = self._call("POST", HIGH_RISK, body={
            "operationType": "bulk_publish", "destinationIds": list(self.destinations),
            "reason": "일괄 게시",
        }, context=admin_context())
        request_id = json.loads(created["body"])["request"]["id"]
        self._record_mfa_session("super-1", "sess-super")

        failed = self._call("POST", f"{HIGH_RISK}/{request_id}/approve", body={}, context=super_admin_context())

        self.assertEqual(failed["statusCode"], 500)
        self.assertTrue(all(item["status"] == "candidate" for item in self.destinations.values()))
        self.assertFalse(self.high_risk.publish_jobs)
        self.assertEqual((self.audit.entries[-1]["result"], self.audit.entries[-1]["reasonCode"]), (
            "failed", "RuntimeError"
        ))

    def test_strict_audit_failure_rolls_back_business_change_and_records_failed_attempt(self):
        self.audit = FailExecutionAuditRepository()
        self.high_risk.audit = self.audit
        request = self._create_role_grant()
        self._record_mfa_session("super-1", "sess-super")

        failed = self._call("POST", f"{HIGH_RISK}/{request['id']}/approve", body={}, context=super_admin_context())

        self.assertEqual(failed["statusCode"], 500)
        self.assertFalse(self.high_risk.role_assignments)
        self.assertEqual(self.high_risk.requests[request["id"]]["status"], "pending")
        audit = self.audit.entries[-1]
        self.assertEqual((audit["action"], audit["result"], audit["reasonCode"]), (
            "high_risk_request.approve", "failed", "RuntimeError"
        ))


if __name__ == "__main__":
    unittest.main()


# EOF: tests/test_admin_high_risk_app.py
