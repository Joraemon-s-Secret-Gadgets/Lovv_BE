import json
from decimal import Decimal

from shared.http import DEFAULT_HEADERS
from small_cities.mapper import VALID_THEMES
from small_cities.s3_raw_repository import CityDataInvalidError, CityDataNotFoundError, CityDataUpstreamError, S3RawCityRepository
from small_cities.service import DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, SmallCityService


VALID_COUNTRIES = {"KR", "JP"}


class RequestValidationError(ValueError):
    pass


def lambda_handler(event, context):
    return handle_request(event)


def handle_request(event, repository=None):
    try:
        method = get_method(event)
        if method == "OPTIONS":
            return json_response({})
        if method != "GET":
            return error_response("INVALID_METHOD", "Only GET is supported.", 405)

        service = SmallCityService(repository or S3RawCityRepository.from_env())
        city_id = get_city_id(event)
        markers_only = is_marker_request(event)
        places_request = is_places_request(event)

        if city_id and places_request:
            places = service.get_city_places(city_id)
            if not places:
                return error_response("NOT_FOUND", "Small city places were not found.", 404)
            return json_response(places)

        if city_id:
            record = service.get_city(city_id)
            if not record:
                return error_response("NOT_FOUND", "Small city was not found.", 404)
            return json_response({"data": record})

        params = event.get("queryStringParameters") or {}
        country = parse_country(params.get("country"))
        query = parse_query(params.get("q"))
        themes = parse_themes(params.get("themes"))
        page = parse_positive_int(params.get("page"), DEFAULT_PAGE, "page")
        page_size = parse_positive_int(params.get("page_size"), DEFAULT_PAGE_SIZE, "page_size", MAX_PAGE_SIZE)

        if markers_only:
            return json_response(service.list_markers(country=country, query=query, themes=themes, page=page, page_size=page_size))

        return json_response(service.list_cities(country=country, query=query, themes=themes, page=page, page_size=page_size))
    except RequestValidationError as error:
        return error_response("INVALID_QUERY", str(error), 400)
    except CityDataNotFoundError as error:
        return error_response(error.code, error.message, error.status_code)
    except CityDataUpstreamError as error:
        return error_response(error.code, error.message, error.status_code)
    except CityDataInvalidError as error:
        return error_response(error.code, error.message, error.status_code)
    except Exception:
        return error_response("INTERNAL_ERROR", "Small-city API is unavailable.", 500)


def get_method(event):
    return (
        ((event.get("requestContext") or {}).get("http") or {}).get("method")
        or event.get("httpMethod")
        or ""
    ).upper()


def get_city_id(event):
    path_parameters = event.get("pathParameters") or {}
    if path_parameters.get("cityId"):
        return path_parameters["cityId"]

    path = event.get("rawPath") or event.get("path") or ""
    prefixes = (
        "/api/small-cities/",
        "/api/v1/small-cities/",
        "/api/v1/map/cities/",
    )
    for prefix in prefixes:
        if path.startswith(prefix):
            return path[len(prefix) :].split("/", 1)[0]

    return None


def is_marker_request(event):
    path = event.get("rawPath") or event.get("path") or ""
    return path == "/api/v1/map/markers"


def is_places_request(event):
    path = event.get("rawPath") or event.get("path") or ""
    return path.endswith("/places")


def parse_country(value):
    if value in (None, ""):
        return None
    if value not in VALID_COUNTRIES:
        raise RequestValidationError("country must be KR or JP.")
    return value


def parse_query(value):
    if value is None:
        return None

    query = value.strip()
    if len(query) > 80:
        raise RequestValidationError("q must be 80 characters or fewer.")
    return query or None


def parse_themes(value):
    if value in (None, ""):
        return []

    themes = [theme.strip() for theme in value.split(",") if theme.strip()]
    invalid = [theme for theme in themes if theme not in VALID_THEMES]
    if invalid:
        raise RequestValidationError("themes contains unsupported values.")

    return themes


def parse_positive_int(value, default, name, maximum=None):
    if value in (None, ""):
        return default

    if not str(value).isdigit():
        raise RequestValidationError(f"{name} must be a positive integer.")

    parsed = int(value)
    if parsed < 1:
        raise RequestValidationError(f"{name} must be a positive integer.")
    if maximum is not None and parsed > maximum:
        raise RequestValidationError(f"{name} must be {maximum} or lower.")

    return parsed


def json_response(body, status_code=200):
    headers = dict(DEFAULT_HEADERS)
    headers["Cache-Control"] = "no-store"
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, ensure_ascii=False, default=json_default),
    }


def error_response(code, message, status_code):
    return json_response({"error": {"code": code, "message": message}}, status_code)


def json_default(value):
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
