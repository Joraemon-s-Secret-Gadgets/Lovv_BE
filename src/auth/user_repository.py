# @file src/auth/user_repository.py
# @description User and social account repository for Lovv auth persistence.
# @lastModified 2026-06-12

import dataclasses
import os
import uuid

from shared.database import create_database_client


@dataclasses.dataclass(frozen=True)
class UserLoginResult:
    user: dict
    is_new_user: bool


class UserRepositoryError(Exception):
    def __init__(self, code, message="User repository error", status_code=500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RdsDataUserRepository:
    def __init__(self, rds_client=None, users_table=None, social_accounts_table=None):
        self.rds = rds_client or create_database_client()
        self.users_table = users_table or os.environ.get("USERS_TABLE_NAME", "users")
        self.social_accounts_table = social_accounts_table or os.environ.get("SOCIAL_ACCOUNTS_TABLE_NAME", "social_accounts")

    @classmethod
    def from_env(cls):
        return cls()

    def upsert_from_provider(self, identity, now):
        linked = self._find_by_social(identity.provider, identity.provider_user_id)
        if linked:
            self._record_social_login(linked["userId"], identity, now)
            user = self.get_user(linked["userId"])
            if not user:
                raise UserRepositoryError("USER_NOT_FOUND", "User was not found", 404)
            return UserLoginResult(user=user, is_new_user=False)

        user = None
        if identity.email and identity.email_verified:
            user = self._find_by_verified_email(identity.email)

        if user is None:
            user = self._create_user(identity, now)
            is_new = True
        else:
            is_new = False

        self._create_social_account(user["userId"], identity, now)
        return UserLoginResult(user=user, is_new_user=is_new)

    def get_user(self, user_id):
        row = self.rds.fetch_one(
            f"""
            SELECT id, email, display_name, avatar_url, birth_date, gender, created_at, status, role
            FROM {self.users_table}
            WHERE id = :user_id AND status = 'active'
            """,
            {"user_id": user_id},
        )
        return _user_from_row(row) if row else None

    def _find_by_social(self, provider, provider_user_id):
        row = self.rds.fetch_one(
            f"""
            SELECT u.id, u.email, u.display_name, u.avatar_url, u.birth_date, u.gender, u.created_at, u.status, u.role
            FROM {self.social_accounts_table} sa
            JOIN {self.users_table} u ON u.id = sa.user_id
            WHERE sa.provider = :provider
              AND sa.provider_user_id = :provider_user_id
              AND u.status = 'active'
            """,
            {"provider": provider, "provider_user_id": provider_user_id},
        )
        return _user_from_row(row) if row else None

    def _find_by_verified_email(self, email):
        row = self.rds.fetch_one(
            f"""
            SELECT id, email, display_name, avatar_url, birth_date, gender, created_at, status, role
            FROM {self.users_table}
            WHERE email = :email AND status = 'active'
            """,
            {"email": email},
        )
        return _user_from_row(row) if row else None

    def _create_user(self, identity, now):
        user_id = str(uuid.uuid4())
        display_name = identity.display_name or "Lovv User"
        self.rds.execute(
            f"""
            INSERT INTO {self.users_table}
              (id, email, email_verified, display_name, avatar_url, status, last_login_at, created_at, updated_at)
            VALUES
              (:id, :email, :email_verified, :display_name, :avatar_url, 'active', :now, :now, :now)
            """,
            {
                "id": user_id,
                "email": identity.email if identity.email_verified else None,
                "email_verified": bool(identity.email_verified),
                "display_name": display_name,
                "avatar_url": identity.avatar_url,
                "now": now,
            },
            include_result_metadata=False,
        )
        return {
            "userId": user_id,
            "email": identity.email if identity.email_verified else None,
            "displayName": display_name,
            "avatarUrl": identity.avatar_url,
            "birthDate": None,
            "gender": None,
            "createdAt": now,
            "role": "user",
            "roles": ["R-USER"],
            "status": "active",
        }

    def _create_social_account(self, user_id, identity, now):
        self.rds.execute(
            f"""
            INSERT INTO {self.social_accounts_table}
              (id, user_id, provider, provider_user_id, email, email_verified, provider_nickname,
               provider_profile_image_url, created_at, last_login_at)
            VALUES
              (:id, :user_id, :provider, :provider_user_id, :email, :email_verified, :provider_nickname,
               :provider_profile_image_url, :now, :now)
            """,
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "provider": identity.provider,
                "provider_user_id": identity.provider_user_id,
                "email": identity.email,
                "email_verified": bool(identity.email_verified),
                "provider_nickname": identity.display_name,
                "provider_profile_image_url": identity.avatar_url,
                "now": now,
            },
            include_result_metadata=False,
        )

    def _record_social_login(self, user_id, identity, now):
        self.rds.execute(
            f"""
            UPDATE {self.users_table}
            SET last_login_at = :now, updated_at = :now
            WHERE id = :user_id
            """,
            {"user_id": user_id, "now": now},
            include_result_metadata=False,
        )
        self.rds.execute(
            f"""
            UPDATE {self.social_accounts_table}
            SET email = :email,
                email_verified = :email_verified,
                provider_nickname = :provider_nickname,
                provider_profile_image_url = :provider_profile_image_url,
                last_login_at = :now
            WHERE provider = :provider AND provider_user_id = :provider_user_id
            """,
            {
                "provider": identity.provider,
                "provider_user_id": identity.provider_user_id,
                "email": identity.email,
                "email_verified": bool(identity.email_verified),
                "provider_nickname": identity.display_name,
                "provider_profile_image_url": identity.avatar_url,
                "now": now,
            },
            include_result_metadata=False,
        )

    def update_profile(self, user_id, now, fields):
        fields = {key: value for key, value in (fields or {}).items() if key in _PROFILE_UPDATE_COLUMNS}
        if fields:
            assignments = [f"{column} = :{column}" for column in fields]
            assignments.append("updated_at = :now")
            params = dict(fields)
            params["user_id"] = user_id
            params["now"] = now
            self.rds.execute(
                f"""
                UPDATE {self.users_table}
                SET {", ".join(assignments)}
                WHERE id = :user_id AND status = 'active'
                """,
                params,
                include_result_metadata=False,
            )

        user = self.get_user(user_id)
        if not user:
            raise UserRepositoryError("USER_NOT_FOUND", "User was not found", 404)
        return user

    def link_provider_to_user(self, user_id, identity, now):
        existing = self._find_by_social(identity.provider, identity.provider_user_id)
        if existing:
            if existing["userId"] == user_id:
                raise UserRepositoryError(
                    "SOCIAL_ACCOUNT_ALREADY_LINKED",
                    "This provider account is already linked to your profile.",
                    409,
                )
            raise UserRepositoryError(
                "SOCIAL_ACCOUNT_LINKED_TO_ANOTHER_USER",
                "This provider account is already linked to a different account.",
                409,
            )

        self._create_social_account(user_id, identity, now)
        return self.list_social_accounts(user_id)

    def list_social_accounts(self, user_id):
        rows = self.rds.fetch_all(
            f"""
            SELECT provider, provider_user_id, provider_nickname, provider_profile_image_url,
                   created_at, last_login_at
            FROM {self.social_accounts_table}
            WHERE user_id = :user_id
            ORDER BY created_at ASC
            """,
            {"user_id": user_id},
        )
        return [_social_account_from_row(row) for row in (rows or [])]


_PROFILE_UPDATE_COLUMNS = {"display_name", "birth_date", "gender"}


class InMemoryUserRepository:
    def __init__(self, now="2026-06-10T09:00:00Z"):
        self.now = now
        self.users = {}
        self.social_accounts = {}

    def upsert_from_provider(self, identity, now=None):
        key = (identity.provider, identity.provider_user_id)
        if key in self.social_accounts:
            user_id = self.social_accounts[key]["userId"]
            user = self.users[user_id]
            user["lastLoginAt"] = now or self.now
            return UserLoginResult(user=dict(user), is_new_user=False)

        user = None
        if identity.email and identity.email_verified:
            user = next(
                (candidate for candidate in self.users.values() if candidate.get("email") == identity.email and candidate.get("status") == "active"),
                None,
            )

        is_new = user is None
        if user is None:
            user_id = f"user-{len(self.users) + 1}"
            user = {
                "userId": user_id,
                "email": identity.email if identity.email_verified else None,
                "displayName": identity.display_name or "Lovv User",
                "avatarUrl": identity.avatar_url,
                "birthDate": None,
                "gender": None,
                "role": "user",
                "roles": ["R-USER"],
                "status": "active",
                "createdAt": now or self.now,
                "updatedAt": now or self.now,
                "lastLoginAt": now or self.now,
            }
            self.users[user_id] = user
        else:
            user["lastLoginAt"] = now or self.now

        self.social_accounts[key] = {
            "userId": user["userId"],
            "provider": identity.provider,
            "providerUserId": identity.provider_user_id,
            "email": identity.email,
            "emailVerified": identity.email_verified,
            "nickname": identity.display_name,
            "avatarUrl": identity.avatar_url,
            "linkedAt": now or self.now,
            "lastLoginAt": now or self.now,
        }
        return UserLoginResult(user=dict(user), is_new_user=is_new)

    def get_user(self, user_id):
        user = self.users.get(user_id)
        if not user or user.get("status") != "active":
            return None
        result = dict(user)
        result["roles"] = roles_for_db_role(result.get("role"))
        return result

    def update_profile(self, user_id, now, fields):
        user = self.users.get(user_id)
        if not user or user.get("status") != "active":
            raise UserRepositoryError("USER_NOT_FOUND", "User was not found", 404)

        fields = fields or {}
        if "display_name" in fields:
            user["displayName"] = fields["display_name"]
        if "birth_date" in fields:
            user["birthDate"] = fields["birth_date"]
        if "gender" in fields:
            user["gender"] = fields["gender"]
        user["updatedAt"] = now or self.now
        return self.get_user(user_id)

    def link_provider_to_user(self, user_id, identity, now=None):
        key = (identity.provider, identity.provider_user_id)
        existing = self.social_accounts.get(key)
        if existing:
            if existing["userId"] == user_id:
                raise UserRepositoryError(
                    "SOCIAL_ACCOUNT_ALREADY_LINKED",
                    "This provider account is already linked to your profile.",
                    409,
                )
            raise UserRepositoryError(
                "SOCIAL_ACCOUNT_LINKED_TO_ANOTHER_USER",
                "This provider account is already linked to a different account.",
                409,
            )

        self.social_accounts[key] = {
            "userId": user_id,
            "provider": identity.provider,
            "providerUserId": identity.provider_user_id,
            "email": identity.email,
            "emailVerified": identity.email_verified,
            "nickname": identity.display_name,
            "avatarUrl": identity.avatar_url,
            "linkedAt": now or self.now,
            "lastLoginAt": now or self.now,
        }
        return self.list_social_accounts(user_id)

    def list_social_accounts(self, user_id):
        return [
            {
                "provider": account["provider"],
                "providerUserId": account["providerUserId"],
                "nickname": account.get("nickname"),
                "avatarUrl": account.get("avatarUrl"),
                "linkedAt": account.get("linkedAt"),
                "lastLoginAt": account.get("lastLoginAt"),
            }
            for account in self.social_accounts.values()
            if account["userId"] == user_id
        ]


def roles_for_db_role(role):
    normalized = (role or "user").strip().lower() if isinstance(role, str) else "user"
    if normalized == "admin":
        return ["R-ADMIN"]
    if normalized == "user":
        return ["R-USER"]
    return []


def _user_from_row(row):
    return {
        "userId": str(row.get("id", "")),
        "email": row.get("email"),
        "displayName": row.get("display_name") or "Lovv User",
        "avatarUrl": row.get("avatar_url"),
        "birthDate": row.get("birth_date"),
        "gender": row.get("gender"),
        "createdAt": row.get("created_at"),
        "role": row.get("role") or "user",
        "roles": roles_for_db_role(row.get("role")),
        "status": row.get("status") or "active",
    }


def _social_account_from_row(row):
    return {
        "provider": row.get("provider"),
        "providerUserId": row.get("provider_user_id"),
        "nickname": row.get("provider_nickname"),
        "avatarUrl": row.get("provider_profile_image_url"),
        "linkedAt": row.get("created_at"),
        "lastLoginAt": row.get("last_login_at"),
    }


# EOF: src/auth/user_repository.py
