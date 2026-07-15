# @file tests/test_admin_mfa_repository.py
# @description Verifies atomic recovery-code consumption in the admin MFA repository.
# @author JJonyeok2
# @lastModified 2026-07-15

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mfa_repository import RdsDataAdminMfaRepository


class FakeSqlClient:
    def __init__(self, updated=1):
        self.updated = updated
        self.executed = []

    def execute(self, sql, parameters=None, include_result_metadata=True):
        self.executed.append(
            {
                "sql": " ".join(sql.split()),
                "parameters": parameters or {},
                "include_result_metadata": include_result_metadata,
            }
        )
        return {"numberOfRecordsUpdated": self.updated}


class AdminMfaRepositoryTests(unittest.TestCase):
    def test_consume_recovery_codes_compares_and_stores_json_values(self):
        client = FakeSqlClient()
        repository = RdsDataAdminMfaRepository(rds_client=client)

        updated = repository.consume_recovery_codes(
            "admin-1",
            [{"salt": "s1", "hash": "h1"}, {"salt": "s2", "hash": "h2"}],
            [{"salt": "s2", "hash": "h2"}],
            "2026-06-30T02:00:00Z",
        )

        self.assertTrue(updated)
        call = client.executed[0]
        self.assertIn("SET recovery_codes_json = CAST(:remaining_codes AS JSON)", call["sql"])
        self.assertIn("AND recovery_codes_json = CAST(:current_codes AS JSON)", call["sql"])
        self.assertEqual(call["parameters"]["current_codes"], '[{"hash":"h1","salt":"s1"},{"hash":"h2","salt":"s2"}]')
        self.assertEqual(call["parameters"]["remaining_codes"], '[{"hash":"h2","salt":"s2"}]')
        self.assertFalse(call["include_result_metadata"])


if __name__ == "__main__":
    unittest.main()


# EOF: tests/test_admin_mfa_repository.py
