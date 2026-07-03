#!/usr/bin/env python3
"""Dev-only check: confirm ALL schema/aurora_mysql migrations (001-004) are applied.

This project has no migration-version table, so application state is verified by
checking that every object each migration creates is present:
  - all expected tables exist, and
  - 004's ALTER on user_role_assignments (R-SUPER-ADMIN in the role_code CHECK)
    is in place.

Run with the SSM tunnel open and credentials set, same as
apply_admin_migration.py / verify_004.py:
  1) RDS_PW (+ optional RDS_USER), or
  2) RDS_SECRET_ARN -> boto3 Secrets Manager.
Host/port use RDS_LOCAL_HOST/RDS_LOCAL_PORT (default 127.0.0.1:3306).

Exit code 0 = fully migrated, 2 = something missing.
NOTE: existence-only. Column-level drift is NOT detected; use SHOW CREATE TABLE
for a full comparison. Requires MySQL 8.0.16+ (information_schema.CHECK_CONSTRAINTS).
"""
import json
import os
import sys

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is not installed. Run: pip install pymysql")

# admin_high_risk_change_requests / admin_mfa_credentials / admin_mfa_sessions
# are owned by 004 only (removed from 002 to avoid a duplicate definition).
EXPECTED = {
    # Base tables are provisioned by infra/data-stack/rds/schema.sql (the single
    # source of truth), where the preferences table is named user_preferences.
    "base tables (infra/data-stack/rds/schema.sql)": [
        "users", "social_accounts", "user_preferences",
        "itineraries", "itinerary_items", "plan_reactions",
    ],
    "002_admin_console_tables": [
        "admin_organizations", "user_role_assignments", "user_region_assignments",
        "admin_data_proposals", "admin_data_proposal_history",
        "monthly_curated_destinations", "admin_publish_jobs",
        "destination_metrics_daily", "admin_audit_logs",
    ],
    "003_admin_operations_tables": [
        "admin_notices", "admin_recommendation_policies",
    ],
    "004_admin_high_risk_approvals": [
        "admin_high_risk_change_requests", "admin_mfa_credentials", "admin_mfa_sessions",
    ],
}


def resolve_credentials():
    user = os.environ.get("RDS_USER")
    password = os.environ.get("RDS_PW")
    if password:
        return (user or "lovvadmin"), password
    secret_arn = os.environ.get("RDS_SECRET_ARN")
    if not secret_arn:
        sys.exit("Set RDS_PW, or set RDS_SECRET_ARN to load credentials via boto3.")
    import boto3
    raw = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)["SecretString"]
    secret = json.loads(raw)
    return (user or secret.get("username")), secret.get("password")


def main():
    host = os.environ.get("RDS_LOCAL_HOST", "127.0.0.1")
    port = int(os.environ.get("RDS_LOCAL_PORT", "3306"))
    database = os.environ.get("RDS_DATABASE", "lovvdev")
    user, password = resolve_credentials()

    all_tables = [t for tables in EXPECTED.values() for t in tables]
    print(f"Checking {len(all_tables)} tables across {len(EXPECTED)} migrations "
          f"in {host}:{port}/{database} as {user}\n")

    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                [database],
            )
            present = {row[0] for row in cur.fetchall()}

            cur.execute(
                "SELECT cc.CHECK_CLAUSE "
                "FROM information_schema.TABLE_CONSTRAINTS tc "
                "JOIN information_schema.CHECK_CONSTRAINTS cc "
                "  ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA "
                " AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
                "WHERE tc.TABLE_SCHEMA = %s AND tc.TABLE_NAME = 'user_role_assignments' "
                "  AND tc.CONSTRAINT_TYPE = 'CHECK' "
                "  AND LOWER(cc.CHECK_CLAUSE) LIKE '%%role_code%%'",
                [database],
            )
            role_check_clauses = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    missing = []
    for migration, tables in EXPECTED.items():
        print(f"[{migration}]")
        for name in tables:
            ok = name in present
            print(f"  [{'OK' if ok else 'MISSING'}] {name}")
            if not ok:
                missing.append(name)

    super_admin_ok = any("R-SUPER-ADMIN" in (c or "") for c in role_check_clauses)
    print("\n[004 ALTER] user_role_assignments role_code CHECK allows R-SUPER-ADMIN")
    print(f"  [{'OK' if super_admin_ok else 'MISSING'}] "
          f"({len(role_check_clauses)} role_code CHECK constraint(s) found)")

    if missing or not super_admin_ok:
        print(f"\nNOT fully migrated. Missing tables: {missing or 'none'}; "
              f"R-SUPER-ADMIN CHECK: {'ok' if super_admin_ok else 'missing'}")
        return 2
    print(f"\nAll {len(all_tables)} tables present and 004 role CHECK applied. Fully migrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
