# API Gateway Simple Login and Lambda Split Spec

## User Request Original

API GateWay 간편 로그인 까지 구현, API와, Lambda 각 기능별로 나누어 Spec Agent로 스펙 작성후, 각 역할 별 알맞는 Agent 생성해서, 병렬 작업

## Structured Agent Contract

- Agent Name: Backend Auth/API Spec Agent
- Core Role: Spec Agent
- Domain Focus: Backend AWS SAM
- Work Focus: Auth/API planning
- Target repo: `/Users/jeonjonghyeok/Documents/Final/Lovv_BE`
- Deliverable: create one planning-only Spec file for MVP API Gateway simple login and feature-level Lambda splitting.
- Execution intent: define a parallel-agent implementation plan with non-overlapping ownership after this Spec is approved.
- Hard boundary: do not implement code, do not edit source/tests/README/template/events, and do not run git operations.

## Summary

This Spec defines an MVP backend auth boundary for the current Lovv AWS SAM backend and a feature-level Lambda split plan. The current backend has one `AWS::Serverless::HttpApi` and one read-only `SmallCitiesFunction` that serves:

- `GET /api/small-cities`
- `GET /api/small-cities/{cityId}`

The requested next backend direction is to add API Gateway simple login and split API/Lambda responsibilities by feature. For MVP, "API Gateway simple login" means a code-owned authentication boundary suitable for local/SAM implementation: a demo login Lambda issues short-lived signed demo tokens, and a custom Lambda authorizer validates those tokens before protected routes run. This is explicitly MVP/simple-login behavior, not full production authentication.

If an external identity provider such as Cognito, OAuth/OIDC, or a social login provider is not approved before implementation, the implementation should use the custom Lambda authorizer plus demo login token flow defined here.

## Goals

- Add a planning contract for MVP simple login through API Gateway and Lambda.
- Define auth endpoints:
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/auth/logout`, or stateless logout by client token discard if no server-side token store is added.
- Preserve the existing small-city API contract:
  - `GET /api/small-cities`
  - `GET /api/small-cities/{cityId}`
- Define whether small-city routes are public or protected for MVP.
- Define feature-level Lambda boundaries so future work can be owned by separate agents without overlapping writes.
- Define shared utility boundaries for request parsing, JSON responses, token signing/verification, auth context, and CORS/header behavior.
- Define dummy environment variable names only. No real secrets, credentials, tokens, or private values.
- Define IAM and API Gateway route behavior at Spec level.
- Define a parallel implementation ownership table with non-overlapping write scopes.
- Provide Task Breakdown using the project Spec/Task format.

## Non-Goals

- Do not implement code in this Spec task.
- Do not choose or integrate a production identity provider.
- Do not add Cognito, OAuth/OIDC, social login, MFA, password reset, refresh-token rotation, account recovery, or production user lifecycle management.
- Do not persist in-progress chats, unfinished travel plans, or durable conversation history.
- Do not change the response contract for `GET /api/small-cities` or `GET /api/small-cities/{cityId}`.
- Do not introduce graph DB behavior, EC2, WebSocket auth, or non-MVP infrastructure.
- Do not create database schema, migrations, or new persistent user tables unless a later approved Spec explicitly adds them.
- Do not make real live API calls from frontend code as part of this planning task.

## User/System Flow

### MVP Login Flow

1. Client submits `POST /api/auth/login` with a demo login request.
2. Auth Lambda validates the request against MVP demo-login rules.
3. Auth Lambda returns a short-lived signed access token and a minimal user object.
4. Client stores the token only for the active MVP session according to the future frontend Spec.
5. Client calls protected backend routes with `Authorization: Bearer <token>`.
6. API Gateway invokes the custom Lambda authorizer for protected routes.
7. Authorizer verifies token signature, expiration, issuer/audience, and required claims.
8. API Gateway forwards the request only when authorization succeeds.
9. Protected Lambda receives user context from the authorizer context.
10. Client calls `GET /api/auth/me` to verify the current token and receive the current minimal user profile.
11. Logout is stateless by default: client discards the token. `POST /api/auth/logout` may return success without server-side invalidation unless a later Spec adds a token denylist or session store.

### Small-City API Flow

1. Client calls `GET /api/small-cities` with optional query parameters already defined by `LOVV_SMALL_CITY_API_CONTRACT.md`.
2. Small-city Lambda validates query parameters and loads records from the configured DynamoDB table.
3. Small-city Lambda returns the existing list response shape.
4. Client calls `GET /api/small-cities/{cityId}` for city detail.
5. Small-city Lambda returns `{"data": record}` or the existing not-found error shape.

### Public vs Protected Route Decision

For MVP, keep both small-city routes public:

- `GET /api/small-cities`: public
- `GET /api/small-cities/{cityId}`: public

Reason: the existing contract is read-only discovery data, the current Lambda has no user-specific behavior, and protecting these routes would force frontend login before map/city exploration. The simple-login boundary should first protect auth introspection and future user-specific routes, not the public city catalog.

Future protected routes, such as saved itineraries, user profile, recommendation history, or personalized ranking, must use the Lambda authorizer unless a later approved Spec changes auth architecture.

## Requirements

### Functional Requirements

- `POST /api/auth/login` must accept only the MVP demo-login request shape approved during implementation.
- `POST /api/auth/login` must return a signed short-lived token and minimal user profile on success.
- `POST /api/auth/login` must return a structured 400 or 401 error for invalid input or invalid demo credentials.
- `GET /api/auth/me` must require a valid bearer token.
- `GET /api/auth/me` must return the current authenticated user context derived from the token or authorizer context.
- `POST /api/auth/logout` must be defined as stateless for MVP unless implementation adds an approved token store.
- Stateless logout must return success and require the client to discard the token.
- Protected routes must reject missing, malformed, expired, or invalid tokens before the integration Lambda handles the request.
- Public small-city routes must remain callable without an `Authorization` header.
- Existing small-city query parameters, pagination shape, city record fields, and error behavior must remain compatible with `LOVV_SMALL_CITY_API_CONTRACT.md`.

### Auth Token Requirements

- Token format should be a compact signed bearer token suitable for Lambda validation.
- Token must include at least:
  - `sub`: stable MVP demo user id.
  - `display_name`: user-facing demo name.
  - `iat`: issued-at timestamp.
  - `exp`: expiration timestamp.
  - `iss`: Lovv MVP auth issuer.
  - `aud`: Lovv backend API audience.
- Token lifetime must be short for MVP. Recommended dummy configuration: `AUTH_TOKEN_TTL_SECONDS`.
- Token signing secret must come from an environment variable such as `AUTH_TOKEN_SIGNING_SECRET`.
- The Spec does not define or expose any real secret value.

### API Gateway Requirements

- The SAM template must keep a single API Gateway boundary unless implementation proves separate APIs are required.
- Public routes must not use the Lambda authorizer:
  - `GET /api/small-cities`
  - `GET /api/small-cities/{cityId}`
  - `POST /api/auth/login`
  - `POST /api/auth/logout` if implemented as stateless token discard only.
- Protected routes must use the custom Lambda authorizer:
  - `GET /api/auth/me`
  - Future user-specific routes.
- CORS must allow required auth headers:
  - `Content-Type`
  - `Authorization`
- CORS must allow required methods:
  - `GET`
  - `POST`
  - `OPTIONS`
- Error responses must remain JSON with stable machine-readable error codes.

### Lambda Split Requirements

Feature-level Lambdas should be split as follows:

| Lambda | Primary Responsibility | Route Ownership |
| --- | --- | --- |
| AuthFunction | Login, current user, stateless logout response | `/api/auth/*` |
| AuthAuthorizerFunction | Validate bearer token for protected routes | API Gateway authorizer only |
| SmallCitiesFunction | Read-only small-city list/detail API | `/api/small-cities`, `/api/small-cities/{cityId}` |

Shared utilities should live outside feature folders only when at least two feature Lambdas need them. Expected boundaries:

| Shared Utility Area | Responsibility | Consumers |
| --- | --- | --- |
| `shared/http` | JSON response, error response, headers, method helpers | AuthFunction, SmallCitiesFunction |
| `shared/auth` | Token signing, token verification, claims validation | AuthFunction, AuthAuthorizerFunction |
| `shared/config` | Environment variable reads with safe defaults/errors | AuthFunction, AuthAuthorizerFunction, SmallCitiesFunction |
| `shared/cors` | Shared CORS constants if template and code need alignment | AuthFunction, SmallCitiesFunction |

Implementation must avoid moving existing small-city logic into shared utilities unless duplication is real and reviewable.

### Environment Variable Requirements

Only dummy names are defined here. Real values must never be hardcoded or committed.

| Environment Variable | Scope | Purpose | Dummy Example |
| --- | --- | --- | --- |
| `TOUR_KOREA_TABLE_NAME` | SmallCitiesFunction | Existing DynamoDB table name for tour/city data | `TourKoreaData` |
| `AUTH_TOKEN_SIGNING_SECRET` | AuthFunction, AuthAuthorizerFunction | Secret used to sign and verify MVP demo tokens | `replace-with-local-demo-secret` |
| `AUTH_TOKEN_TTL_SECONDS` | AuthFunction | Access token lifetime | `3600` |
| `AUTH_ISSUER` | AuthFunction, AuthAuthorizerFunction | Expected token issuer | `lovv-mvp-auth` |
| `AUTH_AUDIENCE` | AuthFunction, AuthAuthorizerFunction | Expected token audience | `lovv-api` |
| `DEMO_LOGIN_USER_ID` | AuthFunction | MVP demo user id | `demo-user` |
| `DEMO_LOGIN_DISPLAY_NAME` | AuthFunction | MVP demo display name | `Lovv Demo User` |
| `DEMO_LOGIN_CODE` | AuthFunction | Optional demo login code if approved | `demo-code-only` |

If implementation uses `.env` or local SAM parameter files, real local values must remain ignored by Git. A future implementation task may update `.env.example` with dummy values only if that file exists or is approved in the task scope.

### IAM Requirements

- `SmallCitiesFunction` keeps DynamoDB read-only permissions:
  - `dynamodb:Scan`
  - `dynamodb:Query`
  - scoped to the configured tour/city table ARN.
- `AuthFunction` must not receive DynamoDB permissions for MVP stateless demo login.
- `AuthAuthorizerFunction` must not receive DynamoDB permissions for MVP stateless token verification.
- Auth Lambdas may use only CloudWatch Logs basic execution permissions through SAM defaults or explicitly scoped managed policy if the project uses one.
- No Lambda should receive wildcard data permissions for auth MVP.
- If a future token denylist or session store is approved, a separate Spec must define the storage engine, IAM actions, TTL behavior, and deletion semantics.

## Acceptance Criteria

- A future implementation has explicit route ownership for all auth and small-city endpoints.
- `POST /api/auth/login`, `GET /api/auth/me`, and `POST /api/auth/logout` are specified with MVP behavior.
- Logout is explicitly stateless for MVP unless a later approved Spec adds a server-side session/token store.
- `GET /api/small-cities` and `GET /api/small-cities/{cityId}` are preserved and remain public for MVP.
- Existing small-city response shape and query parameters are not changed by this Spec.
- The custom Lambda authorizer boundary is defined for protected routes.
- Feature-level Lambda split is defined without requiring implementation in this Spec.
- Shared utility boundaries are defined and do not force unnecessary refactors.
- Dummy environment variable names are listed without real secret values.
- IAM behavior is least-privilege at planning level.
- API Gateway CORS and route protection behavior are defined.
- Parallel implementation ownership has non-overlapping write scopes.
- Task Breakdown follows the project Task format.

## Constraints

- This Spec is planning-only and must not edit source code, tests, README, SAM template, event files, or generated artifacts.
- Implementation must stay inside `/Users/jeonjonghyeok/Documents/Final/Lovv_BE` unless the user approves another workspace.
- Implementation must not contradict `LOVV_SMALL_CITY_API_CONTRACT.md`.
- Implementation must not assume a finalized production database or identity provider.
- Implementation must not hardcode real secrets or commit environment files.
- Implementation must keep public and protected route behavior explicit in the SAM template.
- Implementation must use Python 3.12-compatible Lambda code because the current SAM globals use `python3.12`.
- Implementation must preserve current `arm64`, timeout, memory, and `src/` `CodeUri` defaults unless a later task approves changes.
- Parallel agents must not edit overlapping files or shared contracts without a single owner.
- Auth and authorization logic is security-sensitive; if parallel work creates conflicts, Main Codex must pause integration and route to review before continuing.

## Risks

- MVP simple-login is not production auth. It is acceptable for demo/internal MVP validation only.
- A shared signing secret in environment variables is operationally simple but requires careful local/deployment secret handling.
- Stateless logout cannot revoke already-issued tokens before expiration.
- Custom Lambda authorizer behavior and SAM HTTP API authorizer syntax must be verified during implementation against the installed SAM/toolchain version.
- If future user-specific routes need database-backed users or sessions, this Spec is insufficient and must be updated.
- If small-city routes later expose personalized ranking or private metadata, they may need to become protected in a separate Spec.
- CORS with `Authorization` can break frontend calls if the SAM template and Lambda responses are not kept aligned.
- Parallel implementation can create integration risk if shared utility interfaces are changed without a single shared owner.

## Parallel Implementation Ownership

Parallel work is allowed only after this Spec is approved and a Task Agent creates implementation-ready subtasks. The following ownership table defines safe non-overlapping scopes for future agents.

| Agent | Role | Task/Subtask | Write Scope | Read Scope | Forbidden Scope | Verification | Output |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Auth Lambda Implementation Agent | Implementation Agent | Implement MVP auth endpoints and token utilities | `src/auth/**`, `src/shared/auth/**`, auth-focused unit tests if approved | This Spec, `template.yaml`, existing small-city handler patterns | `src/small_cities/**`, DynamoDB repository code, frontend files | Auth unit tests, local handler event tests | Changed files and auth endpoint behavior report |
| API Gateway/SAM Implementation Agent | Implementation Agent | Add API Gateway auth routes, authorizer, CORS, env vars, IAM | `template.yaml`, SAM auth event samples if approved | This Spec, SAM template, auth Lambda handler contract | `src/small_cities/**` logic, auth business logic beyond handler names/env names | `sam validate`, template diff review | Route/IAM/env summary |
| Small-City Compatibility Agent | Implementation Agent or Review Agent | Keep small-city routes public and contract-compatible | If implementation: only small-city route tests approved by Task Agent. If review: read-only | This Spec, `LOVV_SMALL_CITY_API_CONTRACT.md`, `src/small_cities/**` | Auth implementation files except public/protected route integration checks | Existing small-city unit/handler tests | Compatibility report |
| Shared HTTP Utility Agent | Implementation Agent | Extract only genuinely shared HTTP response helpers if approved | `src/shared/http/**`, narrow imports in owning feature files assigned by Main Codex | Existing `json_response` and `error_response` behavior | Token logic, SAM template, DynamoDB logic | Unit tests for response helper compatibility | Shared utility report |
| Backend Auth/API Review Agent | Review Agent | Review integrated backend auth/API diff | Read-only | Full changed-file list from Main Codex | Any file writes | Review checklist, security notes, verification review | Approval or blocker findings |

Rules for Main Codex before parallel launch:

- Confirm every implementation-ready subtask has one write owner.
- Give `template.yaml` to only one writer.
- Give `src/shared/auth/**` to only one writer.
- Do not let multiple agents edit `src/small_cities/app.py` at the same time.
- Require final integration review after all outputs are collected.

## Task Breakdown

### Task: MVP auth contract finalization

- Purpose: API Gateway 간편 로그인의 MVP 범위와 보안 경계를 구현 전에 확정한다.
- Scope: `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`의 요청/응답, 오류, 토큰 클레임, stateless logout 정책을 확정한다. 프로덕션 인증 제공자 연동은 제외한다.
- Dependencies: 이 Spec 승인.
- Context Budget: 반드시 이 Spec과 `docs/specs/LOVV_SMALL_CITY_API_CONTRACT.md`를 읽는다. 전체 문서나 관련 없는 프론트엔드 파일은 읽지 않는다.
- Acceptance Criteria: MVP/simple-login이 프로덕션 인증이 아님을 명확히 유지하고, 토큰 발급/검증/만료/현재 사용자 조회/로그아웃 정책이 구현 가능하게 정의된다.
- Verification: Spec Review Agent가 요구사항, Non-Goals, 보안 제약, 작은 도시 API 보존 여부를 검토한다.

### Task: SAM API Gateway and authorizer planning

- Purpose: API Gateway 라우트, Lambda authorizer, CORS, 환경 변수, IAM 변경 범위를 구현 전에 분리한다.
- Scope: `template.yaml`에서 필요한 미래 변경사항을 계획한다. 실제 템플릿 수정은 다음 Implementation Task에서만 수행한다.
- Dependencies: MVP auth contract finalization.
- Context Budget: 반드시 이 Spec과 `template.yaml`을 읽는다. 구현 중에는 SAM 공식 문법 또는 로컬 SAM 검증 결과가 필요할 때만 추가 확인한다.
- Acceptance Criteria: 공개 라우트와 보호 라우트가 분리되고, authorizer 적용 대상, CORS 허용 헤더/메서드, IAM 최소 권한이 명확하다.
- Verification: 향후 구현 후 `sam validate`와 템플릿 리뷰를 실행한다.

### Task: Auth Lambda implementation

- Purpose: 간편 로그인, 현재 사용자 조회, stateless logout 응답을 담당하는 Auth Lambda를 구현한다.
- Scope: `src/auth/**`와 필요한 `src/shared/auth/**`만 수정한다. small-city 구현과 SAM 템플릿은 별도 Task가 소유한다.
- Dependencies: SAM API Gateway and authorizer planning.
- Context Budget: Must Read Before Implementation: 이 Spec, Auth Task 지시서, auth route contract. Target Files: `src/auth/**`, `src/shared/auth/**`. Out of Scope: `src/small_cities/**`, DynamoDB repository, frontend files.
- Acceptance Criteria: 로그인은 성공 시 짧은 만료의 토큰과 최소 사용자 정보를 반환하고, 실패 시 JSON 오류를 반환한다. `me`는 유효한 사용자 컨텍스트를 반환한다. logout은 stateless 성공 응답을 반환한다.
- Verification: auth handler unit tests, token utility tests, representative API Gateway event tests를 실행한다.

### Task: Custom Lambda authorizer implementation

- Purpose: 보호 라우트 진입 전에 bearer token을 검증하는 API Gateway authorizer를 구현한다.
- Scope: `src/auth/authorizer.py` 또는 승인된 authorizer 파일과 `src/shared/auth/**` 검증 함수만 수정한다.
- Dependencies: Auth Lambda implementation token utility boundary.
- Context Budget: Required Context: 이 Spec의 Auth Token Requirements와 API Gateway Requirements. Target Files: authorizer 파일과 shared auth utility. Out of Scope: login handler behavior, small-city Lambda, DynamoDB.
- Acceptance Criteria: 누락/형식 오류/만료/서명 불일치 토큰을 거부하고, 유효 토큰은 user context를 반환한다.
- Verification: authorizer event unit tests와 실패 케이스 tests를 실행한다.

### Task: SAM route, environment, and IAM implementation

- Purpose: Auth Lambda와 authorizer를 API Gateway에 연결하고 필요한 환경 변수와 권한을 선언한다.
- Scope: `template.yaml`만 수정한다. 필요 시 승인된 SAM event sample 파일을 별도 범위로 추가한다.
- Dependencies: Auth Lambda and authorizer handler names agreed.
- Context Budget: Must Read Before Implementation: 이 Spec, `template.yaml`, handler export names. Target Files: `template.yaml`. Out of Scope: Python auth logic, small-city business logic, frontend code.
- Acceptance Criteria: `/api/auth/login`, `/api/auth/me`, `/api/auth/logout` 경로가 정의되고, 보호 라우트에 authorizer가 적용되며, CORS에 `Authorization`이 포함되고, Auth Lambdas에는 불필요한 DynamoDB 권한이 없다.
- Verification: `sam validate`를 실행하고, 템플릿에서 public/protected route 적용 여부를 리뷰한다.

### Task: Small-city public route compatibility review

- Purpose: 기존 작은 도시 API 계약을 유지하면서 auth 추가가 읽기 API를 깨지 않도록 확인한다.
- Scope: `GET /api/small-cities`, `GET /api/small-cities/{cityId}`의 공개 접근, query parameter, response shape, DynamoDB read-only 권한을 검토한다.
- Dependencies: SAM route implementation.
- Context Budget: Must Read Before Review: 이 Spec, `LOVV_SMALL_CITY_API_CONTRACT.md`, `src/small_cities/app.py`, `src/small_cities/service.py`, `src/small_cities/dynamodb_repository.py`, `template.yaml`. Out of Scope: auth token implementation 세부 변경.
- Acceptance Criteria: 작은 도시 API는 인증 없이 호출 가능하고 기존 계약과 오류 형태를 유지한다.
- Verification: existing small-city tests 또는 representative handler event tests를 실행하고, 계약 변경 없음(diff)을 확인한다.

### Task: Integrated Backend Auth/API review

- Purpose: 병렬 구현 결과를 통합 관점에서 검토하고 보안/계약/라우팅 충돌을 차단한다.
- Scope: 모든 변경 파일을 읽기 전용으로 검토한다.
- Dependencies: Auth Lambda, authorizer, SAM route/IAM, small-city compatibility work complete.
- Context Budget: Must Read Before Review: 이 Spec, changed-file list, verification output summaries. Conditional: 실패 로그의 관련 부분만 읽는다.
- Acceptance Criteria: Blocker가 없고, 작은 도시 API 보존, MVP auth 경계, secret safety, IAM 최소 권한, CORS, 테스트 결과가 확인된다.
- Verification: Review Agent checklist, `sam validate` 결과, auth/small-city test 결과를 확인한다.

## Verification

This Spec task verification:

- Confirm only this Spec file was created or changed.
- Confirm no source code, tests, README, template, events, or git state were modified.
- Confirm the Spec includes all required sections and route decisions.
- Confirm the Spec preserves the existing small-city API contract.

Future implementation verification:

- `sam validate`
- Auth Lambda unit tests.
- Custom authorizer unit tests.
- Representative API Gateway event tests for:
  - successful login
  - failed login
  - valid `GET /api/auth/me`
  - missing token
  - expired token
  - invalid token signature
  - stateless logout
  - public `GET /api/small-cities`
  - public `GET /api/small-cities/{cityId}`
- Contract review against `LOVV_SMALL_CITY_API_CONTRACT.md`.
- Security review for secret handling, token expiration, authorization bypass, CORS, and IAM scope.
