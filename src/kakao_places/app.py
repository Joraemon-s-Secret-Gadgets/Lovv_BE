from shared.http import error_response, json_response
from shared.logger import Tag, get_logger
from kakao_places.image_resolver import KakaoPlaceImageError, resolve_kakao_place_image, validate_place_id


LOGGER = get_logger(__name__)
CACHE_HEADERS = {"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"}


def lambda_handler(event, context):
    return handle_request(event)


def handle_request(event, resolver=resolve_kakao_place_image):
    method = get_method(event)
    if method == "OPTIONS":
        return json_response(200, {}, headers=CACHE_HEADERS, event=event)
    if method != "GET":
        return error_response(405, "INVALID_METHOD", "Only GET is supported.", event=event)

    try:
        place_id = validate_place_id(get_place_id(event))
        image_url = resolver(place_id)
        return json_response(200, {"placeId": place_id, "imageUrl": image_url}, headers=CACHE_HEADERS, event=event)
    except ValueError as error:
        return error_response(400, "INVALID_PLACE_ID", str(error), event=event)
    except KakaoPlaceImageError:
        LOGGER.warning(Tag.SYSTEM, "Kakao place image lookup failed")
        return error_response(502, "KAKAO_PLACE_UNAVAILABLE", "Kakao place image is unavailable.", event=event)
    except Exception:
        LOGGER.exception(Tag.SYSTEM, "Unhandled Kakao place image API error")
        return error_response(500, "INTERNAL_ERROR", "Kakao place image API is unavailable.", event=event)


def get_method(event):
    return (
        ((event.get("requestContext") or {}).get("http") or {}).get("method")
        or event.get("httpMethod")
        or ""
    ).upper()


def get_place_id(event):
    path_parameters = event.get("pathParameters") or {}
    if path_parameters.get("placeId"):
        return path_parameters["placeId"]

    path = event.get("rawPath") or event.get("path") or ""
    prefix = "/api/v1/kakao-places/"
    suffix = "/image"
    if path.startswith(prefix) and path.endswith(suffix):
        return path[len(prefix) : -len(suffix)].strip("/")
    return None
