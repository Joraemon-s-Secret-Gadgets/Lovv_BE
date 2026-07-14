# @file src/agentcore/routing.py
# @description Optional Kakao Mobility itinerary route enrichment for AgentCore results.
# @lastModified 2026-07-14

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import parse, request

from shared.logger import Tag, get_logger


LOGGER = get_logger(__name__)
DEFAULT_KAKAO_MOBILITY_BASE_URL = "https://apis-navi.kakaomobility.com"
DEFAULT_KAKAO_MOBILITY_TIMEOUT_SECONDS = 3.0
MAX_KAKAO_ROUTE_POINTS = 7
MAX_ROUTE_ENRICHMENT_WORKERS = 4
_ssm_client = None
_ssm_parameter_cache = {}


def calculate_route(coordinates):
    """Calculate one normalized route for an authenticated API request."""
    api_key = _kakao_mobility_api_key()
    if not api_key:
        return None

    base_url = (os.environ.get("KAKAO_MOBILITY_BASE_URL") or DEFAULT_KAKAO_MOBILITY_BASE_URL).strip().rstrip("/")
    return _fetch_route(
        base_url=base_url,
        api_key=api_key,
        coordinates=coordinates,
        timeout_seconds=_timeout_seconds(),
    )


def enrich_itinerary_routes(itinerary):
    """Attach Kakao Mobility route geometry without blocking itinerary creation."""
    api_key = _kakao_mobility_api_key()
    if not api_key or not isinstance(itinerary, dict):
        return itinerary

    days = itinerary.get("days")
    if not isinstance(days, list):
        return itinerary

    base_url = (os.environ.get("KAKAO_MOBILITY_BASE_URL") or DEFAULT_KAKAO_MOBILITY_BASE_URL).strip().rstrip("/")
    timeout_seconds = _timeout_seconds()
    route_jobs = []

    for day in days:
        if not isinstance(day, dict):
            continue
        items = day.get("items") or day.get("stops")
        if not isinstance(items, list):
            continue

        points = _valid_route_points(items)
        if len(points) >= 2:
            route_jobs.append((day, items, points))

    if not route_jobs:
        return itinerary

    worker_count = min(len(route_jobs), MAX_ROUTE_ENRICHMENT_WORKERS)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _fetch_route,
                base_url=base_url,
                api_key=api_key,
                coordinates=[point["coordinate"] for point in points],
                timeout_seconds=timeout_seconds,
            ): (day, items, points)
            for day, items, points in route_jobs
        }

        for future in as_completed(futures):
            day, items, points = futures[future]
            try:
                route_result = future.result()
            except Exception as error:
                LOGGER.warning(
                    Tag.PLAN,
                    "Kakao Mobility route enrichment skipped day=%s pointCount=%s errorType=%s",
                    day.get("day"),
                    len(points),
                    error.__class__.__name__,
                )
                continue

            if route_result:
                day["route"] = route_result
                _apply_leg_summaries(items, points, route_result.get("segments") or [])

    return itinerary


def _fetch_route(base_url, api_key, coordinates, timeout_seconds):
    chunks = []
    start_index = 0
    while start_index < len(coordinates) - 1:
        end_index = min(start_index + MAX_KAKAO_ROUTE_POINTS, len(coordinates))
        chunk = _fetch_route_chunk(
            base_url=base_url,
            api_key=api_key,
            coordinates=coordinates[start_index:end_index],
            timeout_seconds=timeout_seconds,
        )
        if not chunk:
            return None
        chunks.append(chunk)
        start_index = end_index - 1

    geometry_coordinates = []
    segments = []
    for chunk in chunks:
        _extend_unique_coordinates(geometry_coordinates, chunk["geometry"]["coordinates"])
        segments.extend(chunk["segments"])

    return {
        "provider": "kakao-mobility",
        "profile": "driving-car",
        "geometry": {"type": "LineString", "coordinates": geometry_coordinates},
        "distanceMeters": sum(segment["distanceMeters"] for segment in segments),
        "durationSeconds": sum(segment["durationSeconds"] for segment in segments),
        "segments": segments,
    }


def _fetch_route_chunk(base_url, api_key, coordinates, timeout_seconds):
    query = {
        "origin": _coordinate_param(coordinates[0]),
        "destination": _coordinate_param(coordinates[-1]),
        "priority": "RECOMMEND",
        "summary": "false",
    }
    if len(coordinates) > 2:
        query["waypoints"] = "|".join(_coordinate_param(coordinate) for coordinate in coordinates[1:-1])

    url = f"{base_url}/v1/directions?{parse.urlencode(query)}"
    response = _get_json(url, api_key, timeout_seconds)
    route = _first_successful_route(response)
    if not route:
        return None

    sections = route.get("sections")
    if not isinstance(sections, list) or not sections:
        return None

    geometry_coordinates = []
    segments = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        segments.append(
            {
                "distanceMeters": int(float(section.get("distance") or 0)),
                "durationSeconds": int(float(section.get("duration") or 0)),
            }
        )
        for road in section.get("roads") or []:
            if not isinstance(road, dict):
                continue
            vertexes = road.get("vertexes")
            if not isinstance(vertexes, list):
                continue
            road_coordinates = []
            for index in range(0, len(vertexes) - 1, 2):
                longitude = _number_or_none(vertexes[index])
                latitude = _number_or_none(vertexes[index + 1])
                if longitude is not None and latitude is not None:
                    road_coordinates.append([longitude, latitude])
            _extend_unique_coordinates(geometry_coordinates, road_coordinates)

    if not geometry_coordinates or not segments:
        return None
    return {
        "geometry": {"type": "LineString", "coordinates": geometry_coordinates},
        "segments": segments,
    }


def _get_json(url, api_key, timeout_seconds):
    http_request = request.Request(
        url,
        headers={
            "Authorization": f"KakaoAK {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="GET",
    )
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _kakao_mobility_api_key():
    direct_key = (os.environ.get("KAKAO_MOBILITY_REST_API_KEY") or "").strip()
    if direct_key:
        return direct_key

    parameter_name = (os.environ.get("KAKAO_MOBILITY_REST_API_KEY_SSM_NAME") or "").strip()
    if not parameter_name:
        return ""
    try:
        return _get_ssm_parameter(parameter_name).strip()
    except Exception as error:
        LOGGER.warning(
            Tag.PLAN,
            "Kakao Mobility key lookup skipped source=ssm errorType=%s",
            error.__class__.__name__,
        )
        return ""


def _get_ssm_parameter(parameter_name):
    cached_value = _ssm_parameter_cache.get(parameter_name)
    if cached_value is not None:
        return cached_value

    global _ssm_client
    if _ssm_client is None:
        import boto3

        _ssm_client = boto3.client("ssm")
    response = _ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
    value = ((response.get("Parameter") or {}).get("Value") or "").strip()
    _ssm_parameter_cache[parameter_name] = value
    return value


def _valid_route_points(items):
    points = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        latitude = _number_or_none(item.get("latitude"))
        longitude = _number_or_none(item.get("longitude"))
        if latitude is None or longitude is None:
            continue
        points.append({"itemIndex": index, "coordinate": [longitude, latitude]})
    return points


def _apply_leg_summaries(items, points, segments):
    for segment_index, segment in enumerate(segments):
        if segment_index >= len(points) - 1:
            break
        item_index = points[segment_index]["itemIndex"]
        item = items[item_index]
        duration_seconds = int(float(segment.get("durationSeconds") or segment.get("duration") or 0))
        distance_meters = int(float(segment.get("distanceMeters") or segment.get("distance") or 0))
        if duration_seconds > 0:
            item["moveMinutes"] = max(1, math.ceil(duration_seconds / 60))
            item["moveDurationSeconds"] = duration_seconds
        if distance_meters > 0:
            item["moveDistanceMeters"] = distance_meters


def _first_successful_route(response):
    if not isinstance(response, dict):
        return None
    routes = response.get("routes")
    if not isinstance(routes, list):
        return None
    for route in routes:
        if isinstance(route, dict) and route.get("result_code") == 0:
            return route
    return None


def _coordinate_param(coordinate):
    return f"{coordinate[0]},{coordinate[1]}"


def _extend_unique_coordinates(target, coordinates):
    for coordinate in coordinates:
        if not target or target[-1] != coordinate:
            target.append(coordinate)


def _number_or_none(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def _timeout_seconds():
    raw_value = os.environ.get("KAKAO_MOBILITY_TIMEOUT_SECONDS")
    if not raw_value:
        return DEFAULT_KAKAO_MOBILITY_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_KAKAO_MOBILITY_TIMEOUT_SECONDS
    if value <= 0:
        return DEFAULT_KAKAO_MOBILITY_TIMEOUT_SECONDS
    return min(value, 10.0)
