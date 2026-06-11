# AgentCore Itinerary API Spec

## User Request Original

4. AgentCore
- 사용자 조건 입력
- 도시/취향 컨텍스트 전달
- AI 일정 생성 응답

## Structured Agent Contract

- Agent Name: Backend AgentCore Spec Agent
- Core Role: Spec Agent
- Domain Focus: Backend AWS SAM / AgentCore
- Work Focus: AI itinerary generation API
- Target repo: `/Users/jeonjonghyeok/Documents/Final/Lovv_BE`
- Deliverable: create one planning-only Spec file for user condition input, city/preference context handoff, and AI itinerary generation response.
- Hard boundary: do not implement code, do not commit, push, pull, merge, or rebase.

## Summary

This Spec defines the Backend AWS SAM / AgentCore API contract for generating an AI itinerary from user travel conditions, city context, and authenticated preference context.

The existing MVP API contract already assigns AgentCore itinerary generation to `POST /recommendations` under the `/api/v1` base URL. This Spec therefore keeps the canonical endpoint as:

```text
POST /api/v1/recommendations
```

This is preferred over creating a new `/api/agent/itineraries` path because the current confirmed MVP contract defines `AgentCore-Function` ownership for `/recommendations`, `/recommendations/{recommendationId}`, and `/agent/answer`.

The generated response must be usable by the Saved Plans API later, specifically `POST /api/v1/me/itineraries`, without requiring the server to persist raw in-progress chat messages or unfinished drafts. Only final user-saved plan snapshots persist as account data by default.

## Goals

- Define the AI itinerary generation endpoint for AgentCore.
- Define the user condition input contract for city, country, theme, search text, travel dates, duration, companion, pace, and constraints.
- Define how authenticated user preferences are loaded, sanitized, and handed to AgentCore.
- Define how city and content context are handed to AgentCore without exposing raw internal data.
- Define the generated itinerary response schema.
- Keep the response compatible with the existing Saved Plans API request shape.
- Preserve the current persistence rule: do not persist raw in-progress chat messages or unfinished plan drafts by default.
- Define the Lambda and AgentCore boundary for AWS SAM implementation planning.
- Align with the present user preference and map/city API specs where they define current `Lovv_BE` contracts.
- Provide implementation-ready Task Agent notes without writing code.

## Non-Goals

- Do not implement code in this Spec task.
- Do not create or change `template.yaml`, Lambda handlers, source files, tests, events, README files, or environment files.
- Do not create a new production endpoint that conflicts with the confirmed MVP `/recommendations` contract.
- Do not persist raw chat messages, full prompts, raw RAG chunks, raw web search pages, or unfinished PlanDraft state.
- Do not implement graph database behavior.
- Do not assume a finalized database engine, schema, migration path, or live DB connection.
- Do not pin real model provider credentials, API keys, secret names with real values, or production AgentCore deployment details.
- Do not choose a final model family beyond the existing planning direction that model calls are abstracted behind Bedrock Converse API or an equivalent model adapter.
- Do not implement WebSocket behavior. REST is sufficient for this Spec unless a future approved Spec adds streaming or long-running job behavior.
- Do not implement saved-plan mutation, drag-and-drop editing, or itinerary revision APIs.

## User Flow

1. The user enters travel conditions from chat, map marker selection, home recommendation entry, or an itinerary form.
2. The client sends `POST /api/v1/recommendations` with structured conditions and optional natural language search text.
3. If the user is authenticated, API Gateway or the auth boundary validates the bearer token and exposes a stable `userId` to `AgentCore-Function`.
4. `AgentCore-Function` loads the authenticated user's saved preference snapshot when available.
5. `AgentCore-Function` resolves city context:
   - fixed city when `entryType` is `map_marker` and `destinationId` is present,
   - candidate city context when the request is chat/search driven,
   - no cross-country mixing.
6. `AgentCore-Function` builds a sanitized AgentCore context payload from request conditions, user preferences, city/content data, and policy constraints.
7. AgentCore runs the itinerary pipeline:
   - parse and normalize intent,
   - retrieve and rank city/content context,
   - select one destination when not already fixed,
   - generate itinerary days/items,
   - produce recommendation and itinerary-flow explanations,
   - validate country separation, theme coverage, source grounding, and festival date status.
8. `AgentCore-Function` packages the response into the public API schema.
9. The client may show the generated recommendation immediately.
10. If the user chooses to save the plan, the client calls `POST /api/v1/me/itineraries` with the save-compatible snapshot from the recommendation response.

## Requirements

### Functional Requirements

- `POST /api/v1/recommendations` must accept structured itinerary generation input.
- The endpoint must support `entryType` values compatible with the current MVP contract:
  - `map_marker`
  - `chat`
  - `home_recommendation`
- `country` must be required and must be one of `KR` or `JP`.
- `destinationId` must be required when `entryType` is `map_marker`.
- `destinationId`, `cityId`, or a normalized selected destination must be used as the city anchor before itinerary generation returns.
- In current `Lovv_BE` Map/City docs, `cityId` maps to `SmallCityApiRecord.id` from `/api/small-cities`.
- `themes` must use canonical theme ids from the theme/onboarding options contract.
- `themes` should contain 1 to 3 active theme ids for MVP unless a later approved Spec changes the limit.
- Current Map/City docs use Korean theme labels for `/api/small-cities`; implementation must define a theme-key to city-theme-label mapping before retrieval.
- `naturalLanguageQuery` must support the user's search text or chat condition.
- Travel timing input must support the existing `travelYear` and `travelMonth` fields.
- Precise travel dates should be represented by optional `travelDates.startDate` and `travelDates.endDate`.
- Duration must be represented by existing `tripType` and may be normalized into `duration.days` and `duration.nights`.
- Companion context must be accepted as optional structured input.
- Pace context must be accepted as optional structured input.
- User constraints must be accepted as optional structured input.
- `includeFestivals` must control whether confirmed festival events may be placed into the itinerary.
- `userLocation` must remain optional and must not be required when location permission is missing.
- If the authenticated user's preferences are available, the server must load them server-side rather than trusting the client to send the full preference profile.
- The AgentCore handoff payload must not include access tokens, OAuth provider tokens, raw chat history, raw prompt text, or private user metadata.
- The response must include a generated itinerary, destination, explanations, validation/festival status, links, and save-compatible identifiers.
- The response must be compatible with saving through `POST /api/v1/me/itineraries`.

### Validation Requirements

- Reject missing required fields with `400 VALIDATION_ERROR`.
- Reject unsupported `country`, `entryType`, `tripType`, `pace`, or companion values with `400 VALIDATION_ERROR`.
- Reject `themes` that are not canonical theme ids with `400 VALIDATION_ERROR` when the theme source is available.
- Reject `destinationId` that does not exist or does not match `country` with `404 DESTINATION_NOT_FOUND` or `409 COUNTRY_MISMATCH`.
- Reject date ranges where `endDate` is before `startDate`.
- Reject date ranges that conflict with `tripType` when both are provided and the conflict is deterministic.
- Never return an itinerary that mixes Korean and Japanese destinations in one recommendation.
- Never directly place a festival into the itinerary unless its date status is `confirmed`.
- If conditions cannot be fully satisfied, return a partial safe response with lower `confidence` and explicit `userNotice`, or return a structured error when no safe recommendation can be produced.

### Security and Privacy Requirements

- `Authorization: Bearer <accessToken>` is optional for generation, but authenticated preferences must only be loaded after successful token validation.
- Unauthenticated requests may generate recommendations from request-local conditions only.
- The request body must not require the client to send raw saved preference data.
- The response must not expose internal model prompts, chain-of-thought, raw retrieval chunks, raw web documents, internal score vectors, credentials, or private storage keys.
- Redacted trace data may include `recommendationId`, `agentRunId`, node names, retry counts, latency, token usage summaries, fallback flags, and payload summaries.
- Trace data must not include raw conversation text or full generated prompt contents.

## API Contract

### Endpoint

```text
POST /api/v1/recommendations
```

Logical route ownership:

| Item | Value |
| --- | --- |
| Base URL | `/api/v1` |
| Path | `/recommendations` |
| Auth | Optional |
| Lambda | `AgentCore-Function` |
| Primary purpose | Generate one AI itinerary recommendation from user conditions and context |
| Timeout target | User-facing synchronous response within API Gateway integration limits, around 29 seconds |

### Request Body

```json
{
  "entryType": "chat",
  "destinationId": null,
  "city": {
    "cityId": null,
    "name": null,
    "country": "JP"
  },
  "country": "JP",
  "travelYear": 2026,
  "travelMonth": 10,
  "travelDates": {
    "startDate": "2026-10-10",
    "endDate": "2026-10-11"
  },
  "tripType": "2d1n",
  "duration": {
    "days": 2,
    "nights": 1
  },
  "themes": ["art_sense", "history_tradition"],
  "includeFestivals": true,
  "naturalLanguageQuery": "조용하고 예술적인 일본 소도시에서 1박 2일로 걷기 좋은 일정 만들어줘",
  "search": {
    "query": "조용한 미술관과 전통 거리",
    "source": "chat"
  },
  "companion": {
    "type": "couple",
    "count": 2
  },
  "pace": "balanced",
  "constraints": {
    "mobility": "low_walking",
    "budgetLevel": "mid",
    "avoid": ["crowded_places"],
    "mustInclude": ["local_food"],
    "accessibilityNotes": null
  },
  "userLocation": {
    "latitude": 37.5665,
    "longitude": 126.978
  }
}
```

### Request Field Rules

| Field | Required | Rule |
| --- | --- | --- |
| `entryType` | Yes | `map_marker`, `chat`, or `home_recommendation`. |
| `destinationId` | Conditional | Required for `map_marker`; optional for chat/search flow. |
| `city.cityId` | Optional | Current Map/City spec maps this to `SmallCityApiRecord.id`, such as `KR-Gangneung`. |
| `city.name` | Optional | User-entered city hint only; server must resolve it to known city context before final response. |
| `city.country` | Optional | Must match top-level `country` when present. |
| `country` | Yes | `KR` or `JP`. |
| `travelYear` | Conditional | Required when exact `travelDates.startDate` is absent and festival/date verification is needed. |
| `travelMonth` | Conditional | Required when exact travel dates are absent. Must be 1 to 12. |
| `travelDates.startDate` | Optional | ISO 8601 date. If provided with `endDate`, it is the preferred date source. |
| `travelDates.endDate` | Optional | ISO 8601 date. Must not be before `startDate`. |
| `tripType` | Yes | `daytrip`, `2d1n`, `3d2n`, `4d3n`, or `5d4n` unless later specs extend it. |
| `duration.days` | Optional | Derived from `tripType` when absent. Must align with `tripType` when present. |
| `duration.nights` | Optional | Derived from `tripType` when absent. Must align with `tripType` when present. |
| `themes` | Yes | Canonical preference/theme keys for AgentCore input. Task Agent must map these to current Map/City Korean theme labels before `/api/small-cities` lookup. |
| `includeFestivals` | Yes | Controls whether confirmed festivals may be placed into itinerary items. |
| `naturalLanguageQuery` | Optional | Current user search/chat text. Do not persist raw by default. |
| `search.query` | Optional | Structured search text. If both provided, merge with `naturalLanguageQuery` into `cleanedRawQuery`. |
| `search.source` | Optional | `chat`, `form`, `map`, or `home`. |
| `companion.type` | Optional | `solo`, `couple`, `friends`, `family`, or `other`. |
| `companion.count` | Optional | Positive integer when known. |
| `pace` | Optional | `relaxed`, `balanced`, or `active`, aligned with `USER_PREFERENCE_API_SPEC.md`. Defaults to authenticated preference or `balanced`. |
| `constraints` | Optional | Soft and hard planning constraints. Must be sanitized before AgentCore handoff. |
| `userLocation` | Optional | Used only when permission exists. Must be omitted or null otherwise. |

### Response Statuses

| Status | Meaning |
| --- | --- |
| `201` | Recommendation and itinerary generated. |
| `400` | Request validation failed. |
| `401` | Invalid bearer token when an auth header is supplied and validation is required. |
| `404` | Fixed destination/city not found. |
| `409` | Deterministic request conflict, such as country mismatch or incompatible date/duration. |
| `422` | Conditions are valid but cannot produce a safe itinerary. |
| `504` | Generation exceeded the synchronous response boundary and no async fallback is approved. |

### Error Shape

Use the existing common API error structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 값이 올바르지 않습니다.",
    "details": {
      "field": "travelDates.endDate"
    }
  }
}
```

## Context Contract

### Context Sources

| Context | Source | Required For Generation | Notes |
| --- | --- | --- | --- |
| Request conditions | `POST /recommendations` body | Yes | User-provided city/country/theme/search/date/duration/companion/pace/constraints. |
| Authenticated user id | Bearer token/authorizer | No | Required only for loading saved preferences. When production social auth is approved, use `AUTH_SOCIAL_LOGIN_API_SPEC.md` service JWT `sub` as the Lovv service user id. |
| Onboarding preferences | User Preference boundary | No | Use `USER_PREFERENCE_API_SPEC.md`: `countryTrack`, `mappedThemes`, `preferredRegions`, `selectedCityStyle`, `pace`, `tripDays`, `companionStyle`, and `travelStyles` when present. |
| Feedback summary | User Preference boundary | No | Use compact summary only. Do not load raw feedback events into prompt. |
| Destination/city context | Map/City boundary | Yes | Use `MAP_CITY_API_SPEC.md`: current backend routes are `/api/small-cities` and `/api/small-cities/{cityId}` with `SmallCityApiRecord` as the city context source. |
| Candidate places | Destination/content data | Yes | Must include source or verification status where available. |
| Festival date verification | Festival verifier/cache | Conditional | Required when `includeFestivals=true` or festival candidates are considered. |
| Weather trends | Static trend data or weather skill | Optional | Used for alternative itinerary, not live scoring. |

### Authenticated Preference Loading

When `Authorization` is present and valid:

1. Resolve `userId` from the validated token or authorizer context. For production social auth, this should be the service JWT `sub` from `AUTH_SOCIAL_LOGIN_API_SPEC.md`, not a provider token subject passed directly from the client.
2. Load a sanitized preference snapshot from the user preference boundary.
3. Include only fields needed for recommendation:
   - `countryTrack`
   - `selectedCityStyle`
   - `mappedThemes`
   - `preferredRegions`
   - `pace`
   - `tripDays`
   - `companionStyle`
   - `travelStyles`
   - compact `feedbackSummary` such as liked/disliked theme ids or destination ids
   - `updatedAt`
4. Merge preferences with request conditions using this priority:
   - explicit current request condition
   - natural language condition extracted from current request
   - saved onboarding preference
   - safe system default
5. Never pass access tokens, provider tokens, email address, phone number, raw feedback rows, raw chat messages, or private account metadata to AgentCore.

When unauthenticated:

1. Do not load saved preferences.
2. Use request-local `themes`, `naturalLanguageQuery`, `search`, `companion`, `pace`, and `constraints`.
3. Return a recommendation that can be displayed immediately.
4. Require user authentication only if the user later saves through `/me/itineraries`.

### AgentCore Handoff Payload

The internal handoff payload should be normalized before invoking AgentCore:

```json
{
  "requestContext": {
    "recommendationId": "uuid",
    "agentRunId": "uuid",
    "entryType": "chat",
    "authenticated": true
  },
  "conditionContext": {
    "country": "JP",
    "travelYear": 2026,
    "travelMonth": 10,
    "travelDates": {
      "startDate": "2026-10-10",
      "endDate": "2026-10-11"
    },
    "tripType": "2d1n",
    "duration": {
      "days": 2,
      "nights": 1
    },
    "activeRequiredThemes": ["art_sense", "history_tradition"],
    "includeFestivals": true,
    "cleanedRawQuery": "조용하고 예술적인 일본 소도시에서 걷기 좋은 일정",
    "softPreferences": ["quiet", "walkable"],
    "companion": {
      "type": "couple",
      "count": 2
    },
    "pace": "balanced",
    "constraints": {
      "mobility": "low_walking",
      "avoid": ["crowded_places"],
      "mustInclude": ["local_food"]
    }
  },
  "preferenceContext": {
    "userIdHash": "redacted-or-derived-id",
    "mappedThemes": ["art_sense"],
    "selectedCityStyle": "KANAZAWA",
    "pace": "balanced",
    "tripDays": 2,
    "companionStyle": "couple",
    "travelStyles": ["slow_walk", "local_food"],
    "feedbackSummary": {
      "likedThemeIds": ["history_tradition"],
      "dislikedDestinationIds": []
    }
  },
  "cityContext": {
    "selectionMode": "candidate_search",
    "fixedDestinationId": null,
    "fixedCityId": null,
    "candidateCountry": "JP",
    "cityRecordSource": "SmallCityApiRecord",
    "candidateCities": []
  },
  "policyContext": {
    "singleDestinationOnly": true,
    "forbidCountryMixing": true,
    "forbidUnconfirmedFestivalPlacement": true,
    "doNotPersistRawMessages": true
  }
}
```

### Context Minimization Rules

- Pass summaries and normalized ids instead of raw records when possible.
- Pass selected candidate snippets only after retrieval filtering.
- Do not pass full destination catalogs to a model prompt.
- Do not pass raw RAG chunks to `Supervisor_Router`.
- Do not pass full conversation history. Use only the current request and, if later approved, a rolling summary with strict TTL.
- `unsupportedConditions` must be excluded from retrieval filters and surfaced in `userNotice`.

## Response Schema

### Response 201

```json
{
  "recommendationId": "uuid",
  "agentRunId": "uuid",
  "expiresAt": "2026-06-08T09:30:00Z",
  "title": "가나자와 1박 2일 예술 산책",
  "destination": {
    "destinationId": "uuid",
    "cityId": "uuid",
    "name": "가나자와",
    "country": "JP",
    "region": "이시카와현"
  },
  "requestSnapshot": {
    "entryType": "chat",
    "country": "JP",
    "travelYear": 2026,
    "travelMonth": 10,
    "travelDates": {
      "startDate": "2026-10-10",
      "endDate": "2026-10-11"
    },
    "tripType": "2d1n",
    "duration": {
      "days": 2,
      "nights": 1
    },
    "themes": ["art_sense", "history_tradition"],
    "includeFestivals": true,
    "companion": {
      "type": "couple",
      "count": 2
    },
    "pace": "balanced",
    "constraintsApplied": ["low_walking", "avoid:crowded_places"]
  },
  "itinerary": {
    "tripType": "2d1n",
    "days": [
      {
        "day": 1,
        "title": "전통 거리와 미술관 중심 일정",
        "summary": "오전에는 대표 거리, 오후에는 실내 문화 콘텐츠를 배치합니다.",
        "items": [
          {
            "itemId": "uuid",
            "contentId": "uuid",
            "timeOfDay": "morning",
            "sortOrder": 1,
            "title": "히가시차야 거리 산책",
            "body": "전통 거리 분위기를 먼저 느낄 수 있는 산책 블록입니다.",
            "reason": "선택한 예술/전통 테마와 도보 중심 조건에 맞습니다.",
            "moveMinutes": 12,
            "latitude": 36.5724,
            "longitude": 136.6677,
            "sourceBadges": ["destination_catalog"],
            "verificationStatus": "verified",
            "isFestival": false
          }
        ]
      }
    ]
  },
  "alternativeItinerary": {
    "trigger": "weather_trend",
    "reason": "10월 우천 가능성에 대비해 실내 중심 대체 일정을 제공합니다.",
    "days": []
  },
  "explainability": {
    "matchedConditions": [
      "country:JP",
      "travelMonth:10",
      "tripType:2d1n",
      "theme:art_sense",
      "pace:balanced"
    ],
    "unsupportedConditions": [],
    "recommendationReasons": [
      "예술과 전통 테마를 함께 만족하는 장소가 충분합니다.",
      "1박 2일 동안 이동 부담을 낮출 수 있는 동선입니다."
    ],
    "itineraryFlowReason": "오전에는 대표 거리 산책, 오후에는 실내 문화 콘텐츠를 배치해 이동 부담을 낮췄습니다.",
    "confidence": 0.86,
    "userNotice": "숙소 가격과 예약 가능 여부는 실시간 확정 정보가 아니므로 검색 링크에서 확인해야 합니다."
  },
  "festivalDateVerifications": [
    {
      "festivalId": "uuid",
      "dateStatus": "confirmed",
      "startDate": "2026-10-10",
      "endDate": "2026-10-12",
      "sourceUrl": "https://example.official.jp",
      "confidence": 0.91
    }
  ],
  "links": {
    "map": "https://maps.google.com/...",
    "staySearch": "https://..."
  },
  "saveCompatibility": {
    "canSaveWithPostMeItineraries": true,
    "saveFields": {
      "recommendationId": "uuid",
      "destinationId": "uuid",
      "title": "가나자와 1박 2일 예술 산책",
      "tripType": "2d1n",
      "themes": ["art_sense", "history_tradition"],
      "daysSource": "itinerary.days"
    }
  }
}
```

### Response Field Rules

| Field | Rule |
| --- | --- |
| `recommendationId` | Short-lived recommendation result id. Required for later save. |
| `agentRunId` | Redacted trace id. Optional in public response if product decides to hide it. |
| `expiresAt` | TTL for temporary recommendation lookup. Not a saved-plan retention timestamp. |
| `title` | Generated display title suitable for saved plan title default. |
| `destination.destinationId` | Must map to `POST /me/itineraries.destinationId`. |
| `requestSnapshot.themes` | Must map to `POST /me/itineraries.themes`. |
| `itinerary.tripType` | Must map to `POST /me/itineraries.tripType`. |
| `itinerary.days` | Must map to `POST /me/itineraries.days`. |
| `alternativeItinerary` | Optional safe fallback plan; not automatically saved unless user chooses it in a future approved flow. |
| `explainability.confidence` | 0 to 1. Lower when data is missing or fallback behavior was used. |
| `festivalDateVerifications` | Include only structured verification results, not raw web pages. |
| `links.map` | Map search/deep link. |
| `links.staySearch` | Stay search link only. Do not directly recommend lodging inventory. |
| `saveCompatibility` | Helper metadata for Task Agent and client mapping. It is not a separate persistence action. |

## Saved Plans Compatibility

The generated recommendation response must support the existing saved-plan request:

```json
{
  "recommendationId": "uuid",
  "destinationId": "uuid",
  "title": "가나자와 1박 2일 예술 산책",
  "tripType": "2d1n",
  "themes": ["art_sense", "history_tradition"],
  "days": []
}
```

Mapping:

| Saved Plans field | Recommendation source |
| --- | --- |
| `recommendationId` | `recommendationId` |
| `destinationId` | `destination.destinationId` |
| `title` | `title` |
| `tripType` | `itinerary.tripType` |
| `themes` | `requestSnapshot.themes` |
| `days` | `itinerary.days` |

If the client wants to save `alternativeItinerary`, that is out of scope for this Spec and requires a later approved save-alternative flow.

## Persistence Policy

| Data | Persistence Policy |
| --- | --- |
| Raw user chat/search text | Do not persist by default. Use only for the current generation request. |
| Raw prompt text | Do not persist. |
| Raw RAG/web retrieval content | Do not persist in user account data. |
| Normalized condition snapshot | May be held in short-lived response cache with `recommendationId` TTL. |
| `recommendationId` result | May be stored in short-lived cache for `GET /recommendations/{recommendationId}`. |
| Agent trace | May be stored as redacted TTL trace without raw messages. |
| Generated itinerary | Not account-persistent until user calls `POST /me/itineraries`. |
| Final saved plan | Persist only through Saved Plans API after explicit user action. |
| User preferences | Loaded from User Preference boundary only when authenticated; not overwritten by generation. |
| Unfinished PlanDraft | Do not persist server-side by default. |

The implementation must not silently convert a generated recommendation into a saved plan. Saving is a separate intentional user action.

## Lambda/AgentCore Boundary

### AWS SAM Lambda Boundary

| Boundary | Responsibility |
| --- | --- |
| API Gateway | Route `POST /api/v1/recommendations` to `AgentCore-Function`; enforce content type, CORS, auth header pass-through, and integration timeout. |
| `AgentCore-Function` | Request validation, auth context extraction, preference loading, city context lookup orchestration, AgentCore invocation, response packaging, error mapping. |
| Auth/User Preference boundary | Validate token and provide sanitized preference snapshot when authenticated. Use `AUTH_SOCIAL_LOGIN_API_SPEC.md` for production service user/session assumptions and `USER_PREFERENCE_API_SPEC.md` for current preference fields and onboarding gating. |
| Map/City boundary | Provide city/detail context from the current `/api/small-cities` and `/api/small-cities/{cityId}` contracts in `MAP_CITY_API_SPEC.md`. |
| AgentCore Runtime | Execute Supervisor and Sub-Agent graph for retrieval, ranking, itinerary generation, explanation, validation, and fallback. |
| AgentCore Gateway or Lambda skills | Deterministic scoring, matrix transition, validation, link building, weather trend lookup, output packaging. |
| Observability | Record redacted trace, latency, token usage summary, retry count, fallback status, and error code. |

### AgentCore Internal Boundary

| Component | Responsibility |
| --- | --- |
| `Intent_Agent` | Normalize request conditions, natural language query, saved preferences, and unsupported conditions. |
| `Supervisor_Router` | Route state between retrieval, ranking, planning, explanation, validation, and fallback. It must not hold raw conversation or raw retrieval bodies. |
| `Polymorphic_Retriever_Agent` | Retrieve candidate city/place/festival context for fixed or search-driven city flow. |
| `Festival_Verifier_Agent` | Verify festival dates for the requested year/month or exact travel dates. |
| `Ranker_Agent` | Select one destination when the request does not fix a destination. |
| `Itinerary_Planner_Agent` | Generate itinerary days/items and optional alternative itinerary. |
| `Explanation_Writer_Agent` | Produce recommendation reasons, itinerary flow reason, and user notice. |
| `Validation Skill` | Enforce deterministic checks before final response packaging. |
| `Output_Validator_Agent` | Check grounding, hallucination risk, explainability, and fallback safety. |

### Boundary Decisions

- `AgentCore-Function` owns the public API schema.
- AgentCore owns internal planning state and generation flow.
- User Preference and Map/City APIs are dependencies, not part of this implementation scope.
- The public API must remain stable even if the internal AgentCore graph changes.
- Real model/provider credentials and production AgentCore resource identifiers are out of scope until a deployment Spec pins them.

## Acceptance Criteria

- The Spec defines `POST /api/v1/recommendations` as the AI itinerary generation endpoint.
- The Spec does not introduce a conflicting `/api/agent/itineraries` endpoint.
- The request contract includes city, country, themes, search text, travel dates, duration, companion, pace, and constraints where appropriate.
- The request contract remains compatible with existing MVP fields: `entryType`, `destinationId`, `country`, `travelYear`, `travelMonth`, `tripType`, `themes`, `includeFestivals`, `naturalLanguageQuery`, and `userLocation`.
- The Spec defines how authenticated preferences are loaded server-side and sanitized before AgentCore handoff.
- The Spec defines a context handoff payload for AgentCore.
- The response schema includes generated itinerary days/items.
- The response schema includes a destination, title, themes/request snapshot, explanations, festival verification results, links, and save compatibility metadata.
- The response can be mapped into `POST /api/v1/me/itineraries`.
- The persistence policy explicitly blocks raw in-progress chat message persistence and unfinished draft persistence by default.
- The Lambda/AgentCore boundary keeps auth/map APIs separate from heavy AI dependencies.
- Real model credentials and production AgentCore deployment details are marked out of scope.
- Dependency contracts from `USER_PREFERENCE_API_SPEC.md` and `MAP_CITY_API_SPEC.md` are reflected, including remaining theme and route-prefix alignment work.
- No implementation code is required by this Spec.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Auth social-login contract is production-direction but does not prove provider consoles, real secrets, DB sessions, or deployment are ready. | User id/session behavior may differ between local scaffold and production social auth. | Use `AUTH_SOCIAL_LOGIN_API_SPEC.md` for service JWT/session assumptions, rely only on verified `userId`/`sub`, and keep preference snapshot minimal. |
| Map/City uses `/api/small-cities` and Korean theme labels while AgentCore/MVP planning uses `/recommendations` and canonical theme keys. | Theme and city lookup may drift across domains. | Task Agent must define explicit theme-key to city-theme-label mapping and `destinationId`/`cityId` alias handling before implementation. |
| Existing MVP contract is simpler than this itinerary-specific request contract. | Implementation may overbuild. | Keep new fields optional unless needed; preserve existing MVP fields as the minimal request. |
| 29-second synchronous timeout may be too short for full AgentCore generation. | User-facing timeouts or partial output. | Keep MVP generation bounded; future async job or response streaming needs a separate Spec. |
| Model output may hallucinate places or festival dates. | Incorrect itinerary. | Require validation, source badges, festival status checks, and fallback `userNotice`. |
| Raw user text accidentally enters logs. | Privacy risk. | Redact logs and trace payloads; store summaries only. |
| Save response mapping drifts from Saved Plans API. | Client cannot save generated plan cleanly. | Keep `saveCompatibility` mapping and response fields aligned with `/me/itineraries`. |
| Database engine and schema are not finalized. | Implementation might assume incorrect persistence. | Do not add schema/migration work until a later approved DB Spec confirms it. |

## Task Breakdown

### Task: Confirm AgentCore API Dependency Alignment

- Purpose: Confirm user preference and map/city contract alignment before implementation.
- Scope: Read `USER_PREFERENCE_API_SPEC.md` and `MAP_CITY_API_SPEC.md`; define cross-domain field mapping only. Do not implement Lambda code.
- Dependencies: This Spec.
- Context Budget: Must read this Spec, `mvp_confirmed_api_contract.md`, `USER_PREFERENCE_API_SPEC.md`, and `MAP_CITY_API_SPEC.md`.
- Acceptance Criteria: Task Agent can name the exact preference fields, city identifiers, theme source, and content lookup boundary used by `AgentCore-Function`.
- Verification: Documentation review only.

### Task: Define Request Validation and Normalization

- Purpose: Convert public API input into a stable internal condition context.
- Scope: Validate fields, normalize travel dates/duration, merge search text, and derive active themes.
- Dependencies: Theme-key to city-theme-label mapping and `destinationId`/`cityId` alias decision.
- Context Budget: Must read this Spec and the existing MVP API contract; avoid reading unrelated frontend files.
- Acceptance Criteria: Invalid country, date, duration, entry type, theme, and destination conflicts produce structured errors.
- Verification: Unit tests for request validation after implementation begins.

### Task: Define Authenticated Preference Loading Boundary

- Purpose: Load user preferences safely without trusting client-supplied saved profiles.
- Scope: Resolve `userId`, load sanitized preference snapshot, and merge with request conditions by priority.
- Dependencies: `USER_PREFERENCE_API_SPEC.md`.
- Context Budget: Must read auth/preference contracts only; do not read real environment files.
- Acceptance Criteria: Authenticated and unauthenticated generation paths are both defined and privacy-safe.
- Verification: Unit tests for preference merge priority and redaction after implementation begins.

### Task: Define City and Content Context Handoff

- Purpose: Provide AgentCore with enough city/content context to generate grounded itineraries.
- Scope: Fixed destination flow, chat/search candidate flow, candidate place context, source badges, festival verification inputs.
- Dependencies: `MAP_CITY_API_SPEC.md`.
- Context Budget: Must read map/city API contract and agent itinerary flow docs.
- Acceptance Criteria: AgentCore can generate one-destination itineraries without country mixing or unverified festival placement.
- Verification: Contract tests or fixture-based tests after implementation begins.

### Task: Define AgentCore Invocation and Fallback

- Purpose: Bound the AgentCore runtime call and fallback behavior.
- Scope: Handoff payload, retry limit, validation failure behavior, timeout behavior, redacted trace summary.
- Dependencies: Request/context normalization tasks.
- Context Budget: Must read AgentCore mapping sections and technical Lambda boundary only.
- Acceptance Criteria: Implementation has a clear sync path and a clear no-async fallback rule for MVP.
- Verification: Unit tests with mocked AgentCore adapter and timeout/error fixtures after implementation begins.

### Task: Define Response Packaging and Save Mapping

- Purpose: Return an itinerary response that the client can display and later save.
- Scope: Response fields, `saveCompatibility`, saved-plan mapping, error shape.
- Dependencies: Saved Plans API contract.
- Context Budget: Must read this Spec and `mvp_confirmed_api_contract.md` saved itinerary section.
- Acceptance Criteria: `POST /recommendations` response maps deterministically into `POST /me/itineraries`.
- Verification: Schema tests and save-mapping fixture tests after implementation begins.

## Verification

This Spec task is documentation-only. Verification for this task:

- Confirm exactly one file was created:
  - `Lovv_BE/docs/specs/AGENTCORE_ITINERARY_API_SPEC.md`
- Confirm no implementation files were modified.
- Confirm the endpoint uses `POST /api/v1/recommendations`.
- Confirm the Spec includes all required sections:
  - Summary
  - Goals
  - Non-Goals
  - User Flow
  - Requirements
  - API Contract
  - Context Contract
  - Response Schema
  - Persistence Policy
  - Lambda/AgentCore Boundary
  - Acceptance Criteria
  - Risks
  - Task Breakdown
  - Verification
- Confirm dependency specs and remaining alignment work are noted:
  - `USER_PREFERENCE_API_SPEC.md`
  - `MAP_CITY_API_SPEC.md`
- Confirm no real secrets, credentials, production model identifiers, or production AgentCore deployment identifiers are included.

Future implementation verification should include:

- Request schema validation tests.
- Preference merge and redaction tests.
- Destination/country mismatch tests.
- Festival `confirmed` placement tests.
- Save-plan mapping tests.
- AgentCore adapter timeout and fallback tests.
- Redacted observability/trace tests.
