import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.audit_logs_repository import RdsDataAuditLogRepository


class FakeSqlClient:
    def __init__(self, rows_by_table=None, fail_tables=None):
        self.rows_by_table = rows_by_table or {}
        self.fail_tables = set(fail_tables or [])
        self.calls = []

    def fetch_all(self, sql, parameters=None):
        self.calls.append({"sql": sql, "parameters": parameters or {}})
        normalized = " ".join(sql.split())
        for table in self.fail_tables:
            if f"FROM {table}" in normalized:
                raise RuntimeError(f"{table} unavailable")
        for table, rows in self.rows_by_table.items():
            if f"FROM {table}" in normalized:
                return list(rows)
        return []


def audit_row(**overrides):
    row = {
        "id": "audit-1",
        "occurred_at": "2026-07-10T00:00:00Z",
        "actor_user_id": "admin-1",
        "session_id": "sess-1",
        "roles_snapshot": '["R-ADMIN"]',
        "organization_ids_snapshot": "[]",
        "region_ids_snapshot": "[]",
        "action": "data_proposal.approve",
        "resource_type": "data_proposal",
        "resource_id": "proposal-1",
        "result": "succeeded",
        "reason_code": None,
        "before_summary_json": "{}",
        "after_summary_json": '{"status":"approved"}',
        "metadata_json": "{}",
        "created_at": "2026-07-10T00:00:00Z",
    }
    row.update(overrides)
    return row


class RdsDataAuditLogRepositoryDisplayTests(unittest.TestCase):
    def test_list_hydrates_actor_and_resource_display_fields(self):
        client = FakeSqlClient(
            rows_by_table={
                "admin_audit_logs": [audit_row()],
                "users": [{
                    "id": "admin-1",
                    "display_name": "Admin One",
                    "nickname": "admin",
                    "email": "admin@example.com",
                    "status": "active",
                }],
                "admin_data_proposals": [{
                    "id": "proposal-1",
                    "title": "Gangneung Coffee Festival",
                    "proposal_code": "PROP-000001",
                }],
            }
        )
        repo = RdsDataAuditLogRepository(rds_client=client)

        items = repo.list()

        self.assertEqual(items[0]["actorUserId"], "admin-1")
        self.assertEqual(items[0]["actorDisplayName"], "Admin One")
        self.assertEqual(items[0]["actorEmail"], "admin@example.com")
        self.assertEqual(items[0]["resourceType"], "data_proposal")
        self.assertEqual(items[0]["resourceId"], "proposal-1")
        self.assertEqual(items[0]["resourceDisplayName"], "Gangneung Coffee Festival (PROP-000001)")

    def test_list_keeps_audit_rows_when_display_joins_fail(self):
        client = FakeSqlClient(
            rows_by_table={"admin_audit_logs": [audit_row()]},
            fail_tables={"users", "admin_data_proposals"},
        )
        repo = RdsDataAuditLogRepository(rds_client=client)

        with self.assertLogs("admin.audit_logs_repository", level="WARNING"):
            items = repo.list()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["actorUserId"], "admin-1")
        self.assertEqual(items[0]["resourceId"], "proposal-1")
        self.assertIsNone(items[0]["actorDisplayName"])
        self.assertIsNone(items[0]["actorEmail"])
        self.assertIsNone(items[0]["resourceDisplayName"])

    def test_inactive_actor_masks_email_and_uses_deleted_user_label(self):
        client = FakeSqlClient(
            rows_by_table={
                "admin_audit_logs": [audit_row(actor_user_id="admin-2", resource_type="admin_mfa", resource_id="admin-2")],
                "users": [{
                    "id": "admin-2",
                    "display_name": "Former Admin",
                    "nickname": "former",
                    "email": "former@example.com",
                    "status": "withdrawn",
                }],
            }
        )
        repo = RdsDataAuditLogRepository(rds_client=client)

        items = repo.list()

        self.assertEqual(items[0]["actorDisplayName"], "탈퇴/삭제 사용자")
        self.assertIsNone(items[0]["actorEmail"])
        self.assertEqual(items[0]["resourceDisplayName"], "관리자 추가 인증")

    def test_high_risk_request_display_uses_operation_and_reason_summary(self):
        client = FakeSqlClient(
            rows_by_table={
                "admin_audit_logs": [audit_row(
                    action="high_risk_request.create",
                    resource_type="high_risk_request",
                    resource_id="risk-1",
                )],
                "users": [],
                "admin_high_risk_change_requests": [{
                    "id": "risk-1",
                    "operation_type": "role_grant",
                    "reason": "Quarterly access adjustment",
                }],
            }
        )
        repo = RdsDataAuditLogRepository(rds_client=client)

        items = repo.list()

        self.assertEqual(items[0]["resourceDisplayName"], "role_grant (Quarterly access adjustment)")


if __name__ == "__main__":
    unittest.main()
