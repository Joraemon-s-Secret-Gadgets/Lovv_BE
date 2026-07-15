# @file src/auth/authorizer.py
# @description Validates bearer access tokens and builds API Gateway authorization context.
# @author JJonyeok2
# @lastModified 2026-07-15

from shared.auth import AuthTokenError, extract_bearer_token, verify_access_token


def lambda_handler(event, context):
    # Only claims recovered from a verified token cross into the trusted authorizer context.
    try:
        token = _token_from_event(event or {})
        claims = verify_access_token(token)
    except AuthTokenError as error:
        return _deny(error.code)

    return {
        "isAuthorized": True,
        "context": {
            "sub": claims["sub"],
            "userId": claims["sub"],
            "sid": claims.get("sid", ""),
            "sessionId": claims.get("sid", ""),
            "provider": claims.get("provider", ""),
            "roles": ",".join(claims.get("roles") if "roles" in claims else ["R-USER"]),
            # API Gateway authorizer context values must be strings, so list
            # scopes are comma-joined here and split back in shared.authorization.
            "organization_ids": ",".join(claims.get("organization_ids") or []),
            "region_ids": ",".join(claims.get("region_ids") or []),
            "authz_version": claims.get("authz_version", 1),
            "displayName": claims.get("display_name", ""),
            "iss": claims["iss"],
            "aud": claims["aud"],
            "iat": claims["iat"],
            "exp": claims["exp"],
        },
    }


def _token_from_event(event):
    try:
        return extract_bearer_token(event.get("headers") or {})
    except AuthTokenError:
        pass

    identity_sources = event.get("identitySource") or []
    for identity_source in identity_sources:
        try:
            return extract_bearer_token({"Authorization": identity_source})
        except AuthTokenError:
            continue

    raise AuthTokenError("UNAUTHORIZED", "Missing bearer token", 401)


def _deny(code):
    return {"isAuthorized": False, "context": {"error": code}}


# EOF: src/auth/authorizer.py
