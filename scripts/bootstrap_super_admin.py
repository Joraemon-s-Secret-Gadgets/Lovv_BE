#!/usr/bin/env python3
# @file scripts/bootstrap_super_admin.py
# @description Bootstrap the first global Super Admin assignment with locking, audit logging, and cache invalidation.
# @author JJonyeok2
# @lastModified 2026-07-15
"""One-time break-glass bootstrap for the first R-SUPER-ADMIN assignment.

Dry-run (default):
  python scripts/bootstrap_super_admin.py --target-user-id <uuid> \
    --operator <ticket-or-operator-id> --reason "initial production bootstrap"

Execute only after reviewing the target and reason:
  python scripts/bootstrap_super_admin.py ... --execute

Database credentials use the same MYSQL_* / RDS_* variables as MySqlClient.
The operation refuses to add a second Super Admin. Re-running for the already
bootstrapped target is a no-op.
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.audit_logs_repository import RdsDataAuditLogRepository, build_audit_entry
from auth.authz_cache_repository import DynamoDbAuthzCacheRepository
from shared.mysql_data import MySqlClient


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Bootstrap the first Lovv Super Admin")
    parser.add_argument("--target-user-id", required=True)
    parser.add_argument("--operator", required=True, help="Operator identity or change-ticket id")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--execute", action="store_true", help="Apply the assignment; otherwise dry-run")
    return parser.parse_args(argv)


def bootstrap(client, target_user_id, operator, reason, now):
    audit = RdsDataAuditLogRepository(rds_client=client)
    with client.transaction() as transaction:
        user = transaction.fetch_one(
            "SELECT id, status FROM users WHERE id = :id FOR UPDATE", {"id": target_user_id}
        )
        if not user or user.get("status") != "active":
            raise RuntimeError("Target user does not exist or is not active")

        assignments = transaction.fetch_all(
            """
            SELECT id, user_id FROM user_role_assignments
            WHERE role_code = 'R-SUPER-ADMIN' AND organization_id IS NULL
              AND status = 'active' AND valid_from <= UTC_TIMESTAMP(3)
              AND (valid_until IS NULL OR valid_until > UTC_TIMESTAMP(3))
            FOR UPDATE
            """
        )
        if any(item.get("user_id") == target_user_id for item in assignments):
            return "already_bootstrapped"
        if assignments:
            raise RuntimeError("Bootstrap refused: an active Super Admin already exists")

        transaction.execute(
            """
            INSERT INTO user_role_assignments
              (id, user_id, role_code, organization_id, status, valid_from,
               valid_until, granted_by, grant_reason, created_at, updated_at)
            VALUES
              (:id, :user_id, 'R-SUPER-ADMIN', NULL, 'active', :now,
               NULL, NULL, :reason, :now, :now)
            """,
            {
                "id": str(uuid.uuid4()),
                "user_id": target_user_id,
                "reason": reason,
                "now": now,
            },
            include_result_metadata=False,
        )
        entry = build_audit_entry(
            {},
            "super_admin.bootstrap",
            "user",
            target_user_id,
            now,
            result="succeeded",
            reason_code="BREAK_GLASS_BOOTSTRAP",
            after={"roleCode": "R-SUPER-ADMIN", "status": "active"},
            metadata={"operator": operator, "reason": reason},
        )
        audit.record(entry, transaction=transaction, strict=True)
    return "bootstrapped"


def main(argv=None):
    args = parse_args(argv)
    reason = args.reason.strip()
    operator = args.operator.strip()
    if not reason or not operator:
        raise SystemExit("--operator and --reason must not be blank")
    try:
        uuid.UUID(args.target_user_id)
    except ValueError as error:
        raise SystemExit("--target-user-id must be a UUID") from error

    print(f"Target user: {args.target_user_id}")
    print(f"Operator: {operator}")
    print(f"Reason: {reason}")
    if not args.execute:
        print("Dry-run only. Add --execute after independent review.")
        return 0

    # --execute crosses the break-glass boundary and writes the privileged assignment and audit record.
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = bootstrap(MySqlClient(), args.target_user_id, operator, reason, now)
    cache = DynamoDbAuthzCacheRepository.from_env()
    if cache.enabled:
        cache.invalidate(args.target_user_id)
    print(f"Bootstrap result: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# EOF: scripts/bootstrap_super_admin.py
