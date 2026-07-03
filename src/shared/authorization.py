# @file src/shared/authorization.py
# @description Shared authenticated principal and role authorization helpers.
# @lastModified 2026-06-23

from shared.current_user import authenticated_claims


# Server-side authorization is the source of truth. Every admin route re-derives
# the caller's roles and org/region scopes from the verified access token and
# fails closed if anything is missing. Frontend tab/button gating is UX only and
# is always re-checked here, so a client cannot escalate by sending its own
# role/scope fields in the request body.
ROLE_USER = "R-USER"
ROLE_ADMIN = "R-ADMIN"
ROLE_SUPER_ADMIN = "R-SUPER-ADMIN"
ROLE_DATA_PROVIDER = "R-DATA-PROVIDER"
ROLE_LOCAL_OPERATOR = "R-LOCAL-OPERATOR"


class AuthorizationError(Exception):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def authenticated_principal(event):
    # Build a normalized principal (roles + org/region scopes) from verified claims.
    claims = authenticated_claims(event)
    user_id = claims.get("userId") or claims.get("sub")
    if not user_id:
        raise AuthorizationError(401, "UNAUTHORIZED", "Authentication is required")

    return {
        "userId": str(user_id),
        "sub": str(claims.get("sub") or user_id),
        "sessionId": str(claims.get("sessionId") or claims.get("sid") or ""),
        "roles": normalize_roles(claims.get("roles")),
        "organizationIds": _claim_string_list(claims, "organizationIds", "organization_ids"),
        "regionIds": _claim_string_list(claims, "regionIds", "region_ids"),
        "provider": str(claims.get("provider") or ""),
        "claims": claims,
    }


def require_roles(event, allowed_roles, error_code="ROLE_FORBIDDEN", message=None):
    # Allow the call only if the caller holds at least one of allowed_roles, else 403.
    principal = authenticated_principal(event)
    if not has_any_role(principal, allowed_roles):
        raise AuthorizationError(
            403,
            error_code,
            message or "This role cannot perform the requested operation.",
        )
    return principal


def require_admin_access(event):
    # Admin-only guard. Distinct error code lets the UI tell "needs admin" apart
    # from a generic role denial.
    return require_roles(
        event,
        {ROLE_ADMIN, ROLE_SUPER_ADMIN},
        error_code="ADMIN_ACCESS_REQUIRED",
        message="Admin role is required",
    )


def has_any_role(principal, allowed_roles):
    allowed = set(normalize_roles(allowed_roles))
    roles = set((principal or {}).get("roles") or [])
    return bool(allowed.intersection(roles))


def normalize_roles(roles):
    # Accept a list or comma-separated string, trim/dedupe, and treat malformed
    # input as "no roles" (fail closed).
    if roles is None:
        return []
    if isinstance(roles, str):
        raw_roles = roles.split(",")
    elif isinstance(roles, (list, tuple, set)):
        raw_roles = roles
    else:
        return []

    normalized = []
    seen = set()
    for role in raw_roles:
        if not isinstance(role, str):
            continue
        value = role.strip()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def _claim_string_list(claims, camel_key, snake_key):
    if camel_key in claims:
        return _normalize_string_list(claims.get(camel_key))
    return _normalize_string_list(claims.get(snake_key))


def _normalize_string_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        return []

    normalized = []
    seen = set()
    for item in raw_values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in seen:
            normalized.append(text)
            seen.add(text)
    return normalized


# EOF: src/shared/authorization.py
