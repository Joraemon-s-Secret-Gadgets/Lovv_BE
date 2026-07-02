import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import pyotp

from admin.mfa_repository import parse_utc


class AdminMfaError(Exception):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class KmsSecretCipher:
    def __init__(self, key_id=None, kms_client=None):
        self.key_id = key_id or os.environ.get("ADMIN_MFA_KMS_KEY_ID")
        if not self.key_id:
            raise AdminMfaError(500, "ADMIN_MFA_NOT_CONFIGURED", "Admin MFA encryption is not configured")
        self.kms = kms_client

    def encrypt(self, plaintext):
        response = self._client().encrypt(
            KeyId=self.key_id,
            Plaintext=plaintext.encode("utf-8"),
            EncryptionContext={"purpose": "lovv-admin-mfa"},
        )
        return base64.b64encode(response["CiphertextBlob"]).decode("ascii")

    def decrypt(self, ciphertext):
        response = self._client().decrypt(
            CiphertextBlob=base64.b64decode(ciphertext),
            EncryptionContext={"purpose": "lovv-admin-mfa"},
        )
        return response["Plaintext"].decode("utf-8")

    def _client(self):
        if self.kms is None:
            self.kms = _kms_client()
        return self.kms


class PlaintextSecretCipher:
    def encrypt(self, plaintext):
        return plaintext

    def decrypt(self, ciphertext):
        return ciphertext


class AdminMfaService:
    MAX_ATTEMPTS = 5
    LOCK_MINUTES = 15
    SESSION_HOURS = 12

    def __init__(self, repository, cipher, now_provider=None, issuer="Lovv Admin"):
        self.repository = repository
        self.cipher = cipher
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.issuer = issuer

    def status(self, principal):
        credential = self.repository.get_credential(principal["userId"])
        session = self._session(principal)
        return {
            "enrolled": bool(credential and credential.get("status") == "active"),
            "credentialStatus": credential.get("status") if credential else "not_enrolled",
            "sessionVerified": self._session_is_valid(session),
            "sessionVerifiedAt": session.get("verifiedAt") if session else None,
            "sessionExpiresAt": session.get("expiresAt") if session else None,
            "recoveryCodesRemaining": len(credential.get("recoveryCodes") or []) if credential else 0,
        }

    def enroll(self, principal, account_name):
        credential = self.repository.get_credential(principal["userId"])
        if credential and credential.get("status") == "active":
            raise AdminMfaError(409, "ADMIN_MFA_ALREADY_ENROLLED", "Admin MFA is already enrolled")
        secret = pyotp.random_base32()
        now = self._now_iso()
        self.repository.save_pending(principal["userId"], self.cipher.encrypt(secret), now)
        return {
            "secret": secret,
            "provisioningUri": pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=self.issuer),
        }

    def confirm(self, principal, code):
        credential = self._credential(principal, expected_status="pending")
        counter = self._verify_totp(credential, code)
        recovery_codes, recovery_hashes = _new_recovery_codes()
        now = self._now_iso()
        if not self.repository.activate(principal["userId"], counter, recovery_hashes, now):
            raise AdminMfaError(409, "ADMIN_MFA_STATE_CONFLICT", "Admin MFA enrollment state changed")
        self._record_session(principal, "totp")
        return {"recoveryCodes": recovery_codes, "status": self.status(principal)}

    def verify(self, principal, code):
        credential = self._credential(principal, expected_status="active")
        counter = self._verify_totp(credential, code)
        now = self._now_iso()
        if not self.repository.consume_totp_counter(principal["userId"], counter, now):
            raise AdminMfaError(409, "ADMIN_MFA_CODE_REUSED", "Admin MFA code was already used")
        self._record_session(principal, "totp")
        return self.status(principal)

    def recover(self, principal, recovery_code):
        credential = self._credential(principal, expected_status="active")
        current = list(credential.get("recoveryCodes") or [])
        match_index = next((i for i, item in enumerate(current) if _verify_recovery_code(recovery_code, item)), None)
        if match_index is None:
            self._record_failure(principal["userId"])
            raise AdminMfaError(403, "ADMIN_MFA_CODE_INVALID", "Admin MFA recovery code is invalid")
        remaining = current[:match_index] + current[match_index + 1 :]
        if not self.repository.consume_recovery_codes(principal["userId"], current, remaining, self._now_iso()):
            raise AdminMfaError(409, "ADMIN_MFA_CODE_REUSED", "Admin MFA recovery code was already used")
        self._record_session(principal, "recovery_code")
        return self.status(principal)

    def require_verified(self, principal, max_age_seconds=None, allowed_methods=None):
        session = self._session(principal)
        if not self._session_is_valid(session, max_age_seconds=max_age_seconds):
            raise AdminMfaError(403, "ADMIN_MFA_REQUIRED", "Admin MFA verification is required")
        if allowed_methods and session.get("method") not in set(allowed_methods):
            raise AdminMfaError(403, "ADMIN_MFA_TOTP_REQUIRED", "A recent authenticator code is required")
        return session

    def _credential(self, principal, expected_status):
        credential = self.repository.get_credential(principal["userId"])
        if not credential:
            raise AdminMfaError(403, "ADMIN_MFA_ENROLLMENT_REQUIRED", "Admin MFA enrollment is required")
        if credential.get("status") != expected_status:
            raise AdminMfaError(409, "ADMIN_MFA_STATE_CONFLICT", "Admin MFA credential state is invalid")
        locked_until = parse_utc(credential.get("lockedUntil"))
        if locked_until and locked_until > self.now_provider():
            raise AdminMfaError(429, "ADMIN_MFA_LOCKED", "Admin MFA is temporarily locked")
        return credential

    def _verify_totp(self, credential, code):
        if not isinstance(code, str) or not code.isdigit() or len(code) != 6:
            self._record_failure(credential["userId"])
            raise AdminMfaError(403, "ADMIN_MFA_CODE_INVALID", "Admin MFA code is invalid")
        secret = self.cipher.decrypt(credential["encryptedSecret"])
        totp = pyotp.TOTP(secret)
        current_counter = int(self.now_provider().timestamp()) // totp.interval
        for counter in range(current_counter - 1, current_counter + 2):
            if hmac.compare_digest(totp.at(counter * totp.interval), code):
                last_counter = credential.get("lastUsedCounter")
                if last_counter is not None and int(last_counter) >= counter:
                    raise AdminMfaError(409, "ADMIN_MFA_CODE_REUSED", "Admin MFA code was already used")
                return counter
        self._record_failure(credential["userId"])
        raise AdminMfaError(403, "ADMIN_MFA_CODE_INVALID", "Admin MFA code is invalid")

    def _record_failure(self, user_id):
        now = self.now_provider()
        self.repository.record_failure(
            user_id,
            _iso(now),
            _iso(now + timedelta(minutes=self.LOCK_MINUTES)),
            self.MAX_ATTEMPTS,
        )

    def _record_session(self, principal, method):
        session_id = principal.get("sessionId")
        if not session_id:
            raise AdminMfaError(403, "ADMIN_MFA_SESSION_REQUIRED", "Authenticated session is required")
        now = self.now_provider()
        self.repository.record_session(
            principal["userId"], session_id, _iso(now),
            _iso(now + timedelta(hours=self.SESSION_HOURS)), method,
        )

    def _session(self, principal):
        if not principal.get("sessionId"):
            return None
        return self.repository.get_session(principal["userId"], principal["sessionId"])

    def _session_is_valid(self, session, max_age_seconds=None):
        if not session:
            return False
        now = self.now_provider()
        expires_at = parse_utc(session.get("expiresAt"))
        verified_at = parse_utc(session.get("verifiedAt"))
        if not expires_at or not verified_at or expires_at <= now:
            return False
        return max_age_seconds is None or verified_at >= now - timedelta(seconds=max_age_seconds)

    def _now_iso(self):
        return _iso(self.now_provider())


def _new_recovery_codes(count=8):
    codes = [f"{secrets.token_hex(4)[:4]}-{secrets.token_hex(4)[:4]}".upper() for _ in range(count)]
    return codes, [_hash_recovery_code(code) for code in codes]


def _hash_recovery_code(code):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(_normalize_recovery_code(code), salt=salt, n=2**14, r=8, p=1)
    return {"salt": base64.b64encode(salt).decode("ascii"), "hash": base64.b64encode(digest).decode("ascii")}


def _verify_recovery_code(code, stored):
    try:
        salt = base64.b64decode(stored["salt"])
        expected = base64.b64decode(stored["hash"])
        actual = hashlib.scrypt(_normalize_recovery_code(code), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError):
        return False


def _normalize_recovery_code(code):
    return str(code or "").strip().upper().encode("utf-8")


def _iso(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _kms_client():
    import boto3
    return boto3.client("kms")
