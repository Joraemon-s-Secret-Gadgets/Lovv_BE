import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.user_repository import RdsDataUserRepository


class FakeSqlClient:
    def __init__(self, fetch_one_rows=None, fetch_all_rows=None):
        self.fetch_one_rows = list(fetch_one_rows or [])
        self.fetch_all_rows = list(fetch_all_rows or [])
        self.fetch_one_calls = []
        self.fetch_all_calls = []

    def fetch_one(self, sql, parameters=None):
        self.fetch_one_calls.append({"sql": " ".join(sql.split()), "parameters": parameters or {}})
        return self.fetch_one_rows.pop(0) if self.fetch_one_rows else None

    def fetch_all(self, sql, parameters=None):
        self.fetch_all_calls.append({"sql": " ".join(sql.split()), "parameters": parameters or {}})
        return self.fetch_all_rows.pop(0) if self.fetch_all_rows else []


class UserRepositoryAuthorizationTest(unittest.TestCase):
    def test_get_user_merges_active_role_and_region_assignments(self):
        client = FakeSqlClient(
            fetch_one_rows=[
                {
                    "id": "user-1",
                    "email": "user@example.com",
                    "display_name": "Lovv User",
                    "avatar_url": None,
                    "birth_date": None,
                    "gender": None,
                    "created_at": "2026-06-10T09:00:00Z",
                    "status": "active",
                    "role": "user",
                }
            ],
            fetch_all_rows=[
                [
                    {"role_code": "R-DATA-PROVIDER", "organization_id": "org-gangneung"},
                    {"role_code": "R-LOCAL-OPERATOR", "organization_id": "org-gangneung"},
                ],
                [
                    {"region_id": "KR-42-150", "organization_id": "org-gangneung"},
                    {"region_id": "KR-42-170", "organization_id": None},
                ],
            ],
        )
        repository = RdsDataUserRepository(rds_client=client)

        user = repository.get_user("user-1")

        self.assertEqual(user["roles"], ["R-USER", "R-DATA-PROVIDER", "R-LOCAL-OPERATOR"])
        self.assertEqual(user["organizationIds"], ["org-gangneung"])
        self.assertEqual(user["regionIds"], ["KR-42-150", "KR-42-170"])
        self.assertEqual(user["authzVersion"], 1)
        self.assertIn("FROM user_role_assignments", client.fetch_all_calls[0]["sql"])
        self.assertIn("FROM user_region_assignments", client.fetch_all_calls[1]["sql"])
        self.assertIn("valid_from <= UTC_TIMESTAMP(3)", client.fetch_all_calls[0]["sql"])
        self.assertIn("(valid_until IS NULL OR valid_until > UTC_TIMESTAMP(3))", client.fetch_all_calls[1]["sql"])


if __name__ == "__main__":
    unittest.main()
