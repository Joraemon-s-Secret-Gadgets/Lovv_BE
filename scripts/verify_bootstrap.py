#!/usr/bin/env python3
"""Dev-only check: confirm a Super Admin bootstrap took effect for a target user.

For --target-user-id, checks:
  - an active global (organization_id IS NULL) R-SUPER-ADMIN role assignment
  - a succeeded 'super_admin.bootstrap' audit log row

Same connection/credentials as verify_004.py / verify_schema.py:
  SSM tunnel open + RDS_PW (or RDS_SECRET_ARN); host/port from
  RDS_LOCAL_HOST/RDS_LOCAL_PORT (default 127.0.0.1:3306).

Exit 0 = bootstrap verified, 2 = not found.
"""
import argparse
import json
import os
import sys

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is not installed. Run: pip install pymysql")


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
    parser = argparse.ArgumentParser(description="Verify a Super Admin bootstrap result")
    parser.add_argument("--target-user-id", required=True)
    args = parser.parse_args()
    target = args.target_user_id

    host = os.environ.get("RDS_LOCAL_HOST", "127.0.0.1")
    port = int(os.environ.get("RDS_LOCAL_PORT", "3306"))
    database = os.environ.get("RDS_DATABASE", "lovvdev")
    user, password = resolve_credentials()

    print(f"Verifying bootstrap for {target} in {host}:{port}/{database}\n")
    conn = pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=database, cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, valid_until
                FROM user_role_assignments
                WHERE user_id = %s AND role_code = 'R-SUPER-ADMIN'
                  AND organization_id IS NULL AND status = 'active'
                """,
                [target],
            )
            roles = cur.fetchall()
            cur.execute(
                """
                SELECT result, occurred_at
                FROM admin_audit_logs
                WHERE action = 'super_admin.bootstrap' AND resource_id = %s
                ORDER BY occurred_at DESC
                LIMIT 1
                """,
                [target],
            )
            audit = cur.fetchone()
    finally:
        conn.close()

    role_ok = len(roles) >= 1
    audit_ok = audit is not None and audit.get("result") == "succeeded"

    print(f"  [{'OK' if role_ok else 'MISSING'}] active global R-SUPER-ADMIN assignment "
          f"({len(roles)} found)")
    if audit is None:
        print("  [MISSING] super_admin.bootstrap audit log (none found)")
    else:
        print(f"  [{'OK' if audit_ok else 'FAIL'}] super_admin.bootstrap audit "
              f"(result={audit.get('result')}, at={audit.get('occurred_at')})")

    if role_ok and audit_ok:
        print("\nBootstrap verified.")
        return 0
    print("\nBootstrap NOT verified.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
