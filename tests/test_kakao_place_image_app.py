import json
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kakao_places.app import handle_request
from kakao_places.image_resolver import KakaoPlaceImageError, normalize_image_url, resolve_kakao_place_image


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size):
        return self.payload[:size]


def event(place_id="26338954", method="GET"):
    return {
        "rawPath": f"/api/v1/kakao-places/{place_id}/image",
        "pathParameters": {"placeId": place_id},
        "requestContext": {"http": {"method": method}},
        "headers": {"origin": "http://localhost:5173"},
    }


class KakaoPlaceImageResolverTest(unittest.TestCase):
    def test_extracts_and_normalizes_allowed_open_graph_image(self):
        payload = b'<html><head><meta property="og:image" content="//img1.kakaocdn.net/place.jpg"></head></html>'

        image_url = resolve_kakao_place_image("26338954", opener=lambda request, timeout: FakeResponse(payload))

        self.assertEqual(image_url, "https://img1.kakaocdn.net/place.jpg")

    def test_rejects_untrusted_image_host(self):
        self.assertIsNone(normalize_image_url("https://attacker.example/place.jpg"))


class KakaoPlaceImageAppTest(unittest.TestCase):
    def test_returns_image_url_with_browser_cache_headers(self):
        response = handle_request(event(), resolver=lambda place_id: "https://img1.kakaocdn.net/place.jpg")
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body, {"placeId": "26338954", "imageUrl": "https://img1.kakaocdn.net/place.jpg"})
        self.assertEqual(response["headers"]["Cache-Control"], "public, max-age=86400, stale-while-revalidate=604800")
        self.assertEqual(response["headers"]["Access-Control-Allow-Origin"], "http://localhost:5173")

    def test_returns_null_when_place_has_no_open_graph_image(self):
        response = handle_request(event(), resolver=lambda place_id: None)

        self.assertEqual(response["statusCode"], 200)
        self.assertIsNone(json.loads(response["body"])["imageUrl"])

    def test_rejects_non_numeric_place_id_without_calling_resolver(self):
        called = False

        def resolver(place_id):
            nonlocal called
            called = True

        response = handle_request(event("https:evil.example"), resolver=resolver)

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(json.loads(response["body"])["error"]["code"], "INVALID_PLACE_ID")
        self.assertFalse(called)

    def test_maps_upstream_failure_to_safe_error(self):
        def resolver(place_id):
            raise KakaoPlaceImageError("details")

        response = handle_request(event(), resolver=resolver)

        self.assertEqual(response["statusCode"], 502)
        self.assertEqual(json.loads(response["body"])["error"]["code"], "KAKAO_PLACE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
