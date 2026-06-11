# Product API Decisions

Agent Name: Backend Product API Decision Agent
Core Role: Task Agent
Domain Focus: Backend AWS SAM
Work Focus: product API decisions

## Scope

This file records product API decisions only. It does not implement code, edit `template.yaml`, define database migrations, create repositories, configure provider consoles, or approve deployment.

Required context reviewed:

- `docs/specs/PRODUCT_API_DOMAIN_TASKS.md`
- `docs/specs/AUTH_SOCIAL_LOGIN_API_SPEC.md`
- `docs/specs/USER_PREFERENCE_API_SPEC.md`
- `docs/specs/MAP_CITY_API_SPEC.md`
- `docs/specs/AGENTCORE_ITINERARY_API_SPEC.md`
- `docs/specs/SAVED_PLANS_API_SPEC.md`
- `template.yaml`
- `/Users/jeonjonghyeok/Documents/Final/oh_my_documents/docs/07_api_spec/mvp_confirmed_api_contract.md`
- `/Users/jeonjonghyeok/Documents/Final/oh_my_documents/docs/07_api_spec/07_api_spec.md`
- Google official docs:
  - <https://developers.google.com/identity/gsi/web/guides/verify-google-id-token>
  - <https://developers.google.com/identity/sign-in/web/backend-auth>
- Kakao official docs:
  - <https://developers.kakao.com/docs/en/kakaologin/rest-api>
  - <https://developers.kakao.com/docs/en/kakaologin/common>

## Decision Summary

| Decision Area | Decision |
| --- | --- |
| Product route prefix | Use `/api/v1` as the single public product API base for new product APIs. Preserve existing `/api/small-cities` routes as compatibility routes until a separate migration or alias Spec is approved. |
| Provider validation | Google and Kakao provider credentials must be validated server-side using official provider rules before service user lookup, creation, linking, or session issuance. |
| Simple-login scaffold | Remove from production product auth. A dev-only demo login may be retained only if isolated, disabled by default, and impossible to deploy as a production bypass. |
| Auth identity convention | Service JWT `sub` is the Lovv service user id. DB columns use `user_id`. Public API fields use `userId`. Provider subjects live only in `social_accounts.provider_user_id`. |
| Theme mapping | Exact canonical `themeId` to Map/City Korean-label mapping is still pending. Do not pass canonical IDs into `/api/small-cities?themes=` until a mapping contract is approved. |
| DB/session store | Still blocked. Physical store, migration path, connection path, session TTL cleanup, and revocation lookup policy are not approved by current docs. |

## 1. Route Prefix Recommendation

Decision:

- New product APIs should use one public base: `/api/v1`.
- Product logical routes should be externally exposed as:
  - `POST /api/v1/auth/google`
  - `POST /api/v1/auth/kakao`
  - `GET /api/v1/auth/me`
  - `GET /api/v1/auth/session`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/me/preferences`
  - `PUT /api/v1/me/preferences`
  - `POST /api/v1/recommendations`
  - `GET /api/v1/recommendations/{recommendationId}` only after the short-lived recommendation lookup contract is confirmed
  - `POST /api/v1/me/itineraries`
  - `GET /api/v1/me/itineraries`
  - `GET /api/v1/me/itineraries/{itineraryId}`
  - `PUT /api/v1/me/itineraries/{itineraryId}/reactions/like`
  - `DELETE /api/v1/me/itineraries/{itineraryId}/reactions/like`
- Existing Map/City backend compatibility routes remain:
  - `GET /api/small-cities`
  - `GET /api/small-cities/{cityId}`
- Do not replace `/api/small-cities` with `/destinations/*` in the next implementation task.
- If the product later requires `/api/v1/destinations/*`, create a separate route migration or alias Spec that defines:
  - whether `/api/v1/destinations/map-markers` aliases `/api/small-cities` or returns a lean marker projection,
  - whether `/api/v1/destinations/{destinationId}` maps to `cityId`,
  - response-shape differences,
  - compatibility and deprecation behavior.

Rationale:

- `mvp_confirmed_api_contract.md` and `07_api_spec.md` both use `/api/v1` as the product base.
- Auth, User Preference, AgentCore, and Saved Plans Specs define logical product routes that fit cleanly under `/api/v1`.
- `MAP_CITY_API_SPEC.md` explicitly preserves `/api/small-cities` and `/api/small-cities/{cityId}` as the active backend boundary, and `template.yaml` currently exposes those routes.
- Preserving `/api/small-cities` avoids breaking current backend compatibility while allowing product APIs to converge on `/api/v1`.

Implementation implications:

- `template.yaml` route expansion must be handled by exactly one future SAM Template Owner.
- Auth, preference, AgentCore, and saved-plan route implementation may proceed only after Main Codex accepts `/api/v1` as the product public base.
- Map/City hardening can proceed without changing route paths.
- API Gateway base path, stage mapping, local SAM paths, and deployed URL behavior still need a route implementation task before code changes.

## 2. Provider Validation Recommendation

Decision:

- Google login must not accept a plain user id, email, display name, provider subject, or profile payload from the client as proof of identity.
- Kakao login must not accept a plain user id, mutable email, phone number, profile payload, or unverified token payload from the client as proof of identity.
- Both providers must produce a verified provider subject before Lovv creates, links, or loads a service user.

### Google

Recommended contract:

- Accept a Google ID token from the official Google Identity flow, or an authorization code only if the implementation task explicitly selects a code-exchange flow.
- For Google ID tokens, backend verification must validate at least:
  - JWT signature using Google public keys or official Google library,
  - `aud` equals an approved Lovv Google client id,
  - `iss` equals `accounts.google.com` or `https://accounts.google.com`,
  - `exp` has not passed,
  - CSRF and nonce/state requirements when the chosen frontend flow requires them.
- Use the verified Google ID token `sub` only as `social_accounts.provider_user_id`.
- Do not use Google email as the stable provider identity or Lovv service user id.

Official-source basis:

- Google says the backend should verify ID-token integrity, including signature, audience, issuer, and expiration.
- Google says only the ID token `sub` should be used as the unique Google-account identifier and that email is not a stable identifier.

### Kakao

Recommended contract:

- Prefer Kakao authorization-code exchange with OIDC enabled when feasible:
  - exchange code through `https://kauth.kakao.com/oauth/token`,
  - validate the returned ID token using Kakao OIDC discovery and JWKS from `https://kauth.kakao.com/.well-known/openid-configuration`.
- If an ID token is accepted directly from the client, validate it server-side before trust.
- Backend validation must validate at least:
  - JWT signature using Kakao OIDC JWKS,
  - issuer `https://kauth.kakao.com`,
  - audience/client id against the approved Kakao REST API key or app id,
  - expiration,
  - nonce when used.
- Treat Kakao `https://kauth.kakao.com/oauth/tokeninfo` as debugging/reference only, not as the production validity-verification path.
- Use the verified Kakao service user id / ID token `sub` only as `social_accounts.provider_user_id`.
- Do not use Kakao email or phone number as the service user id because Kakao marks those as mutable account information.

Official-source basis:

- Kakao REST docs define authorization code and token APIs, OIDC behavior, OIDC discovery, and the token endpoint.
- Kakao docs state the ID-token-info API is for debugging and that production services must perform ID-token validity verification rather than payload-only validation.
- Kakao common docs recommend mapping by service user ID and warn against using mutable email or phone as the service user ID.

Implementation implications:

- Future auth implementation needs provider validation adapters with mocked official responses in tests.
- Required env var names may be listed with dummy values only; real client ids, REST API keys, client secrets, tokens, and session values must not be committed.
- Provider validation decisions should be reviewed by a Backend Security Review Agent before production deployment.

## 3. Simple-Login Scaffold Disposition

Decision:

- The current simple-login scaffold is not a production auth contract.
- Production product auth must remove or bypass from production:
  - `POST /api/auth/login`
  - `DEMO_LOGIN_USER_ID`
  - `DEMO_LOGIN_DISPLAY_NAME`
  - `DEMO_LOGIN_CODE`
  - stateless demo logout behavior
  - any demo-login path that can issue a service token in deployed production
- `GET /api/auth/me` and `POST /api/auth/logout` should be replaced by product routes under `/api/v1/auth/me` and `/api/v1/auth/logout` when the auth route migration task runs.
- If local demo login is still useful for development, it may remain only as a local/dev-only scaffold with all of these controls:
  - not mounted under `/api/v1`,
  - disabled by default,
  - explicitly named as local/demo,
  - unavailable in production deployment parameters,
  - covered by template/static checks that prevent accidental production exposure.

Implementation implications:

- The Auth implementation task should not expose old and new login paths together in production.
- Auth tests should be replaced or split so production tests cover provider validation, session creation, `/auth/me`, `/auth/session`, and session-backed logout.
- A future SAM template task must remove production demo-login parameters or isolate them behind local-only deployment configuration.

## 4. Auth Identity Convention

Decision:

- Lovv service user identity:
  - Service JWT claim: `sub`
  - Meaning: `users.id`, the Lovv service user id
  - Not: Google `sub`, Kakao `sub`, provider access token subject, email, phone, display name, or client-supplied id
- Session identity:
  - Service JWT claim: `sid`
  - Meaning: public service session id matching an `auth_sessions` record after session store approval
- Provider identity:
  - DB column: `social_accounts.provider_user_id`
  - Meaning: verified provider subject, such as Google ID-token `sub` or Kakao service user id / ID-token `sub`
- Internal DB ownership:
  - Use `user_id` columns in tables such as `social_accounts`, `auth_sessions`, `user_preferences`, `itineraries`, and `plan_reactions`.
- Public API response ownership:
  - Use `userId` in response bodies.
- Request-body ownership:
  - Product APIs must reject or ignore writable `userId`, `user_id`, `ownerId`, `createdBy`, provider subject, or equivalent owner fields.

Recommended authorizer-to-handler context:

- `userId`: service JWT `sub`
- `sessionId`: service JWT `sid`, when present
- `roles`: service roles, default `["R-USER"]`
- `provider`: current session provider, when relevant

Implementation implications:

- User Preference and Saved Plans handlers must derive ownership only from trusted authorizer/session context.
- AgentCore may load preferences only after a valid token resolves `userId`.
- Provider account linking must use `(provider, provider_user_id)` and map that row to service `user_id`.

## 5. Theme Mapping Recommendation

Decision:

- Exact canonical `themeId` to Map/City Korean-label mapping remains pending.
- Do not implement canonical theme filters against `/api/small-cities` yet.
- Do not pass values such as `history_tradition`, `food_local`, `art_sense`, or `healing_rest` directly into `/api/small-cities?themes=`.
- Keep current Map/City filtering by Korean labels:
  - `온천`
  - `바다`
  - `미식`
  - `전통`
  - `자연`
  - `예술`
  - `축제`
  - `산책`

Provisional mapping candidates for the next mapping decision task, not yet approved for implementation:

| Canonical `themeId` | Candidate Map/City labels | Status |
| --- | --- | --- |
| `history_tradition` | `전통` | Likely, but needs approval. |
| `food_local` | `미식` | Likely, but needs approval. |
| `art_sense` | `예술` | Likely, but needs approval. |
| `healing_rest` | `자연`, `산책`, `온천` | Ambiguous; exact labels and match semantics pending. |

Required next decision:

- Define the full approved canonical theme enum.
- Map every canonical `themeId` to one or more current Map/City labels, or mark it unsupported for MVP.
- Define whether multi-label mappings use OR semantics or ranking boosts.
- Define whether `바다` and `축제` have canonical IDs.
- Define `destinationId` and `cityId` aliasing:
  - current Map/City `cityId` equals `SmallCityApiRecord.id`,
  - product `destinationId` may alias `cityId` only after an approved route/identifier mapping Spec.

Implementation implications:

- AgentCore request validation may accept canonical `themeId` values, but city lookup must wait for the mapping contract.
- User Preference may store canonical `mappedThemes`, but Map/City must keep its current `themes` query contract.
- Saved Plans may store canonical `themes` from the generated recommendation snapshot, but those values must not be treated as Map/City labels.

## 6. DB And Session Store Approval

Decision:

- DB/session store approval is still blocked.
- Do not create DB migrations, schema files, repository code, live DB connection code, seed data, or session persistence code from the current docs.

Blocked items:

- Physical DB engine for user-owned product state.
- Migration directory, migration tool, rollback command, and deployment path.
- DB connection path for Lambda functions.
- `auth_sessions` physical store:
  - relational table vs DynamoDB table,
  - TTL behavior,
  - cleanup strategy,
  - session-token hash uniqueness,
  - revocation lookup behavior,
  - authorizer cache policy.
- `user_preferences` physical table/store and uniqueness on `user_id`.
- Saved Plans schema reconciliation:
  - `itineraries`,
  - `itinerary_items`,
  - possible `itinerary_days`,
  - `plan_reactions`,
  - `sourceRecommendationId`,
  - `destination`,
  - `tripType`,
  - `themes`,
  - day grouping,
  - full item body,
  - snapshot hash,
  - idempotency key,
  - active like uniqueness.

Implementation implications:

- Social auth can be planned around logical `users`, `social_accounts`, and `auth_sessions`, but production implementation cannot persist sessions until the physical store is approved.
- User Preference and Saved Plans implementation must wait for DB readiness.
- AgentCore can remain request/response and mocked-adapter focused, but authenticated preference loading depends on auth and preference store readiness.
- `GET /auth/session` aggregation cannot be fully implemented until session store and preference read boundaries are approved.

## 7. Next Task Agent Input

Recommended next Task Agent package:

### Task A: Product Route Implementation Subtasks

- Source of Truth: this decision file, `AUTH_SOCIAL_LOGIN_API_SPEC.md`, `USER_PREFERENCE_API_SPEC.md`, `AGENTCORE_ITINERARY_API_SPEC.md`, `SAVED_PLANS_API_SPEC.md`, `MAP_CITY_API_SPEC.md`, and `template.yaml`.
- Purpose: create implementation-ready subtasks for mounting new product APIs under `/api/v1` while preserving `/api/small-cities`.
- Target owner: one SAM Template Owner for `template.yaml`.
- Out of Scope: DB migrations, provider code, frontend adapters.
- Verification to define: `sam validate` when available, static route table review, and route-prefix `rg` checks.

### Task B: Auth Provider Validation And Scaffold Cleanup Subtasks

- Source of Truth: this decision file and `AUTH_SOCIAL_LOGIN_API_SPEC.md`.
- Purpose: create sequential auth subtasks for provider validation adapter, user upsert/linking, service JWT/session shape, `/auth/session`, `/auth/me`, logout, and simple-login removal/dev-only containment.
- Dependencies: DB/session store approval before production session persistence.
- Required review: Backend Security Review Agent.

### Task C: DB/Session Store Readiness Decision

- Source of Truth: this decision file, Auth/User Preference/Saved Plans Specs, and approved DB design docs.
- Purpose: approve or block the physical store for `auth_sessions`, `user_preferences`, saved itineraries, items/day grouping, and reactions.
- Output: one DB readiness decision or schema task packet.
- Out of Scope: DDL until approved.
- Required review: Database Review Agent and Security Review Agent.

### Task D: Theme And Destination Mapping Decision

- Source of Truth: this decision file, `MAP_CITY_API_SPEC.md`, `USER_PREFERENCE_API_SPEC.md`, `AGENTCORE_ITINERARY_API_SPEC.md`, `SAVED_PLANS_API_SPEC.md`, and `mvp_confirmed_api_contract.md`.
- Purpose: approve the exact canonical `themeId` to Map/City label mapping and `destinationId`/`cityId` alias rule.
- Output: mapping table usable by AgentCore and future product map routes.
- Out of Scope: changing `/api/small-cities` query behavior.

### Task E: Map/City Compatibility Hardening

- Source of Truth: `MAP_CITY_API_SPEC.md`, current small-city contracts, and `template.yaml`.
- Purpose: proceed with route-compatible Map/City tests and mapper hardening without auth, DB, route migration, or product `/destinations/*` changes.
- Candidate verification: `python3 -m unittest tests/test_small_city_handler.py tests/test_small_city_mapper.py`.

## 8. Implementation Candidates After Decisions

Can proceed now, if assigned separately:

- Map/City compatibility and test hardening for existing `/api/small-cities` routes.
- Static SAM route review for current routes, without editing `template.yaml`.

Must wait:

- Production social auth implementation.
- `template.yaml` product route expansion.
- User Preference persistence.
- Saved Plans persistence.
- `GET /auth/session` full aggregation.
- AgentCore authenticated preference loading.
- AgentCore Map/City theme-based lookup.
- DB migrations/schema/repositories.

## Final Decision

The recommended product direction is `/api/v1` for all new product APIs, with `/api/small-cities` preserved as an existing compatibility backend route. Auth must use official server-side provider validation and service-owned identity/session records. The simple-login scaffold must not remain in production. Identity naming is resolved as JWT `sub`, DB `user_id`, and API `userId`. Theme mapping and DB/session store remain blockers and require separate decision tasks before implementation.
