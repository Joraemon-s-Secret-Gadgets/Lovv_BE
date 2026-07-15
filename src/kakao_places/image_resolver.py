# @file src/kakao_places/image_resolver.py
# @description Kakao 장소 페이지에서 허용된 CDN의 Open Graph 이미지 URL을 안전하게 추출한다.
# @author JJonyeok2
# @lastModified 2026-07-15

import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PLACE_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,19}$")
MAX_RESPONSE_BYTES = 512 * 1024
REQUEST_TIMEOUT_SECONDS = 3
ALLOWED_IMAGE_HOST_SUFFIXES = (".kakaocdn.net", ".daumcdn.net")


class KakaoPlaceImageError(RuntimeError):
    pass


class _OpenGraphImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url = None

    def handle_starttag(self, tag, attrs):
        if self.image_url or tag.lower() != "meta":
            return

        values = {key.lower(): value for key, value in attrs if key and value}
        property_name = (values.get("property") or values.get("name") or "").lower()
        if property_name == "og:image":
            self.image_url = values.get("content")


def validate_place_id(value):
    place_id = str(value or "").strip()
    if not PLACE_ID_PATTERN.fullmatch(place_id):
        raise ValueError("placeId must contain 1 to 20 digits and cannot start with zero.")
    return place_id


def resolve_kakao_place_image(place_id, opener=urlopen):
    validated_place_id = validate_place_id(place_id)
    request = Request(
        f"https://place.map.kakao.com/{validated_place_id}",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Lovv/1.0 (+https://www.lovv.site)",
        },
    )

    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            # 신뢰할 수 없는 업스트림 응답이 Lambda 메모리를 과도하게 사용하지 못하도록 상한보다 한 바이트만 더 읽는다.
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise KakaoPlaceImageError("Kakao place metadata is unavailable.") from error

    if len(payload) > MAX_RESPONSE_BYTES:
        raise KakaoPlaceImageError("Kakao place metadata response is too large.")

    parser = _OpenGraphImageParser()
    try:
        parser.feed(payload.decode("utf-8", errors="replace"))
    except (TypeError, ValueError) as error:
        raise KakaoPlaceImageError("Kakao place metadata is invalid.") from error

    return normalize_image_url(parser.image_url)


def normalize_image_url(value):
    if not isinstance(value, str) or not value.strip():
        return None

    image_url = value.strip()
    if image_url.startswith("//"):
        image_url = f"https:{image_url}"
    elif image_url.startswith("http://"):
        image_url = f"https://{image_url[len('http://') :]}"

    parsed = urlparse(image_url)
    hostname = (parsed.hostname or "").lower()
    # 외부 페이지가 임의 호스트를 주입해도 클라이언트에 전달되지 않도록 HTTPS Kakao CDN만 허용한다.
    if parsed.scheme != "https" or not any(hostname.endswith(suffix) for suffix in ALLOWED_IMAGE_HOST_SUFFIXES):
        return None

    return image_url

# EOF: src/kakao_places/image_resolver.py
