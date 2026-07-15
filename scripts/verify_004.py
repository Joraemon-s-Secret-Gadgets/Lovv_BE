#!/usr/bin/env python3
# @file scripts/verify_004.py
# @description Verify that the three high-risk approval and MFA tables from migration 004 exist in the target database.
# @author JJonyeok2
# @lastModified 2026-07-15
"""Dev-only check: confirm the 004 high-risk/MFA tables exist in the target DB.

Run with the SSM tunnel open and credentials set, exactly like
check_admin_migration.py / apply_admin_migration.py:
  1) RDS_PW (+ optional RDS_USER), or
  2) RDS_SECRET_ARN -> fetched via boto3 from Secrets Manager.

Host/port point at the local tunnel (RDS_LOCAL_HOST/RDS_LOCAL_PORT, default
127.0.0.1:3306), never at the private RDS host.

Exit code 0 = all 3 tables present, 2 = some missing.
"""
import json
import os
import sys

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is not installed. Run: pip install pymysql")

EXPECTED = [
    "admin_high_risk_change_requests",
    "admin_mfa_credentials",
    "admin_mfa_sessions",
]


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

    print(f"Checking 004 tables in {host}:{port}/{database} as {user}")
    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name IN (%s, %s, %s)",
                [database, *EXPECTED],
            )
            present = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    missing = [name for name in EXPECTED if name not in present]
    for name in EXPECTED:
        print(f"  [{'OK' if name in present else 'MISSING'}] {name}")

    if missing:
        print(f"\nMissing {len(missing)} table(s): {', '.join(missing)}")
        return 2
    print("\nAll 3 tables present. 004 applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# EOF: scripts/verify_004.py
