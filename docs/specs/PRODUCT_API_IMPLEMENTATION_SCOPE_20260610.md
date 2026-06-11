# Product API Implementation Scope - 2026-06-10

## User Request Original

```text
AgentCore 실제 연동은 제외하고, Auth / User Preference / Map-City / Saved Plans 백엔드 구현을 진행해주세요.

구현 범위는 다음과 같습니다.

1. Auth
- Google/Kakao 소셜 로그인 API
- 서버 측 provider token 검증
- 사용자 조회/생성
- JWT access token 발급
- refresh session 저장
- 세션 확인 API
- 로그아웃 API

2. User Preference
- 온보딩 취향 저장
- 마이페이지 취향 수정
- 로그인 후 취향 조회
- 사용자별 preference 매핑

3. Map / City
- 기존 /api/small-cities 호환 유지
- /api/v1 기준 신규 Map/City API 정리
- 한국 소도시 40곳 목록 조회
- 소도시 상세 조회
- 이미지 URL 검증 로직 유지
- 지도 마커용 좌표 응답 제공

4. Saved Plans
- 생성 일정 저장
- 저장 일정 목록 조회
- 일정 상세 조회
- 좋아요/좋아요 취소

제외 범위:
- Bedrock AgentCore 실제 연결
- LLM 호출
- AI 일정 생성 품질 개선
- 대화 기록 저장
- 추천 알고리즘 고도화

AgentCore 관련 API는 프론트 연동을 위해 mock response까지만 유지하고, 실제 Bedrock AgentCore 연결은 후속 작업으로 분리해주세요.

구현 전 결정 필요 사항:
- users / social_accounts / preferences / saved_plans는 Aurora MySQL 기준
- auth_sessions는 DynamoDB TTL 기준
- refresh token은 HttpOnly Secure Cookie로 처리
- access token은 JWT로 처리
- 기존 demo /api/auth/login은 production social login으로 사용하지 않음
```

## Structured Agent Contract

- Implement Lovv backend APIs in the AWS SAM repository.
- Use `/api/v1` for new product APIs.
- Preserve legacy `GET /api/small-cities` and `GET /api/small-cities/{cityId}`.
- Use Aurora MySQL for `users`, `social_accounts`, `preferences`, and `saved_plans`.
- Use DynamoDB TTL for refresh-session records.
- Store only refresh-token hashes server-side.
- Return refresh token only as an HttpOnly Secure cookie.
- Return access token as a short-lived JWT.
- Remove the old demo login route from production routing.
- Keep AgentCore route as mock-only; do not call Bedrock, LLMs, or AgentCore.

## Implemented Route Boundary

| Domain | Routes |
| --- | --- |
| Auth | `POST /api/v1/auth/google`, `POST /api/v1/auth/kakao`, `GET /api/v1/auth/me`, `GET /api/v1/auth/session`, `POST /api/v1/auth/logout` |
| User Preference | `GET /api/v1/me/preferences`, `PUT /api/v1/me/preferences` |
| Map / City | `GET /api/small-cities`, `GET /api/small-cities/{cityId}`, `GET /api/small-cities/{cityId}/places`, `GET /api/v1/small-cities`, `GET /api/v1/small-cities/{cityId}`, `GET /api/v1/small-cities/{cityId}/places`, `GET /api/v1/map/cities`, `GET /api/v1/map/cities/{cityId}`, `GET /api/v1/map/cities/{cityId}/places`, `GET /api/v1/map/markers` |
| AgentCore mock | `POST /api/v1/recommendations` |
| Saved Plans | `POST /api/v1/me/itineraries`, `GET /api/v1/me/itineraries`, `GET /api/v1/me/itineraries/{itineraryId}`, `PUT /api/v1/me/itineraries/{itineraryId}/reactions/like`, `DELETE /api/v1/me/itineraries/{itineraryId}/reactions/like` |

## Storage Boundary

- Aurora MySQL baseline schema: `schema/aurora_mysql/001_product_api_tables.sql`.
- Runtime Aurora access path: RDS Data API through `AURORA_CLUSTER_ARN`, `AURORA_SECRET_ARN`, and `AURORA_DATABASE_NAME`.
- Auth sessions table: `AuthSessionsTable` in `template.yaml` with TTL attribute `expiresAt` and `RefreshTokenHashIndex`.
- Map/City detailed tourism content uses S3 raw city JSON directly:
  - bucket: `lovv-data-pipeline-dev-925273580929`
  - prefix: `raw/KR/details/20260609/`
  - file unit: one JSON per city, for example `Gangneung.json`
- Aurora is not used for full `attractions`, `festivals`, or `visitor_statistics` ingestion in this scope.
- If a city master is needed later, keep it to minimal marker/list columns only.

## Security Policy Decisions

- Kakao production login uses an OIDC `id_token` and validates `aud`, `iss`, and `exp` before user lookup/create.
- Access JWTs are stateless for the configured short TTL, currently `900` seconds by default.
- Logout revokes the refresh session and clears the refresh cookie. Already-issued access JWTs remain accepted by the Lambda authorizer until expiration unless a later task adds active-session authorizer checks.
- Logout revocation order is: valid refresh cookie first, bearer JWT `sid` fallback when no active refresh-cookie session is found, then idempotent no-content response when no usable credential exists.
- Map/City S3 source errors are converted to stable API envelopes without exposing bucket names, object keys, stack traces, or provider internals.

## Out Of Scope For This Implementation

- Bedrock AgentCore integration.
- LLM calls.
- Recommendation quality/ranking work.
- Conversation or draft persistence.
- Public/community saved-plan reactions.
- Provider console setup and real secret values.
- Full Aurora ingestion for attractions, festivals, or visitor statistics.
- Kakao API live calls for Map/City data.
