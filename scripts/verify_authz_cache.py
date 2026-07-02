#!/usr/bin/env python3
"""Dev-only check: prove authz cache invalidate() actually deletes from DynamoDB.

Round-trips a throwaway test key through the real repository:
  put -> get (value matches) -> invalidate -> get (None).
Uses a fixed non-user UUID so no real user's cache is touched; cleans up in
finally.

Prereqs:
  - AUTH_AUTHZ_CACHE_TABLE_NAME   (e.g. lovv_dev_admin_authz_cache)
  - AWS credentials with dynamodb PutItem/GetItem/DeleteItem on that table
  - AWS_REGION / AWS_DEFAULT_REGION = us-east-1
No SSM tunnel needed (DynamoDB is a public AWS API).

Exit 0 = invalidate verified, 2 = failed.

NOTE: the repository swallows all exceptions (best-effort by design), so on
failure this script re-issues one raw boto3 call to surface the real error.
A rare false FAIL on the get-after-put step is possible due to DynamoDB
eventual consistency; just re-run.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.authz_cache_repository import DynamoDbAuthzCacheRepository

TEST_UID = "00000000-0000-0000-0000-0000000000ff"
PROBE = {"roles": ["R-VERIFY-PROBE"], "organizationIds": [], "regionIds": [], "authzVersion": 42}


def diagnose(cache):
    # The repository guards every call; re-issue raw to reveal the real error.
    print("\n--- raw boto3 diagnosis (repository swallows exceptions) ---")
    try:
        cache.table.put_item(Item={
            "userId": TEST_UID,
            "roles": ["diag"],
            "authzVersion": 1,
            "cachedAt": int(time.time()),
            "expiresAt": int(time.time()) + 60,
        })
        print("raw put_item: OK (write permission present)")
        cache.table.delete_item(Key={"userId": TEST_UID})
        print("raw delete_item: OK")
    except Exception as error:
        print(f"raw call failed: {type(error).__name__}: {error}")


def main():
    cache = DynamoDbAuthzCacheRepository.from_env()
    if not cache.enabled:
        sys.exit(
            "Cache disabled: set AUTH_AUTHZ_CACHE_TABLE_NAME "
            "(e.g. lovv_dev_admin_authz_cache) and retry."
        )

    print(f"Table: {cache.table_name}")
    print(f"Probe userId: {TEST_UID} (not a real user)\n")

    try:
        put_item = cache.put(TEST_UID, PROBE)
        got = cache.get(TEST_UID)
        cache.invalidate(TEST_UID)
        after = cache.get(TEST_UID)

        put_ok = put_item is not None
        get_ok = (
            got is not None
            and got.get("roles") == ["R-VERIFY-PROBE"]
            and int(got.get("authzVersion") or 0) == 42
        )
        invalidate_ok = after is None

        print(f"  [{'OK' if put_ok else 'FAIL'}] put stored an item")
        print(f"  [{'OK' if get_ok else 'FAIL'}] get returned the stored value")
        print(f"  [{'OK' if invalidate_ok else 'FAIL'}] get after invalidate returned None")

        if put_ok and get_ok and invalidate_ok:
            print("\nInvalidate verified against live DynamoDB.")
            return 0
        diagnose(cache)
        print("\nVerification FAILED.")
        return 2
    finally:
        try:
            cache.invalidate(TEST_UID)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
