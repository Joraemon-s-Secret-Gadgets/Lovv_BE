# Map / City API Spec

## User Request Original

```text
3. Map / City
- 소도시 마커 목록
- 국가/테마/검색 필터
- 소도시 상세 정보
- 이미지 URL 제공
```

## Structured Agent Contract

- Agent Name: Backend Map City Spec Agent
- Core Role: Spec Agent
- Domain Focus: Backend AWS SAM
- Work Focus: map/city API
- Target repo: `/Users/jeonjonghyeok/Documents/Final/Lovv_BE`
- Deliverable: create one planning-only Spec file for the Map/City API domain.
- Contract: create a Backend AWS SAM Map/City domain Spec for marker list, country/theme/search filters, city detail, and image URL fields.
- Compatibility rule: preserve existing small-city contracts unless explicitly extending them backward-compatibly.
- Hard boundary: do not implement code and do not commit, push, pull, merge, or rebase.

## Summary

This Spec defines the Lovv backend Map/City API boundary for small-city map markers, country/theme/search filtering, city detail, and image URL delivery.

The active backend boundary in `Lovv_BE` is the existing AWS SAM `SmallCitiesFunction`:

- `GET /api/small-cities`
- `GET /api/small-cities/{cityId}`
- `GET /api/small-cities/{cityId}/places`

These routes are already represented in `template.yaml`, `src/small_cities/app.py`, `src/small_cities/service.py`, `src/small_cities/mapper.py`, and the existing small-city API/data contracts. This Spec does not replace them with the older planning paths from `oh_my_documents/docs/07_api_spec/mvp_confirmed_api_contract.md` such as `/destinations/map-markers` or `/destinations/{destinationId}`. Those planning paths remain external product-contract context only unless a future approved migration Spec maps them into the current backend route boundary.

The list API must continue returning the existing `SmallCityApiListResponse` shape. The frontend or a future adapter may derive a lean marker projection from each city record, but the HTTP list response must not be narrowed in a breaking way.

Latest data-source decision, 2026-06-10:

- Tourism detail data is not bulk-loaded into Aurora in this implementation.
- `attractions`, `festivals`, and `visitor_statistics` are read from S3 raw city JSON.
- S3 bucket: `lovv-data-pipeline-dev-925273580929`
- S3 prefix: `raw/KR/details/20260609/`
- File unit: one JSON file per city, for example `Gangneung.json`.
- Aurora is reserved first for durable user-owned data such as `users`, `social_accounts`, `preferences`, and `saved_plans`.
- If a `small_cities` city master is introduced later, keep it to the minimum marker/list columns needed by the map.
- Do not create Aurora `attractions`, `festivals`, or `visitor_statistics` tables in this implementation scope.

This Spec does not prove that a live API Gateway deployment, stage URL, database readiness, or production data population already exists. Implementation agents must verify deployment and environment state before using live calls.

## Goals

- Preserve the current `GET /api/small-cities` list contract.
- Preserve the current `GET /api/small-cities/{cityId}` detail contract.
- Define the map marker projection separately from full city detail.
- Support current country, theme, and search filters through the existing query parameters.
- Keep pagination behavior compatible with `LOVV_SMALL_CITY_API_CONTRACT.md`.
- Define how S3 raw city JSON maps into API records.
- Define how `/places` maps S3 raw attractions/festivals into frontend response data.
- Define representative coordinate behavior for map markers.
- Define `image_url` behavior without adding external image or map-provider calls.
- Define acceptance criteria, risks, implementation task breakdown, and verification expectations for a future Task Agent.

## Non-Goals

- Do not implement code in this Spec task.
- Do not add, rename, or remove API routes in this Spec task.
- Do not replace `/api/small-cities` with `/destinations/*`.
- Do not introduce external map provider calls, geocoding calls, directions calls, map-bounds calls, or provider-specific marker APIs.
- Do not introduce external image-provider calls, image download/proxy behavior, image transformation, or S3 image-copy behavior.
- Do not add GPS, bounds-based filtering, cursor pagination, month filtering, personalized ranking, or recommendation scoring.
- Do not change authentication, authorization, login, or user-specific persistence.
- Do not add graph DB behavior, EC2, WebSocket behavior, or non-MVP infrastructure.
- Do not create Aurora tables for `attractions`, `festivals`, or `visitor_statistics` in this Spec task.
- Do not call Kakao APIs or other live map/content provider APIs for Map/City data in this Spec task.
- Do not expose `internal_meta` as user-facing map or detail copy.

## User Flow

1. The client opens the map/city discovery view.
2. The client calls `GET /api/small-cities` with optional filters:
   - `country`
   - `themes`
   - `q`
   - `page`
   - `page_size`
3. The Lambda validates query parameters before repository work.
4. The service loads city JSON files from S3 raw detail storage, maps them into `SmallCityApiRecord` objects, applies filters, and returns the list response with pagination metadata.
5. The client derives map marker records from returned city records.
6. The map renders markers using city identity, display name, country, region, and representative coordinates.
7. When the user selects a marker or list item, the client resolves full city detail from the list record or calls `GET /api/small-cities/{cityId}`.
8. The detail view displays city base information plus a summary derived from the S3 raw detail file.
9. When the client needs place lists, it calls `GET /api/small-cities/{cityId}/places` and receives S3-derived `attractions` and `festivals`.
10. If `image_url` is `null` or missing, the client must use its own fallback UI; the backend must not fail the city record only because an image is unavailable.

## Requirements

### Route And Compatibility Requirements

- R1. The API must keep `GET /api/small-cities` as the primary small-city list route.
- R2. The API must keep `GET /api/small-cities/{cityId}` as the primary small-city detail route.
- R3. Existing response fields in `SmallCityApiRecord` must not be removed, renamed, or made incompatible.
- R4. Backward-compatible extensions may add optional nullable fields, optional metadata, or internal fields, but must not require existing clients to change.
- R5. If future product docs require `/destinations/map-markers` or `/destinations/{destinationId}`, a separate approved migration Spec must define route aliasing, response mapping, and deprecation behavior.

### Filter Requirements

- R6. `country` must align with the current query parameter and accept only `KR` or `JP`.
- R7. `q` must align with the current query parameter and be treated as a trimmed search string with the current maximum length of 80 characters.
- R8. `themes` must align with the current comma-separated query parameter.
- R9. `themes` values must use the current backend-supported theme labels:
  - `온천`
  - `바다`
  - `미식`
  - `전통`
  - `자연`
  - `예술`
  - `축제`
  - `산책`
- R10. Multiple `themes` values must match records when any requested theme is present in the city record.
- R11. `country`, `themes`, and `q` filters must compose with AND semantics across filter categories.
- R12. This Spec does not add singular `theme`, canonical `themeId`, or `month` query parameters to `/api/small-cities`.
- R13. If canonical theme IDs from `/themes/onboarding-options` are introduced later, a separate approved Spec must define ID-to-label mapping without breaking the current `themes` parameter.

### Marker Requirements

- R14. The HTTP list response remains `SmallCityApiListResponse`.
- R15. The map marker shape must be treated as a projection derived from each city record, not as a replacement for the list response.
- R16. Marker labels must use `name_ko` only.
- R17. Marker records must not use `themes`, `highlights`, or `route_seed` as marker labels.
- R18. Marker records must not include `summary`, `detail`, `highlights`, `route_seed`, or `internal_meta`.
- R19. Marker coordinates must come from the representative coordinates in `SmallCityApiRecord.latitude` and `SmallCityApiRecord.longitude`.

### Detail Requirements

- R20. `GET /api/small-cities/{cityId}` must return `{"data": SmallCityApiRecord}` for a known city.
- R21. Unknown city IDs must return a structured `NOT_FOUND` error with HTTP 404.
- R22. Detail responses must preserve `summary`, `detail`, `themes`, `highlights`, `route_seed`, and `image_url`.
- R23. `internal_meta` may remain available for backend/debug compatibility, but it must not become user-facing UI copy without a future copy/security review.

### Data Requirements

- R24. Source data for this domain is S3 raw city detail JSON configured by `MAP_CITY_S3_BUCKET` and `MAP_CITY_S3_PREFIX`.
- R25. List loading must use one city JSON file per Korean small city under `raw/KR/details/20260609/`.
- R26. Detail loading must map `cityId` into the matching city JSON file, for example `KR-Gangneung` to `Gangneung.json`.
- R27. City records with no usable place coordinates must not produce invalid map records.
- R28. Theme normalization must use the current backend label set and aliases from the mapper.
- R29. `image_url` must be nullable and must not be required for a valid city record.
- R29a. `GET /api/small-cities/{cityId}/places` must return frontend-ready `attractions` and `festivals` arrays derived from the S3 raw JSON.
- R29b. `visitor_statistics` records may be summarized in counts or lightweight detail summaries, but must not be loaded into Aurora in this scope.

### Error And Security Requirements

- R30. Non-GET methods must return a structured `INVALID_METHOD` error with HTTP 405.
- R31. Invalid query parameters must return a structured `INVALID_QUERY` error with HTTP 400.
- R32. Backend failures must return a structured `INTERNAL_ERROR` error with HTTP 500 and must not expose internal exception details.
- R33. Response headers must remain JSON-compatible and CORS-compatible with the existing SAM HTTP API behavior.
- R34. The API must not hardcode secrets, API keys, external provider tokens, or private config.
- R35. The API must not make live external provider calls for marker coordinates or images.

## API Contract

### `GET /api/small-cities`

Returns a page of small-city API records. This response shape is preserved from `LOVV_SMALL_CITY_API_CONTRACT.md`.

#### Query Parameters

| Parameter | Type | Required | Current Behavior |
| --- | --- | --- | --- |
| `country` | `KR` or `JP` | No | Exact country filter. Empty value means no country filter. Invalid values return `INVALID_QUERY`. |
| `q` | string | No | Trimmed search string. Empty value means no search filter. More than 80 characters returns `INVALID_QUERY`. |
| `themes` | comma-separated theme labels | No | Any-match filter against city `themes`. Unsupported labels return `INVALID_QUERY`. |
| `page` | positive integer | No | Defaults to `1`. Invalid or less than `1` returns `INVALID_QUERY`. |
| `page_size` | positive integer | No | Defaults to `120`. Maximum is `120`. Invalid, less than `1`, or over max returns `INVALID_QUERY`. |

#### Filter Semantics

- `country=KR` returns only Korea records.
- `country=JP` returns only Japan records.
- `themes=미식,바다` returns records that include either `미식` or `바다`.
- `q` searches across the current service search blob:
  - `id`
  - `country_label`
  - `region`
  - `name_ko`
  - `name_local`
  - `summary`
  - `detail`
  - `themes`
  - `highlights`
  - `route_seed`
- When multiple filter categories are supplied, a record must satisfy every supplied category.
- Pagination is applied after filtering in the current service behavior.

#### Response 200

```ts
type SmallCityApiListResponse = {
  data: SmallCityApiRecord[]
  page: {
    page: number
    pageSize: number
    total: number
    hasNext: boolean
  }
}
```

### `GET /api/small-cities/{cityId}`

Returns one full city record by ID.

#### Path Parameters

| Parameter | Type | Required | Current Behavior |
| --- | --- | --- | --- |
| `cityId` | string | Yes | City API ID such as `KR-Gangneung`. Unknown IDs return `NOT_FOUND`. |

#### Response 200

```ts
type SmallCityApiDetailResponse = {
  data: SmallCityApiRecord
}
```

#### Response 404

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Small city was not found."
  }
}
```

### `SmallCityApiRecord`

This shape is the compatibility source of truth for both list and detail responses.

```ts
type SmallCityApiRecord = {
  id: string
  country: 'KR' | 'JP'
  country_label?: '한국' | '일본'
  region: string
  name_ko: string
  name_local?: string | null
  latitude: number
  longitude: number
  themes: string[]
  summary: string
  detail: string
  highlights: string[]
  route_seed: string[]
  image_url?: string | null
  internal_meta?: {
    rankingScore?: number
    source?: string
    provider?: string
    updatedAt?: string
    [key: string]: unknown
  }
}
```

Compatibility rules:

- `id` is the stable city identifier and must match `cityId` in the detail route.
- `country_label` is optional; clients may derive it from `country`.
- `image_url` is optional and nullable.
- `internal_meta` is backend/internal metadata and must not be required for frontend rendering.
- New optional fields may be added later, but existing fields must remain compatible.

### Marker Projection Shape

This shape is the map-rendering projection derived from `SmallCityApiRecord`. It is not a new HTTP response contract for this Spec.

```ts
type SmallCityMapMarkerApiProjection = {
  id: string
  cityId: string
  country: 'KR' | 'JP'
  countryLabel: '한국' | '일본'
  region: string
  label: string
  localLabel?: string | null
  latitude: number
  longitude: number
}
```

Projection mapping:

| Marker Field | Source |
| --- | --- |
| `id` | `SmallCityApiRecord.id` |
| `cityId` | `SmallCityApiRecord.id` |
| `country` | `SmallCityApiRecord.country` |
| `countryLabel` | `SmallCityApiRecord.country_label` or derived from `country` |
| `region` | `SmallCityApiRecord.region` |
| `label` | `SmallCityApiRecord.name_ko` |
| `localLabel` | `SmallCityApiRecord.name_local` |
| `latitude` | `SmallCityApiRecord.latitude` |
| `longitude` | `SmallCityApiRecord.longitude` |

The marker projection intentionally excludes detail/planner fields. List cards or detail cards may use the full list record, including `image_url`, but the map marker layer should remain lean.

## Data Source/Mapping

### S3 Raw JSON Source

The current backend reads from S3 raw city JSON configured by:

- SAM parameter: `MapCityS3Bucket`
- SAM parameter: `MapCityS3Prefix`
- Lambda environment variable: `MAP_CITY_S3_BUCKET`
- Lambda environment variable: `MAP_CITY_S3_PREFIX`
- Default bucket: `lovv-data-pipeline-dev-925273580929`
- Default prefix: `raw/KR/details/20260609/`

The current repository behavior is:

1. List request lists JSON objects under the configured S3 prefix.
2. For each city JSON object, read `city_record` plus `records`.
3. Build one `SmallCityApiRecord` from `city_record` plus related city records.
4. Skip records that cannot produce a valid mapped city record.

The current detail behavior is:

1. Convert `cityId` into the city filename stem, such as `KR-Gangneung` -> `Gangneung.json`.
2. Read the matching S3 JSON object.
3. Build one `SmallCityApiRecord` and attach a lightweight `detail_summary`.
4. Return `NOT_FOUND` when the object is absent or mapping cannot produce a valid city record.

The current places behavior is:

1. Convert `cityId` into the city filename stem.
2. Read the matching S3 JSON object.
3. Return `attractions` and `festivals` arrays mapped from raw records.
4. Exclude full `visitor_statistics` payloads from `/places`; expose only lightweight counts in `summary`.

### Field Mapping

| API Field | S3 Raw / Mapper Source |
| --- | --- |
| `id` | `city_record.city_id` |
| `country` | Derived from `city_id`; IDs starting with `JP-` map to `JP`, otherwise `KR` |
| `country_label` | Derived from `country` as `일본` or `한국` |
| `region` | Normalized `city_record.province` |
| `name_ko` | Normalized `city_record.city_name_ko` with common city/county suffix removed |
| `name_local` | `city_record.city_name_ko` |
| `latitude` | Representative latitude from related place rows |
| `longitude` | Representative longitude from related place rows |
| `themes` | Normalized theme labels from attraction/festival rows and festival presence |
| `summary` | Backend-generated Korean summary using region, city name, and top themes |
| `detail` | Backend-generated Korean detail using highlights and source counts |
| `highlights` | Up to four deterministic attraction/festival titles |
| `route_seed` | Current route seed is derived from highlights |
| `image_url` | First usable image URL from deterministic related place ordering |
| `internal_meta.source` | `S3RawCityDetails` |
| `internal_meta.sourceKey` | S3 object key, such as `raw/KR/details/20260609/Gangneung.json` |
| `internal_meta.attractionCount` | Count of related attraction rows |
| `internal_meta.festivalCount` | Count of related festival rows |
| `internal_meta.visitorStatisticsCount` | Count of related visitor-statistics rows |

### Representative Coordinate Behavior

- Representative coordinates are currently calculated from related place rows with usable `latitude` and `longitude`.
- Place rows are rows whose `entity_type` is `attraction` or `festival`.
- The representative coordinate is the arithmetic mean of usable place coordinates.
- Rows with missing or invalid coordinates are ignored for coordinate calculation.
- If no related place row has usable coordinates, the city record is invalid for map rendering and must not produce a marker.
- This behavior is deterministic but not the same as official city-center geocoding.
- This Spec does not authorize external geocoding, map-provider lookup, or coordinate enrichment calls.

### Theme Mapping Behavior

The current normalized theme labels are:

- `온천`
- `바다`
- `미식`
- `전통`
- `자연`
- `예술`
- `축제`
- `산책`

Mapper aliases may normalize source labels such as `해안`, `노포`, `역사`, `트레킹`, or `감성` into the supported theme label set. Festival rows also contribute `축제`. The current mapper returns up to four themes sorted by frequency and the configured theme order, with `자연` as fallback when no source theme is available.

## Image URL Behavior

- `image_url` is the API field for image delivery in this Spec.
- `image_url` must remain optional and nullable.
- `image_url` must be sourced from related `attraction` or `festival` records in the S3 raw city JSON.
- The current mapper chooses the first non-empty `image_url` from deterministically sorted place rows.
- Current place ordering prefers festival rows before attraction rows, then sorts by title.
- If no usable image URL exists, return `image_url: null` or omit the optional field in a backward-compatible way.
- Missing image URLs must not make the list or detail request fail.
- The backend must not call external image search, image CDN, map provider, or scraping providers to fill this field in this Spec.
- The backend must not download, transform, proxy, or re-host the image in this Spec.
- A future implementation may validate that image URLs are safe HTTP(S) strings, but invalid source values should degrade to `null` rather than breaking the entire city record unless a future data-quality Spec says otherwise.
- The older product-planning `image.heroImageUrl`, `thumbnailImageUrl`, or gallery object shape is not part of this current backend route contract. Adding that shape requires a backward-compatible extension or a separate migration Spec.

## Acceptance Criteria

- The Spec preserves `GET /api/small-cities` and `GET /api/small-cities/{cityId}` as the active backend routes.
- The Spec does not introduce `/destinations/*` as a replacement route.
- The Spec preserves the existing `SmallCityApiListResponse` shape.
- The Spec preserves the existing `SmallCityApiRecord` fields.
- The Spec defines the marker projection separately from the full city record.
- The Spec keeps marker labels sourced from `name_ko`.
- The Spec aligns filters with current query parameters: `country`, `q`, `themes`, `page`, and `page_size`.
- The Spec does not add unsupported `theme`, `themeId`, `month`, bounds, GPS, or cursor filters.
- The Spec documents S3 raw city JSON as the current data source.
- The Spec documents representative coordinate behavior.
- The Spec documents `image_url` behavior, including nullable fallback.
- The Spec forbids external map-provider and image-provider calls for this scope.
- The Spec includes a future Task Breakdown and Verification section.

## Risks

- Current list loading reads one S3 JSON object per city. This is acceptable for the 40-city MVP data but may need a compact city-master file or minimal city-master table if the dataset grows.
- Current pagination is applied after in-memory filtering. This preserves behavior but is not equivalent to object-store cursor pagination.
- Representative coordinates are averaged from available place coordinates and may not match official city centers.
- `cityId` to partition-key mapping depends on the current ID format. Future Japan or multi-country data must verify the same format before relying on this conversion.
- Current theme labels are Korean display labels, while older product-planning docs mention canonical `themeId` values. Introducing canonical IDs requires a separate compatibility plan.
- Source image URLs may be missing, stale, blocked, or unsuitable for display. This Spec treats images as best-effort optional fields.
- Current records may include `internal_meta`; clients must not display it as user-facing content.
- Live API Gateway deployment, stage/base URL, S3 bucket/prefix readiness, and IAM/runtime environment have not been verified by this Spec.

## Task Breakdown

### Task: Map/City contract compatibility review

- Purpose: 기존 소도시 API 계약을 깨지 않고 Map/City 기능 범위를 구현할 수 있는지 확인한다.
- Scope: `LOVV_SMALL_CITY_API_CONTRACT.md`, `LOVV_CITY_DATA_CONTRACT.md`, this Spec, `src/small_cities/app.py`, `src/small_cities/service.py`, `src/small_cities/mapper.py`, and `template.yaml` only. Source changes are allowed only after Task Agent approval.
- Dependencies: This Spec approval.
- Context Budget: Do not load unrelated auth, frontend, generated build, or `.aws-sam` artifacts unless a verification failure requires it.
- Acceptance Criteria: Active routes, query params, response fields, and marker projection rules are confirmed as compatible.
- Verification: Review existing unit tests and identify any missing compatibility tests before implementation.

### Task: Filter and response test hardening

- Purpose: 국가/테마/검색 필터와 페이지네이션이 계약대로 동작하는지 자동 검증한다.
- Scope: Small-city handler/service tests for `country`, `q`, `themes`, `page`, `page_size`, invalid query errors, and composed filters.
- Dependencies: Map/City contract compatibility review.
- Context Budget: Read this Spec, existing small-city tests, and small-city service/handler files. Do not edit SAM template unless a route-level issue is found and separately approved.
- Acceptance Criteria: Tests cover valid filters, invalid filters, pagination metadata, and list response shape.
- Verification: `python -m unittest tests/test_small_city_handler.py tests/test_small_city_mapper.py`

### Task: Data mapping and image behavior hardening

- Purpose: S3 raw city JSON에서 소도시 상세/마커에 필요한 좌표, 테마, 하이라이트, 이미지 URL이 안정적으로 매핑되도록 한다.
- Scope: Mapper/repository behavior and mapper tests for representative coordinates, no-coordinate records, theme aliases, highlight ordering, and nullable image behavior.
- Dependencies: Map/City contract compatibility review.
- Context Budget: Read this Spec, `src/small_cities/mapper.py`, `src/small_cities/s3_raw_repository.py`, and mapper/repository tests. Do not add external provider calls.
- Acceptance Criteria: Mapping behavior is deterministic, invalid source rows degrade safely, and missing images do not fail records.
- Verification: `python -m unittest tests/test_small_city_mapper.py`

### Task: SAM route and local event verification

- Purpose: AWS SAM 라우트가 현재 API 계약과 일치하는지 확인한다.
- Scope: `template.yaml`, small-city event samples, and route-level tests if approved.
- Dependencies: Map/City contract compatibility review.
- Context Budget: Read this Spec, `template.yaml`, and small-city event samples. Do not edit auth routes or unrelated Lambdas.
- Acceptance Criteria: SAM routes remain `GET /api/small-cities`, `GET /api/small-cities/{cityId}`, and `GET /api/small-cities/{cityId}/places`, with the expected handler and S3 read permissions.
- Verification: `sam validate` when SAM CLI is available; otherwise report SAM CLI unavailability and verify route definitions by static review.

### Task: Backend Map/City review

- Purpose: 구현 후 Review Agent가 사용자 원문과 구조화된 계약을 기준으로 변경 범위와 호환성을 검증한다.
- Scope: Read-only review of changed files, tests, and verification output.
- Dependencies: Any implementation tasks completed.
- Context Budget: Read this Spec, preserved User Request Original, Structured Agent Contract, changed-file list, and relevant test output. Do not load unrelated full docs unless a contradiction is found.
- Acceptance Criteria: No blocker remains for route compatibility, filter behavior, marker/detail/place separation, S3 raw mapping, image URL behavior, Aurora exclusion for tourism details, or external-provider exclusion.
- Verification: Review Agent report with findings ordered by severity.

## Verification

Spec-task verification:

- Confirm this file exists at `/Users/jeonjonghyeok/Documents/Final/Lovv_BE/docs/specs/MAP_CITY_API_SPEC.md`.
- Confirm no implementation files were changed for this Spec task.
- Confirm no git commit, push, pull, merge, or rebase was performed.
- Run a placeholder scan before final handoff.

Future implementation verification:

- `python -m unittest tests/test_small_city_handler.py tests/test_small_city_mapper.py`
- `sam validate` when SAM CLI is available.
- Static review that `template.yaml` still maps:
  - `GET /api/small-cities`
  - `GET /api/small-cities/{cityId}`
- Static review that no external map/image provider calls were introduced.
- Contract review against:
  - `/Users/jeonjonghyeok/Documents/Final/docs/specs/LOVV_SMALL_CITY_API_CONTRACT.md`
  - `/Users/jeonjonghyeok/Documents/Final/docs/specs/LOVV_CITY_DATA_CONTRACT.md`
  - this Spec
