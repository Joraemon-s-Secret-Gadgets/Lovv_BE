# @file tests/test_bootstrap_super_admin.py
# @description Verifies guarded super-admin bootstrap argument and dry-run behavior.
# @author JJonyeok2
# @lastModified 2026-07-15

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.bootstrap_super_admin import main, parse_args


class BootstrapSuperAdminTests(unittest.TestCase):
    def test_requires_explicit_execute_flag(self):
        args = parse_args([
            "--target-user-id", "00000000-0000-0000-0000-000000000001",
            "--operator", "CHG-123", "--reason", "initial bootstrap",
        ])
        self.assertFalse(args.execute)

    def test_dry_run_does_not_create_database_client(self):
        result = main([
            "--target-user-id", "00000000-0000-0000-0000-000000000001",
            "--operator", "CHG-123", "--reason", "initial bootstrap",
        ])
        self.assertEqual(result, 0)

    def test_rejects_non_uuid_target(self):
        with self.assertRaises(SystemExit):
            main(["--target-user-id", "not-a-uuid", "--operator", "CHG-123", "--reason", "bootstrap"])


if __name__ == "__main__":
    unittest.main()


# EOF: tests/test_bootstrap_super_admin.py
