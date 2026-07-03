# Lovv Backend (BE)

Lovv 서비스의 AWS SAM(Serverless Application Model) 기반 서버리스 백엔드 애플리케이션입니다. Amazon API Gateway, AWS Lambda, Amazon Aurora MySQL, Amazon DynamoDB, Amazon S3를 연동하여 안전하고 확장 가능한 백엔드 API를 제공합니다.

---

## 🛠 Tech Stack & Architecture

- **Framework**: AWS SAM (Serverless Application Model)
- **Runtime**: Python 3.9
- **API Gateway**: Amazon API Gateway (REST API & Cognito JWT Authorizer)
- **Database**:
  - **Amazon Aurora MySQL**: VPC 내부의 관계형 데이터베이스로, 사용자 정보(`users`), 소셜 계정 연동(`social_accounts`), 취향 선호도(`user_preferences`), 저장한 일정(`itineraries`, `itinerary_items`, `plan_reactions`) 데이터를 보관합니다.
  - **Amazon DynamoDB**: TTL(Time-To-Live) 기반의 세션 관리용 저장소(`auth_sessions`)로 사용됩니다.
- **Object Storage**:
  - **Amazon S3**: 한국/일본 소도시 상세 정보(명소, 축제, 통계 등)를 포함하는 원천 JSON 데이터를 적재 및 조회하는 용도로 사용됩니다.

---

## 🌐 API Endpoints

### 1. 인증 및 세션 (Auth)
- **`POST /api/v1/auth/google`**: Google ID Token 또는 Authorization Code 검증 및 로그인 처리.
- **`POST /api/v1/auth/kakao`**: Kakao ID Token 또는 Authorization Code 검증 및 로그인 처리.
- **`POST /api/v1/auth/cognito/session`**: Cognito JWT Authorizer가 검증한 클레임을 Lovv 세션으로 연동(Bridge).
- **`GET /api/v1/auth/session`**: HttpOnly Secure 쿠키(`lovv_session`)에 담긴 refresh token 기반 세션 연환 및 복원.
- **`GET /api/v1/auth/me`**: 현재 로그인된 사용자의 상세 프로필 조회.
- **`POST /api/v1/auth/logout`**: 활성 세션을 파기하고 브라우저 쿠키를 만료 처리.

### 2. 사용자 취향 선호도 (Preferences)
- **`GET /api/v1/me/preferences`**: 현재 사용자의 맞춤 여행 선호도 프로필 조회.
- **`PUT /api/v1/me/preferences`**: 취향 온보딩 결과 또는 마이페이지에서의 선호도 업데이트.

### 3. 소도시 및 지도 데이터 (Map/Cities)
- **`GET /api/small-cities`**: 소도시 목록 마커 정보 조회 (CORS 및 위도/경도 데이터 포함).
- **`GET /api/small-cities/{cityId}`**: 특정 소도시의 상세 메타데이터 조회.
- **`GET /api/small-cities/{cityId}/places`**: 소도시 내 명소(`attractions`) 및 축제(`festivals`) 정보 조회 (S3 연동).

### 4. AI 일정 추천 (AgentCore Mock)
- **`POST /api/v1/recommendations`**: 여행 테마, 일정 기간, 축제 포함 여부를 기반으로 한 AI 일정 매핑 (MVP 범위 내 Mock 처리).

### 5. 일정 저장 및 반응 (Saved Plans)
- **`POST /api/v1/me/itineraries`**: 생성된 여행 일정을 보관함에 영속 저장.
- **`GET /api/v1/me/itineraries`**: 저장된 일정 목록 조회.
- **`GET /api/v1/me/itineraries/{itineraryId}`**: 저장된 일정의 일차별 상세 명세 조회.
- **`DELETE /api/v1/me/itineraries/{itineraryId}`**: 저장된 일정의 soft delete (`deleted_at` 처리).
- **`POST /api/v1/me/itineraries/{itineraryId}/like`**: 저장된 일정에 좋아요 누르기.
- **`DELETE /api/v1/me/itineraries/{itineraryId}/like`**: 저장된 일정의 좋아요 취소.

### 6. 관리자 보안 및 고위험 변경 (Admin Security)

- **`GET /api/v1/admin/security/mfa/status`**: 관리자 MFA 등록 및 현재 세션 검증 상태 조회.
- **`POST /api/v1/admin/security/mfa/enroll`**: TOTP 등록 시작.
- **`POST /api/v1/admin/security/mfa/confirm`**: TOTP 등록 확인 및 recovery code 발급.
- **`POST /api/v1/admin/security/mfa/verify`**: 현재 관리자 세션을 TOTP로 검증.
- **`POST /api/v1/admin/security/mfa/recover`**: 1회용 recovery code로 복구 세션 생성.
- **`GET /api/v1/admin/high-risk-requests`**: 고위험 변경 요청 목록 조회.
- **`POST /api/v1/admin/high-risk-requests`**: 역할·지역 할당 변경 또는 대량 게시 요청 생성.
- **`POST /api/v1/admin/high-risk-requests/{id}/approve`**: 다른 `R-SUPER-ADMIN`이 요청 승인 및 실행.
- **`POST /api/v1/admin/high-risk-requests/{id}/reject`**: 다른 `R-SUPER-ADMIN`이 요청 거절.

일반 관리자 읽기·목록 API는 관리자 role 인증만 요구하며 MFA를 전역 게이트로 사용하지 않습니다. 고위험 approve/reject에만 최근 5분 이내 TOTP 검증이 필요합니다. Recovery code 세션은 고위험 결정에 사용할 수 없고, approve/reject body에도 TOTP code를 넣지 않습니다. 먼저 `/api/v1/admin/security/mfa/verify`로 세션을 검증해야 합니다.

상세 계약은 `docs/specs/ADMIN_RBAC_SPEC.md`, 운영 절차는 `docs/specs/ADMIN_OPERATIONS_RUNBOOK.md`를 참조합니다.

---

## 🔒 Authentication Model

- **Access Token**: HMAC-SHA256(`AUTH_TOKEN_SIGNING_SECRET`)으로 서명한 짧은 수명의 JWT를 Bearer 헤더로 전달받아 API 인증에 사용합니다.
- **Refresh Token**: 브라우저와 연동되는 `HttpOnly; Secure; SameSite=None` 속성의 opaque 쿠키를 활용하여 무상태(Stateless) JWT의 한계를 보완하고 세션을 유지합니다.
- **Session DB**: DynamoDB에는 노출을 최소화하기 위해 해시된 refresh token 값만 저장하며, 세션 만료 시 TTL에 의해 자동 청소됩니다.
- **Cognito Bridge**: Hosted UI를 거친 사용자는 API Gateway의 Cognito JWT Authorizer 검증을 마친 뒤 `/auth/cognito/session`으로 연결(Bridge)되어 `R-USER` 권한을 할당받습니다.
- **Admin RBAC**: `require_admin_access`가 적용된 공통 관리자 API는 `R-ADMIN`과 `R-SUPER-ADMIN`을 허용합니다. 역할별 전용 API는 별도 role 검사를 따르며, 고위험 변경의 승인·거절은 `R-SUPER-ADMIN`만 가능하고 요청자 본인 승인은 금지됩니다.

---

## 📂 Backend Directory Structure

```text
Lovv_BE/
├── .aws-sam/             # AWS SAM 빌드 임시 결과물
├── docs/                 # 백엔드 설계 및 API 스펙 문서
├── events/               # Lambda 로컬 실행 테스트용 API Gateway mock events
├── infra/                # 인프라 SQL 및 데이터 스택 정의
│   └── data-stack/rds/schema.sql
├── schema/aurora_mysql/  # 관리자 콘솔 002/003/004 migration
├── parameters/           # 배포 매개변수 설정 템플릿
├── src/
│   ├── admin/            # 관리자 콘솔, MFA, 고위험 승인 Lambda 핸들러
│   ├── auth/             # 로그인, 세션 처리, 토큰 관리 Lambda 핸들러
│   ├── map_city/         # 소도시 정보 및 S3 JSON 파싱 Lambda 핸들러
│   ├── preferences/      # 선호도 CRUD Lambda 핸들러
│   ├── recommendations/  # AI 일정 생성 처리 Lambda 핸들러
│   ├── saved_plans/      # 일정 보관함 및 반응 CRUD Lambda 핸들러
│   └── shared/           # DB 커넥션, CORS, Response 등 공유 헬퍼
├── template.yaml         # CloudFormation 기반 AWS 리소스 정의 템플릿
└── tests/                # unittest 프레임워크 기반 API/핸들러 테스트 케이스
```

---

## 🚀 Local Verification & Testing

배포하기 전 로컬 환경에서 백엔드 함수와 API 흐름을 검증할 수 있습니다.

```powershell
# 1. unittest 기반 백엔드 단위 테스트 수행
$env:PYTHONPATH='src'
python -m unittest

# 2. 관리자 MFA/고위험 승인 핵심 테스트
python -m unittest tests.test_admin_high_risk_app
python -m unittest tests.test_admin_mfa_app.AdminMfaAppTest.test_admin_read_routes_need_role_only_and_mfa_status_is_accessible

# 3. 로컬 API 스모크 테스트 (외부 API Mocking을 통한 핸들러 동작 점검)
python scripts/local_api_smoke.py

# 4. AWS SAM 템플릿 검증 및 린팅
sam validate
sam validate --lint

# 5. SAM 빌드 실행 (Lambda 모듈 패키징)
sam build
```

실DB 통합 테스트는 일반 unittest에서 기본 skip됩니다. `RUN_ADMIN_DB_INTEGRATION=1` 또는 `RUN_RDS_DATA_API_INTEGRATION=1`을 명시한 실행만 실DB 검증 완료로 기록합니다. 로컬 MySQL 초기화와 현재 schema 순서는 `docs/LOCAL_DB_DOCKER.md`를 참조합니다.

---

## ☁️ Deployment

`sam deploy` 명령을 사용해 AWS에 리소스를 배포합니다. 실제 Secret Key 등은 파라미터 재정의(`--parameter-overrides`) 옵션을 통해 주입합니다.

```bash
sam deploy --guided \
  --parameter-overrides \
  MapCityS3Bucket=your-data-pipeline-bucket \
  MapCityS3Prefix=raw/KR/details/20260609/ \
  AllowedCorsOrigin=http://localhost:5173,https://your-cloudfront-domain.net \
  AuthTokenSigningSecret=your-token-signing-secret \
  AuthRefreshCookieSameSite=None \
  AuthRefreshCookieSecure=true \
  AuthRefreshCookiePath=/ \
  GoogleClientId=your-google-client-id \
  GoogleClientSecret=your-google-client-secret \
  KakaoClientId=your-kakao-client-id \
  EnableCognitoPoC=true \
  RdsHost=your-rds-aurora-endpoint \
  RdsSecretArn=your-rds-credentials-secret-arn \
  RdsDatabaseName=lovvdev \
  VpcId=your-vpc-id \
  PrivateSubnetA=your-private-subnet-a \
  PrivateSubnetC=your-private-subnet-c \
  AuthSessionsTableName=lovv_dev_auth_sessions
```
