# User Preference API Spec

## User Request Original

2. User Preference
- 온보딩 취향 저장
- 마이페이지 취향 수정
- 로그인 후 취향 로드

## Structured Agent Contract

- Agent Name: Backend User Preference Spec Agent
- Core Role: Spec Agent
- Domain Focus: Backend AWS SAM
- Work Focus: user preferences API
- Workspace: `/Users/jeonjonghyeok/Documents/Final/Lovv_BE`
- Deliverable: create exactly one planning-only Spec file at `docs/specs/USER_PREFERENCE_API_SPEC.md`.
- Hard boundary: do not implement code, do not commit, do not push, do not pull, do not merge, and do not rebase.

## Summary

This Spec defines the Backend AWS SAM contract for Lovv user preferences. It covers saving onboarding preferences, reading the current authenticated user's preferences, updating preferences from My Page, and returning preferences during the post-login/session loading flow.

The current shared project API planning document already names `GET /me/preferences`, `PUT /me/preferences`, and `GET /auth/session` as user preference or session-related routes. In this Spec, paths are logical paths relative to the API base. The current `Lovv_BE` SAM implementation uses `/api/...` for existing auth routes, so implementation should mount these logical routes under the active API prefix, for example `/api/me/preferences` and `/api/auth/session`, unless the approved route-prefix contract changes before implementation.

`AUTH_SOCIAL_LOGIN_API_SPEC.md` does not exist in `Lovv_BE` at the time this Spec was written. Auth output is therefore a dependency: implementation may rely only on a stable authenticated `userId` from the existing MVP authorizer/token context, and must not assume production social-login, refresh-token, or deployed session behavior until a later approved Auth Spec defines it.

## Goals

- Define the API/data contract for saving onboarding preferences.
- Define the API/data contract for reading the current authenticated user's preferences.
- Define the API/data contract for updating preferences from My Page.
- Define how preferences are included in the post-login/session load response.
- Preserve mandatory onboarding behavior: a user must complete onboarding before personalized planning.
- Ensure My Page preference edits affect future plan generation and future preference snapshots.
- Define persistence ownership and the `user_id` relationship without assuming a finalized production database engine.
- Keep preference fields conservative and structured, with no free-form disliked constraints in MVP.

## Non-Goals

- Do not implement Lambda handlers, repositories, tests, migrations, or SAM template changes in this Spec task.
- Do not invent frontend UI, page layout, labels, or interaction details.
- Do not define production social login, provider token verification, refresh-token rotation, account recovery, or server-side session storage.
- Do not persist in-progress chat messages or unfinished plan drafts.
- Do not change the small-city map/list/detail data contract.
- Do not introduce graph DB behavior, WebSocket behavior, EC2, or non-MVP infrastructure.
- Do not store free-form disliked constraints, sensitive notes, or natural-language preference text as durable user preference data.
- Do not treat existing endpoint paths as live deployed API addresses until SAM/API Gateway deployment, base URL, stage, auth configuration, DB readiness, and environment configuration are verified.

## User Flow

### Onboarding Preference Save

1. Authenticated user completes required onboarding preference inputs.
2. Client submits a full preference payload to `PUT /me/preferences`.
3. API validates the authenticated `userId`, required fields, option keys, and value bounds.
4. API upserts the user's current preference profile.
5. API returns the saved preference profile with `onboardingCompleted: true`.
6. Personalized planning is allowed only after the saved profile is complete.

### My Page Preference Edit

1. Authenticated user opens My Page.
2. Client loads current preferences with `GET /me/preferences`, or from `GET /auth/session` when already available.
3. User edits supported preference fields.
4. Client submits the full updated preference payload to `PUT /me/preferences`.
5. API replaces the current preference profile for that `userId`.
6. Future plan generation uses the updated current preference profile.
7. Previously saved itineraries keep their own `preference_snapshot` and are not rewritten by this edit.

### Login/Session Preference Load

1. User logs in or restores a valid authenticated session.
2. Client calls `GET /auth/session` after auth succeeds, or the auth layer returns an equivalent session payload when a later Auth Spec approves it.
3. Session response includes user identity, `preferences`, and `onboardingCompleted`.
4. If `onboardingCompleted` is false, the client must route the user through onboarding before personalized planning.
5. If `onboardingCompleted` is true, the client may use the returned preferences to initialize personalized planning.

## Requirements

### Functional Requirements

- `GET /me/preferences` must require authentication.
- `GET /me/preferences` must read preferences only for the authenticated `userId`.
- `GET /me/preferences` must return `onboardingCompleted: false` and `preferences: null` when the user has no complete preference profile.
- `PUT /me/preferences` must require authentication.
- `PUT /me/preferences` must upsert the current preference profile for the authenticated `userId`.
- `PUT /me/preferences` must support both onboarding save and My Page replacement update with the same canonical request shape.
- `PUT /me/preferences` must reject missing required onboarding fields when the request marks the profile complete.
- My Page updates must affect future recommendation and itinerary-generation inputs.
- My Page updates must not rewrite preference snapshots already attached to saved itineraries.
- `GET /auth/session` must include the user's current preference state when the route is implemented.
- Personalized planning routes must reject or block user-specific planning when `onboardingCompleted` is false.
- All responses must be JSON with stable machine-readable error codes.

### Preference Field Requirements

MVP preference fields are controlled option keys, not frontend display text. The backend validates structure and stores stable keys; frontend copy and UI controls are out of scope.

Required for a complete onboarding profile:

- `countryTrack`: one of `KR`, `JP`, or `BOTH`.
- `mappedThemes`: non-empty array of approved theme keys.

Optional, when the onboarding/My Page source already supplies approved option keys:

- `preferredRegions`: array of region keys or labels matching approved country/region options.
- `selectedCityStyle`: onboarding style key already present in the shared API planning document.
- `pace`: one of `relaxed`, `balanced`, or `active`.
- `tripDays`: integer day count for the user's typical trip length.
- `companionStyle`: approved companion/travel-party option key.
- `travelStyles`: array of approved travel-style option keys.

Excluded from MVP current-preference persistence:

- Free-form disliked constraints.
- Sensitive notes.
- Natural-language chat text.
- Private operational notes.

If disliked constraints become a product requirement later, a new Spec must define allowed enum keys, validation, retention, and privacy boundaries before implementation.

### Auth And Authorization Requirements

- Preference routes must use the existing protected-route authorizer boundary.
- The authenticated user identifier must come from authorizer context or verified token claims, not from request body.
- Request bodies must not accept `userId` as a writable field.
- Users must never read or mutate another user's preferences.
- Missing, expired, malformed, or invalid bearer tokens must be rejected before preference business logic runs.
- The missing `AUTH_SOCIAL_LOGIN_API_SPEC.md` means social-login provider payloads, provider account linkage details, and production session shape are pending.
- The current MVP auth implementation returns a minimal user from token claims. Preference implementation must either use that `sub` value as `userId` for MVP or wait for an approved Auth Spec that maps social accounts to `users.id`.

### Persistence Requirements

- Current preferences are user-owned state and must be related to exactly one `users.id`.
- Logical persistence ownership belongs to the User Preference domain.
- Preferred logical model is one current preference profile per user:
  - `user_preferences.id`
  - `user_preferences.user_id` unique FK to `users.id`
  - `user_preferences.country_track`
  - `user_preferences.mapped_themes`
  - `user_preferences.preferred_regions`
  - `user_preferences.selected_city_style`
  - `user_preferences.pace`
  - `user_preferences.trip_days`
  - `user_preferences.companion_style`
  - `user_preferences.travel_styles`
  - `user_preferences.onboarding_completed`
  - `user_preferences.created_at`
  - `user_preferences.updated_at`
- Because the current shared database design does not yet define a dedicated `user_preferences` table, Task Agent must create a DB/schema confirmation task before implementation.
- MySQL is the preferred logical owner for user-modifiable final state based on current database planning, but the physical DB engine, migration path, and connection path must be confirmed before code implementation.
- DynamoDB event or API logs may store hashed identifiers and summaries only; they must not become the preference source of truth.
- Saved itineraries may keep `preference_snapshot` as an immutable snapshot at save time. This is separate from current user preferences.

### Planning And Generation Requirements

- Recommendation or itinerary-generation code must load the current preference profile for authenticated personalized planning.
- If current preferences are missing or incomplete, personalized planning must not proceed as if preferences exist.
- My Page preference edits must be visible to future planning requests after the update succeeds.
- Existing saved itinerary snapshots remain historical records and must not be used as the current preference profile unless a future Spec explicitly defines fallback behavior.

## API Contract

### Shared Types

```json
{
  "preferenceId": "uuid",
  "userId": "uuid-or-mvp-user-id",
  "countryTrack": "KR",
  "preferredRegions": ["gyeongbuk"],
  "selectedCityStyle": "GYEONGJU",
  "mappedThemes": ["history_tradition"],
  "pace": "balanced",
  "tripDays": 3,
  "companionStyle": "solo",
  "travelStyles": ["slow_walk", "local_food"],
  "onboardingCompleted": true,
  "createdAt": "2026-06-10T09:00:00Z",
  "updatedAt": "2026-06-10T09:00:00Z"
}
```

Implementation may omit optional fields when not supplied. It must not return server-only storage details, auth tokens, provider tokens, or raw internal logs in preference responses.

### `GET /me/preferences`

Auth: User.

Purpose: Read the current authenticated user's preference profile.

Response 200 when complete:

```json
{
  "preferences": {
    "preferenceId": "uuid",
    "userId": "uuid-or-mvp-user-id",
    "countryTrack": "KR",
    "preferredRegions": ["gyeongbuk"],
    "selectedCityStyle": "GYEONGJU",
    "mappedThemes": ["history_tradition"],
    "pace": "balanced",
    "tripDays": 3,
    "companionStyle": "solo",
    "travelStyles": ["slow_walk", "local_food"],
    "onboardingCompleted": true,
    "createdAt": "2026-06-10T09:00:00Z",
    "updatedAt": "2026-06-10T09:00:00Z"
  }
}
```

Response 200 when not complete:

```json
{
  "preferences": null,
  "onboardingCompleted": false
}
```

### `PUT /me/preferences`

Auth: User.

Purpose: Save onboarding preferences or replace current My Page preferences.

Request:

```json
{
  "countryTrack": "KR",
  "preferredRegions": ["gyeongbuk"],
  "selectedCityStyle": "GYEONGJU",
  "mappedThemes": ["history_tradition"],
  "pace": "balanced",
  "tripDays": 3,
  "companionStyle": "solo",
  "travelStyles": ["slow_walk", "local_food"]
}
```

Response 200:

```json
{
  "preferences": {
    "preferenceId": "uuid",
    "userId": "uuid-or-mvp-user-id",
    "countryTrack": "KR",
    "preferredRegions": ["gyeongbuk"],
    "selectedCityStyle": "GYEONGJU",
    "mappedThemes": ["history_tradition"],
    "pace": "balanced",
    "tripDays": 3,
    "companionStyle": "solo",
    "travelStyles": ["slow_walk", "local_food"],
    "onboardingCompleted": true,
    "createdAt": "2026-06-10T09:00:00Z",
    "updatedAt": "2026-06-10T09:00:00Z"
  }
}
```

Validation rules:

- `countryTrack` is required and must be `KR`, `JP`, or `BOTH`.
- `mappedThemes` is required, must be an array, and must contain at least one approved theme key.
- `preferredRegions`, when present, must be an array of approved region keys or labels.
- `pace`, when present, must be `relaxed`, `balanced`, or `active`.
- `tripDays`, when present, must be a positive integer.
- `companionStyle`, when present, must be an approved option key.
- `travelStyles`, when present, must be an array of approved option keys.
- Request must not contain writable `userId`, `preferenceId`, `createdAt`, or `updatedAt`.
- Request must not contain raw free-text disliked constraints or chat text.

### `GET /auth/session`

Auth: User.

Purpose: Return lightweight post-login/session state including preferences.

Response 200:

```json
{
  "user": {
    "userId": "uuid-or-mvp-user-id",
    "displayName": "Lovv Demo User",
    "roles": ["R-USER"]
  },
  "preferences": {
    "preferenceId": "uuid",
    "countryTrack": "KR",
    "mappedThemes": ["history_tradition"],
    "preferredRegions": ["gyeongbuk"],
    "pace": "balanced",
    "tripDays": 3,
    "companionStyle": "solo",
    "travelStyles": ["slow_walk", "local_food"],
    "onboardingCompleted": true,
    "updatedAt": "2026-06-10T09:00:00Z"
  },
  "onboardingCompleted": true
}
```

If preferences are missing:

```json
{
  "user": {
    "userId": "uuid-or-mvp-user-id",
    "displayName": "Lovv Demo User",
    "roles": ["R-USER"]
  },
  "preferences": null,
  "onboardingCompleted": false
}
```

Route ownership note: `GET /auth/session` may be owned by `AuthFunction` as a session aggregator or by a future user-session Lambda. If it reads user preferences, it must depend on the same User Preference read service/repository contract as `GET /me/preferences` and must not duplicate preference mapping rules.

### Error Responses

All endpoints use JSON errors:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid preference payload"
  }
}
```

Required error cases:

- 400 `INVALID_JSON`: request body is not valid JSON.
- 400 `INVALID_REQUEST`: request body is not an object.
- 400 `VALIDATION_ERROR`: fields are missing, out of bounds, or not approved option keys.
- 401 `UNAUTHORIZED`: token is missing or malformed.
- 401 `TOKEN_EXPIRED`: token is expired.
- 403 `ONBOARDING_REQUIRED`: personalized planning was requested before onboarding completion.
- 404 `NOT_FOUND`: route is unknown.
- 500 `PREFERENCE_STORAGE_NOT_CONFIGURED`: DB/storage configuration is missing.
- 500 `INTERNAL_ERROR`: unexpected server error without leaking secrets or internals.

## Data Model

### Logical Entity: `UserPreference`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `preferenceId` | string UUID | yes | Server-generated preference record id. |
| `userId` | string | yes | Authenticated user id; relates to `users.id` when production user DB is confirmed. |
| `countryTrack` | enum | yes | `KR`, `JP`, or `BOTH`; aligns with city country keys. |
| `preferredRegions` | string array | no | Approved country/region option keys or labels. |
| `selectedCityStyle` | string | no | Existing onboarding style key from shared API planning. |
| `mappedThemes` | string array | yes | Approved theme keys; must not be map marker labels. |
| `pace` | enum | no | `relaxed`, `balanced`, or `active`; maps to planning intensity, not saved itinerary snapshots. |
| `tripDays` | integer | no | Typical trip length preference. |
| `companionStyle` | string | no | Approved companion/travel-party option key. |
| `travelStyles` | string array | no | Approved travel-style option keys. |
| `onboardingCompleted` | boolean | yes | Computed from required fields for current profile. |
| `createdAt` | ISO datetime | yes | Server timestamp. |
| `updatedAt` | ISO datetime | yes | Server timestamp. |

### Storage Relationship

- `users.id` has zero or one current `user_preferences` record.
- `user_preferences.user_id` must be unique.
- `user_preferences.user_id` must reference `users.id` once the production user table is available.
- In MVP demo-auth mode, `userId` may be the stable token `sub` claim until the Auth/User DB mapping is approved.
- `itineraries.preference_snapshot` stores the preference/request state at itinerary save time and is not the source of truth for current preferences.

### Option Source

- `mappedThemes` must align with approved onboarding/theme option keys.
- `countryTrack` must align with city country keys from the city data contract.
- `preferredRegions` must not create duplicate city records or map marker labels.
- Future backend data may use preferences for ranking or filtering, but must not pass personalization metadata into the map marker layer unless a future Spec approves it.

## Auth Dependency

`AUTH_SOCIAL_LOGIN_API_SPEC.md` is missing, so production social-login behavior is pending.

Current known auth context in `Lovv_BE`:

- Existing MVP auth route shape uses `/api/auth/login`, `/api/auth/me`, and `/api/auth/logout`.
- Existing token claims include a stable `sub` and `display_name`.
- Existing protected-route work uses a custom Lambda authorizer boundary.

Implementation dependencies:

- Confirm whether preference routes use the current MVP authorizer or a later social-login authorizer.
- Confirm the canonical user id claim name passed to business Lambdas.
- Confirm whether `GET /auth/session` is added to AuthFunction or a separate user-session/preference function.
- Confirm DB readiness before writing persistence code.
- Confirm route prefix: logical `/me/preferences` and `/auth/session` must be mounted under the approved API base for `Lovv_BE`.

## Acceptance Criteria

- The Spec defines onboarding preference save, My Page preference update, current preference read, and login/session preference load.
- Preference routes require authenticated user context.
- Request body cannot override `userId`.
- The current preference model is related to `users.id` through `user_id`.
- The Spec preserves mandatory onboarding before personalized planning.
- The Spec states that My Page edits affect future plan generation.
- The Spec states that saved itinerary `preference_snapshot` records are not rewritten by later My Page edits.
- Preference fields stay conservative and structured.
- Free-form disliked constraints are excluded from MVP persistence.
- The missing social-login Auth Spec is documented as a blocker/dependency.
- The Spec does not invent frontend UI behavior.
- The Spec does not implement code or require git operations.

## Risks

- The production database engine, schema, migration path, and connection path are not finalized.
- The shared database design does not yet contain a dedicated `user_preferences` table.
- The current `Lovv_BE` auth implementation is MVP demo auth, not production social login.
- The route prefix differs across planning documents and current backend code; Task Agent must pin down the effective SAM route paths before implementation.
- If option-key catalogs are not centralized, frontend and backend validation may drift.
- If planning code uses saved itinerary snapshots as current preferences, user edits from My Page may not affect future generation correctly.
- If session aggregation duplicates preference mapping logic, `/auth/session` and `/me/preferences` responses may diverge.

## Task Breakdown

### Task: Preference API contract confirmation

- Purpose: `/me/preferences`와 `/auth/session`의 최종 route prefix, 요청/응답 shape, 오류 code, authorizer 적용 범위를 구현 전에 확정한다.
- Scope: Spec/API contract confirmation only. No Lambda code, no SAM changes, no DB schema changes.
- Dependencies: This Spec, current auth route contract, project route-prefix decision.
- Context Budget: Must read this Spec, `docs/projects/lovv-project-context.md`, existing auth Spec/task files, and current `template.yaml` route paths. Do not read unrelated frontend files.
- Acceptance Criteria: Logical paths and current `Lovv_BE` SAM paths are mapped without contradiction, and auth/session dependency is explicit.
- Verification: Manual contract review against this Spec and existing auth route files.

### Task: Preference persistence design

- Purpose: 현재 사용자 취향 원장의 저장 위치와 `users.id` 관계를 확정한다.
- Scope: DB/schema design and migration plan only. No runtime Lambda implementation.
- Dependencies: Preference API contract confirmation and DB engine/readiness confirmation.
- Context Budget: Must read this Spec and shared database design sections for `users`, `social_accounts`, `itineraries.preference_snapshot`, and user-state ownership. Do not assume a DB engine beyond approved docs.
- Acceptance Criteria: `user_preferences` or an approved equivalent model has owner, columns, unique `user_id` relation, timestamps, and migration/rollback approach.
- Verification: DB design review; confirm no free-form sensitive text is persisted.

### Task: Preference Lambda implementation

- Purpose: 인증된 사용자의 취향 조회와 저장/update Lambda 로직을 구현한다.
- Scope: Preference handler/service/repository code and focused tests only.
- Dependencies: Preference API contract confirmation, preference persistence design, auth user-id contract.
- Context Budget: Must read this Spec sections `API Contract`, `Data Model`, `Auth Dependency`, and `Acceptance Criteria`. Target files should be limited to new or approved preference-domain files and shared utilities only when needed. Out of Scope: small-city logic, frontend code, social-login implementation.
- Acceptance Criteria: `GET /me/preferences` and `PUT /me/preferences` enforce auth, validate payloads, isolate by authenticated `userId`, and return the approved JSON shape.
- Verification: Unit tests for complete profile, missing profile, validation errors, auth isolation, and storage-not-configured behavior.

### Task: Session preference loading integration

- Purpose: 로그인 후 세션 조회 응답에 현재 취향과 onboarding 상태를 포함한다.
- Scope: `GET /auth/session` route ownership, aggregation behavior, and tests.
- Dependencies: Preference read service, auth user context, route-prefix confirmation.
- Context Budget: Must read this Spec sections `Login/Session Preference Load`, `GET /auth/session`, and `Auth Dependency`. Do not change social-login behavior unless a later Auth Spec approves it.
- Acceptance Criteria: Session response includes `preferences` and `onboardingCompleted`, handles missing preferences, and reuses the preference read/mapping contract.
- Verification: Unit or handler tests for session with complete preferences and session without preferences.

### Task: Personalized planning gate integration

- Purpose: 개인화 계획 생성 전에 onboarding 완료 여부를 backend boundary에서 검증한다.
- Scope: Planning/recommendation entrypoint integration only after that API exists or is approved.
- Dependencies: Preference read service and approved planning/recommendation API Spec.
- Context Budget: Must read this Spec and the approved planning API Spec. Do not implement chat history persistence or draft persistence.
- Acceptance Criteria: Personalized planning rejects incomplete onboarding with `ONBOARDING_REQUIRED` and uses updated current preferences for future generation.
- Verification: Focused tests or contract checks for missing/incomplete preferences and updated preference usage.

## Verification

For this Spec-only task:

- Confirm exactly one file was created: `docs/specs/USER_PREFERENCE_API_SPEC.md`.
- Confirm no source code, tests, SAM template, events, README, generated artifacts, or git state were intentionally modified.
- Confirm required sections are present: Summary, Goals, Non-Goals, User Flow, Requirements, API Contract, Data Model, Auth dependency, Acceptance Criteria, Risks, Task Breakdown, Verification.
- Confirm `AUTH_SOCIAL_LOGIN_API_SPEC.md` absence is documented as a dependency.

For future implementation tasks:

- Run focused unit tests for preference validation, auth isolation, read missing profile, read complete profile, upsert complete profile, and session aggregation.
- Run SAM/template validation after route and Lambda resources are added.
- Run security review for auth context handling, `userId` isolation, secret handling, and environment variable behavior.
- Run DB/migration review before adding a current-preference table or equivalent persistence model.
