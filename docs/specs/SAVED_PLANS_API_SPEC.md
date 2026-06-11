# Saved Plans API Spec

## User Request Original

5. Saved Plans
- 생성 일정 저장
- 저장 일정 목록 조회
- 좋아요/좋아요 취소
- 일정 상세 조회

## Structured Agent Contract

- Agent Name: Backend Saved Plans Spec Agent
- Core Role: Spec Agent
- Domain Focus: Backend AWS SAM
- Work Focus: saved itineraries and reactions API
- Target repo: `/Users/jeonjonghyeok/Documents/Final/Lovv_BE`
- Deliverable: create one planning-only Spec file for saved generated itineraries, saved itinerary list/detail retrieval, and like/unlike reactions.
- Hard boundary: do not implement code and do not commit, push, pull, merge, or rebase.

## Source Context

- Lovv backend work follows the AWS SAM, Lambda, and API Gateway direction from `docs/projects/lovv-project-context.md`.
- The current MVP API contract defines `GET /me/itineraries` and `POST /me/itineraries` as authenticated user APIs. It also defines `POST /me/feedback` for recommendation feedback, which is separate from saved-plan private reactions.
- The database design treats `itineraries`, `itinerary_items`, and `plan_reactions` as MySQL ledger data for saved schedules and reactions. DynamoDB may store short-lived events or traces, but it must not become the source of truth for saved plans.
- `oh_my_documents/docs/05_agent_spec/itinerary_flow.md` says `PlanDraft` is temporary and should become persistent only when the user explicitly saves it.
- `/Users/jeonjonghyeok/Documents/Final/Lovv_BE/docs/specs/AGENTCORE_ITINERARY_API_SPEC.md` is not present at spec time. This Spec therefore treats the exact generated itinerary response contract as a pending upstream dependency.

## Summary

This Spec defines the Backend AWS SAM contract for the Saved Plans domain. It covers saving a generated itinerary snapshot, listing the authenticated user's saved itineraries, retrieving one saved itinerary detail, liking a saved itinerary, and unliking it.

Saved plans are private user-owned records. The authenticated user can access only their own saved plans. A saved plan stores a snapshot of the generated itinerary payload at save time, not raw chat history, not an unfinished draft, and not a pointer that becomes unusable when a recommendation cache expires.

This Spec adds detail and reaction endpoints around the existing `/me/itineraries` MVP boundary. It does not implement code, migrations, or deployment changes.

## Goals

- Define API endpoints for:
  - save generated itinerary snapshot
  - list saved plans
  - get saved plan detail
  - like saved plan
  - unlike saved plan
- Keep saved plans authenticated and user-owned.
- Preserve the current persistence rule: only confirmed/final saved itineraries become server-side ledger records.
- Define duplicate-save behavior so repeated save attempts do not create accidental duplicate records.
- Define like/unlike idempotency so repeated calls are safe.
- Map API fields to existing `itineraries`, `itinerary_items`, and `plan_reactions` concepts.
- Identify schema and upstream-contract gaps that must be resolved before implementation.
- Provide Task Breakdown and Verification notes for a future Task Agent.

## Non-Goals

- Do not implement code, tests, migrations, SAM template changes, or deployment changes in this Spec task.
- Do not add sharing, public community feeds, collaborative editing, comments, followers, payment, booking, or monetization.
- Do not persist raw chat history, in-progress chat messages, unfinished `PlanDraft` state, or full conversation transcripts.
- Do not add graph database behavior, public like counts for community ranking, social notifications, or recommendation re-ranking.
- Do not replace `/me/feedback`; recommendation-level feedback remains a separate API concern.
- Do not assume the production database engine, live API base URL, DB connection path, deployed authorizer, or deployed SAM stage is ready.

## User Flow

### Save Generated Itinerary

1. The user receives a generated itinerary from AgentCore or a recommendation flow.
2. The user chooses to save the generated itinerary.
3. The client sends `POST /me/itineraries` with the generated itinerary snapshot and optional idempotency key.
4. The backend authenticates the user from the authorizer context.
5. The backend validates that the request contains a saveable itinerary snapshot and does not contain raw chat history.
6. The backend stores the saved plan as user-owned ledger data.
7. The backend returns the saved `itineraryId`.
8. If the same save request is repeated, the backend returns the existing saved plan instead of creating another duplicate.

### List Saved Plans

1. The authenticated user opens the saved plans area.
2. The client calls `GET /me/itineraries`.
3. The backend returns only saved plans owned by the authenticated user, ordered by newest saved first.
4. The list response contains summary fields only, not the full itinerary item body.

### Get Saved Plan Detail

1. The authenticated user opens a saved plan.
2. The client calls `GET /me/itineraries/{itineraryId}`.
3. The backend verifies that the `itineraryId` belongs to the authenticated user.
4. The backend returns the saved snapshot detail, including days and itinerary items.
5. If the plan does not exist or belongs to another user, the backend returns the same not-found response.

### Like Saved Plan

1. The authenticated user taps like on one of their saved plans.
2. The client calls `PUT /me/itineraries/{itineraryId}/reactions/like`.
3. The backend verifies ownership of the saved plan.
4. The backend creates a private `like` reaction if it does not already exist.
5. Repeating the same call leaves the plan liked and returns success.

### Unlike Saved Plan

1. The authenticated user removes the like from one of their saved plans.
2. The client calls `DELETE /me/itineraries/{itineraryId}/reactions/like`.
3. The backend verifies ownership of the saved plan.
4. The backend removes the private `like` reaction if it exists.
5. Repeating the same call remains successful and leaves the plan unliked.

## Requirements

### Functional Requirements

- The API must require user authentication for every saved-plan endpoint.
- The API must derive `userId` only from trusted auth context. It must ignore or reject any client-supplied owner/user id.
- `POST /me/itineraries` must save a generated itinerary snapshot for the authenticated user.
- The saved snapshot must include enough itinerary data to render the saved plan after the source recommendation cache expires.
- The saved snapshot must not include raw chat history, full conversation transcripts, server secrets, provider tokens, or private operational trace data.
- `GET /me/itineraries` must return only the authenticated user's saved plans.
- `GET /me/itineraries/{itineraryId}` must return detail only when the saved plan belongs to the authenticated user.
- `PUT /me/itineraries/{itineraryId}/reactions/like` must mark the authenticated user's own saved plan as liked.
- `DELETE /me/itineraries/{itineraryId}/reactions/like` must remove the authenticated user's like from their own saved plan.
- The API must treat missing and not-owned saved plans the same in external responses to avoid leaking plan existence.
- The API must use the common structured error response shape from the MVP API contract.

### Duplicate Save Requirements

- Duplicate save detection must be scoped to the authenticated user.
- A repeated request with the same `idempotencyKey` must return the original saved plan result.
- A repeated request with the same `sourceRecommendationId` and the same canonical snapshot hash must return the existing saved plan result.
- If the same `sourceRecommendationId` is saved with a materially different snapshot hash, the backend may create a separate saved plan variant unless the future AgentCore contract defines stricter behavior.
- If the same `idempotencyKey` is reused with a different payload, the backend must return `409 Conflict`.
- The backend must compute the canonical snapshot hash server-side. The client may send an idempotency key, but the client must not be trusted to provide the authoritative hash.

### Like/Unlike Idempotency Requirements

- Like is a private reaction/favorite marker for the authenticated user's own saved plan. It is not a public community reaction in this MVP scope.
- Like must be idempotent: liking an already liked plan must return success without creating duplicate `plan_reactions` rows.
- Unlike must be idempotent: unliking an already unliked plan must return success without error.
- The data layer should enforce uniqueness for active `like` reactions by authenticated user, itinerary, and reaction type.
- Reaction writes must verify saved-plan ownership before creating or deleting reaction records.

### Validation Requirements

- `itineraryId`, `sourceRecommendationId`, and `idempotencyKey` values must be validated as UUID-like identifiers when present.
- `title` must be present and must fit the storage/display length chosen by the implementation task.
- `destination.country` must use the same country code style as the recommendation output.
- `itinerary.days` must contain at least one day and at least one item across all days.
- `sortOrder` values within a day must be unique and stable.
- The request must reject raw transcript-like fields such as `messages`, `chatHistory`, `conversation`, or `transcript`.
- Unknown optional fields may be ignored only if they are not persisted and do not affect the canonical snapshot hash. Otherwise they must trigger validation errors.

## API Contract

### Common Contract

- Base path: no production base URL is confirmed by this Spec. Paths below are route paths only.
- Auth: `User` authentication required for every endpoint in this Spec.
- Owner source: trusted Lambda authorizer or equivalent authenticated context.
- Content type: `application/json`.
- Timestamp format: ISO-8601 UTC strings.
- Not found behavior: return `404` for both absent and not-owned `itineraryId`.
- Error shape: follow the MVP contract's `error.code`, `error.message`, `error.details` structure.

### Endpoint Summary

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/me/itineraries` | User | Save generated itinerary snapshot |
| `GET` | `/me/itineraries` | User | List authenticated user's saved plans |
| `GET` | `/me/itineraries/{itineraryId}` | User | Get authenticated user's saved plan detail |
| `PUT` | `/me/itineraries/{itineraryId}/reactions/like` | User | Idempotently like a saved plan |
| `DELETE` | `/me/itineraries/{itineraryId}/reactions/like` | User | Idempotently unlike a saved plan |

### `POST /me/itineraries`

Saves a generated itinerary snapshot as an authenticated user's saved plan.

**Request**

```json
{
  "sourceRecommendationId": "uuid",
  "idempotencyKey": "uuid",
  "title": "경주 1박 2일 전통 산책",
  "summary": "역사와 산책 중심으로 구성한 1박 2일 일정입니다.",
  "destination": {
    "destinationId": "uuid",
    "name": "경주",
    "country": "KR",
    "region": "경상북도"
  },
  "tripType": "2d1n",
  "durationLabel": "1박 2일",
  "themes": ["history_tradition"],
  "festivalChoice": "include_confirmed_only",
  "intensityLabel": "보통",
  "conditionsSnapshot": {
    "travelMonth": 10,
    "activeRequiredThemes": ["history_tradition"],
    "softPreferences": ["quiet"],
    "validationStatus": {
      "festivalConfirmedOnly": true,
      "singleDestination": true,
      "countrySeparated": true
    }
  },
  "requestSummary": "10월에 조용하게 역사 산책을 할 수 있는 경주 일정",
  "itinerary": {
    "days": [
      {
        "day": 1,
        "title": "전통 산책과 야경",
        "summary": "오전에는 대표 유적, 저녁에는 야경 산책을 배치합니다.",
        "items": [
          {
            "itemId": "uuid",
            "contentId": "uuid",
            "sortOrder": 1,
            "timeOfDay": "morning",
            "title": "불국사 산책",
            "body": "전통 산책 흐름을 먼저 잡습니다.",
            "reason": "선택 테마와 소도시 상세 seed가 맞습니다.",
            "moveMinutes": 18,
            "latitude": 35.7901,
            "longitude": 129.3321,
            "sourceBadges": ["official_seed"]
          }
        ]
      }
    ]
  },
  "alternativeItinerary": {
    "trigger": "weather_trend",
    "reason": "우천 가능성에 대비한 실내 중심 대체 일정입니다.",
    "days": []
  }
}
```

`idempotencyKey` is optional but recommended. `sourceRecommendationId` is required until the AgentCore itinerary contract defines a replacement source identifier.

**Response 201**

```json
{
  "itineraryId": "uuid",
  "sourceRecommendationId": "uuid",
  "savedAt": "2026-06-10T09:00:00Z",
  "duplicate": false
}
```

**Duplicate Response 200**

```json
{
  "itineraryId": "uuid",
  "sourceRecommendationId": "uuid",
  "savedAt": "2026-06-10T09:00:00Z",
  "duplicate": true
}
```

**Error Cases**

| Status | Code | Condition |
| --- | --- | --- |
| `400` | `INVALID_ITINERARY_SNAPSHOT` | Snapshot is missing required saveable itinerary data |
| `400` | `RAW_CHAT_HISTORY_NOT_ALLOWED` | Request contains raw chat history or transcript-like fields |
| `401` | `UNAUTHORIZED` | Auth context is missing or invalid |
| `409` | `IDEMPOTENCY_KEY_CONFLICT` | Same idempotency key is reused with a different payload |

### `GET /me/itineraries`

Returns saved-plan summaries for the authenticated user only.

**Query Parameters**

| Name | Required | Default | Notes |
| --- | --- | --- | --- |
| `limit` | No | `20` | Maximum should be capped by implementation, recommended cap `50` |
| `cursor` | No | none | Opaque pagination cursor |

**Response 200**

```json
{
  "items": [
    {
      "itineraryId": "uuid",
      "sourceRecommendationId": "uuid",
      "title": "경주 1박 2일 전통 산책",
      "summary": "역사와 산책 중심으로 구성한 1박 2일 일정입니다.",
      "destination": {
        "destinationId": "uuid",
        "name": "경주",
        "country": "KR",
        "region": "경상북도"
      },
      "tripType": "2d1n",
      "durationLabel": "1박 2일",
      "themes": ["history_tradition"],
      "isLiked": true,
      "savedAt": "2026-06-10T09:00:00Z",
      "updatedAt": "2026-06-10T09:00:00Z"
    }
  ],
  "nextCursor": null
}
```

### `GET /me/itineraries/{itineraryId}`

Returns the full saved snapshot detail for one authenticated user's saved plan.

**Response 200**

```json
{
  "itineraryId": "uuid",
  "sourceRecommendationId": "uuid",
  "title": "경주 1박 2일 전통 산책",
  "summary": "역사와 산책 중심으로 구성한 1박 2일 일정입니다.",
  "destination": {
    "destinationId": "uuid",
    "name": "경주",
    "country": "KR",
    "region": "경상북도"
  },
  "tripType": "2d1n",
  "durationLabel": "1박 2일",
  "themes": ["history_tradition"],
  "festivalChoice": "include_confirmed_only",
  "intensityLabel": "보통",
  "conditionsSnapshot": {
    "travelMonth": 10,
    "activeRequiredThemes": ["history_tradition"],
    "softPreferences": ["quiet"],
    "validationStatus": {
      "festivalConfirmedOnly": true,
      "singleDestination": true,
      "countrySeparated": true
    }
  },
  "requestSummary": "10월에 조용하게 역사 산책을 할 수 있는 경주 일정",
  "itinerary": {
    "days": [
      {
        "day": 1,
        "title": "전통 산책과 야경",
        "summary": "오전에는 대표 유적, 저녁에는 야경 산책을 배치합니다.",
        "items": [
          {
            "itemId": "uuid",
            "contentId": "uuid",
            "sortOrder": 1,
            "timeOfDay": "morning",
            "title": "불국사 산책",
            "body": "전통 산책 흐름을 먼저 잡습니다.",
            "reason": "선택 테마와 소도시 상세 seed가 맞습니다.",
            "moveMinutes": 18,
            "latitude": 35.7901,
            "longitude": 129.3321,
            "sourceBadges": ["official_seed"]
          }
        ]
      }
    ]
  },
  "alternativeItinerary": {
    "trigger": "weather_trend",
    "reason": "우천 가능성에 대비한 실내 중심 대체 일정입니다.",
    "days": []
  },
  "isLiked": true,
  "savedAt": "2026-06-10T09:00:00Z",
  "updatedAt": "2026-06-10T09:00:00Z"
}
```

**Error Cases**

| Status | Code | Condition |
| --- | --- | --- |
| `401` | `UNAUTHORIZED` | Auth context is missing or invalid |
| `404` | `ITINERARY_NOT_FOUND` | Saved plan does not exist or is not owned by the authenticated user |

### `PUT /me/itineraries/{itineraryId}/reactions/like`

Idempotently likes the authenticated user's own saved plan.

**Response 200**

```json
{
  "itineraryId": "uuid",
  "reactionType": "like",
  "isLiked": true,
  "changed": true,
  "updatedAt": "2026-06-10T09:00:00Z"
}
```

If the plan was already liked, `changed` is `false`.

### `DELETE /me/itineraries/{itineraryId}/reactions/like`

Idempotently removes the authenticated user's like from their own saved plan.

**Response 204**

No response body. Return `204` whether a like row existed or was already absent, as long as the saved plan exists and belongs to the authenticated user.

## Data Model Mapping

### Ownership

| API Concept | Storage Mapping | Notes |
| --- | --- | --- |
| Authenticated user | `users.id` | Derived from authorizer context, never from request body |
| Saved plan owner | `itineraries.user_id` | Every saved-plan query must filter by this value |
| Saved plan id | `itineraries.id` | Public API field `itineraryId` |

### Saved Itinerary Snapshot

| API Field | Current DB Mapping Candidate | Notes |
| --- | --- | --- |
| `itineraryId` | `itineraries.id` | Generated on save |
| `sourceRecommendationId` | pending dedicated column or `preference_snapshot.sourceRecommendationId` | Current DB design does not show a dedicated column |
| `title` | `itineraries.title` | Required |
| `summary` | `itineraries.summary` | Nullable |
| `durationLabel` | `itineraries.duration_label` | Required by current DB design |
| `festivalChoice` | `itineraries.festival_choice` | Nullable |
| `intensityLabel` | `itineraries.intensity_label` | Nullable |
| `conditionsSnapshot`, `themes`, validation flags | `itineraries.preference_snapshot` | Must not include raw chat history |
| `requestSummary` | `itineraries.request_summary` | Summary only, not transcript |
| `savedAt` | `itineraries.saved_at` | Newest-first list ordering |
| itinerary item order | `itinerary_items.sort_order` | Existing unique rule covers itinerary-level order only |
| itinerary item title/place | `itinerary_items.place_name` plus pending item title mapping | Current DB design does not show separate `title` and `place_name` fields |
| `timeOfDay` | `itinerary_items.time_slot` | Naming differs from current API example |
| `moveMinutes` or move text | `itinerary_items.move_hint` | Implementation must choose text or numeric persistence |
| `reason` | `itinerary_items.recommendation_reason` | Save generated reason summary |

### Reaction Mapping

| API Field | Storage Mapping | Notes |
| --- | --- | --- |
| `reactionType = like` | `plan_reactions.reaction_type` | Only `like` is in this Spec scope |
| Reaction owner | `plan_reactions.user_id` | Must match authenticated user |
| Reaction target | `plan_reactions.itinerary_id` | Must belong to authenticated user before write |
| Reaction creation | `plan_reactions.created_at` | Used for audit/order if needed |

The implementation task should add or confirm a uniqueness rule equivalent to `(user_id, itinerary_id, reaction_type)` for active reactions. The current database design lists indexes but not this unique constraint.

### Known Mapping Gaps

- The current DB design lists `itineraries`, `itinerary_items`, and `plan_reactions`, while `itinerary_flow.md` also mentions `itinerary_days` and `saved_itineraries`. A Task Agent must reconcile this before implementation.
- The current DB design does not finalize storage for `sourceRecommendationId`, `destination`, `tripType`, `themes`, day grouping, full item body, latitude/longitude, or `alternativeItinerary`.
- The missing `AGENTCORE_ITINERARY_API_SPEC.md` means the exact generated itinerary input to `POST /me/itineraries` is not yet authoritative.
- Until the DB schema is finalized, this Spec defines API behavior and mapping intent, not executable migration details.

## Auth Dependency

- Every endpoint in this Spec depends on an authenticated `User` context.
- For the current Lovv_BE direction, authentication should come from the existing or approved API Gateway/Lambda authorizer boundary, such as the simple-login authorizer Spec already present in `Lovv_BE/docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`.
- The MVP API contract currently places `/me/itineraries` under `Auth-Function` ownership. A separate `SavedPlansFunction` may be introduced only if a later Task Agent explicitly assigns non-overlapping Lambda ownership and updates the SAM route plan.
- The authorizer must provide a stable user identifier that maps to `users.id` or a demo equivalent in local MVP mode.
- The save/list/detail/reaction handlers must not trust any client-provided `userId`, `ownerId`, `createdBy`, or equivalent field.
- If auth is missing or invalid, return `401`.
- If auth is valid but the saved plan is absent or owned by another user, return `404`, not `403`, to avoid existence disclosure.

## Acceptance Criteria

- WHEN an authenticated user saves a valid generated itinerary snapshot, THE system SHALL create a user-owned saved plan and return `201` with `itineraryId`.
- WHEN the same authenticated user repeats the same save request with the same idempotency key or same source recommendation and snapshot hash, THE system SHALL return the existing saved plan result without creating a duplicate.
- IF an idempotency key is reused with a different payload, THE system SHALL return `409 Conflict`.
- WHEN an authenticated user lists saved plans, THE system SHALL return only plans where `itineraries.user_id` matches the authenticated user.
- WHEN an authenticated user requests detail for their own saved plan, THE system SHALL return the stored snapshot detail.
- IF a user requests a saved plan that does not exist or belongs to another user, THE system SHALL return `404`.
- WHEN an authenticated user likes their own saved plan, THE system SHALL create one active `like` reaction or leave the existing one unchanged.
- WHEN an authenticated user likes an already liked saved plan, THE system SHALL return success and SHALL NOT create duplicate reaction rows.
- WHEN an authenticated user unlikes their own saved plan, THE system SHALL remove the active `like` reaction if present.
- WHEN an authenticated user unlikes an already unliked saved plan, THE system SHALL return success with no state change.
- IF a save request contains raw chat history, THE system SHALL reject it and SHALL NOT persist the transcript.
- The Spec SHALL NOT add sharing, collaborative editing, payment, or public community behavior.

## Risks

- `AGENTCORE_ITINERARY_API_SPEC.md` is missing, so the generated itinerary snapshot shape may need adjustment after that upstream Spec exists.
- The database documents are not fully consistent about `itinerary_days` and `saved_itineraries`; implementation must reconcile the chosen physical schema before migrations or handlers.
- Current `plan_reactions` indexes do not explicitly define the uniqueness needed for idempotent likes.
- Duplicate-save detection requires stable canonicalization of the snapshot payload; inconsistent JSON ordering or optional fields can break idempotency if not specified in implementation.
- Returning full saved-plan detail from normalized tables may lose fields unless the implementation defines a full snapshot JSON column or a complete day/item schema.
- The current backend auth and DB readiness are not verified by this Spec. Implementation must confirm SAM routes, authorizer context, DB connection path, environment variables, and local/deployed test strategy.
- Treating plan likes as private markers avoids community-scope creep, but product language must stay clear so users do not expect public social likes.

## Task Breakdown

### Task 1: Confirm Upstream Contracts

- Purpose: Confirm the generated itinerary source payload and auth context before implementation.
- Scope: Read or create the AgentCore itinerary API Spec, confirm authorizer user context, and confirm whether `/me/itineraries` remains in `Auth-Function` or moves to a dedicated saved-plans Lambda.
- Dependencies: This Spec.
- Context Budget: Must read this Spec, Lovv project context, MVP API contract, and the future AgentCore itinerary Spec if it exists. Do not read unrelated frontend files.
- Acceptance Criteria: Source recommendation identifier, generated itinerary snapshot shape, auth user id claim, and Lambda ownership are explicit.
- Verification: Document review by Backend Task Agent before implementation starts.

### Task 2: Finalize Saved-Plan Data Model

- Purpose: Convert the API mapping into an implementation-ready schema plan.
- Scope: Decide how to store day grouping, item fields, `sourceRecommendationId`, destination, themes, snapshot hash, idempotency key, and active like uniqueness.
- Dependencies: Task 1.
- Context Budget: Must read this Spec and the database design sections for `itineraries`, `itinerary_items`, and `plan_reactions`.
- Acceptance Criteria: The implementation task has a clear table/column/index plan and no unresolved mapping gaps.
- Verification: Schema/migration plan review; no code until approved.

### Task 3: Implement Save/List/Detail APIs

- Purpose: Add the saved-plan read/write behavior after contracts and schema are approved.
- Scope: Implement `POST /me/itineraries`, `GET /me/itineraries`, and `GET /me/itineraries/{itineraryId}` in the approved Lambda ownership boundary.
- Dependencies: Tasks 1 and 2.
- Context Budget: Must read this Spec's API Contract, Data Model Mapping, Auth Dependency, and Acceptance Criteria sections.
- Acceptance Criteria: Save, duplicate save, list, detail, validation, not-owned `404`, and raw-chat rejection behavior are covered.
- Verification: Unit tests, local Lambda event tests, `sam validate`, and repository test command.

### Task 4: Implement Like/Unlike Reactions

- Purpose: Add private saved-plan reaction behavior.
- Scope: Implement `PUT /me/itineraries/{itineraryId}/reactions/like` and `DELETE /me/itineraries/{itineraryId}/reactions/like`.
- Dependencies: Tasks 1 and 2.
- Context Budget: Must read this Spec's Like/Unlike Idempotency Requirements and Reaction Mapping.
- Acceptance Criteria: Like and unlike are idempotent, ownership-checked, and duplicate reaction rows are prevented.
- Verification: Unit tests for like, repeated like, unlike, repeated unlike, not-owned plan, and missing plan.

### Task 5: Add API Gateway, Events, and Documentation Updates

- Purpose: Wire approved routes into AWS SAM and make local verification repeatable.
- Scope: Add SAM route definitions, local event fixtures, dummy env documentation, and any required `.env.example` dummy keys if approved.
- Dependencies: Tasks 3 and 4.
- Context Budget: Must read this Spec, existing SAM template, and existing auth/simple-login Spec.
- Acceptance Criteria: Routes are protected by the approved authorizer, CORS supports `Authorization`, and no real secrets are committed.
- Verification: `sam validate`, local handler invocation where available, and full backend test suite.

## Verification

### Spec Verification Performed

- This task is planning-only. No application tests, SAM validation, or handler invocation are required because no source, template, or test code is changed.
- File-level verification should confirm that only `/Users/jeonjonghyeok/Documents/Final/Lovv_BE/docs/specs/SAVED_PLANS_API_SPEC.md` changed for this task.
- `.gitignore` should continue to ignore `.env` and `.env.*` while allowing `.env.example`.

### Future Implementation Verification

- Run repository unit tests for saved-plan handlers, repositories, mappers, and auth integration.
- Run idempotency tests for duplicate save, repeated like, and repeated unlike.
- Run ownership tests proving users cannot list or retrieve another user's plans.
- Run validation tests proving raw chat history fields are rejected.
- Run `sam validate` after route/template changes.
- Run local API Gateway/Lambda events for success and error paths if the project has event fixtures.
- Confirm no real secrets or environment files are tracked.
