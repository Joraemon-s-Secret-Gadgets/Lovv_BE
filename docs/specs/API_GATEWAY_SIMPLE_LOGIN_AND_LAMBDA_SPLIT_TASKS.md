# API Gateway Simple Login and Lambda Split Tasks

## Source Of Truth

- Full Spec: `docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`
- Existing API Contract: `/Users/jeonjonghyeok/Documents/Final/docs/specs/LOVV_SMALL_CITY_API_CONTRACT.md`
- Current Backend: `template.yaml`, `src/small_cities/**`, `tests/test_small_city_*.py`

## Parallel Scope Ownership

| Agent | Role | Task/Subtask | Write Scope | Read Scope | Forbidden Scope | Verification | Output |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Backend Auth Implementation Agent | Implementation Agent | Auth handlers, token utilities, authorizer, auth tests | `src/auth/**`, `src/shared/auth.py`, `src/shared/http.py`, `src/shared/__init__.py`, `tests/test_auth_*.py` | Full Spec, this task file, current small-city handler tests for style | `template.yaml`, `src/small_cities/**`, small-city tests | `python3 -m unittest tests.test_auth_app tests.test_auth_authorizer` | Auth implementation report |
| Backend SAM Implementation Agent | Implementation Agent | API Gateway routes, Lambda resources, authorizer config, CORS, env vars, sample events | `template.yaml`, `events/auth-*.json` | Full Spec, this task file, auth handler contract names | Python source and tests | `sam validate --lint`, `sam build` if possible | SAM/template report |
| Backend Small-City Compatibility Review Agent | Review Agent | Verify small-city API remains public and contract-compatible | Read-only | Full Spec, small-city contract, `src/small_cities/**`, `template.yaml`, small-city tests | File edits | `python3 -m unittest tests.test_small_city_mapper tests.test_small_city_handler` | Compatibility findings |
| Main Codex Coordinator | Main Codex | Integrate outputs, resolve conflicts, final verification | Any required integration fix inside `Lovv_BE` after agent outputs | All changed files and reports | Commits/push/deploy unless user asks | Full test/SAM validation suite | Final integration report |

Rules:

- `template.yaml` has exactly one writer: Backend SAM Implementation Agent.
- `src/shared/auth.py` has exactly one writer: Backend Auth Implementation Agent.
- `src/small_cities/**` must not be modified during auth implementation unless Main Codex explicitly handles a final integration fix.
- Review agents are read-only.
- No agent may commit, push, pull, merge, or rebase.

## Handler Contract For Parallel Work

The implementation agents must use these stable handler names:

- Auth API handler: `auth.app.lambda_handler`
- Lambda authorizer handler: `auth.authorizer.lambda_handler`
- Existing small-city handler: `small_cities.app.lambda_handler`

Auth routes:

- `POST /api/auth/login`: public
- `GET /api/auth/me`: protected by `LovvTokenAuthorizer`
- `POST /api/auth/logout`: public and stateless

Small-city routes remain public:

- `GET /api/small-cities`
- `GET /api/small-cities/{cityId}`

## Subtask 1: Auth Handlers And Token Utilities

- Purpose: MVP 간편 로그인 토큰 발급, 현재 사용자 조회, stateless logout, authorizer 검증 로직을 Python 코드와 테스트로 구현한다.
- Required Context:
  - Full Spec의 `# Requirements`, `# Auth Token Requirements`, `# Lambda Split Requirements`, `# Acceptance Criteria`.
  - 이 문서의 `Handler Contract For Parallel Work`.
- Context Budget:
  - Must read: `docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`, this task file.
  - Do not read: frontend files, generated `.aws-sam/**`, unrelated docs.
  - Optional read: `tests/test_small_city_handler.py` for Lambda event test style only.
- Source of Truth:
  - Full Spec: `docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`
- Required Sections:
  - `## Requirements`
  - `### Auth Token Requirements`
  - `### Lambda Split Requirements`
  - `## Acceptance Criteria`
- Must Read Before Implementation:
  - Same as Required Sections.
- Target Files:
  - `src/auth/__init__.py`
  - `src/auth/app.py`
  - `src/auth/authorizer.py`
  - `src/shared/__init__.py`
  - `src/shared/auth.py`
  - `src/shared/http.py`
  - `tests/test_auth_app.py`
  - `tests/test_auth_authorizer.py`
- Out of Scope:
  - `template.yaml`
  - `src/small_cities/**`
  - DynamoDB repository logic
  - production identity provider integration
  - server-side token revocation store
- Acceptance Criteria:
  - `POST /api/auth/login` accepts JSON body with a demo login code when `DEMO_LOGIN_CODE` is set, or accepts demo login without password when it is empty or unset.
  - Successful login returns `access_token`, `token_type: "Bearer"`, `expires_in`, and `user`.
  - Failed login returns JSON error with stable code and no secret leakage.
  - `GET /api/auth/me` returns user context from authorizer claims when present, or validates a bearer token when called directly in tests.
  - `POST /api/auth/logout` returns stateless success.
  - Token utility verifies signature, expiration, issuer, and audience.
  - Authorizer returns HTTP API simple response shape with `isAuthorized`.
- Verification:
  - `python3 -m unittest tests.test_auth_app tests.test_auth_authorizer`

## Subtask 2: SAM API Gateway Route And Authorizer Wiring

- Purpose: Auth Lambda, custom Lambda authorizer, protected route, public routes, CORS, environment variables, and IAM boundaries를 SAM 템플릿에 연결한다.
- Required Context:
  - Full Spec의 `### API Gateway Requirements`, `### Environment Variable Requirements`, `### IAM Requirements`.
  - 이 문서의 `Handler Contract For Parallel Work`.
- Context Budget:
  - Must read: `docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`, this task file, `template.yaml`.
  - Do not read: Python source internals except handler names in this task file.
  - Optional read: SAM CLI validation output.
- Source of Truth:
  - Full Spec: `docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`
- Required Sections:
  - `### API Gateway Requirements`
  - `### Environment Variable Requirements`
  - `### IAM Requirements`
- Must Read Before Implementation:
  - Same as Required Sections.
- Target Files:
  - `template.yaml`
  - `events/auth-login.json`
  - `events/auth-me.json`
  - `events/auth-logout.json`
- Out of Scope:
  - Python source files
  - Unit tests
  - small-city business logic
  - frontend integration
- Acceptance Criteria:
  - `AuthFunction` exists with handler `auth.app.lambda_handler`.
  - `AuthAuthorizerFunction` exists with handler `auth.authorizer.lambda_handler`.
  - `LovvHttpApi` CORS allows `Authorization`, `Content-Type`, `GET`, `POST`, and `OPTIONS`.
  - `POST /api/auth/login` is public.
  - `GET /api/auth/me` uses `LovvTokenAuthorizer`.
  - `POST /api/auth/logout` is public/stateless.
  - Existing small-city routes remain public and keep current paths.
  - Auth functions do not receive DynamoDB permissions.
  - Template uses dummy/default-safe environment variable names only.
- Verification:
  - `sam validate --lint`
  - `sam build`

## Subtask 3: Small-City Compatibility Review

- Purpose: Auth/SAM 변경 후 기존 작은 도시 API 계약과 공개 접근이 깨지지 않았는지 검토한다.
- Required Context:
  - Full Spec의 public small-city route decision.
  - Existing API Contract.
- Context Budget:
  - Must read: `docs/specs/API_GATEWAY_SIMPLE_LOGIN_AND_LAMBDA_SPLIT_SPEC.md`, `/Users/jeonjonghyeok/Documents/Final/docs/specs/LOVV_SMALL_CITY_API_CONTRACT.md`, `src/small_cities/**`, `template.yaml`, small-city tests.
  - Do not read: unrelated frontend or data pipeline files.
  - Optional read: final SAM validation output.
- Source of Truth:
  - Full Spec and existing small-city API contract.
- Required Sections:
  - Full Spec `### Small-City API Flow`
  - Full Spec `### Public vs Protected Route Decision`
  - Small-city contract `## Endpoints`, `## List Response`, `## City Record`
- Must Read Before Review:
  - Same as Required Sections.
- Target Files:
  - Read-only review.
- Out of Scope:
  - File edits.
- Acceptance Criteria:
  - `GET /api/small-cities` and `GET /api/small-cities/{cityId}` remain public.
  - Response and query contract remains compatible.
  - Small-city tests still pass.
- Verification:
  - `python3 -m unittest tests.test_small_city_mapper tests.test_small_city_handler`

## Subtask 4: Integrated Backend Auth/API Review

- Purpose: 병렬 구현 결과를 하나의 백엔드 변경으로 검토하고 보안, IAM, CORS, 계약, 테스트 누락을 확인한다.
- Required Context:
  - Full Spec, this task file, changed-file list, verification outputs.
- Context Budget:
  - Must read: changed files only.
  - Do not read: generated `.aws-sam/**` except build template if a SAM validation failure references it.
  - Optional read: relevant failure logs only.
- Source of Truth:
  - Full Spec and this task file.
- Required Sections:
  - `## Acceptance Criteria`
  - `## Risks`
  - `## Parallel Implementation Ownership`
- Must Read Before Review:
  - Same as Required Sections.
- Target Files:
  - Read-only review unless Main Codex asks for a bounded fix.
- Out of Scope:
  - New feature implementation.
  - production identity provider integration.
- Acceptance Criteria:
  - No Blocker findings remain.
  - All required verification commands have passed or an explicit blocker is reported.
  - No real secrets or local environment files are introduced.
- Verification:
  - `python3 -m unittest discover -s tests`
  - `python3 -m compileall src tests`
  - `sam validate --lint`
  - `sam build`
