#!/usr/bin/env python3
"""Local-only HTTP server for verifying the Lovv admin console <-> backend wiring.

Why this exists
---------------
The admin proposal APIs (``/api/v1/admin/data-proposals*``) talk to Aurora MySQL
through a VPC. Running them with ``sam local start-api`` still needs a reachable
RDS instance with the admin tables applied, so it is not a practical way to
verify the frontend integration during development.

This script mounts the *real* admin Lambda handler (``src/admin/app.py``) on top
of the in-memory repositories used by the unit tests, and exposes them over plain
HTTP. The frontend dev server can then exercise the full
``list -> review -> approve / reject -> history`` flow without SAM, RDS, or AWS.

It is a development tool only. It is never imported by Lambda and must not be
deployed.

Usage
-----
    python scripts/local_admin_server.py
    # then point the admin web .env at it:
    #   VITE_LOVV_API_BASE_URL=http://localhost:3000
    #   VITE_LOVV_ADMIN_ACCESS_TOKEN=<token printed on startup>

Environment
-----------
Reads ``.env`` from the repository root if present (AUTH_TOKEN_SIGNING_SECRET,
CORS_ALLOW_ORIGINS, ...). Falls back to safe local defaults otherwise. The
signing secret used here must match the one used to mint the frontend dev token.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def _load_dotenv(path):
    """Minimal .env loader (KEY=VALUE lines). Does not override existing env."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")

# Local defaults so the server runs even without a .env file.
os.environ.setdefault("AUTH_TOKEN_SIGNING_SECRET", "lovv-local-admin-dev-secret")
os.environ.setdefault("AUTH_TOKEN_TTL_SECONDS", "86400")
os.environ.setdefault(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
)

from admin.app import handle_request  # noqa: E402  (after sys.path / env setup)
from admin.proposals_repository import InMemoryAdminProposalRepository  # noqa: E402
from shared.auth import create_access_token  # noqa: E402


HOST = os.environ.get("LOCAL_ADMIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOCAL_ADMIN_PORT", "3000"))

# Stable demo identities so seeded data and tokens line up.
DATA_PROVIDER = {
    "userId": "dev-data-provider-1",
    "roles": ["R-DATA-PROVIDER"],
    "organizationIds": ["org-gangneung-tourism"],
    "regionIds": [],
}
ADMIN = {
    "userId": "dev-admin-1",
    "roles": ["R-ADMIN"],
    "organizationIds": [],
    "regionIds": [],
}


def _make_repository():
    """In-memory proposal repo seeded with a few proposals across statuses."""
    repo = InMemoryAdminProposalRepository(now="2026-06-23T09:00:00Z")

    seeds = [
        {
            "contentType": "festival",
            "regionId": "KR-42-150",
            "cityId": "KR-Gangneung",
            "cityName": "강릉",
            "title": "강릉 커피 골목 야간 투어",
            "description": "야간 카페 거리와 해변 산책을 묶은 저강도 체험 후보입니다.",
            "officialSourceName": "강릉시 관광과",
            "officialSourceUrl": "https://example.gangneung.go.kr/coffee-night",
            "evidenceText": "지역 축제 일정표, 운영자 검수 메모, 이미지 링크",
        },
        {
            "contentType": "attraction",
            "regionId": "KR-47-130",
            "cityId": "KR-Gyeongju",
            "cityName": "경주",
            "title": "경주 황리단길 아침 산책 코스",
            "description": "이른 아침 한적한 황리단길 도보 코스입니다.",
            "officialSourceName": "경주시 문화관광",
            "evidenceText": "현지 운영자 추천 동선",
        },
        {
            "contentType": "experience",
            "regionId": "JP-44-201",
            "cityName": "벳푸",
            "title": "벳푸 온천 숙소 체류 추천",
            "description": "온천 중심의 1박 체류형 추천 후보입니다.",
            "evidenceText": "숙소 제휴 정보, 온천 운영 시간",
        },
    ]

    created = [repo.create(DATA_PROVIDER, seed, now="2026-06-23T09:00:00Z") for seed in seeds]

    # Move one into review, and approve another, so the FE shows multiple statuses.
    repo.transition(created[1]["proposalId"], "in_review", ADMIN, now="2026-06-23T09:30:00Z",
                    note="근거 자료 확인 중")
    repo.transition(created[2]["proposalId"], "in_review", ADMIN, now="2026-06-23T09:35:00Z")
    repo.transition(created[2]["proposalId"], "approved", ADMIN, now="2026-06-23T09:40:00Z",
                    note="단일 소도시 원칙 충족, 승인")

    return repo


PROPOSAL_REPOSITORY = _make_repository()


def _build_event(method, path, query, headers, body):
    """Translate an HTTP request into the API-Gateway-style event the handler expects."""
    lower_headers = {key.lower(): value for key, value in headers.items()}
    return {
        "rawPath": path,
        "headers": lower_headers,
        "queryStringParameters": query or None,
        "requestContext": {"http": {"method": method, "path": path}},
        "body": body,
    }


class AdminRequestHandler(BaseHTTPRequestHandler):
    server_version = "LovvLocalAdmin/1.0"

    def _dispatch(self, method):
        raw_path = self.path
        path, _, raw_query = raw_path.partition("?")
        query = {}
        for pair in raw_query.split("&"):
            if not pair:
                continue
            key, _, value = pair.partition("=")
            query[key] = value

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else None

        event = _build_event(method, path, query, dict(self.headers), body)
        try:
            result = handle_request(event, proposal_repository=PROPOSAL_REPOSITORY)
        except Exception as error:  # pragma: no cover - defensive, handler already guards
            result = {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": {"code": "LOCAL_SERVER_ERROR", "message": str(error)}}),
            }

        status = int(result.get("statusCode", 500))
        response_body = (result.get("body") or "").encode("utf-8")
        self.send_response(status)
        for key, value in (result.get("headers") or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def log_message(self, fmt, *args):
        sys.stderr.write("[local-admin] %s - %s\n" % (self.address_string(), fmt % args))


def _print_banner():
    admin_token = create_access_token(
        user_id=ADMIN["userId"],
        session_id="dev-admin-session",
        roles=ADMIN["roles"],
        organization_ids=ADMIN["organizationIds"],
        region_ids=ADMIN["regionIds"],
    ).token
    provider_token = create_access_token(
        user_id=DATA_PROVIDER["userId"],
        session_id="dev-provider-session",
        roles=DATA_PROVIDER["roles"],
        organization_ids=DATA_PROVIDER["organizationIds"],
        region_ids=DATA_PROVIDER["regionIds"],
    ).token

    print("=" * 72)
    print(" Lovv local admin API server (in-memory, no RDS / no SAM)")
    print("=" * 72)
    print(f" Listening on   : http://{HOST}:{PORT}")
    print(f" CORS allowed   : {os.environ.get('CORS_ALLOW_ORIGINS')}")
    print(f" Signing secret : {os.environ.get('AUTH_TOKEN_SIGNING_SECRET')}")
    print(" Seeded proposals: 3 (submitted / in_review / approved)")
    print("-" * 72)
    print(" Dev tokens (24h). Put one in admin web .env as VITE_LOVV_ADMIN_ACCESS_TOKEN:")
    print("")
    print(" R-ADMIN (review/approve/reject/history):")
    print(f"   {admin_token}")
    print("")
    print(" R-DATA-PROVIDER (create/list own proposals):")
    print(f"   {provider_token}")
    print("=" * 72)
    sys.stdout.flush()


def main():
    _print_banner()
    server = ThreadingHTTPServer((HOST, PORT), AdminRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[local-admin] shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
