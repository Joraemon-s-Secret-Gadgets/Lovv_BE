# Admin Console Operations Runbook

운영자/관리자가 Lovv 관리자 콘솔(`/api/v1/admin/*`)을 운영하고 모니터링하기 위한 런북이다.
1차 PoC 세로축(제안 → 검토 → 승인 → 월간 후보/게시 → 반영 이력)과 운영 기능(공지·추천 정책,
감사 로그)을 포함한다.

## 1. 역할·권한

서버가 권한의 단일 진실 원천이다. 모든 라우트는 검증된 액세스 토큰에서 역할·범위를 다시 도출하며,
프론트의 탭/버튼 게이팅은 UX일 뿐이다. 자세한 권한 매트릭스는 `ADMIN_RBAC_SPEC.md`를 참고한다.

- `R-ADMIN`: 검토/승인/반려, 월간 후보 게시 상태 전이, 반영 잡 운영, 공지·정책 관리, 감사 로그 조회, 고위험 요청 생성/조회.
- `R-SUPER-ADMIN`: 고위험 변경 요청 생성/조회와 TOTP 재인증 후 승인·거절. 일반 운영 API의 `R-ADMIN` 권한은 자동 상속하지 않는다. 본인 요청 승인은 금지된다.
- `R-DATA-PROVIDER`: 데이터 제안 등록/조회(본인·조직 범위).
- `R-LOCAL-OPERATOR`: 담당 지역의 제안/월간 후보/반영 이력 조회.

## 2. 핵심 운영 흐름

1. 데이터 제공자가 제안을 등록한다(`POST /api/v1/admin/data-proposals`).
2. 관리자가 검토→승인/반려한다(`POST .../{id}/review|approve|reject`). 본인 제안은 검토할 수 없다.
3. 승인된 제안을 월간 후보로 승격한다(`POST /api/v1/admin/monthly-destinations`).
4. 후보를 게시 상태머신으로 운영한다(`schedule`/`publish`/`hide`/`expire`/`reject`).
5. 게시 시 4종 반영 잡(catalog/RAG/검색/추천)이 자동 enqueue된다. 운영자는 잡을
   `start`/`succeed`/`fail`/`retry`/`cancel`로 진행한다(`POST /api/v1/admin/publish-jobs/{jobId}/{action}`).
6. 후보별 반영 이력은 `GET /api/v1/admin/monthly-destinations/{id}/publish-jobs`로 확인한다.

### 2.1 관리자 MFA 운영 흐름

MFA는 관리자 콘솔 전체의 전역 게이트가 아니다. 일반 관리자 읽기·목록 API는 역할 인증만으로 접근하고,
고위험 요청 approve/reject 시점에만 최근 TOTP MFA를 요구한다.

1. 관리자는 `GET /api/v1/admin/security/mfa/status`로 등록 상태와 현재 세션 검증 상태를 확인한다.
2. 미등록 관리자는 `POST /api/v1/admin/security/mfa/enroll`로 TOTP secret/provisioning URI를 받고 인증 앱에 등록한다.
3. `POST /api/v1/admin/security/mfa/confirm`에 6자리 TOTP code를 제출해 credential을 활성화하고 recovery code를 1회 발급받는다.
4. 이후 고위험 결정을 하기 전 `POST /api/v1/admin/security/mfa/verify`로 현재 세션을 TOTP 검증 세션으로 만든다.
5. recovery code는 계정 복구용이다. `POST /api/v1/admin/security/mfa/recover`로 세션을 만들 수 있지만, 이 세션만으로는 고위험 approve/reject를 수행할 수 없다.

운영자가 확인해야 할 오류:

| Code | 의미 | 대응 |
| --- | --- | --- |
| `ADMIN_MFA_REQUIRED` | TOTP 세션이 없거나 5분 freshness가 지남 | 다시 `/security/mfa/verify` 수행 |
| `ADMIN_MFA_TOTP_REQUIRED` | recovery code 세션 등 TOTP가 아닌 세션으로 결정 시도 | 인증 앱 TOTP로 다시 verify |
| `ADMIN_MFA_ENROLLMENT_REQUIRED` | MFA credential 없음 | enroll/confirm부터 진행 |
| `ADMIN_MFA_LOCKED` | 실패 횟수 초과로 일시 잠김 | 잠금 만료 후 재시도, 필요 시 break-glass 절차 검토 |

### 2.2 고위험 변경 승인 흐름

고위험 변경은 요청 생성과 결정자를 분리한다.

1. `R-ADMIN` 또는 `R-SUPER-ADMIN`이 `POST /api/v1/admin/high-risk-requests`로 요청을 만든다.
2. 관리자 콘솔은 `GET /api/v1/admin/high-risk-requests?status=pending&limit=50`로 pending 목록을 조회한다. 이 목록 조회에는 MFA가 필요 없다.
3. 요청자와 다른 `R-SUPER-ADMIN`이 TOTP MFA를 verify한다.
4. 승인 시 `POST /api/v1/admin/high-risk-requests/{id}/approve`를 호출한다. body에는 선택적 `decisionReason`만 넣고 TOTP code는 넣지 않는다.
5. 거절 시 `POST /api/v1/admin/high-risk-requests/{id}/reject`를 호출한다. body에는 필수 `decisionReason`만 넣는다.

고위험 대상:

- `role_grant`
- `role_revoke`
- `region_grant`
- `region_revoke`
- `bulk_publish`

보호 규칙:

- 요청자는 자기 요청을 승인·거절할 수 없다.
- `R-ADMIN`은 요청 생성과 목록 조회는 가능하지만 승인·거절은 할 수 없다.
- 마지막 활성 `R-SUPER-ADMIN` 회수는 거부된다.
- 역할·지역 변경 성공 후 해당 사용자의 인가 캐시를 무효화한다.
- 고위험 성공 감사로그는 업무 변경과 같은 트랜잭션에 strict로 기록한다. strict 감사 기록이 실패하면 업무 변경도 롤백된다.

## 3. 공지·추천 정책

- 공지: `GET/POST /api/v1/admin/notices`, 전이 `publish`/`archive`.
- 추천 정책: `GET/POST /api/v1/admin/recommendation-policies`, 전이 `activate`/`archive`.
- 정책은 우선순위(priority)와 규칙(rules JSON)을 가지며, 추천 후보 정렬에 활용할 운영 파라미터다.

## 4. 감사 로그 (Audit Trail)

모든 관리자 변이는 `admin_audit_logs`에 append-only로 기록된다. 일반 관리자 동작의 감사 기록은
best-effort다. 고위험 변경의 성공 감사는 업무 변경과 동일 트랜잭션에서 strict로 기록되며, 감사
기록 실패 시 업무 변경도 롤백된다. 거부·실패 감사는 롤백된 트랜잭션 밖에서 별도로 기록한다.
별도 기록도 실패하면 `SECURITY_AUDIT_FALLBACK` 구조화 오류를 CloudWatch Logs에 남긴다.

기록되는 액션(action):

| 영역 | action |
| --- | --- |
| 제안 | `data_proposal.review` / `.approve` / `.reject` |
| 월간 후보 | `monthly_destination.schedule` / `.publish` / `.hide` / `.expire` / `.reject` |
| 반영 잡 | `publish_job.start` / `.succeed` / `.fail` / `.retry` / `.cancel` |
| 공지 | `notice.create` / `.publish` / `.archive` |
| 추천 정책 | `recommendation_policy.create` / `.activate` / `.archive` |
| 고위험 변경 | `high_risk_request.create` / `.approve` / `.reject`, `{operation}.execute` |
| 관리자 MFA | `admin_mfa.enroll` / `.confirm` / `.verify` / `.recover` |

각 항목은 행위자(actor)·역할/조직/지역 스냅샷·대상 리소스·결과(`succeeded`, `denied`, `failed`)·after 요약을 남긴다.
`monthly_destination.publish`는 metadata에 enqueue된 반영 잡 수(`reflectionJobCount`)를 기록한다.

조회: `GET /api/v1/admin/audit-logs` (R-ADMIN 전용). 필터 쿼리: `action`, `resourceType`,
`result`, `actorUserId`, `limit`(최대 50).

## 5. 모니터링

별도 모니터링 인프라를 두지 않고, 다음 두 가지를 1차 모니터링 표면으로 사용한다.

1. **감사 로그 조회 API/콘솔 탭** — 누가 무엇을 했고 결과가 무엇인지 추적.
2. **구조화 로그** — Lambda 핸들러는 `shared.logger`로 태그 기반 로그를 남긴다. 처리되지 않은
   예외는 `INTERNAL_ERROR`로 응답되며 `LOGGER.exception`으로 스택이 남는다(CloudWatch Logs).

운영 점검 포인트:

- 게시 후 반영 잡이 `failed`로 누적되면(반복 `publish_job.fail`) 다운스트림 동기화 연동을 점검한다.
- `data_proposal.reject`/`monthly_destination.reject` 급증은 데이터 품질 이슈 신호일 수 있다.
- `audit-logs`에서 예상치 못한 actor/역할의 변이가 보이면 권한 배정(역할/지역)을 재검토한다.

## 6. 데이터 모델 참조

- 제안/이력: `admin_data_proposals`, `admin_data_proposal_history`
- 월간 후보: `monthly_curated_destinations`
- 반영 잡: `admin_publish_jobs`
- 지표: `destination_metrics_daily`
- 공지/정책: `admin_notices`, `admin_recommendation_policies`
- 감사 로그: `admin_audit_logs`

스키마 정의는 `schema/aurora_mysql/002_admin_console_tables.sql`,
`schema/aurora_mysql/003_admin_operations_tables.sql`, 기존 DB 보강용
`schema/aurora_mysql/004_admin_high_risk_approvals.sql`을 참고한다.

## 7. 관리자 접근 재검토 (Access Attestation)

관리자 권한 누적을 방지하기 위해 활성 역할·지역 할당을 분기마다 재검토한다. 인사 이동, 계약 종료,
보안 사고 또는 고권한 오부여가 확인되면 정기 일정과 무관하게 즉시 재검토한다.

### 7.1 주기와 책임

- 정기 검토: 매 분기 첫 영업일부터 5영업일 이내 완료한다.
- 검토 대상: `user_role_assignments`, `user_region_assignments`의 활성 할당 전체와 최근 90일간 로그인하지 않은 관리자 계정이다.
- 1차 확인자: 해당 역할·지역의 업무 책임자다.
- 최종 확인자: 최초 부여자와 다른 보안·운영 책임자다. 본인 권한을 본인이 최종 승인할 수 없다.

### 7.2 판정과 회수

- 판정은 `유지`, `범위 축소`, `회수`, `추가 확인` 중 하나로 기록한다.
- `R-ADMIN`과 `R-SUPER-ADMIN`의 불필요 권한은 1영업일, 그 외 권한은 5영업일 이내 회수한다.
- 회수 시 할당 상태를 `revoked`로 변경하고 `valid_until`을 확정한 뒤, 권한 캐시와 활성 세션을 무효화한다.
- 다음 로그인에서 발급된 토큰의 역할·기관·지역 범위가 변경 결과와 일치하는지 확인한다.

### 7.3 증적

검토 기준일, 대상 사용자 ID, 역할·기관·지역, 최근 로그인 시각, 판정, 사유, 1차·최종 확인자,
처리 기한, 완료 시각, 변경 요청 ID를 보존한다. 액세스 토큰, 리프레시 쿠키, 소셜 제공자 토큰과
민감 원문은 증적에 포함하지 않는다. 역할·지역 변경 API가 제공되면 변경과 회수 결과를
`admin_audit_logs`에 각각 기록한다.

## 8. 운영 마이그레이션과 최초 Super Admin

기본 product 테이블의 단일 기준은 `infra/data-stack/rds/schema.sql`이다. `schema/aurora_mysql/001_product_api_tables.sql`은 더 이상 사용하지 않는다. 신규 로컬 DB는 base schema를 먼저 적용한 뒤 `002`, `003`, `004`를 순서대로 적용한다.

기존 운영·staging DB에는 base schema나 신규 설치용 `002`를 임의 재적용하지 않는다. 고위험 승인/MFA 보강이 필요하면 `004_admin_high_risk_approvals.sql`을 적용한다. `004`는 운영 DB의 실제 역할 CHECK 제약 이름과 식을 조회하며 재실행할 수 있다.

```powershell
python scripts/apply_admin_migration.py 004_admin_high_risk_approvals.sql
python scripts/apply_admin_migration.py 004_admin_high_risk_approvals.sql  # 재실행 검증
python scripts/verify_004.py
python scripts/verify_schema.py
```

실DB 통합 테스트는 opt-in이다. 아래 환경변수를 설정하지 않으면 일반 unittest에서 skip된다. 실제로 실행하지 않았다면 완료로 기록하지 않는다.

```powershell
$env:RUN_ADMIN_DB_INTEGRATION = "1"
python -m unittest tests.test_admin_migration tests.test_admin_high_risk_db_integration

$env:RUN_RDS_DATA_API_INTEGRATION = "1"
python -m unittest tests.test_admin_high_risk_db_integration.RdsDataApiLiveTransactionTests
```

staging에서는 적용 전 스냅샷과 변경 티켓을 확보하고 위 순서로 migration 검증·재실행·필요한 opt-in 통합 테스트를 완료한다. 최초 Super Admin은 정적 seed가 아니라 기존 활성 사용자에게 break-glass 절차로 부여한다.

```powershell
python scripts/bootstrap_super_admin.py --target-user-id <uuid> --operator <ticket-or-operator> --reason "<reason>"
python scripts/bootstrap_super_admin.py --target-user-id <uuid> --operator <ticket-or-operator> --reason "<reason>" --execute
```

첫 명령은 DB를 변경하지 않는다. 실행 명령은 활성 Super Admin이 0명일 때만 역할과 strict 감사로그를
같은 트랜잭션으로 기록하며, 동일 대상에 대한 재실행은 no-op이다.

부트스트랩 후 확인:

```powershell
python scripts/verify_bootstrap.py --target-user-id <uuid>
python scripts/list_user_authz.py --user-id <uuid>
```

인가 캐시 무효화가 실제 DynamoDB에서 동작하는지 확인해야 하면 다음 검증은 별도로 실행한다.

```powershell
python scripts/verify_authz_cache.py
```

이 검증은 live DynamoDB 권한이 필요하므로 일반 로컬 unittest 완료와 구분해 기록한다.

## 9. 테스트와 검증 기록

문서·코드 변경 후 최소 BE 검증:

```powershell
$env:PYTHONPATH='src'
python -m unittest
python -m unittest tests.test_admin_high_risk_app
python -m unittest tests.test_admin_mfa_app.AdminMfaAppTest.test_admin_read_routes_need_role_only_and_mfa_status_is_accessible
```

로컬 DB 초기화 문서나 compose 설정을 바꾼 경우:

```powershell
docker compose config
git diff --check
```

`docker compose config`가 Docker 사용자 config 접근 경고를 출력해도 compose 설정이 정상 출력되면 YAML 파싱은 성공한 것이다. 단, 실제 컨테이너 초기화 검증은 별도로 `docker compose down -v && docker compose up -d` 후 `SHOW TABLES` 또는 `scripts/verify_schema.py`로 확인한다.
