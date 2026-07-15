# @file src/preferences/app.py
# @description 인증된 사용자의 온보딩 취향 설정을 RDS MySQL에 로드 및 저장하는 Lambda 핸들러.
# @author JJonyeok2
# @lastModified 2026-07-15

import base64
import json
from datetime import datetime, timezone

from preferences.repository import RdsDataPreferenceRepository
from shared.auth import AuthTokenError
from shared.current_user import authenticated_claims
from shared.http import error_response, json_response
from shared.logger import Tag, get_logger


LOGGER = get_logger(__name__)


# 지원하는 국가 취향 범위
COUNTRY_TRACKS = {"KR", "JP"}
# 지원하는 여행 템포(Pace) 목록
PACES = {"relaxed", "balanced", "active"}
# 페이로드 수신 시 수정을 차단할 시스템 읽기 전용 필드들
FORBIDDEN_OWNER_FIELDS = {"userId", "user_id", "ownerId", "createdBy", "preferenceId", "createdAt", "updatedAt"}
# 직접 입력 텍스트 등 가독성 및 정형화를 위해 제한할 필드들
FORBIDDEN_FREE_TEXT_FIELDS = {"dislikedConstraints", "freeText", "naturalLanguagePreference", "chatText", "messages"}


class PreferenceRequestError(Exception):
    """취향 정보 처리 및 유효성 검증 오류 시 발생하는 커스텀 예외"""
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def lambda_handler(event, context):
    """AWS Lambda 실행 진입점"""
    return handle_request(event or {})


def handle_request(event, repository=None):
    """API Gateway 요청 수신 및 취향 API 전역 에러 핸들링"""
    try:
        return _handle_request(event or {}, repository)
    except PreferenceRequestError as error:
        return error_response(error.status_code, error.code, error.message)
    except AuthTokenError as error:
        return error_response(error.status_code, error.code, error.message)
    except Exception:
        LOGGER.exception(Tag.SYSTEM, "Unhandled preference API error")
        return error_response(500, "INTERNAL_ERROR", "Preference API is unavailable")


def _handle_request(event, repository=None):
    """HTTP Method 기반 요청 분기 및 RDS Repository 연동"""
    method = _event_method(event)
    path = _event_path(event)
    
    # OPTIONS preflight 요청 처리
    if method == "OPTIONS":
        return json_response(200, {})
        
    # /api/v1/me/preferences 경로만 허용
    if path != "/api/v1/me/preferences":
        return error_response(404, "NOT_FOUND", "Route not found")

    # 1. JWT 클레임에서 사용자 고유 ID 추출 및 인증 상태 확인
    user_id = _current_user_id(event)
    repository = repository or RdsDataPreferenceRepository.from_env()

    # 2. GET 요청: 사용자 설정 로드 및 온보딩 완료 상태 분기
    if method == "GET":
        preference = repository.get_by_user_id(user_id)
        if not preference or not preference.get("onboardingCompleted"):
            return json_response(200, {"preferences": None, "onboardingCompleted": False})
        return json_response(200, {"preferences": public_preference(preference), "onboardingCompleted": True})

    # 3. PUT 요청: 온보딩 또는 마이페이지 취향 설정 수정/저장 (Upsert)
    if method == "PUT":
        payload = _validate_payload(_json_body(event))
        preference = repository.upsert(user_id, payload, _now_iso())
        LOGGER.info(
            Tag.PREF,
            "Preferences updated (userId=%s, countryTrack=%s, themes=%s)",
            user_id,
            payload.get("countryTrack"),
            len(payload.get("mappedThemes") or []),
        )
        return json_response(200, {"preferences": public_preference(preference)})

    return error_response(405, "INVALID_METHOD", "Only GET and PUT are supported")


def _validate_payload(body):
    """입력 데이터 필드 검증 및 금지 필드 검사"""
    # 1. 수정 불가능한 필드나 자유 서술형 필드가 포함되어 있는지 검사
    forbidden = sorted((FORBIDDEN_OWNER_FIELDS | FORBIDDEN_FREE_TEXT_FIELDS).intersection(body.keys()))
    if forbidden:
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "Preference payload contains unsupported fields")

    # 2. 필수 필드 검증 (국가 트랙, 매핑된 여행 테마 목록)
    country_track = _read_country_track(body)
    mapped_themes = _read_mapped_themes(body)

    # 3. 추가 선택 속성 타입 검증 (리스트 및 정수 조건 검증)
    if "preferredRegions" in body and not _is_string_list(body.get("preferredRegions")):
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "preferredRegions must be an array")
    if "travelStyles" in body and not _is_string_list(body.get("travelStyles")):
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "travelStyles must be an array")
    if body.get("pace") not in (None, "", *PACES):
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "pace is invalid")
    if "tripDays" in body and (not isinstance(body.get("tripDays"), int) or body.get("tripDays") < 1):
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "tripDays must be a positive integer")

    return {
        "countryTrack": country_track,
        "mappedThemes": mapped_themes,
        "preferredRegions": body.get("preferredRegions") or [],
        "selectedCityStyle": body.get("selectedCityStyle"),
        "pace": body.get("pace"),
        "tripDays": body.get("tripDays"),
        "companionStyle": body.get("companionStyle"),
        "travelStyles": body.get("travelStyles") or [],
    }


def _read_country_track(body):
    """국가 취향 설정(countryTrack) 값 유효성 체크"""
    if "countryTrack" not in body:
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "countryTrack is required")

    country_track = body.get("countryTrack")
    if country_track not in COUNTRY_TRACKS:
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "countryTrack is invalid")
    return country_track


def _read_mapped_themes(body):
    """테마 설정 데이터(mappedThemes 또는 selectedThemeIds) 추출 및 동기화"""
    mapped_themes = body.get("mappedThemes")
    if _is_non_empty_string_list(mapped_themes):
        return mapped_themes

    # 프론트엔드와 백엔드의 필드 포맷(selectedThemeIds -> mappedThemes) 호환을 위한 매핑 처리
    selected_theme_ids = body.get("selectedThemeIds")
    if _is_non_empty_string_list(selected_theme_ids):
        return selected_theme_ids

    raise PreferenceRequestError(400, "VALIDATION_ERROR", "mappedThemes or selectedThemeIds is required")


def public_preference(preference):
    """데이터베이스에서 로드한 취향 정보 모델을 프론트엔드 반환용 안전한 스키마 구조로 재구성"""
    mapped_themes = preference.get("mappedThemes") or []

    return {
        "preferenceId": preference.get("preferenceId"),
        "userId": preference.get("userId"),
        "countryTrack": preference.get("countryTrack"),
        "preferredRegions": preference.get("preferredRegions") or [],
        "selectedCityStyle": preference.get("selectedCityStyle"),
        "mappedThemes": mapped_themes,
        "selectedThemeIds": mapped_themes,  # 프론트엔드와 호환성 보장
        "pace": preference.get("pace"),
        "tripDays": preference.get("tripDays"),
        "companionStyle": preference.get("companionStyle"),
        "travelStyles": preference.get("travelStyles") or [],
        "onboardingCompleted": bool(preference.get("onboardingCompleted")),
        "createdAt": preference.get("createdAt"),
        "updatedAt": preference.get("updatedAt"),
    }


def _current_user_id(event):
    """API Gateway가 인증 검증 후 주입한 요청 컨텍스트 클레임에서 사용자 고유 ID(userId/sub) 확인"""
    claims = authenticated_claims(event)
    user_id = claims.get("userId") or claims.get("sub")
    if not user_id:
        raise PreferenceRequestError(401, "UNAUTHORIZED", "Authentication is required")
    return user_id


def _json_body(event):
    """HTTP 요청 바디 JSON 디코딩 및 Base64 인코딩 해제"""
    raw_body = event.get("body")
    if raw_body in (None, ""):
        return {}
    if event.get("isBase64Encoded"):
        try:
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        except Exception:
            raise PreferenceRequestError(400, "INVALID_JSON", "Request body must be valid JSON")
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        raise PreferenceRequestError(400, "INVALID_JSON", "Request body must be valid JSON")
    if not isinstance(parsed, dict):
        raise PreferenceRequestError(400, "VALIDATION_ERROR", "Request body must be a JSON object")
    return parsed


def _event_method(event):
    """요청 메소드(HTTP Method) 추출"""
    return (((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod") or "").upper()


def _event_path(event):
    """요청 URL 경로 추출"""
    return event.get("rawPath") or event.get("path") or ""


def _is_string_list(value):
    """문자열 리스트 유형인지 검사"""
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _is_non_empty_string_list(value):
    """비어있지 않은 문자열 리스트 유형인지 검사"""
    return _is_string_list(value) and bool(value)


def _now_iso():
    """현재 시각을 UTC 기준 ISO 8601 포맷으로 변환"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# EOF: src/preferences/app.py
