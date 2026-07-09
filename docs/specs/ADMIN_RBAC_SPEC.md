# Lovv Admin RBAC Spec

## 1. 목적

이 문서는 Lovv 관리자 콘솔의 인증·인가 경계를 확정한다. 대상 역할은 서비스 관리자, 공공 데이터 제공자, 지역 관광 운영자이며, 관리자 API 구현 전에 역할별 접근 범위, 담당 지역 제한, 토큰 클레임, 거부 규칙과 감사 요건을 고정한다.

현재 관리자 프론트는 다음 역할을 Mock Session으로 전환해 기능을 시연한다.

- `R-ADMIN`
- `R-SUPER-ADMIN`
- `R-DATA-PROVIDER`
- `R-LOCAL-OPERATOR`

일반 로그인 사용자의 기본 역할은 `R-USER`이며, 관리자 역할은 서비스 DB의 활성 역할 할당 또는 검증된 관리자 세션 클레임으로만 부여한다. 프론트의 탭/버튼 게이팅은 UX 보조 수단이며, API 권한 판단은 서버가 최종 수행한다.

## 2. 핵심 결정

| 항목 | 결정 |
| --- | --- |
| 인증 제공자 | 기존 Lovv 서비스 세션과 Cognito 로그인을 유지한다. |
| 역할 Source of Truth | Lovv 서비스 DB의 활성 역할 할당을 최종 권한 기준으로 사용한다. |
| Cognito Group | 최초 역할 연결과 운영 편의를 위한 입력으로만 사용하고, 단독 권한 기준으로 신뢰하지 않는다. |
| API 권한 검증 | API Gateway 인증 후 각 관리자 핸들러에서 역할과 리소스 범위를 다시 검증한다. |
| 지역 범위 | `R-LOCAL-OPERATOR`는 활성 `region assignment`가 있는 지역만 조회한다. |
| 제공자 범위 | `R-DATA-PROVIDER`는 본인 또는 소속 기관의 제안만 조회·수정한다. |
| 관리자 범위 | `R-ADMIN`은 전체 제안 검토, 반영 상태, 전역 운영 지표를 조회·처리한다. |
| 월간 여행지 운영 | 데이터 제안 승인과 월간 여행지 게시를 분리한다. 승인된 데이터도 별도 게시 결정 전에는 `이번 달 여행지`로 노출하지 않는다. |
| 공익/제휴 지표 분리 | 공식 정보 이동과 제휴 링크 이동은 화면, 이벤트, 리포트에서 분리한다. B2G 리포트에는 예약액, 수수료, GMV를 포함하지 않는다. |
| 역할 상속 | 역할은 서로 자동 상속하지 않는다. 권한은 역할별 허용 작업의 합집합으로 계산한다. |
| 고위험 변경 | 역할·지역 할당 변경과 대량 게시는 고위험 요청으로 만들고, 요청자와 다른 `R-SUPER-ADMIN`이 결정한다. |
| 관리자 MFA | 일반 관리자 읽기/목록 경로에는 MFA를 요구하지 않는다. MFA는 고위험 approve/reject 시점에만 요구한다. |
| 기본 역할 | 일반 로그인 사용자는 `R-USER`만 가진다. 관리자 역할은 명시적으로 할당해야 한다. |
| 프론트 신뢰 | 요청 본문의 `roles`, `regionIds`, `organizationId`, `reviewerId` 등 소유권·권한 필드는 신뢰하지 않는다. |
| 실패 원칙 | 역할 또는 범위를 확인할 수 없으면 fail-closed로 거부한다. |

## 3. 역할 정의

### 3.1 `R-USER`

일반 여행 사용자 역할이다.

- 일반 여행 서비스 API를 사용한다.
- 관리자 콘솔과 `/api/v1/admin/*` API를 사용할 수 없다.
- 관리자 역할이 추가되어도 일반 사용자 기능을 유지할 수 있다.

### 3.2 `R-DATA-PROVIDER`

공공 데이터 제공 기관 또는 승인된 데이터 제공자 역할이다.

- 관광지, 축제, 체험 데이터 제안을 작성한다.
- 본인 또는 본인이 속한 기관이 제출한 제안 목록과 처리 결과를 조회한다.
- `draft`, `change_requested` 상태의 허용 필드를 수정하고 다시 제출한다.
- 다른 기관의 제안, 내부 검토 메모, 전체 운영 지표는 조회할 수 없다.
- 제안을 직접 승인, 반려, 게시 또는 추천 인덱스에 반영할 수 없다.

### 3.3 `R-LOCAL-OPERATOR`

지자체·관광 운영자 역할이다.

- 자신에게 할당된 지역의 관광 자원 현황과 운영 지표를 조회한다.
- 담당 지역의 제안·승인 현황을 집계 수준에서 조회한다.
- 담당 지역의 데이터 품질 경고와 공개 가능한 피드백 요약을 조회한다.
- 할당되지 않은 지역의 원시 이벤트, 사용자 식별 정보와 제안 내부 검토 내용은 조회할 수 없다.
- PoC 1차 범위에서는 직접 제안을 작성하거나 검토 결정을 내리지 않는다.

### 3.4 `R-ADMIN`

Lovv 내부 서비스 관리자 역할이다.

- 전체 운영 요약과 지역별 운영 지표를 조회한다.
- 모든 데이터 제안과 근거 자료를 검토한다.
- 승인, 수정 요청, 반려 결정을 내린다.
- 승인된 데이터의 게시·인덱스 반영 상태를 확인하고 실패 작업을 재시도한다.
- 공지와 추천 정책 관리는 후속 API가 추가되면 `R-ADMIN`에만 허용한다.
- 역할·지역 할당 변경과 대량 게시 같은 고위험 변경 요청을 생성할 수 있다.
- 고위험 요청을 직접 승인하거나 거절할 수 없다.
- 데이터 제안 작성 권한은 자동으로 포함하지 않는다. 관리자가 제안도 작성해야 하면 `R-DATA-PROVIDER`를 함께 할당한다.

### 3.5 `R-SUPER-ADMIN`

고위험 변경 결정자 역할이다.

- MFA 상태/등록 API, 관리자 사용자 조회, 고위험 요청 조회·생성처럼 `R-ADMIN` 또는 `R-SUPER-ADMIN`을 허용하는 공통 관리자 API에 접근할 수 있다.
- 제안 검토, 월간 여행지 운영, 반영 잡 전이, 공지·추천 정책 관리, 감사 로그 조회처럼 `R-ADMIN`을 직접 요구하는 일반 운영 API 권한은 자동 상속하지 않는다.
- 고위험 변경 요청을 생성할 수 있다.
- 본인이 요청하지 않은 고위험 변경 요청을 승인·거절할 수 있다.
- 승인·거절 시점에는 최근 5분 이내 TOTP MFA 세션이 필요하다.
- recovery code는 TOTP 재등록용 1회 복구 키이며, recovery code로 생성된 MFA 세션만으로는 고위험 요청을 결정할 수 없다.
- 마지막 활성 `R-SUPER-ADMIN` 회수 요청은 승인할 수 없다.

## 4. 권한 매트릭스

`Own`은 본인 또는 본인 소속 기관 소유 리소스, `Assigned`는 할당된 지역, `All`은 전역 범위를 의미한다.

| 작업 | R-USER | R-DATA-PROVIDER | R-LOCAL-OPERATOR | R-ADMIN | R-SUPER-ADMIN |
| --- | --- | --- | --- | --- | --- |
| 관리자 콘솔 세션 확인 | 거부 | 허용 | 허용 | 허용 | 허용 |
| 데이터 제안 작성 | 거부 | 허용 | 거부 | 거부 | 거부 |
| 제안 조회 | 거부 | Own | Assigned 집계만 | All | 거부 |
| 제안 수정·재제출 | 거부 | Own | 거부 | 거부 | 거부 |
| 제안 상세 근거 조회 | 거부 | Own | 거부 | All | 거부 |
| 승인·수정 요청·반려 | 거부 | 거부 | 거부 | All | 거부 |
| 처리 이력 조회 | 거부 | Own 공개 이력 | Assigned 집계만 | All | 거부 |
| 운영 지표 조회 | 거부 | 거부 | Assigned | All | 거부 |
| 월간 여행지 후보·게시 상태 조회 | 거부 | 본인 제안의 공개 상태 | Assigned 요약 | All | 거부 |
| 월간 여행지 게시·비노출·만료 처리 | 거부 | 거부 | 거부 | All | 거부 |
| 게시 작업 상태 조회 | 거부 | 본인 제안의 공개 상태 | Assigned 요약 | All | 거부 |
| 게시 작업 재시도 | 거부 | 거부 | 거부 | All | 거부 |
| 공지·추천 정책 변경 | 거부 | 거부 | 거부 | All | 거부 |
| 고위험 요청 목록 조회 | 거부 | 거부 | 거부 | All | All |
| 고위험 요청 생성 | 거부 | 거부 | 거부 | 허용 | 허용 |
| 고위험 요청 승인·거절 | 거부 | 거부 | 거부 | 거부 | 허용(TOTP MFA 필요) |

## 4.1 월간 여행지 운영 리소스

B2G 공익 협력의 핵심 운영 단위는 단순 데이터 레코드가 아니라 `이번 달 여행지` 월간 큐레이션이다. 따라서 데이터 제안과 월간 노출 리소스는 분리한다.

논리 모델:

#### `monthly_curated_destinations`

| 필드 | 설명 |
| --- | --- |
| `id` | 월간 여행지 운영 ID |
| `city_id` | 추천 대상 소도시 ID |
| `region_id` | 지역 운영·지표 귀속 기준 |
| `source_proposal_id` | 근거가 되는 승인 제안 ID, nullable |
| `curation_month` | 노출 기준 월 |
| `theme_codes` | 월간·테마별 노출 기준 |
| `official_source_url` | 공식 정보 확인 링크 |
| `official_source_name` | 기관명 또는 공식 출처 |
| `source_updated_at` | 공식 정보 최종 확인일 |
| `valid_from`, `valid_until` | 게시 유효 기간 |
| `status` | `candidate`, `scheduled`, `published`, `hidden`, `expired`, `rejected` |
| `published_by` | 게시 처리자 ID |
| `published_at` | 게시 시각 |
| `created_at`, `updated_at` | 변경 시각 |

규칙:

- 데이터 제안이 `approved` 상태가 되어도 자동으로 월간 여행지에 게시하지 않는다.
- `R-ADMIN`만 월간 여행지 후보를 게시, 비노출, 만료 처리할 수 있다.
- `R-LOCAL-OPERATOR`는 담당 지역의 후보·게시 상태와 집계 성과만 조회한다.
- `R-DATA-PROVIDER`는 본인 또는 소속 기관 제안이 월간 여행지에 반영되었는지 공개 가능한 상태만 조회한다.
- 유효기간이 지난 콘텐츠는 자동 추천과 일정 생성에서 제외되어야 한다.
- 축제 취소, 휴장, 교통 중단, 안전 관련 변경은 정기 갱신 주기를 기다리지 않고 비노출 또는 재검수 상태로 전환한다.

### 4.2 공식 링크와 제휴 링크 분리

B2G 공익 협력 리포트와 B2B 제휴 성과는 같은 사용자 여정 안에 있어도 분리해서 기록·표시한다.

규칙:

- 공식 정보 이동 이벤트는 `official_link_clicked`로 기록한다.
- 제휴·예약·검색 링크 이동 이벤트는 `partner_link_clicked`로 기록한다.
- B2G 리포트에는 노출, 상세 클릭, 일정 생성, 저장, 공유, 교통 확인, 공식 정보 이동과 선택적 방문 의향·방문 확인만 포함한다.
- B2G 리포트에는 예약액, 수수료, 승인 GMV, 제휴 매출과 같은 재정 지표를 포함하지 않는다.
- 제휴 링크 클릭은 사용자 행동 경로를 이해하기 위한 보조 지표로만 노출할 수 있으며, 공익 성과의 핵심 전환율 분자에 합산하지 않는다.
- 목적지 선정, 추천 순위, 월간 노출 여부에 제휴 수수료나 파트너 비용 지불 여부를 반영하지 않는다.
- 화면에서는 공공기관 제공 정보, Lovv 추천, 공식 링크, 제휴·예약 링크를 사용자가 구분할 수 있게 표시한다.

### 4.3 단일 소도시와 관문도시 분리 검수

관리자 검수는 콘텐츠 사실 확인뿐 아니라 Lovv의 단일 소도시 추천 원칙을 확인해야 한다.

규칙:

- 추천 요청 1건의 최종 목적지는 소도시 1곳이어야 한다.
- 관광지, 축제, 체험, 숙소는 원칙적으로 추천 소도시의 서비스 범위 안에 있어야 한다.
- 공항, 역, 대도시 관문은 접근 안내에만 사용하고 추천 소도시의 일정 구성이나 성과 귀속에 포함하지 않는다.
- 관문도시의 클릭, 숙박, 예약, 방문 행동은 추천 소도시 성과로 집계하지 않는다.
- 행정경계를 넘어선 관광권을 하나의 목적지로 운영하려면 포함 지역, 서비스 경계, 성과 귀속 기준을 게시 전에 기록해야 한다.
- 적합한 소도시를 확정할 수 없으면 여러 도시를 섞어 승인하지 않고 추가 정보 요청 또는 추천 보류로 처리한다.

### 4.4 지역 운영자 지표 노출 원칙

`R-LOCAL-OPERATOR`와 기관 공유 리포트는 익명·집계 데이터만 제공한다.

규칙:

- 개인 사용자 이벤트, 원시 로그, 세션 단위 행동 경로, 사용자 식별 정보는 지역 운영자에게 제공하지 않는다.
- 최소 집단 크기 미만의 통계는 숨김, 병합 또는 기간 확장 처리한다.
- 기관 공유 리포트는 담당 지역 기준으로만 생성한다.
- 공식 링크 행동과 제휴 링크 행동은 리포트 필드에서 분리한다.
- 방문 여부는 선택적 피드백, 캠페인 QR, 기관의 비식별 집계처럼 확인 가능한 근거가 있을 때만 별도 표시한다.
- 개인 위치 이력이나 민감정보를 방문 확인 목적으로 수집하거나 기관에 제공하지 않는다.

## 5. 권한 Source of Truth

### 5.1 서비스 DB

최종 권한은 아래 논리 모델에서 조회한다. 물리 스키마와 마이그레이션은 후속 DB Task에서 작성한다.

#### `user_role_assignments`

| 필드 | 설명 |
| --- | --- |
| `id` | 역할 할당 ID |
| `user_id` | Lovv `users.id` |
| `role_code` | 허용된 역할 코드 |
| `organization_id` | 제공자 또는 운영자 소속 기관, nullable |
| `status` | `active`, `suspended`, `revoked` |
| `valid_from` | 효력 시작 시각 |
| `valid_until` | 효력 종료 시각, nullable |
| `granted_by` | 역할을 부여한 운영자 ID |
| `created_at`, `updated_at` | 변경 시각 |

제약:

- 활성 역할 조회 시 `status`, `valid_from`, `valid_until`을 모두 검사한다.
- 동일 사용자·역할·기관의 중복 활성 할당을 방지한다.
- `R-USER`는 기본 역할이며 별도 행 없이도 부여할 수 있다.
- 관리자 역할은 소셜 로그인이나 이메일 도메인만으로 자동 부여하지 않는다.

#### `user_region_assignments`

| 필드 | 설명 |
| --- | --- |
| `id` | 지역 할당 ID |
| `user_id` | Lovv `users.id` |
| `region_id` | 서비스 표준 지역 ID |
| `organization_id` | 담당 기관 ID, nullable |
| `status` | `active`, `suspended`, `revoked` |
| `valid_from`, `valid_until` | 효력 기간 |
| `granted_by` | 할당 처리자 ID |
| `created_at`, `updated_at` | 변경 시각 |

제약:

- 지역명 문자열이 아니라 서비스 표준 `region_id`를 사용한다.
- `R-LOCAL-OPERATOR`의 지역 조회 범위는 이 테이블의 활성 행과 서버 측 쿼리 조건으로 제한한다.
- 클라이언트가 요청한 `regionId`가 할당 범위 밖이면 빈 결과로 위장하지 않고 `403 REGION_SCOPE_FORBIDDEN`을 반환한다.

### 5.2 Cognito Group 매핑

현재 구현은 Cognito Group 이름만으로 서비스 역할을 발급하지 않는다. 서비스 DB의 활성 역할 할당과 검증된 세션 역할을 기준으로 권한을 판정한다. Cognito Group 연동을 추가하려면 그룹 이름, bridge 매핑, DB 교차 확인 규칙을 함께 확정해야 한다.

규칙:

- Cognito Group은 로그인한 외부 주체와 사전 등록된 관리자 후보를 연결하는 신호다.
- 실제 서비스 JWT 발급 시 DB의 활성 할당과 교차 확인한다.
- Cognito Group에 있지만 DB 할당이 없거나 정지 상태라면 관리자 역할을 발급하지 않는다.
- DB에 활성 할당이 있지만 Cognito Group이 제거된 경우에도 다음 로그인·세션 갱신에서는 관리자 역할을 발급하지 않는다.
- 긴급 권한 회수를 위해 DB 할당을 정지하면 신규 토큰 발급이 즉시 차단되어야 한다.
- 기존에 발급된 access token은 최대 15분 TTL까지 유효할 수 있다. 즉시 회수가 필요하면 후속 active-session 검증 또는 denylist가 필요하다.

## 6. 세션과 토큰 클레임

서비스 access token의 최소 클레임은 다음과 같다.

```json
{
  "sub": "lovv-user-uuid",
  "sid": "service-session-id",
  "roles": ["R-USER", "R-LOCAL-OPERATOR"],
  "organization_ids": ["org-gangneung-tourism"],
  "region_ids": ["KR-42-150"],
  "provider": "cognito",
  "iat": 1782115200,
  "exp": 1782116100,
  "iss": "lovv-auth",
  "aud": "lovv-api",
  "jti": "unique-token-id",
  "authz_version": 1
}
```

규칙:

- `sub`는 Cognito subject가 아니라 Lovv 서비스 `users.id`다.
- `roles`, `organization_ids`, `region_ids`는 서버가 DB 할당으로 계산한다.
- 배열은 중복 제거하고 정렬해 발급한다.
- 유효한 관리자 역할이 없으면 `roles`는 `R-USER`만 포함한다.
- `authz_version`은 역할·범위 모델 변경 시 토큰 호환성을 판단하기 위한 정수 버전이다.
- 클라이언트는 클레임으로 UI를 숨길 수 있지만 API 허가 판단의 최종 주체가 아니다.
- 지역 할당이 매우 많아 토큰 크기 문제가 생기면 `region_ids`를 제거하고 요청마다 DB에서 조회하는 방식으로 전환한다. PoC에서는 소수 지역 할당을 전제로 토큰에 포함할 수 있다.

### 세션 발급·갱신 흐름

1. Cognito 또는 기존 제공자 인증으로 사용자를 식별한다.
2. Lovv `users.id`를 조회·생성한다.
3. 서비스 DB에서 활성 역할, 기관, 지역 할당을 조회한다.
4. Cognito 로그인인 경우 허용된 Group과 DB 할당을 교차 확인한다.
5. 계산된 권한으로 서비스 access token을 발급한다.
6. `/auth/me`와 `/auth/session`은 같은 계산 결과를 `user.roles`, `organizationIds`, `regionIds`로 반환한다.
7. 세션 갱신 시 역할과 지역을 다시 조회해 변경된 권한을 새 토큰에 반영한다.

## 7. 관리자 API 인가 규칙

### 7.1 공통 처리 순서

모든 `/api/v1/admin/*` 요청은 다음 순서로 처리한다.

1. 서명, issuer, audience, expiration을 검증한다.
2. Lovv 서비스 `userId`와 세션을 확인한다.
3. 하나 이상의 관리자 역할이 있는지 확인한다.
4. 라우트에 필요한 역할을 확인한다.
5. 요청 리소스의 소유 기관 또는 지역 범위를 서버 데이터로 조회한다.
6. 역할과 범위가 일치하는 경우에만 데이터를 읽거나 변경한다.
7. 중요 조회와 모든 상태 변경을 감사 로그로 남긴다.

### 7.2 객체 단위 인가

- 제안 상세 조회 시 요청자의 `userId`나 `organizationId`를 요청 본문에서 받지 않는다.
- 제안 수정 시 DB의 `created_by`, `organization_id`, 현재 상태를 기준으로 소유권을 검사한다.
- 지역 지표 쿼리는 `user_region_assignments`와 교집합을 서버에서 구성한다.
- `R-ADMIN`만 제안 상태를 검토 상태로 전환할 수 있다.
- `R-ADMIN`만 월간 여행지의 `scheduled`, `published`, `hidden`, `expired` 상태를 변경할 수 있다.
- `R-ADMIN`만 공지·추천 정책과 반영 잡 상태를 변경하고 감사 로그를 조회할 수 있다.
- 승인·반려 요청의 `reviewerId`는 access token의 `sub`에서 설정한다.
- 권한 없는 리소스가 존재하는지 노출하면 보안상 문제가 되는 경우 `404 NOT_FOUND`를 사용할 수 있다. 단, 명시적인 지역 필터 위반처럼 클라이언트가 자신의 허용 범위를 알아야 하는 경우 `403`을 사용한다.

### 7.3 역할 조합

- 사용자는 여러 역할을 가질 수 있다.
- 권한은 활성 역할별 허용 작업의 합집합으로 계산한다.
- 범위 제한은 역할마다 따로 적용한다.
- 예: `R-DATA-PROVIDER`와 `R-LOCAL-OPERATOR`를 함께 가진 사용자는 본인 기관 제안을 작성하고 담당 지역 지표를 조회할 수 있지만, 제안을 승인할 수는 없다.
- `R-ADMIN`과 `R-DATA-PROVIDER`를 함께 가진 사용자가 본인 제안을 검토하는 것은 이해충돌 방지를 위해 거부한다.
- `R-ADMIN`과 `R-SUPER-ADMIN`을 함께 가진 사용자는 일반 관리자 API와 고위험 결정 API를 모두 사용할 수 있지만, 본인이 만든 고위험 요청은 직접 결정할 수 없다.

### 7.4 관리자 MFA API

관리자 MFA는 고위험 결정 전 본인 확인 수단이다. 일반 관리자 읽기/목록 경로의 전역 게이트로 사용하지 않는다.

| Method | Path | 권한 | MFA 필요 | 설명 |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/security/mfa/status` | 관리자 역할 | 불필요 | 등록 상태, 현재 세션 검증 상태, recovery code 잔여 개수 조회 |
| POST | `/api/v1/admin/security/mfa/enroll` | 관리자 역할 | 불필요 | TOTP secret과 provisioning URI 발급 |
| POST | `/api/v1/admin/security/mfa/confirm` | 관리자 역할 | TOTP code 제출 | pending credential 활성화, recovery code 발급, 현재 세션 검증 |
| POST | `/api/v1/admin/security/mfa/verify` | 관리자 역할 | TOTP code 제출 | 현재 세션을 TOTP 검증 세션으로 기록 |
| POST | `/api/v1/admin/security/mfa/recover` | 관리자 역할 | recoveryCode 제출 | recovery code 1개를 소모하고 복구 세션 기록 |
| POST | `/api/v1/admin/security/mfa/recovery/enroll` | 관리자 역할 | recovery 세션 | 새 TOTP secret과 provisioning URI 발급 |

규칙:

- TOTP code는 6자리 숫자만 허용한다.
- 이미 사용한 TOTP counter는 재사용할 수 없다.
- recovery code는 1회용이다.
- recovery code는 TOTP 재등록용이다. `/recover` 성공 후 같은 세션에서 `/recovery/enroll`로 새 TOTP secret을 발급받고 `/confirm`으로 새 TOTP code를 확정한다.
- 5회 연속 실패하면 MFA가 일시 잠긴다.
- recovery code 세션은 계정 복구용이며, 고위험 approve/reject에는 사용할 수 없다.

### 7.5 고위험 변경 API

| Method | Path | 권한 | MFA 필요 | 설명 |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/high-risk-requests?status=pending&limit=50` | 관리자 역할 | 불필요 | 고위험 요청 목록 조회. `limit`은 최대 50으로 clamp되고 현재 `nextCursor`는 `null` |
| POST | `/api/v1/admin/high-risk-requests` | `R-ADMIN` 또는 `R-SUPER-ADMIN` | 불필요 | 고위험 요청 생성 |
| POST | `/api/v1/admin/high-risk-requests/{id}/approve` | `R-SUPER-ADMIN` | 최근 5분 이내 TOTP | 요청 승인 및 실행 |
| POST | `/api/v1/admin/high-risk-requests/{id}/reject` | `R-SUPER-ADMIN` | 최근 5분 이내 TOTP | 요청 거절 |

고위험 `operationType`:

- `role_grant`
- `role_revoke`
- `region_grant`
- `region_revoke`
- `bulk_publish`

요청 body 규칙:

- 생성 요청은 `operationType`, `reason`과 operation별 필수 필드를 포함한다.
- role 변경은 `targetUserId`, `roleCode`, 선택적 `organizationId`, grant 시 선택적 `validUntil`을 사용한다.
- `R-SUPER-ADMIN`은 전역 역할이므로 `organizationId`를 가질 수 없다.
- region 변경은 `targetUserId`, `regionId`, 선택적 `organizationId`, grant 시 선택적 `validUntil`을 사용한다.
- bulk publish는 `destinationIds` 10~100개를 요구한다.
- approve body는 선택적 `decisionReason`만 허용한다.
- reject body는 필수 `decisionReason`만 허용한다.
- approve/reject body에는 TOTP code를 넣지 않는다. TOTP 세션은 `/api/v1/admin/security/mfa/verify`로 별도 생성한다.

## 8. 이해충돌 및 2인 통제

PoC에서도 다음 규칙을 적용한다.

- 제안 작성자와 동일한 사용자는 그 제안을 승인·반려할 수 없다.
- 동일 기관 소속 관리자의 검토 허용 여부는 운영 정책 확정 전까지 허용하되 감사 로그에 기관 일치 여부를 남긴다.
- 역할·지역 변경과 대량 게시는 `admin_high_risk_change_requests`에 요청을 만들고 요청자와 다른 `R-SUPER-ADMIN`이 결정한다. 추천 정책 변경은 현재 별도 관리자 API와 일반 감사로그 정책을 따른다.
- 고위험 승인·거절에는 5분 이내의 TOTP 재인증이 필요하며 recovery code 인증만으로는 결정할 수 없다.
- 마지막 활성 `R-SUPER-ADMIN` 회수는 거부하고, 역할·지역 변경 커밋 후 해당 사용자의 인가 캐시를 무효화한다.
- 일반 `R-ADMIN`은 고위험 변경을 요청할 수 있지만 직접 승인할 수 없다.

## 9. 오류 계약

기존 공통 JSON 오류 형식을 유지한다.

```json
{
  "error": {
    "code": "ROLE_FORBIDDEN",
    "message": "This role cannot perform the requested operation.",
    "details": {}
  }
}
```

| HTTP | Code | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | 인증 정보가 없거나 유효하지 않음 |
| 401 | `TOKEN_EXPIRED` | access token 만료 |
| 403 | `ADMIN_ACCESS_REQUIRED` | 관리자 역할이 없음 |
| 403 | `ROLE_FORBIDDEN` | 관리자 역할은 있지만 작업 권한이 없음 |
| 403 | `REGION_SCOPE_FORBIDDEN` | 담당하지 않은 지역 접근 |
| 403 | `ORGANIZATION_SCOPE_FORBIDDEN` | 다른 기관 소유 리소스 접근 |
| 403 | `SELF_REVIEW_FORBIDDEN` | 본인이 작성한 제안 검토 |
| 403 | `SUPER_ADMIN_REQUIRED` | 고위험 요청 결정에 Super Admin 역할이 없음 |
| 403 | `ADMIN_MFA_REQUIRED` | 관리자 MFA 인증이 없거나 만료됨 |
| 403 | `ADMIN_MFA_TOTP_REQUIRED` | recovery code 세션 등 TOTP가 아닌 MFA 세션으로 고위험 요청 결정 시도 |
| 403 | `ADMIN_MFA_RECOVERY_REQUIRED` | recovery 세션 없이 TOTP 재등록 시도 |
| 403 | `ADMIN_MFA_ENROLLMENT_REQUIRED` | MFA credential이 없는 관리자가 MFA 검증 시도 |
| 403 | `ADMIN_MFA_CODE_INVALID` | TOTP 또는 recovery code가 유효하지 않음 |
| 429 | `ADMIN_MFA_LOCKED` | MFA 실패 횟수 초과로 일시 잠김 |
| 400 | `INVALID_ADMIN_MFA_PAYLOAD` | MFA 요청 body 필드 누락 또는 형식 오류 |
| 400 | `INVALID_HIGH_RISK_PAYLOAD` | 고위험 요청 생성 body 필드 누락 또는 형식 오류 |
| 400 | `INVALID_HIGH_RISK_DECISION` | 고위험 결정 body 필드 누락 또는 형식 오류 |
| 409 | `SELF_APPROVAL_FORBIDDEN` | 본인이 요청한 고위험 변경 결정 |
| 409 | `LAST_SUPER_ADMIN_REQUIRED` | 마지막 활성 Super Admin 회수 시도 |
| 409 | `ADMIN_MFA_CODE_REUSED` | 이미 사용한 TOTP counter 또는 recovery code 재사용 |
| 409 | `ADMIN_MFA_ALREADY_ENROLLED` | 이미 활성 MFA credential이 있음 |
| 409 | `HIGH_RISK_REQUEST_ALREADY_DECIDED` | 이미 승인·거절된 고위험 요청 재결정 |
| 404 | `NOT_FOUND` | 리소스가 없거나 존재 여부를 숨겨야 함 |
| 404 | `HIGH_RISK_REQUEST_NOT_FOUND` | 고위험 요청이 없음 |
| 409 | `ROLE_ASSIGNMENT_CONFLICT` | 중복되거나 충돌하는 역할 할당 |
| 409 | `INVALID_PROPOSAL_STATE` | 현재 상태에서 허용되지 않는 작업 |

오류 메시지에는 다른 사용자의 ID, 기관명, 지역 할당, 제안 존재 여부와 내부 권한 계산 결과를 포함하지 않는다.

## 10. 감사 로그

다음 작업은 성공·거부 여부를 모두 기록한다.

- 관리자 로그인과 세션 갱신
- 역할 또는 지역 범위로 거부된 요청
- 제안 상세·첨부 근거 조회
- 승인, 수정 요청, 반려
- 월간 여행지 게시, 비노출, 만료, 재검수 전환
- 게시 재시도
- 공지·추천 정책 변경
- 역할·지역 할당 변경
- 고위험 변경의 승인·거절·실행 실패
- MFA 코드 검증 성공·거부

최소 필드:

- `audit_id`
- `occurred_at`
- `actor_user_id`
- `session_id`
- `roles_snapshot`
- `organization_ids_snapshot`
- `region_ids_snapshot`
- `action`
- `resource_type`
- `resource_id`
- `result`
- `reason_code`
- `request_id`
- 변경 전·후 값의 허용된 요약

access token, refresh token, 쿠키, OAuth credential, 민감한 원본 첨부 내용과 전체 개인정보는 기록하지 않는다.

## 11. CORS 및 관리자 프론트

- `https://lovv-admin-web.vercel.app`을 명시적인 허용 origin으로 추가한다.
- credential 요청을 사용하므로 wildcard origin을 허용하지 않는다.
- `Authorization`, `Content-Type`, `Cookie`, `X-CSRF-Token`만 필요한 범위에서 허용한다.
- 운영과 preview 배포 도메인을 wildcard Vercel origin으로 열지 않는다. preview 환경은 승인된 고정 origin을 별도 파라미터로 관리한다.
- 관리자 프론트의 Mock SSO와 역할 선택 UI는 개발 모드에서만 사용할 수 있으며, 운영 빌드에서는 제거하거나 비활성화한다.
- 프론트 라우트 가드는 UX 보조 수단이며 보안 경계가 아니다.

## 12. 테스트 요구사항

### 인증·토큰

- 일반 사용자는 관리자 API에서 `403 ADMIN_ACCESS_REQUIRED`를 받는다.
- DB에 활성 할당이 없는 Cognito Group만으로 관리자 토큰이 발급되지 않는다.
- 정지·만료된 역할과 지역 할당이 토큰에 포함되지 않는다.
- 세션 갱신 시 최신 역할과 지역 범위가 반영된다.
- 잘못된 타입의 `roles`, `region_ids`, `organization_ids` 클레임을 거부한다.

### 역할별 허용·거부

- 각 권한 매트릭스 행마다 성공 및 거부 테스트를 작성한다.
- 데이터 제공자가 다른 제공자의 제안을 조회·수정하지 못한다.
- 지역 운영자가 미할당 지역의 지표를 조회하지 못한다.
- 지역 운영자가 원시 이벤트, 세션 단위 로그와 최소 집단 크기 미만의 통계를 조회하지 못한다.
- 관리자가 제안을 검토할 수 있지만 별도 제공자 역할 없이는 제안을 작성하지 못한다.
- 복수 역할 사용자의 허용 작업 합집합과 역할별 범위 제한을 검증한다.
- 작성자 본인의 검토를 거부한다.
- 관리자가 승인한 데이터라도 별도 월간 여행지 게시 상태가 아니면 `이번 달 여행지`로 노출되지 않는다.

### 보안 회귀

- 요청 본문의 `roles`, `userId`, `organizationId`, `regionIds`, `reviewerId` 변조가 권한에 영향을 주지 않는다.
- 목록 검색, 페이지네이션, 집계 API에서도 객체·지역 범위가 누락되지 않는다.
- 공식 링크와 제휴 링크 이벤트가 서로 다른 필드·이벤트명으로 저장되고 B2G 리포트에서 재정 지표와 합산되지 않는다.
- 관문도시 행동이 추천 소도시 성과로 귀속되지 않는다.
- 권한 거부 응답이 타 사용자 리소스 존재 여부를 노출하지 않는다.
- 감사 로그에 토큰과 민감 정보가 저장되지 않는다.
- 관리자 origin 이외의 credentialed CORS 요청을 허용하지 않는다.
- 일반 관리자 읽기 경로는 MFA 세션 없이도 role 인증만으로 성공한다.
- 고위험 approve/reject는 MFA 세션 없이 `ADMIN_MFA_REQUIRED`로 거부된다.
- recovery code로 만든 MFA 세션은 고위험 approve/reject에서 `ADMIN_MFA_TOTP_REQUIRED`로 거부된다.
- 요청자는 본인이 만든 고위험 요청을 승인·거절할 수 없다.
- 마지막 활성 `R-SUPER-ADMIN` 회수는 거부된다.
- 고위험 변경 실행 중 업무 변경 또는 strict 감사 기록 실패가 발생하면 업무 변경이 롤백된다.
- opt-in 실DB 통합 테스트는 `RUN_ADMIN_DB_INTEGRATION=1` 또는 `RUN_RDS_DATA_API_INTEGRATION=1`을 설정한 경우에만 실행되며, 일반 unittest 완료와 구분해 기록한다.

## 13. 구현 대상 파일 범위

후속 구현은 최소한 다음 영역을 다룬다.

- `src/shared/auth.py`: 관리자 권한 클레임 검증
- `src/shared/current_user.py`: roles 문자열·배열 정규화와 범위 조회 계약
- `src/auth/app.py`: 로그인 및 세션 갱신 시 DB 역할 계산
- `src/auth/user_repository.py`: 고정 `R-USER` 반환 제거와 역할 조회 연동
- `src/auth/authorizer.py`: 신뢰 가능한 권한 컨텍스트 전달
- `template.yaml`: 관리자 origin, 관리자 API authorizer와 환경 변수
- `schema/aurora_mysql/`: 역할·지역 할당 마이그레이션
- `schema/aurora_mysql/`: 월간 여행지 운영, 공식/제휴 링크 분리 지표를 위한 마이그레이션
- `tests/test_auth_app.py`, `tests/test_auth_authorizer.py`: 관리자 토큰과 회수 회귀 테스트
- 신규 관리자 도메인 패키지와 테스트

기존 일반 사용자 API의 소유권 검증과 `R-USER` 동작은 그대로 유지해야 한다.

## 14. 완료 조건

이 명세를 기반으로 하는 관리자 인증·RBAC 구현은 아래 조건을 모두 만족할 때 완료로 본다.

- 역할과 담당 지역의 DB 모델이 마이그레이션으로 존재한다.
- 데이터 제안과 월간 여행지 게시 상태가 분리된 모델로 존재한다.
- 로그인·세션 갱신이 활성 권한을 조회해 토큰에 반영한다.
- `/auth/me`, `/auth/session`이 역할과 허용 범위를 안정된 응답 형식으로 반환한다.
- 모든 관리자 API가 역할과 객체·지역 범위를 서버에서 검증한다.
- 공식 링크와 제휴 링크가 이벤트·리포트에서 분리되고 B2G 리포트에 재정 지표가 포함되지 않는다.
- 지역 운영자는 담당 지역의 익명·집계 지표만 조회한다.
- Mock SSO 역할 선택 없이 실제 계정으로 역할별 화면에 진입한다.
- 역할 정지 후 새 토큰과 세션 갱신에서 관리자 권한이 제거된다.
- 권한 매트릭스와 보안 회귀 테스트가 통과한다.
- 관리자 프론트 origin만 credentialed CORS로 허용된다.
- 역할·범위 거부와 중요 상태 변경이 감사 로그에 남는다.

## 15. 후속 작업 순서

1. 역할·지역 할당 DB 마이그레이션과 repository 구현
2. 데이터 제안·월간 여행지 운영 DB 마이그레이션과 repository 구현
3. 인증 세션의 권한 계산 및 토큰 클레임 확장
4. 공통 `require_role`·`require_region_scope` 인가 유틸리티 구현
5. 관리자 API에 authorizer와 객체 단위 인가 적용
6. 관리자 프론트 Mock SSO 제거 및 `/auth/session` 연동
7. 권한 매트릭스·감사 로그·CORS·B2G 지표 분리 통합 테스트
