# Auth Social Login API Spec

## User Request Original

```text
1. Auth
- Google/Kakao 로그인
- 사용자 조회/생성
- 세션 확인
- 로그아웃
```

## Structured Agent Contract

- Agent Name: Backend Auth Social Login Spec Agent
- Core Role: Spec Agent
- Domain Focus: Backend AWS SAM
- Work Focus: Google/Kakao auth, user upsert, session, logout
- Workspace: `/Users/jeonjonghyeok/Documents/Final/Lovv_BE`
- Deliverable: create exactly one planning-only Spec file at `docs/specs/AUTH_SOCIAL_LOGIN_API_SPEC.md`.
- Hard boundary: do not implement code, and do not commit, push, pull, merge, or rebase.

## Summary

This Spec defines the production-direction Lovv auth API for Google and Kakao social login in the Backend AWS SAM boundary. It covers provider token validation, service user lookup/create, social account linking, service session creation, current user/session checks, and logout.

This Spec supersedes the current MVP simple-login boundary where social auth overlaps with it:

- The existing demo route `POST /api/auth/login` is not the production login contract.
- The existing demo `DEMO_LOGIN_*` configuration is local/dev scaffold only.
- Production auth must use Google/Kakao provider validation and service-owned user/session records.
- The product API contract should expose `/auth/*` resources under the Lovv API base. If the API Gateway deployment owns a base prefix such as `/api/v1`, the full deployed paths become `/api/v1/auth/*`.

This Spec is planning-only. It does not prove that the provider consoles, real secrets, database, API Gateway stage, or production deployment are ready.

## Context Sources

- `/Users/jeonjonghyeok/Documents/Final/docs/projects/lovv-project-context.md`
- `/Users/jeonjonghyeok/Documents/Final/docs/agents/spec-task-format.md`
- `/Users/jeonjonghyeok/Documents/Final/oh_my_documents/docs/06_technical_spec/06_technical_spec.md`
- `/Users/jeonjonghyeok/Documents/Final/oh_my_documents/docs/07_api_spec/07_api_spec.md`
- `/Users/jeonjonghyeok/Documents/Final/oh_my_documents/docs/04_database_design/04_database_design.md`
- `/Users/jeonjonghyeok/Documents/Final/Lovv_BE/docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`
- `/Users/jeonjonghyeok/Documents/Final/Lovv_BE/template.yaml`
- Current scaffold files inspected for route replacement planning:
  - `src/auth/app.py`
  - `src/auth/authorizer.py`
  - `src/shared/auth.py`
  - `events/auth-login.json`
  - `events/auth-me.json`
  - `events/auth-logout.json`
  - `tests/test_auth_app.py`
  - `tests/test_auth_authorizer.py`

## Goals

- Define Google and Kakao social login endpoints for the Auth Lambda.
- Define user lookup/create semantics for provider-authenticated users.
- Define social account linking rules for Google and Kakao identities.
- Define service JWT and session behavior for authenticated API calls.
- Define current user and session check endpoints.
- Define logout behavior that invalidates the service session and clears the browser session cookie.
- Define the logical `users`, `social_accounts`, and `auth_sessions` data model needed by the auth flow.
- Define Lambda/API Gateway route ownership and how the current simple-login scaffold should be replaced, retained for local dev, or removed.
- Define dummy environment variable names only.
- Require official Google and Kakao documentation verification before implementation depends on provider token validation details.
- Keep real provider console setup, real OAuth credentials, real secrets, DB provisioning, and deployment as out of scope for this Spec task.

## Non-Goals

- Do not implement source code, tests, SAM template changes, README updates, event fixtures, migrations, or provider integrations in this Spec task.
- Do not commit, push, pull, merge, or rebase.
- Do not configure Google Cloud Console, Kakao Developers, OAuth redirect URIs, consent screens, or real app credentials.
- Do not record real client IDs, client secrets, REST API keys, signing secrets, provider tokens, refresh tokens, or session tokens in Git.
- Do not add password login, email signup, MFA, account recovery, admin auth, or role-management UI.
- Do not persist in-progress chat messages or unfinished itinerary drafts server-side.
- Do not introduce Cognito, EC2, WebSocket auth, graph DB behavior, or a new backend framework unless a later approved Spec changes the stack.
- Do not change the existing small-city API contract as part of auth planning.

## User Flow

### Social Login

1. User clicks Google or Kakao login in the client.
2. Client completes the provider UX and receives a provider credential according to the provider's official web login flow.
3. Client sends the credential to `POST /auth/google` or `POST /auth/kakao`.
4. `AuthFunction` verifies the provider credential server-side using official provider rules.
5. `AuthFunction` extracts a stable provider subject, verified email if available, display name, and avatar URL.
6. `AuthFunction` looks up `social_accounts(provider, provider_user_id)`.
7. If the social account exists, `AuthFunction` loads the linked service user.
8. If the social account does not exist, `AuthFunction` either links to an existing user by verified email or creates a new user.
9. `AuthFunction` creates an `auth_sessions` record and returns a short-lived service access JWT.
10. `AuthFunction` sets an HttpOnly secure session cookie for refresh/session continuity.
11. Client stores the access JWT in memory and sends it as `Authorization: Bearer <accessToken>` for protected API calls.
12. On page reload, client calls `GET /auth/session`; the HttpOnly session cookie can restore a fresh access JWT without exposing a refresh token to JavaScript.

### Current User And Session Check

1. Client calls `GET /auth/me` with a valid service access JWT to retrieve lightweight current-user identity.
2. Client calls `GET /auth/session` after login or page reload to verify the active service session and load initial lightweight dashboard/session data.
3. If the access JWT is missing or expired but the session cookie is valid, `GET /auth/session` may issue a fresh access JWT.
4. If no active session exists, the API returns the standard unauthenticated error.

### Logout

1. Client calls `POST /auth/logout`.
2. `AuthFunction` validates the session cookie and/or bearer token if present.
3. `AuthFunction` marks the matching `auth_sessions` record revoked.
4. `AuthFunction` clears the session cookie with an expired `Set-Cookie` header.
5. Client drops any in-memory access JWT.
6. Logout is idempotent: repeated logout calls return success without leaking whether a session existed.

## Requirements

### Functional Requirements

- `POST /auth/google` shall validate a Google credential server-side before issuing a Lovv service session.
- `POST /auth/kakao` shall validate a Kakao credential server-side before issuing a Lovv service session.
- Login shall reject missing, malformed, expired, wrong-audience, wrong-issuer, revoked, or otherwise invalid provider credentials.
- Login shall not trust user identity fields supplied directly by the client request body.
- Login shall look up users by existing `social_accounts(provider, provider_user_id)` first.
- Login shall create a new `users` row when no social account exists and no safe verified-email link target exists.
- Login shall create a new `social_accounts` row when a provider account is first linked to a service user.
- Login shall update provider metadata and `last_login_at` without overwriting user-owned profile fields unexpectedly.
- `GET /auth/me` shall return the current authenticated user's lightweight profile and roles.
- `GET /auth/session` shall verify an active service session and return session bootstrap data.
- `POST /auth/logout` shall revoke the server-side session when one exists and clear the session cookie.
- Public small-city routes shall stay outside this auth change unless a later approved Spec changes their access policy.
- All errors shall use the existing common JSON error envelope.

### Provider Credential Requirements

- Implementation must verify the current official Google Identity/OAuth documentation before accepting a Google `id_token`, authorization code, access token, JWKS, issuer, audience, nonce, or tokeninfo validation path.
- Implementation must verify the current official Kakao Login/OIDC documentation before accepting a Kakao access token, authorization code, ID token, user-info response, issuer, audience, or key-discovery path.
- Provider token validation details in this Spec are contract-level requirements, not a substitute for official docs verification.
- Prefer authorization-code-with-PKCE or provider ID token validation where the frontend/provider flow supports it.
- If a provider-specific MVP flow accepts a provider access token from the client, the backend must call the provider or validate the token according to official docs before trusting the provider subject.
- The backend must verify provider `aud` or app/client identity whenever the credential format supports it.
- The backend must verify token expiration and issuer whenever the credential format supports it.
- The backend must validate nonce/state if the selected provider flow returns or requires those values.

### User Lookup/Create Requirements

- The canonical lookup key for an existing social identity is `(provider, provider_user_id)`.
- `provider` values are limited to `google` and `kakao` for this Spec.
- `provider_user_id` must come from the verified provider response, not the client request body.
- If a social account exists, login uses the linked `user_id`.
- If no social account exists and the provider returns a verified email:
  - If exactly one active `users.email` match exists, link the new social account to that user.
  - If no user exists for that email, create a new user.
  - If multiple or conflicting records exist, reject with `409 CONFLICT` and require manual resolution in a later admin/support flow.
- If no social account exists and the provider email is missing or unverified, create a new user without email rather than guessing.
- Do not auto-merge users on unverified email, display name, avatar URL, or client-supplied data.
- Do not support unlinking social accounts in this Spec.
- Do not support linking more than one account from the same provider to the same user unless a later account-management Spec allows it.

### Session And JWT Requirements

- Use a short-lived service access JWT for API authorization.
- Recommended access JWT TTL: 15 minutes or less, configurable with `SERVICE_JWT_TTL_SECONDS`.
- Access JWT claims shall include at least:
  - `sub`: Lovv service user id.
  - `sid`: service session id or session public id.
  - `roles`: array of service roles, default `["R-USER"]`.
  - `provider`: `google` or `kakao` for the login that created the current session.
  - `iat`: issued-at timestamp.
  - `exp`: expiration timestamp.
  - `iss`: Lovv service issuer.
  - `aud`: Lovv API audience.
  - `jti`: unique JWT id.
- The access JWT must be sent by clients as `Authorization: Bearer <accessToken>` for protected API calls.
- Do not store access JWTs in `localStorage`.
- Store long-lived session continuity in an HttpOnly, Secure, SameSite cookie that maps to an `auth_sessions` record.
- Store only a hash of session tokens in the database.
- `GET /auth/session` may issue a new access JWT when the session cookie is valid.
- Logout must revoke the refresh/session record. For this implementation, already-issued short-lived access JWTs remain stateless and valid until the configured `exp`; immediate access-token revocation requires a later active-session authorizer check or denylist task.

### Cookie Vs Bearer Recommendation

Recommended approach: hybrid access JWT plus HttpOnly session cookie.

- Bearer access JWT is practical for API Gateway Lambda authorizers and non-cookie API authorization.
- HttpOnly cookie keeps refresh/session continuity out of JavaScript and reduces damage from XSS compared with a JavaScript-readable refresh token.
- Cookie-based session continuity requires explicit CORS origins, credentialed requests, SameSite policy, and CSRF consideration for state-changing endpoints.
- Bearer-only auth is simpler but would push refresh/session storage into JavaScript or require frequent logins.
- Cookie-only auth would simplify frontend token storage but makes API Gateway authorizer integration and non-browser clients less direct.

Implementation should keep the access JWT in memory and rely on `GET /auth/session` plus the HttpOnly cookie to restore a session after browser reload.

## API Contract

### Route Prefix

The canonical resource paths in this Spec are:

- `POST /auth/google`
- `POST /auth/kakao`
- `GET /auth/me`
- `GET /auth/session`
- `POST /auth/logout`

If API Gateway is deployed with `/api/v1` as the public base path, the externally visible paths are `/api/v1/auth/google`, `/api/v1/auth/kakao`, `/api/v1/auth/me`, `/api/v1/auth/session`, and `/api/v1/auth/logout`.

The current scaffold paths `/api/auth/login`, `/api/auth/me`, and `/api/auth/logout` are simple-login MVP paths and must not remain as production social-login paths.

### Common Error Envelope

```json
{
  "error": {
    "code": "UNAUTHENTICATED",
    "message": "Authentication is required.",
    "details": {}
  }
}
```

### `POST /auth/google`

Auth: Public.

Purpose: Validate a Google credential, upsert/link the Lovv user, create a service session, return a short-lived access JWT, and set a session cookie.

Request:

```json
{
  "credentialType": "id_token",
  "credential": "dummy-google-provider-credential",
  "redirectUri": "https://lovv.example.com/auth/callback",
  "nonce": "dummy-nonce-if-used"
}
```

Notes:

- `credentialType` allowed values must be finalized after official Google docs verification.
- `credential` is a dummy placeholder in this Spec. Never commit real provider tokens.
- `redirectUri` is required only if the selected provider flow uses server-side authorization-code exchange.
- `nonce` is required when the selected provider flow requires nonce validation.

Response 200:

```json
{
  "accessToken": "dummy-service-jwt",
  "tokenType": "Bearer",
  "expiresIn": 900,
  "session": {
    "expiresAt": "2026-06-10T12:00:00Z"
  },
  "user": {
    "userId": "uuid",
    "displayName": "Lovv User",
    "email": "user@example.com",
    "avatarUrl": "https://example.com/avatar.png",
    "roles": ["R-USER"],
    "isNewUser": false
  },
  "linkedProvider": "google"
}
```

Response headers:

```http
Set-Cookie: lovv_session=dummy-opaque-session-token; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1209600
```

Failure cases:

- `400 BAD_REQUEST`: missing credential, unsupported credential type, malformed JSON.
- `401 UNAUTHENTICATED`: provider credential invalid, expired, wrong issuer, wrong audience, or failed provider verification.
- `409 CONFLICT`: verified email maps to conflicting service users or unsafe linking condition.
- `500 INTERNAL_ERROR`: auth configuration missing or provider validation dependency unavailable.

### `POST /auth/kakao`

Auth: Public.

Purpose: Validate a Kakao credential, upsert/link the Lovv user, create a service session, return a short-lived access JWT, and set a session cookie.

Request:

```json
{
  "credentialType": "id_token",
  "credential": "dummy-kakao-oidc-id-token",
  "redirectUri": "https://lovv.example.com/auth/callback",
  "nonce": "dummy-nonce-if-used"
}
```

Notes:

- This implementation uses Kakao OIDC `id_token` validation through tokeninfo and checks `aud`, `iss`, `exp`, nonce when supplied, and subject before user lookup/create.
- Kakao may not always provide verified email. Missing or unverified email must not block login, but it must prevent email-based account linking.

Response 200: same shape as `POST /auth/google`, with `linkedProvider` set to `kakao`.

Failure cases: same categories as `POST /auth/google`.

### `GET /auth/me`

Auth: User. Requires `Authorization: Bearer <accessToken>`.

Purpose: Return the current lightweight authenticated service user.

Response 200:

```json
{
  "user": {
    "userId": "uuid",
    "displayName": "Lovv User",
    "email": "user@example.com",
    "avatarUrl": "https://example.com/avatar.png",
    "roles": ["R-USER"]
  }
}
```

Failure cases:

- `401 UNAUTHENTICATED`: missing, malformed, expired, revoked, or invalid service access JWT.
- `404 NOT_FOUND`: user from valid token no longer exists or is inactive.

### `GET /auth/session`

Auth: User session. Accepts a valid HttpOnly session cookie. May also accept a valid bearer access JWT for direct API clients.

Purpose: Verify the current Lovv service session and return lightweight session bootstrap data.

Response 200:

```json
{
  "authenticated": true,
  "accessToken": "dummy-refreshed-service-jwt-if-issued",
  "tokenType": "Bearer",
  "expiresIn": 900,
  "user": {
    "userId": "uuid",
    "displayName": "Lovv User",
    "email": "user@example.com",
    "avatarUrl": "https://example.com/avatar.png",
    "roles": ["R-USER"]
  },
  "preferences": {
    "countryTrack": "JP",
    "mappedThemes": ["art_sense", "history_tradition"]
  },
  "savedItineraries": [
    {
      "itineraryId": "uuid",
      "destinationName": "Kanazawa",
      "country": "JP",
      "updatedAt": "2026-06-10T09:00:00Z"
    }
  ]
}
```

Notes:

- `preferences` and `savedItineraries` are lightweight bootstrap data only.
- If those backing tables are not ready during the first implementation, return empty objects or arrays while keeping the response keys stable.
- Do not include provider tokens, refresh tokens, session token hashes, raw user-agent values, or raw IP addresses.

Failure cases:

- `401 UNAUTHENTICATED`: no active service session or invalid bearer access JWT.
- `404 NOT_FOUND`: active session references a deleted or inactive user.

### `POST /auth/logout`

Auth: User session. Accepts a valid HttpOnly session cookie and/or bearer access JWT.

Purpose: Revoke the Lovv service session and clear the session cookie.

Request body: empty JSON object or no body.

Response 200:

```json
{
  "success": true
}
```

Response headers:

```http
Set-Cookie: lovv_session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0
```

Notes:

- Logout is idempotent.
- Logout must not return provider tokens, session tokens, token hashes, or secret material.
- Logout does not revoke Google/Kakao provider sessions unless a later Spec adds provider-side disconnect/revoke behavior.

## Data Model

The current Lovv database document defines `users` and `social_accounts`. It does not fully define `auth_sessions`; this Spec adds `auth_sessions` as a logical requirement because server-side session continuity and logout invalidation require a service-owned session record.

Physical DB engine, connection path, migration tool, and readiness must be confirmed before implementation. The logical model below should be mapped to the approved DB engine by a later Task.

### `users`

Purpose: service user profile source of truth.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid/string | yes | Service user id. |
| `email` | string nullable | no | Provider email only when available. Unique for non-null active users if DB supports partial unique index. |
| `email_verified` | boolean | no | True only when provider verification proves it. |
| `display_name` | string | yes | Initial value from provider or generated fallback. User-owned changes should not be overwritten by later provider metadata updates. |
| `avatar_url` | string nullable | no | Initial provider avatar. |
| `status` | string | yes | `active`, `disabled`, or `deleted`. |
| `created_at` | datetime | yes | Server timestamp. |
| `updated_at` | datetime | yes | Server timestamp. |
| `last_login_at` | datetime nullable | no | Updated after successful service login. |

Indexes:

- `users(email)` for verified-email lookup.
- `users(status)` if active/disabled filtering needs it.

### `social_accounts`

Purpose: link provider identities to Lovv service users.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid/string | yes | Social account row id. |
| `user_id` | uuid/string | yes | FK to `users.id`. |
| `provider` | string | yes | `google` or `kakao`. |
| `provider_user_id` | string | yes | Stable provider subject from verified provider response. |
| `provider_email` | string nullable | no | Provider email, if supplied. |
| `provider_email_verified` | boolean nullable | no | Provider verified-email flag, if supplied. |
| `provider_display_name` | string nullable | no | Provider profile display name. |
| `provider_avatar_url` | string nullable | no | Provider profile avatar URL. |
| `created_at` | datetime | yes | Server timestamp. |
| `updated_at` | datetime | yes | Server timestamp. |
| `last_login_at` | datetime nullable | no | Updated after successful login through this provider. |

Constraints and indexes:

- Unique: `(provider, provider_user_id)`.
- Index: `(user_id)`.
- Optional unique, if approved later: `(user_id, provider)` to limit one linked account per provider per user.

### `auth_sessions`

Purpose: server-side Lovv session continuity, refresh, and logout invalidation.

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | uuid/string | yes | Public session id used in JWT `sid` claim. |
| `user_id` | uuid/string | yes | FK to `users.id`. |
| `session_token_hash` | string | yes | Hash of opaque session cookie token. Never store raw session token. |
| `provider` | string | yes | Provider used to create the session. |
| `created_at` | datetime | yes | Server timestamp. |
| `expires_at` | datetime | yes | Session expiry. |
| `last_seen_at` | datetime nullable | no | Updated on session checks when appropriate. |
| `revoked_at` | datetime nullable | no | Set on logout or forced invalidation. |
| `user_agent_hash` | string nullable | no | Hash only. Do not store raw user-agent unless a later privacy review approves it. |
| `ip_hash` | string nullable | no | Hash only. Do not store raw IP unless a later privacy review approves it. |

Constraints and indexes:

- Unique: `session_token_hash`.
- Index: `(user_id, expires_at)`.
- Index: `(revoked_at, expires_at)` if cleanup jobs need it.

Retention:

- Expired and revoked sessions should be cleaned up by a future scheduled task or DB TTL mechanism once the physical store is approved.
- Session retention must not become durable conversation or itinerary-draft persistence.

## Lambda/API Gateway Boundary

### AuthFunction

Owns:

- `POST /auth/google`
- `POST /auth/kakao`
- `GET /auth/session`
- `POST /auth/logout`
- Optional direct handling for `GET /auth/me` if the authorizer forwards user context to the same Lambda.

Responsibilities:

- Parse and validate request bodies.
- Verify provider credentials server-side.
- Normalize provider identity into a provider profile.
- Upsert `users` and `social_accounts`.
- Create, read, and revoke `auth_sessions`.
- Issue service access JWTs.
- Set and clear HttpOnly session cookies.
- Return common JSON error responses.

Must not own:

- Small-city data reads.
- AI, RAG, recommendation, or itinerary-generation logic.
- Provider console setup or real secret storage.

### AuthAuthorizerFunction

Owns:

- API Gateway authorizer for protected routes that use `Authorization: Bearer <accessToken>`.

Responsibilities:

- Validate service access JWT signature, issuer, audience, expiration, and required claims.
- Reject missing, malformed, expired, invalid, or revoked tokens.
- Optionally check `auth_sessions` active status using `sid` when immediate logout revocation is required.
- Return minimal user context to downstream Lambdas.

Caching:

- Do not cache authorizer decisions beyond the accepted logout-revocation window.
- Default recommendation: disable or keep very short authorizer result caching until session invalidation behavior is verified.

### API Gateway

Responsibilities:

- Route public login endpoints to `AuthFunction`.
- Route session and logout endpoints to `AuthFunction`.
- Apply authorizer to protected user-specific routes.
- Allow `Authorization`, `Content-Type`, and `Cookie` request headers where needed.
- If cookies are used cross-origin, replace wildcard CORS origins with explicit configured origins and allow credentials.

### Current Simple-Login Scaffold Disposition

| Current File/Route | Current Role | Future Disposition |
| --- | --- | --- |
| `template.yaml` route `POST /api/auth/login` | Demo login route | Remove or move behind local/dev-only route. Production social auth uses `POST /auth/google` and `POST /auth/kakao` under the approved API base. |
| `template.yaml` route `GET /api/auth/me` | Demo token current user | Replace path and response with `GET /auth/me`; preserve only the concept of current-user introspection. |
| `template.yaml` route `POST /api/auth/logout` | Stateless demo logout | Replace with session-backed `POST /auth/logout` that revokes `auth_sessions` and clears cookie. |
| `template.yaml` parameters `DemoLoginUserId`, `DemoLoginDisplayName`, `DemoLoginCode` | Demo configuration | Local/dev only. Remove from production auth configuration. |
| `template.yaml` parameters `AuthTokenSigningSecret`, `AuthTokenTtlSeconds`, `AuthIssuer`, `AuthAudience` | Demo service JWT config | Replace or rename to social-auth service JWT names. Keep only if Task Agent chooses backward-compatible names deliberately. |
| `src/auth/app.py` | Demo login, me, logout handler | Replace request routing and demo code validation with Google/Kakao validation, user upsert, session handling, and logout invalidation. |
| `src/auth/authorizer.py` | Demo HMAC JWT authorizer | Refactor to validate production service JWT claims and optional active session status. |
| `src/shared/auth.py` | Demo HMAC JWT helpers | Replace demo defaults and claims with service JWT/session utilities. Keep reusable primitives only if they meet this Spec. |
| `events/auth-login.json` | Demo login event | Replace with Google/Kakao login sample events using dummy credentials only. |
| `events/auth-me.json` | Demo me event | Replace path/claims with social-auth JWT/session shape. |
| `events/auth-logout.json` | Demo logout event | Replace with cookie/session logout sample. |
| `tests/test_auth_app.py` | Demo auth tests | Replace with provider validation mocking, upsert, session, me, and logout tests. |
| `tests/test_auth_authorizer.py` | Demo authorizer tests | Replace with service JWT and revoked/expired/session edge tests. |
| `src/small_cities/**` | Public small-city API | Keep unchanged unless a later approved auth integration Task explicitly touches route protection. |

Implementation must not expose both the old demo login path and new social login paths in production unless a later approved compatibility Spec explicitly requires it.

## Security

- Real secrets must never be hardcoded or committed.
- `.env`, `.env.local`, local SAM parameter files containing real values, provider tokens, and session secrets must remain ignored by Git.
- Provider console setup and real credential generation are out of scope for this Spec.
- Required env vars below use dummy placeholders only.
- Provider credentials must be verified server-side before any user lookup, creation, linking, or session issuance.
- Do not trust client-supplied user id, email, display name, avatar URL, roles, provider, or provider subject.
- Do not auto-link accounts using unverified email.
- Hash session tokens before persistence.
- Use constant-time comparison where comparing token hashes or signatures directly.
- Access JWT signing must use a strong secret or approved asymmetric key path. The key source must be environment/secret manager, not source code.
- Session cookies must be `HttpOnly`, `Secure` outside local development, and `SameSite=Lax` by default.
- If cross-site login embedding requires `SameSite=None`, require `Secure` and a CSRF review before implementation.
- If cookies are sent cross-origin, CORS must use explicit allowed origins, not `*`.
- Logout must clear cookies and revoke server-side sessions.
- Provider access tokens, ID tokens, authorization codes, service access JWTs, and session cookie values must not be logged.
- Store only hashed IP and user-agent values if needed for session risk signals.
- A Backend Security Review Agent is required before production deployment of this auth flow.

### Required Environment Variables

All values below are dummy placeholders or names only. Real values must come from a deployment secret mechanism and must not be committed.

| Environment Variable | Scope | Purpose | Dummy Placeholder |
| --- | --- | --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` | AuthFunction | Expected Google client/app id or audience. | `dummy-google-client-id.apps.exampleusercontent.com` |
| `GOOGLE_OAUTH_CLIENT_SECRET` | AuthFunction | Required only if server-side code exchange is selected. | `replace-with-secret-manager-value` |
| `GOOGLE_OAUTH_ISSUER` | AuthFunction | Expected Google issuer if ID token validation is selected. | `https://accounts.google.com` |
| `KAKAO_REST_API_KEY` | AuthFunction | Kakao REST API key or app id used for validation/code exchange. | `dummy-kakao-rest-api-key` |
| `KAKAO_CLIENT_SECRET` | AuthFunction | Required only if the selected Kakao app flow uses a client secret. | `replace-with-secret-manager-value` |
| `KAKAO_OAUTH_ISSUER` | AuthFunction | Expected Kakao issuer if Kakao OIDC ID token validation is selected. | `https://kauth.kakao.com` |
| `SERVICE_JWT_SIGNING_SECRET` | AuthFunction, AuthAuthorizerFunction | Service access JWT signing secret. | `replace-with-secret-manager-value` |
| `SERVICE_JWT_ISSUER` | AuthFunction, AuthAuthorizerFunction | Lovv service JWT issuer. | `lovv-auth` |
| `SERVICE_JWT_AUDIENCE` | AuthFunction, AuthAuthorizerFunction | Lovv API audience. | `lovv-api` |
| `SERVICE_JWT_TTL_SECONDS` | AuthFunction, AuthAuthorizerFunction | Access JWT TTL. | `900` |
| `AUTH_SESSION_COOKIE_NAME` | AuthFunction | Session cookie name. | `lovv_session` |
| `AUTH_SESSION_TTL_SECONDS` | AuthFunction | Server session TTL. | `1209600` |
| `AUTH_COOKIE_DOMAIN` | AuthFunction | Cookie domain for deployed environments. | `.lovv.example.com` |
| `AUTH_COOKIE_SECURE` | AuthFunction | Whether to force Secure cookie. | `true` |
| `AUTH_COOKIE_SAMESITE` | AuthFunction | Cookie SameSite policy. | `Lax` |
| `ALLOWED_WEB_ORIGINS` | API Gateway/AuthFunction | Explicit CORS origins for credentialed browser calls. | `https://lovv.example.com,http://localhost:5173` |
| `AUTH_DB_SECRET_ID` | AuthFunction, AuthAuthorizerFunction if session lookup is required | Secret manager id for DB credentials, not the secret value itself. | `lovv/auth/db` |
| `AUTH_DB_NAME` | AuthFunction | Logical auth/user DB name. | `lovv` |

If the approved physical session store is DynamoDB instead of the relational user DB, Task Agent must update implementation subtasks with a specific table name, IAM actions, TTL behavior, and cleanup strategy before code is written.

## Acceptance Criteria

- The Spec preserves `User Request Original` and the structured contract.
- The Spec defines Google and Kakao login endpoints.
- The Spec defines current user and session check endpoints.
- The Spec defines logout behavior.
- The Spec defines user lookup/create semantics.
- The Spec defines social account linking semantics.
- The Spec defines a service JWT and server-side session strategy.
- The Spec recommends cookie vs bearer behavior and explains the tradeoff.
- The Spec lists dummy environment variable names only.
- The Spec marks provider console setup and real secret values as out of scope.
- The Spec requires official Google and Kakao documentation verification before implementation relies on provider validation details.
- The Spec defines which current simple-login files/routes should be replaced, kept only for local dev, or removed.
- The Spec keeps small-city API behavior out of scope.
- The Spec includes Summary, Goals, Non-Goals, User Flow, Requirements, API Contract, Data Model, Lambda/API Gateway Boundary, Security, Acceptance Criteria, Risks, Task Breakdown, and Verification.

## Risks

- Provider credential validation differs by Google/Kakao flow and can be implemented incorrectly if official docs are not checked immediately before coding.
- Kakao email may be absent or unverified, so account linking must not depend on email alone.
- Auto-linking by verified email can still surprise users if they expected separate accounts; this should be product-reviewed before implementation.
- Server-side session storage adds DB readiness, migration, cleanup, and IAM concerns that the current simple-login MVP did not have.
- Authorizer session checks improve logout revocation but add latency and DB dependency to protected routes.
- If authorizer checks only JWT signature and expiry, logout may not revoke already-issued access JWTs until the short TTL expires.
- Cookie-based session continuity requires explicit CORS origins and credentialed browser requests; the current wildcard CORS scaffold is insufficient for production cookies.
- Real provider secrets and provider tokens are high-risk values and must not appear in tests, fixtures, logs, docs, commits, or screenshots.
- Supporting old `/api/auth/login` alongside social login in production could create an unintended bypass.
- The Lovv DB engine and migration path are not finalized; implementation must verify the approved DB path before creating schema or live connections.

## Task Breakdown

### Task: Provider validation decision and docs verification

- Purpose: Google/Kakao 공식 문서를 확인해 어떤 credential flow를 구현할지 확정한다.
- Scope: Google/Kakao credential type, issuer/audience validation, token exchange or token introspection, nonce/state requirements, provider profile fields를 확정한다. 코드 구현은 제외한다.
- Dependencies: This Spec approval.
- Context Budget: Must read this Spec and current official Google/Kakao auth docs. Do not read unrelated Lovv frontend or AI docs.
- Acceptance Criteria: Google/Kakao 각각에 대해 허용할 `credentialType`, 검증 절차, 필요한 env vars, 실패 조건이 구현 가능한 수준으로 확정된다.
- Verification: Task Agent or Review Agent confirms that official docs were checked and implementation assumptions are cited in the task packet.

### Task: Auth data model and session store finalization

- Purpose: `users`, `social_accounts`, `auth_sessions`의 실제 저장소와 migration 범위를 구현 전에 확정한다.
- Scope: logical columns, indexes, uniqueness, session hashing, expiration, revoked session cleanup, DB connection path. Provider console setup and code implementation are excluded.
- Dependencies: Provider validation decision.
- Context Budget: Must read this Spec and `oh_my_documents/docs/04_database_design/04_database_design.md` relevant user/social-account sections. Conditional read: approved DB readiness docs if they exist.
- Acceptance Criteria: user upsert, social linking, session creation, session lookup, and logout invalidation can be implemented without guessing the physical store.
- Verification: DB/Security review confirms no raw session tokens, provider tokens, or real secrets are persisted.

### Task: Social AuthFunction implementation

- Purpose: Google/Kakao login, user upsert, session creation, and response shaping을 Auth Lambda에 구현한다.
- Scope: `src/auth/**`, approved auth repository/session modules, and focused auth tests. `src/small_cities/**` and unrelated routes are out of scope.
- Dependencies: Provider validation decision and data model/session store finalization.
- Context Budget: Must read this Spec sections `Requirements`, `API Contract`, `Data Model`, `Security`, and the implementation task packet. Do not read the full planning docs unless a referenced detail conflicts.
- Acceptance Criteria: `POST /auth/google` and `POST /auth/kakao` validate provider credentials through mocked/provider abstraction tests, upsert/link users safely, create sessions, issue service JWTs, set cookies, and return the agreed response shape.
- Verification: Auth handler unit tests and provider validation mock tests pass.

### Task: Session, current user, and logout implementation

- Purpose: 세션 확인, 현재 사용자 조회, 로그아웃을 service session 정책에 맞게 구현한다.
- Scope: `GET /auth/me`, `GET /auth/session`, `POST /auth/logout`, cookie handling, session revocation, focused tests.
- Dependencies: Social AuthFunction implementation and session store availability.
- Context Budget: Must read this Spec sections `User Flow`, `API Contract`, `Session And JWT Requirements`, and `Security`.
- Acceptance Criteria: active sessions return current user/session bootstrap data, invalid sessions return `401`, logout revokes the server session, clears the cookie, and remains idempotent.
- Verification: Tests cover valid session, expired session, revoked session, missing cookie/token, logout success, repeated logout, and no token leakage in responses.

### Task: Service JWT authorizer update

- Purpose: API Gateway protected routes can validate service JWTs produced by social login.
- Scope: `src/auth/authorizer.py`, `src/shared/auth.py` or approved JWT/session utility files, and authorizer tests.
- Dependencies: Service JWT claim shape and session revocation policy finalized.
- Context Budget: Must read this Spec sections `Session And JWT Requirements`, `Lambda/API Gateway Boundary`, and `Security`.
- Acceptance Criteria: authorizer validates required claims, rejects missing/malformed/expired/wrong-issuer/wrong-audience/revoked tokens, and returns minimal downstream user context.
- Verification: Authorizer unit tests cover all accept/reject paths and session revocation behavior selected by the Task Agent.

### Task: SAM routes, CORS, env vars, and IAM update

- Purpose: `template.yaml`을 social auth contract에 맞게 갱신한다.
- Scope: Auth routes, authorizer attachment, CORS headers/origins/credentials, env var declarations, DB/session/provider IAM permissions. Auth business logic is out of scope.
- Dependencies: Handler names, route prefix decision, session store decision, and provider env var decision.
- Context Budget: Must read this Spec and `template.yaml`. Conditional read: official SAM docs for HTTP API authorizers/CORS if syntax is uncertain.
- Acceptance Criteria: old production demo login route is removed or made local/dev-only, social auth routes are defined, protected routes use the authorizer where appropriate, CORS supports cookies safely, and IAM is least privilege.
- Verification: `sam validate`, template review, and route table review.

### Task: Simple-login scaffold migration

- Purpose: 기존 demo-login 산출물이 production social auth와 섞이지 않도록 정리한다.
- Scope: current `DEMO_LOGIN_*` params, `/api/auth/login` route, auth sample events, and auth tests. Keep local/dev-only samples only if clearly named and disabled for production.
- Dependencies: SAM route update and social auth handler contract.
- Context Budget: Must read this Spec section `Current Simple-Login Scaffold Disposition`, existing simple-login Spec, and changed auth files only.
- Acceptance Criteria: production API has no demo login bypass, old response casing does not conflict with new API contract, and remaining dev-only scaffolds cannot be enabled accidentally in production.
- Verification: Tests and template review confirm no production `POST /api/auth/login` demo path remains.

### Task: Backend auth security review

- Purpose: production-direction auth changes are reviewed for provider validation, secret safety, account linking, session security, CORS, and IAM.
- Scope: read-only review of the final implementation diff, tests, template, and verification outputs.
- Dependencies: All implementation tasks complete.
- Context Budget: Must read this Spec, changed-file list, auth tests, `template.yaml`, and verification summaries. Read only relevant failure logs.
- Acceptance Criteria: No blocker remains for secret leakage, auth bypass, unsafe linking, invalid session behavior, wildcard credentialed CORS, excessive IAM, or provider-doc mismatch.
- Verification: Review Agent report with blocker/non-blocker findings and explicit approval status.

## Verification

This Spec task verification:

- Confirm exactly this Spec file was created.
- Confirm no source code, tests, README, SAM template, event fixtures, commits, pushes, pulls, merges, or rebases were performed.
- Confirm the Spec includes all user-required sections.
- Confirm the Spec preserves the original Korean request.
- Confirm the Spec calls out official Google/Kakao docs verification before implementation.
- Confirm the Spec identifies simple-login scaffold replacement/dev-only/removal decisions.

Future implementation verification:

- `sam validate`
- Auth handler unit tests.
- Provider validation adapter tests with mocked Google/Kakao responses.
- User upsert and social account linking tests.
- Session repository tests.
- Authorizer tests for valid, missing, malformed, expired, wrong issuer, wrong audience, and revoked tokens.
- API Gateway event tests for:
  - `POST /auth/google`
  - `POST /auth/kakao`
  - `GET /auth/me`
  - `GET /auth/session`
  - `POST /auth/logout`
- CORS review for explicit origins and credentialed requests.
- Security review for secret handling, token logging, account linking, session hashing, cookie flags, CSRF exposure, authorizer caching, and IAM scope.
