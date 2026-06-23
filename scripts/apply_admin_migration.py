#!/usr/bin/env python3
"""Dev-only: apply schema/aurora_mysql/002_admin_console_tables.sql to the target DB.

Run while an SSM port-forward to dev RDS is open (e.g. 127.0.0.1:13306).
Credentials resolve the same way as check_admin_migration.py:
  1) RDS_PW (+ optional RDS_USER), or
  2) RDS_SECRET_ARN -> boto3 Secrets Manager.

This writes to the shared dev database. All statements are CREATE TABLE IF NOT
EXISTS, so re-running is idempotent.

    python scripts/apply_admin_migration.py
"""
import json
import os
import sys
from pathlib import Path

try:
    import pymysql
except ImportError:
    sys.exit("pymysql is not installed. Run: pip install pymysql")

MIGRATION = Path(__file__).resolve().parents[1] / "schema" / "aurora_mysql" / "002_admin_console_tables.sql"


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


def split_statements(sql_text):
    statements = []
    for chunk in sql_text.split(";"):
        # drop full-line SQL comments and blank lines
        lines = [ln for ln in chunk.splitlines() if not ln.strip().startswith("--")]
        statement = "\n".join(lines).strip()
        if statement:
            statements.append(statement)
    return statements


host = os.environ.get("RDS_LOCAL_HOST", "127.0.0.1")
port = int(os.environ.get("RDS_LOCAL_PORT", "3306"))
database = os.environ.get("RDS_DATABASE", "lovvdev")
user, password = resolve_credentials()
if not user or not password:
    sys.exit("Could not resolve DB username/password.")

sql_text = MIGRATION.read_text(encoding="utf-8")
statements = split_statements(sql_text)
print(f"Applying {MIGRATION.name} -> {host}:{port}/{database} as {user}")
print(f"Statements to run: {len(statements)}")

conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database, autocommit=False)
try:
    with conn.cursor() as cur:
        for index, statement in enumerate(statements, start=1):
            head = statement.splitlines()[0][:70]
            print(f"  [{index}/{len(statements)}] {head} ...")
            cur.execute(statement)
    conn.commit()
finally:
    conn.close()

print("\nMigration applied. Re-run check_admin_migration.py to confirm 9/9.")
