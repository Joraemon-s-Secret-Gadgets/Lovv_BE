#!/usr/bin/env python3
"""Dev-only check: confirm the 002 admin console tables exist in the target DB.

Run this while an SSM port-forward to dev RDS is open on 127.0.0.1:3306.

Credentials are resolved in this order:
  1) RDS_PW (+ optional RDS_USER) environment variables, or
  2) RDS_SECRET_ARN  -> fetched via boto3 from Secrets Manager (same as the app)

The DB host/port always point at the local tunnel (127.0.0.1:3306 by default),
never at the secret's private RDS host.

    # simplest (mirrors the backend secret parsing, avoids shell quoting):
    $env:RDS_SECRET_ARN = aws ssm get-parameter --name /lovv/dev/rds/secret_arn --query Parameter.Value --output text
    python scripts/check_admin_migration.py

Exit code 0 = all 9 tables present, 2 = some missing.
"""
import json
import os
import sys

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is not installed. Run: pip install pymysql")

EXPECTED = [
    "admin_organizations",
    "user_role_assignments",
    "user_region_assignments",
    "admin_data_proposals",
    "admin_data_proposal_history",
    "monthly_curated_destinations",
    "admin_publish_jobs",
    "destination_metrics_daily",
    "admin_audit_logs",
]


def resolve_credentials():
    user = os.environ.get("RDS_USER")
    password = os.environ.get("RDS_PW")
    if password:
        return (user or "lovvadmin"), password

    secret_arn = os.environ.get("RDS_SECRET_ARN")
    if not secret_arn:
        sys.exit("Set RDS_PW, or set RDS_SECRET_ARN to load credentials via boto3.")
    try:
        import boto3
    except ImportError:
        sys.exit("boto3 is required for RDS_SECRET_ARN mode. Run: pip install boto3")
    raw = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)["SecretString"]
    secret = json.loads(raw)
    return (user or secret.get("username")), secret.get("password")


host = os.environ.get("RDS_LOCAL_HOST", "127.0.0.1")
port = int(os.environ.get("RDS_LOCAL_PORT", "3306"))
database = os.environ.get("RDS_DATABASE", "lovvdev")
user, password = resolve_credentials()

if not user or not password:
    sys.exit("Could not resolve DB username/password.")

print(f"Connecting to {host}:{port}/{database} as {user} ...")
conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
try:
    with conn.cursor() as cur:
        placeholders = ",".join(["%s"] * len(EXPECTED))
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=%s AND table_name IN (" + placeholders + ")",
            [database, *EXPECTED],
        )
        found = {row[0] for row in cur.fetchall()}
finally:
    conn.close()

missing = [t for t in EXPECTED if t not in found]
print(f"DB={database}  admin tables found: {len(found)}/{len(EXPECTED)}")
for table in EXPECTED:
    print(("  [OK]      " if table in found else "  [MISSING] ") + table)

if missing:
    print("\nMissing:", ", ".join(missing))
    print("Apply with: schema/aurora_mysql/002_admin_console_tables.sql")
    sys.exit(2)

print("\nAll admin console tables are present. 002 migration is applied.")
sys.exit(0)
