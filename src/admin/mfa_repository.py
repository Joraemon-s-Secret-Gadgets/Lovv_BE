import os
from datetime import datetime, timezone

from shared.database import create_database_client
from shared.rds_data import json_dumps, json_loads


class RdsDataAdminMfaRepository:
    def __init__(self, rds_client=None, credentials_table=None, sessions_table=None):
        self.rds = rds_client or create_database_client()
        self.credentials_table = credentials_table or os.environ.get(
            "ADMIN_MFA_CREDENTIALS_TABLE_NAME", "admin_mfa_credentials"
        )
        self.sessions_table = sessions_table or os.environ.get(
            "ADMIN_MFA_SESSIONS_TABLE_NAME", "admin_mfa_sessions"
        )

    @classmethod
    def from_env(cls):
        return cls()

    def get_credential(self, user_id):
        row = self.rds.fetch_one(
            f"SELECT * FROM {self.credentials_table} WHERE user_id = :user_id",
            {"user_id": user_id},
        )
        return _credential_from_row(row) if row else None

    def save_pending(self, user_id, encrypted_secret, now):
        self.rds.execute(
            f"""
            INSERT INTO {self.credentials_table}
              (user_id, encrypted_secret, status, last_used_counter, recovery_codes_json,
               failed_attempts, locked_until, enrolled_at, confirmed_at, updated_at)
            VALUES
              (:user_id, :encrypted_secret, 'pending', NULL, :recovery_codes_json,
               0, NULL, :enrolled_at, NULL, :updated_at)
            ON DUPLICATE KEY UPDATE
              encrypted_secret = VALUES(encrypted_secret), status = 'pending',
              last_used_counter = NULL, recovery_codes_json = VALUES(recovery_codes_json),
              failed_attempts = 0, locked_until = NULL, enrolled_at = VALUES(enrolled_at),
              confirmed_at = NULL, updated_at = VALUES(updated_at)
            """,
            {
                "user_id": user_id,
                "encrypted_secret": encrypted_secret,
                "recovery_codes_json": json_dumps([]),
                "enrolled_at": now,
                "updated_at": now,
            },
            include_result_metadata=False,
        )

    def activate(self, user_id, counter, recovery_codes, now):
        result = self.rds.execute(
            f"""
            UPDATE {self.credentials_table}
            SET status = 'active', last_used_counter = :counter,
                recovery_codes_json = :recovery_codes_json, failed_attempts = 0,
                locked_until = NULL, confirmed_at = :confirmed_at, updated_at = :updated_at
            WHERE user_id = :user_id AND status = 'pending'
            """,
            {
                "user_id": user_id,
                "counter": counter,
                "recovery_codes_json": json_dumps(recovery_codes),
                "confirmed_at": now,
                "updated_at": now,
            },
            include_result_metadata=False,
        )
        return _updated_once(result)

    def consume_totp_counter(self, user_id, counter, now):
        result = self.rds.execute(
            f"""
            UPDATE {self.credentials_table}
            SET last_used_counter = :counter, failed_attempts = 0,
                locked_until = NULL, updated_at = :updated_at
            WHERE user_id = :user_id AND status = 'active'
              AND (last_used_counter IS NULL OR last_used_counter < :counter)
            """,
            {"user_id": user_id, "counter": counter, "updated_at": now},
            include_result_metadata=False,
        )
        return _updated_once(result)

    def consume_recovery_codes(self, user_id, current_codes, remaining_codes, now):
        result = self.rds.execute(
            f"""
            UPDATE {self.credentials_table}
            SET recovery_codes_json = :remaining_codes, failed_attempts = 0,
                locked_until = NULL, updated_at = :updated_at
            WHERE user_id = :user_id AND status = 'active'
              AND recovery_codes_json = :current_codes
            """,
            {
                "user_id": user_id,
                "current_codes": json_dumps(current_codes),
                "remaining_codes": json_dumps(remaining_codes),
                "updated_at": now,
            },
            include_result_metadata=False,
        )
        return _updated_once(result)

    def record_failure(self, user_id, now, locked_until, max_attempts):
        self.rds.execute(
            f"""
            UPDATE {self.credentials_table}
            SET failed_attempts = failed_attempts + 1,
                locked_until = CASE
                  WHEN failed_attempts + 1 >= :max_attempts THEN :locked_until
                  ELSE locked_until
                END,
                updated_at = :updated_at
            WHERE user_id = :user_id
            """,
            {
                "user_id": user_id,
                "max_attempts": max_attempts,
                "locked_until": locked_until,
                "updated_at": now,
            },
            include_result_metadata=False,
        )

    def record_session(self, user_id, session_id, verified_at, expires_at, method):
        self.rds.execute(
            f"""
            INSERT INTO {self.sessions_table}
              (session_id, user_id, verified_at, expires_at, method, created_at, updated_at)
            VALUES
              (:session_id, :user_id, :verified_at, :expires_at, :method, :created_at, :updated_at)
            ON DUPLICATE KEY UPDATE
              user_id = VALUES(user_id), verified_at = VALUES(verified_at),
              expires_at = VALUES(expires_at), method = VALUES(method),
              updated_at = VALUES(updated_at)
            """,
            {
                "session_id": session_id,
                "user_id": user_id,
                "verified_at": verified_at,
                "expires_at": expires_at,
                "method": method,
                "created_at": verified_at,
                "updated_at": verified_at,
            },
            include_result_metadata=False,
        )

    def get_session(self, user_id, session_id):
        row = self.rds.fetch_one(
            f"""
            SELECT * FROM {self.sessions_table}
            WHERE user_id = :user_id AND session_id = :session_id
            """,
            {"user_id": user_id, "session_id": session_id},
        )
        return _session_from_row(row) if row else None


class InMemoryAdminMfaRepository:
    def __init__(self):
        self.credentials = {}
        self.sessions = {}

    def get_credential(self, user_id):
        item = self.credentials.get(user_id)
        return dict(item) if item else None

    def save_pending(self, user_id, encrypted_secret, now):
        self.credentials[user_id] = {
            "userId": user_id,
            "encryptedSecret": encrypted_secret,
            "status": "pending",
            "lastUsedCounter": None,
            "recoveryCodes": [],
            "failedAttempts": 0,
            "lockedUntil": None,
            "enrolledAt": now,
            "confirmedAt": None,
            "updatedAt": now,
        }

    def activate(self, user_id, counter, recovery_codes, now):
        item = self.credentials.get(user_id)
        if not item or item["status"] != "pending":
            return False
        item.update(status="active", lastUsedCounter=counter, recoveryCodes=list(recovery_codes),
                    failedAttempts=0, lockedUntil=None, confirmedAt=now, updatedAt=now)
        return True

    def consume_totp_counter(self, user_id, counter, now):
        item = self.credentials.get(user_id)
        if not item or item["status"] != "active":
            return False
        if item["lastUsedCounter"] is not None and item["lastUsedCounter"] >= counter:
            return False
        item.update(lastUsedCounter=counter, failedAttempts=0, lockedUntil=None, updatedAt=now)
        return True

    def consume_recovery_codes(self, user_id, current_codes, remaining_codes, now):
        item = self.credentials.get(user_id)
        if not item or item["recoveryCodes"] != current_codes:
            return False
        item.update(recoveryCodes=list(remaining_codes), failedAttempts=0, lockedUntil=None, updatedAt=now)
        return True

    def record_failure(self, user_id, now, locked_until, max_attempts):
        item = self.credentials.get(user_id)
        if not item:
            return
        item["failedAttempts"] += 1
        if item["failedAttempts"] >= max_attempts:
            item["lockedUntil"] = locked_until
        item["updatedAt"] = now

    def record_session(self, user_id, session_id, verified_at, expires_at, method):
        self.sessions[(user_id, session_id)] = {
            "userId": user_id,
            "sessionId": session_id,
            "verifiedAt": verified_at,
            "expiresAt": expires_at,
            "method": method,
        }

    def get_session(self, user_id, session_id):
        item = self.sessions.get((user_id, session_id))
        return dict(item) if item else None


def _credential_from_row(row):
    return {
        "userId": row.get("user_id"),
        "encryptedSecret": row.get("encrypted_secret"),
        "status": row.get("status"),
        "lastUsedCounter": row.get("last_used_counter"),
        "recoveryCodes": json_loads(row.get("recovery_codes_json"), []),
        "failedAttempts": int(row.get("failed_attempts") or 0),
        "lockedUntil": row.get("locked_until"),
        "enrolledAt": row.get("enrolled_at"),
        "confirmedAt": row.get("confirmed_at"),
        "updatedAt": row.get("updated_at"),
    }


def _session_from_row(row):
    return {
        "sessionId": row.get("session_id"),
        "userId": row.get("user_id"),
        "verifiedAt": row.get("verified_at"),
        "expiresAt": row.get("expires_at"),
        "method": row.get("method"),
    }


def _updated_once(result):
    return int((result or {}).get("numberOfRecordsUpdated") or 0) == 1


def parse_utc(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
