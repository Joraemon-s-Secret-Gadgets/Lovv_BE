# @file tests/test_admin_high_risk_db_integration.py
# @description Verifies transactional high-risk approval behavior against MySQL.
# @author JJonyeok2
# @lastModified 2026-07-15

import os
import sys
import threading
import unittest
import uuid
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.audit_logs_repository import RdsDataAuditLogRepository
from admin.high_risk_repository import HighRiskChangeError, RdsDataHighRiskChangeRepository
from shared.mysql_data import MySqlClient
from shared.rds_data import RdsDataClient


REQUESTER = "90000000-0000-0000-0000-000000000001"
APPROVER_1 = "90000000-0000-0000-0000-000000000002"
APPROVER_2 = "90000000-0000-0000-0000-000000000003"
TARGET_1 = "90000000-0000-0000-0000-000000000004"
TARGET_2 = "90000000-0000-0000-0000-000000000005"
NOW = "2026-07-01T00:00:00Z"


class RecordingCache:
    def __init__(self):
        self.invalidated = []

    def invalidate(self, user_id):
        self.invalidated.append(user_id)


class FailExecutionAudit:
    def __init__(self, delegate):
        self.delegate = delegate

    def record(self, entry, transaction=None, strict=False):
        if entry.get("action", "").endswith(".execute"):
            raise RuntimeError("forced strict audit failure")
        return self.delegate.record(entry, transaction=transaction, strict=strict)


@unittest.skipUnless(os.environ.get("RUN_ADMIN_DB_INTEGRATION") == "1", "live MySQL integration is opt-in")
class HighRiskMySqlIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db = MySqlClient()
        self._cleanup()
        for index, user_id in enumerate((REQUESTER, APPROVER_1, APPROVER_2, TARGET_1, TARGET_2), start=1):
            self.db.execute(
                """
                INSERT INTO users
                  (id, email, email_verified, display_name, status, created_at, updated_at)
                VALUES (:id, :email, TRUE, :display_name, 'active', :now, :now)
                """,
                {"id": user_id, "email": f"db-integration-{index}@lovv.local", "display_name": f"DB Test {index}", "now": NOW},
                include_result_metadata=False,
            )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        ids = (REQUESTER, APPROVER_1, APPROVER_2, TARGET_1, TARGET_2)
        params = {f"user_{index}": value for index, value in enumerate(ids)}
        placeholders = ", ".join(f":user_{index}" for index in range(len(ids)))
        # FK order matters; each delete is scoped to fixed integration-test UUIDs.
        for sql in (
            f"DELETE FROM admin_audit_logs WHERE actor_user_id IN ({placeholders})",
            f"DELETE FROM admin_high_risk_change_requests WHERE requested_by IN ({placeholders}) OR decided_by IN ({placeholders})",
            f"DELETE FROM user_role_assignments WHERE user_id IN ({placeholders})",
            f"DELETE FROM users WHERE id IN ({placeholders})",
        ):
            try:
                self.db.execute(sql, params, include_result_metadata=False)
            except Exception:
                # Before 004 is applied, setup should fail at the actual test operation.
                pass

    def repository(self, cache=None):
        return RdsDataHighRiskChangeRepository(
            rds_client=MySqlClient(),
            audit_repository=RdsDataAuditLogRepository(rds_client=MySqlClient()),
            authz_cache=cache,
        )

    def _create_role_request(self, repository, target, operation="role_grant", role="R-LOCAL-OPERATOR"):
        return repository.create(
            {"userId": REQUESTER, "roles": ["R-ADMIN"], "sessionId": "integration-requester"},
            {"operationType": operation, "targetUserId": target, "roleCode": role, "reason": "DB integration"},
            NOW,
        )

    def _approver(self, user_id=APPROVER_1):
        return {"userId": user_id, "roles": ["R-SUPER-ADMIN"], "sessionId": f"session-{user_id}"}

    def test_role_grant_commits_strict_audit_and_invalidates_cache(self):
        cache = RecordingCache()
        repository = self.repository(cache)
        request = self._create_role_request(repository, TARGET_1)

        repository.approve(request["id"], self._approver(), NOW)

        assignment = self.db.fetch_one(
            "SELECT status FROM user_role_assignments WHERE user_id = :user_id AND role_code = 'R-LOCAL-OPERATOR'",
            {"user_id": TARGET_1},
        )
        audit = self.db.fetch_one(
            "SELECT result FROM admin_audit_logs WHERE resource_id = :request_id AND action = 'role_grant.execute'",
            {"request_id": request["id"]},
        )
        self.assertEqual(assignment["status"], "active")
        self.assertEqual(audit["result"], "succeeded")
        self.assertEqual(cache.invalidated, [TARGET_1])

    def test_strict_audit_failure_rolls_back_role_and_request_state(self):
        repository = self.repository()
        request = self._create_role_request(repository, TARGET_1)
        repository.audit = FailExecutionAudit(repository.audit)

        with self.assertRaisesRegex(RuntimeError, "forced strict audit failure"):
            repository.approve(request["id"], self._approver(), NOW)

        assignment = self.db.fetch_one(
            "SELECT id FROM user_role_assignments WHERE user_id = :user_id AND role_code = 'R-LOCAL-OPERATOR'",
            {"user_id": TARGET_1},
        )
        stored_request = self.db.fetch_one(
            "SELECT status FROM admin_high_risk_change_requests WHERE id = :id", {"id": request["id"]}
        )
        self.assertIsNone(assignment)
        self.assertEqual(stored_request["status"], "pending")

    def test_concurrent_revokes_preserve_one_super_admin(self):
        for index, target in enumerate((TARGET_1, TARGET_2), start=1):
            self.db.execute(
                """
                INSERT INTO user_role_assignments
                  (id, user_id, role_code, organization_id, status, valid_from,
                   granted_by, grant_reason, created_at, updated_at)
                VALUES (:id, :user_id, 'R-SUPER-ADMIN', NULL, 'active', :now,
                        :granted_by, 'integration seed', :now, :now)
                """,
                {"id": f"90000000-0000-0000-0000-00000000010{index}", "user_id": target, "now": NOW, "granted_by": REQUESTER},
                include_result_metadata=False,
            )
        repository = self.repository()
        requests = [
            self._create_role_request(repository, target, operation="role_revoke", role="R-SUPER-ADMIN")
            for target in (TARGET_1, TARGET_2)
        ]
        barrier = threading.Barrier(2)
        results = []

        def revoke(request, approver_id):
            local_repository = self.repository()
            barrier.wait()
            try:
                local_repository.approve(request["id"], self._approver(approver_id), NOW)
                results.append("executed")
            except HighRiskChangeError as error:
                results.append(error.code)

        threads = [
            threading.Thread(target=revoke, args=(requests[0], APPROVER_1)),
            threading.Thread(target=revoke, args=(requests[1], APPROVER_2)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        active = self.db.fetch_one(
            "SELECT COUNT(*) AS count FROM user_role_assignments WHERE role_code = 'R-SUPER-ADMIN' AND status = 'active'"
        )
        self.assertEqual(sorted(results), sorted(["executed", "LAST_SUPER_ADMIN_REQUIRED"]))
        self.assertEqual(active["count"], 1)


@unittest.skipUnless(os.environ.get("RUN_RDS_DATA_API_INTEGRATION") == "1", "live RDS Data API integration is opt-in")
class RdsDataApiLiveTransactionTests(unittest.TestCase):
    def test_commit_and_rollback_are_observable_in_audit_table(self):
        db = RdsDataClient()
        committed_id = str(uuid.uuid4())
        rolled_back_id = str(uuid.uuid4())
        insert = """
            INSERT INTO admin_audit_logs
              (id, occurred_at, actor_user_id, action, resource_type, resource_id,
               result, created_at)
            VALUES (:id, :now, NULL, 'integration.transaction', 'integration', :id,
                    'succeeded', :now)
        """
        try:
            with db.transaction() as transaction:
                transaction.execute(insert, {"id": committed_id, "now": NOW}, False)
            with self.assertRaisesRegex(RuntimeError, "rollback"):
                with db.transaction() as transaction:
                    transaction.execute(insert, {"id": rolled_back_id, "now": NOW}, False)
                    raise RuntimeError("rollback")

            self.assertIsNotNone(db.fetch_one("SELECT id FROM admin_audit_logs WHERE id = :id", {"id": committed_id}))
            self.assertIsNone(db.fetch_one("SELECT id FROM admin_audit_logs WHERE id = :id", {"id": rolled_back_id}))
        finally:
            db.execute("DELETE FROM admin_audit_logs WHERE id IN (:committed, :rolled_back)", {
                "committed": committed_id, "rolled_back": rolled_back_id,
            }, False)


if __name__ == "__main__":
    unittest.main()


# EOF: tests/test_admin_high_risk_db_integration.py
