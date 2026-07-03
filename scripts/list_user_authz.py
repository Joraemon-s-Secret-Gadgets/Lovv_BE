#!/usr/bin/env python3
"""Dev-only: list users' admin authority (role + region assignments).

Lists every user that has at least one role or region assignment, with their
role_code(organization)@status and region_id(organization)@status.

  python scripts/list_user_authz.py            # active assignments only
  python scripts/list_user_authz.py --all      # include suspended/revoked
  python scripts/list_user_authz.py --user-id <uuid>   # filter one user

Same connection/credentials as verify_004.py / verify_schema.py:
  SSM tunnel open + RDS_PW (or RDS_SECRET_ARN); host/port from
  RDS_LOCAL_HOST/RDS_LOCAL_PORT (default 127.0.0.1:3306).
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
    parser = argparse.ArgumentParser(description="List user role/region authority")
    parser.add_argument("--all", action="store_true", help="include suspended/revoked (default: active only)")
    parser.add_argument("--user-id", help="filter to a single user id")
    args = parser.parse_args()

    host = os.environ.get("RDS_LOCAL_HOST", "127.0.0.1")
    port = int(os.environ.get("RDS_LOCAL_PORT", "3306"))
    database = os.environ.get("RDS_DATABASE", "lovvdev")
    user, password = resolve_credentials()

    status_clause = "" if args.all else "AND a.status = 'active'"
    user_clause = "AND a.user_id = %(uid)s" if args.user_id else ""
    params = {"uid": args.user_id} if args.user_id else {}

    role_sql = f"""
        SELECT a.user_id, u.email, u.display_name,
               a.role_code, a.organization_id, a.status, a.valid_until
        FROM user_role_assignments a JOIN users u ON u.id = a.user_id
        WHERE 1=1 {status_clause} {user_clause}
        ORDER BY u.email, a.role_code
    """
    region_sql = f"""
        SELECT a.user_id, u.email, u.display_name,
               a.region_id, a.organization_id, a.status, a.valid_until
        FROM user_region_assignments a JOIN users u ON u.id = a.user_id
        WHERE 1=1 {status_clause} {user_clause}
        ORDER BY u.email, a.region_id
    """

    conn = pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=database, cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(role_sql, params)
            role_rows = cur.fetchall()
            cur.execute(region_sql, params)
            region_rows = cur.fetchall()
    finally:
        conn.close()

    users = {}
    for r in role_rows:
        u = users.setdefault(r["user_id"], {"email": r["email"], "name": r["display_name"], "roles": [], "regions": []})
        org = f"({r['organization_id']})" if r["organization_id"] else "(global)"
        suffix = "" if r["status"] == "active" else f"@{r['status']}"
        u["roles"].append(f"{r['role_code']}{org}{suffix}")
    for r in region_rows:
        u = users.setdefault(r["user_id"], {"email": r["email"], "name": r["display_name"], "roles": [], "regions": []})
        org = f"({r['organization_id']})" if r["organization_id"] else ""
        suffix = "" if r["status"] == "active" else f"@{r['status']}"
        u["regions"].append(f"{r['region_id']}{org}{suffix}")

    scope = "all statuses" if args.all else "active only"
    print(f"User authority in {host}:{port}/{database} ({scope}) - {len(users)} user(s)\n")
    if not users:
        print("(no assignments found)")
        return 0
    for uid, info in sorted(users.items(), key=lambda kv: kv[1]["email"] or ""):
        print(f"- {info['email']}  [{uid}]  {info['name'] or ''}")
        print(f"    roles:   {', '.join(info['roles']) or '(none)'}")
        print(f"    regions: {', '.join(info['regions']) or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
