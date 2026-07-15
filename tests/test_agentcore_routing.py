# @file tests/test_agentcore_routing.py
# @description Unit tests for Kakao Mobility route fetching, chunking, enrichment, and fallback behavior.
# @author JJonyeok2
# @lastModified 2026-07-15

import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentcore.routing import _get_json, enrich_itinerary_routes


def kakao_response(distance=4200, duration=780):
    return kakao_response_with_sections([(distance, duration)])


def kakao_response_with_sections(leg_values):
    sections = []
    for index, (distance, duration) in enumerate(leg_values):
        sections.append(
            {
                "distance": distance,
                "duration": duration,
                "roads": [
                    {
                        "vertexes": [
                            128.947 - index / 100,
                            37.771 + index / 100,
                            128.930 - index / 100,
                            37.790 + index / 100,
                        ]
                    }
                ],
            }
        )
    return {
        "routes": [
            {
                "result_code": 0,
                "result_msg": "길찾기 성공",
                "summary": {
                    "distance": sum(distance for distance, _ in leg_values),
                    "duration": sum(duration for _, duration in leg_values),
                },
                "sections": sections,
            }
        ]
    }


class AgentCoreRoutingTest(unittest.TestCase):
    def test_enriches_itinerary_day_with_kakao_geometry_and_leg_summary(self):
        itinerary = {
            "days": [
                {
                    "day": 1,
                    "items": [
                        {"title": "안목해변", "latitude": 37.771, "longitude": 128.947},
                        {"title": "경포해변", "latitude": 37.805, "longitude": 128.908},
                    ],
                }
            ]
        }

        def fake_get_json(url, api_key, timeout_seconds):
            self.assertEqual(api_key, "test-kakao-key")
            parsed_url = parse.urlparse(url)
            query = parse.parse_qs(parsed_url.query)
            self.assertEqual(parsed_url.path, "/v1/directions")
            self.assertEqual(query["origin"], ["128.947,37.771"])
            self.assertEqual(query["destination"], ["128.908,37.805"])
            self.assertEqual(query["summary"], ["false"])
            self.assertEqual(timeout_seconds, 3.0)
            return kakao_response()

        with patch.dict(
            os.environ,
            {
                "KAKAO_MOBILITY_REST_API_KEY": "test-kakao-key",
                "KAKAO_MOBILITY_TIMEOUT_SECONDS": "3",
            },
            clear=False,
        ):
            with patch("agentcore.routing._get_json", side_effect=fake_get_json) as get_json:
                enriched = enrich_itinerary_routes(itinerary)

        day = enriched["days"][0]
        self.assertEqual(get_json.call_count, 1)
        self.assertEqual(day["route"]["provider"], "kakao-mobility")
        self.assertEqual(day["route"]["profile"], "driving-car")
        self.assertEqual(day["route"]["geometry"]["type"], "LineString")
        self.assertEqual(day["route"]["geometry"]["coordinates"][0], [128.947, 37.771])
        self.assertEqual(day["route"]["distanceMeters"], 4200)
        self.assertEqual(day["route"]["durationSeconds"], 780)
        self.assertEqual(day["items"][0]["moveMinutes"], 13)
        self.assertEqual(day["items"][0]["moveDistanceMeters"], 4200)

    def test_skips_route_enrichment_when_kakao_key_is_missing(self):
        itinerary = {
            "days": [
                {
                    "day": 1,
                    "items": [
                        {"title": "A", "latitude": 37.1, "longitude": 127.1},
                        {"title": "B", "latitude": 37.2, "longitude": 127.2},
                    ],
                }
            ]
        }

        with patch.dict(
            os.environ,
            {"KAKAO_MOBILITY_REST_API_KEY": "", "KAKAO_MOBILITY_REST_API_KEY_SSM_NAME": ""},
            clear=False,
        ):
            with patch("agentcore.routing._get_json") as get_json:
                enriched = enrich_itinerary_routes(itinerary)

        self.assertIs(enriched, itinerary)
        self.assertNotIn("route", enriched["days"][0])
        get_json.assert_not_called()

    def test_reads_kakao_key_from_ssm_name_when_direct_env_key_is_missing(self):
        itinerary = {
            "days": [
                {
                    "day": 1,
                    "items": [
                        {"title": "A", "latitude": 37.1, "longitude": 127.1},
                        {"title": "B", "latitude": 37.2, "longitude": 127.2},
                    ],
                }
            ]
        }

        with patch.dict(
            os.environ,
            {
                "KAKAO_MOBILITY_REST_API_KEY": "",
                "KAKAO_MOBILITY_REST_API_KEY_SSM_NAME": "/lovv/dev/kakao_mobility/rest_api_key",
            },
            clear=False,
        ):
            with patch("agentcore.routing._get_ssm_parameter", return_value="ssm-kakao-key") as get_parameter:
                with patch("agentcore.routing._get_json", return_value=kakao_response()) as get_json:
                    enriched = enrich_itinerary_routes(itinerary)

        self.assertEqual(get_parameter.call_args.args[0], "/lovv/dev/kakao_mobility/rest_api_key")
        self.assertEqual(get_json.call_args.args[1], "ssm-kakao-key")
        self.assertEqual(enriched["days"][0]["route"]["provider"], "kakao-mobility")

    def test_splits_more_than_five_waypoints_and_merges_route_chunks(self):
        items = [
            {"title": str(index), "latitude": 37.0 + index / 100, "longitude": 127.0 + index / 100}
            for index in range(9)
        ]
        itinerary = {"days": [{"day": 1, "items": items}]}

        responses = [
            kakao_response_with_sections([(1000, 60)] * 6),
            kakao_response_with_sections([(1000, 60)] * 2),
        ]

        with patch.dict(os.environ, {"KAKAO_MOBILITY_REST_API_KEY": "test-kakao-key"}, clear=False):
            with patch("agentcore.routing._get_json", side_effect=responses) as get_json:
                enriched = enrich_itinerary_routes(itinerary)

        route = enriched["days"][0]["route"]
        first_query = parse.parse_qs(parse.urlparse(get_json.call_args_list[0].args[0]).query)
        second_query = parse.parse_qs(parse.urlparse(get_json.call_args_list[1].args[0]).query)
        self.assertEqual(get_json.call_count, 2)
        self.assertEqual(first_query["origin"], ["127.0,37.0"])
        self.assertEqual(first_query["destination"], ["127.06,37.06"])
        self.assertEqual(len(first_query["waypoints"][0].split("|")), 5)
        self.assertEqual(second_query["origin"], ["127.06,37.06"])
        self.assertEqual(second_query["destination"], ["127.08,37.08"])
        self.assertEqual(len(second_query["waypoints"][0].split("|")), 1)
        self.assertEqual(route["distanceMeters"], 8000)
        self.assertEqual(route["durationSeconds"], 480)
        self.assertEqual(len(route["segments"]), 8)
        self.assertTrue(all(item.get("moveDistanceMeters") == 1000 for item in items[:-1]))
        self.assertTrue(all(item.get("moveMinutes") == 1 for item in items[:-1]))

    def test_enriches_multiple_days_concurrently_with_isolated_failures(self):
        itinerary = {
            "days": [
                {
                    "day": day_number,
                    "items": [
                        {"title": "A", "latitude": 37.1, "longitude": 127.0 + day_number},
                        {"title": "B", "latitude": 37.2, "longitude": 127.5 + day_number},
                    ],
                }
                for day_number in range(1, 4)
            ]
        }
        all_workers_started = threading.Barrier(3)
        release_first_day = threading.Event()

        def fake_fetch_route(**kwargs):
            all_workers_started.wait(timeout=1)
            day_number = int(kwargs["coordinates"][0][0] - 127.0)
            if day_number == 2:
                raise TimeoutError("simulated Kakao timeout")
            if day_number == 1:
                self.assertTrue(release_first_day.wait(timeout=1))
            else:
                release_first_day.set()
            distance_meters = day_number * 1000
            return {
                "provider": "kakao-mobility",
                "profile": "driving-car",
                "geometry": {"type": "LineString", "coordinates": []},
                "distanceMeters": distance_meters,
                "durationSeconds": 180,
                "segments": [{"distanceMeters": distance_meters, "durationSeconds": 180}],
            }

        with patch.dict(os.environ, {"KAKAO_MOBILITY_REST_API_KEY": "test-kakao-key"}, clear=False):
            with patch("agentcore.routing._fetch_route", side_effect=fake_fetch_route) as fetch_route:
                enriched = enrich_itinerary_routes(itinerary)

        self.assertEqual(fetch_route.call_count, 3)
        self.assertEqual(enriched["days"][0]["route"]["distanceMeters"], 1000)
        self.assertNotIn("route", enriched["days"][1])
        self.assertEqual(enriched["days"][2]["route"]["distanceMeters"], 3000)

    def test_get_json_sends_kakao_authorization_header(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"routes":[]}'

        def fake_urlopen(http_request, timeout):
            captured["accept"] = http_request.get_header("Accept")
            captured["authorization"] = http_request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("agentcore.routing.request.urlopen", side_effect=fake_urlopen):
            response = _get_json("https://apis-navi.kakaomobility.com/v1/directions", "test-kakao-key", 3.0)

        self.assertEqual(response, {"routes": []})
        self.assertEqual(captured["accept"], "application/json")
        self.assertEqual(captured["authorization"], "KakaoAK test-kakao-key")
        self.assertEqual(captured["timeout"], 3.0)


if __name__ == "__main__":
    unittest.main()

# EOF: tests/test_agentcore_routing.py
