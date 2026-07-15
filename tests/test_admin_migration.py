# @file tests/test_admin_migration.py
# @description Verifies admin migration discovery, parsing, and repeatable application.
# @author JJonyeok2
# @lastModified 2026-07-15

import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.apply_admin_migration import _resolve_migration, split_statements


MIGRATION = ROOT / "schema" / "aurora_mysql" / "004_admin_high_risk_approvals.sql"


class AdminMigrationContractTests(unittest.TestCase):
    def test_exact_migration_filename_wins_when_prefix_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_dir = Path(temp_dir)
            exact = schema_dir / "004_admin_high_risk_approvals.sql"
            exact.touch()
            (schema_dir / "004_add_itinerary_share_columns.sql").touch()

            self.assertEqual(_resolve_migration(exact.name, schema_dir), exact)

    def test_unique_migration_prefix_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_dir = Path(temp_dir)
            migration = schema_dir / "003_admin_operations_tables.sql"
            migration.touch()

            self.assertEqual(_resolve_migration("003", schema_dir), migration)

    def test_ambiguous_migration_prefix_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_dir = Path(temp_dir)
            (schema_dir / "004_admin_high_risk_approvals.sql").touch()
            (schema_dir / "004_add_itinerary_share_columns.sql").touch()

            with self.assertRaises(SystemExit) as context:
                _resolve_migration("004", schema_dir)

            message = str(context.exception)
            self.assertIn("Migration prefix is ambiguous: 004", message)
            self.assertIn("004_admin_high_risk_approvals.sql", message)
            self.assertIn("004_add_itinerary_share_columns.sql", message)

    def test_004_discovers_role_check_and_contains_mfa_tables(self):
        sql = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("information_schema.CHECK_CONSTRAINTS", sql)
        self.assertIn("@user_role_check_name", sql)
        self.assertNotIn("DROP CHECK chk_user_role_code,", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS admin_mfa_credentials", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS admin_mfa_sessions", sql)

    def test_004_is_compatible_with_the_migration_statement_splitter(self):
        statements = split_statements(MIGRATION.read_text(encoding="utf-8"))

        self.assertEqual(len(statements), 9)
        self.assertTrue(any(item.startswith("PREPARE user_role_check_statement") for item in statements))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS admin_mfa_credentials" in item for item in statements))
        self.assertTrue(all(item.strip() for item in statements))


@unittest.skipUnless(os.environ.get("RUN_ADMIN_DB_INTEGRATION") == "1", "live MySQL integration is opt-in")
class AdminMigrationLiveMySqlTests(unittest.TestCase):
    def test_004_can_be_applied_twice(self):
        import pymysql

        connection = pymysql.connect(
            host=os.environ.get("MYSQL_HOST") or os.environ.get("RDS_LOCAL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT") or os.environ.get("RDS_LOCAL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER") or os.environ.get("RDS_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD") or os.environ.get("RDS_PW", ""),
            database=os.environ.get("MYSQL_DATABASE") or os.environ.get("RDS_DATABASE", "lovvdev"),
            autocommit=True,
        )
        try:
            statements = split_statements(MIGRATION.read_text(encoding="utf-8"))
            with connection.cursor() as cursor:
                for _ in range(2):
                    for statement in statements:
                        cursor.execute(statement)
                cursor.execute(
                    """
                    SELECT TABLE_NAME FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME IN ('admin_mfa_credentials', 'admin_mfa_sessions')
                    ORDER BY TABLE_NAME
                    """
                )
                self.assertEqual(
                    [row[0] for row in cursor.fetchall()],
                    ["admin_mfa_credentials", "admin_mfa_sessions"],
                )
                cursor.execute(
                    """
                    SELECT cc.CHECK_CLAUSE
                    FROM information_schema.TABLE_CONSTRAINTS tc
                    JOIN information_schema.CHECK_CONSTRAINTS cc
                      ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
                     AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                    WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
                      AND tc.TABLE_NAME = 'user_role_assignments'
                      AND LOWER(cc.CHECK_CLAUSE) LIKE '%role_code%'
                    """
                )
                self.assertIn("R-SUPER-ADMIN", cursor.fetchone()[0])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()


# EOF: tests/test_admin_migration.py
