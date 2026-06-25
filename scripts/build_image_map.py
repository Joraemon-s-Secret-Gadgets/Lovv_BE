#!/usr/bin/env python3
"""
S3 이미지 버킷(lovv-image-dev-*)을 스캔해서
{ "KR-Cheongdo/청도박물관": "images/KR/Cheongdo/Cheongdobakmulwan_1.jpg" }
형식의 매핑 JSON을 생성하는 스크립트.

실행:
    python3 scripts/build_image_map.py --profile jjonyeok --region us-east-1
"""

import argparse
import json
import re
import sys


IMAGE_BUCKET = "lovv-image-dev-925273580929"
IMAGE_PREFIX = "images/KR/"
CDN_BASE = "https://det7vj7wxfmim.cloudfront.net"

# Korean Revised Romanization tables (same as frontend)
ONSET = [
    'g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's', 'ss', '',
    'j', 'jj', 'ch', 'k', 't', 'p', 'h',
]
VOWEL = [
    'a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o',
    'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu',
    'eu', 'ui', 'i',
]
CODA = [
    "",    # 0  (없음)
    "k",   # 1  ㄱ
    "k",   # 2  ㄲ
    "k",   # 3  ㄳ
    "n",   # 4  ㄴ
    "n",   # 5  ㄵ
    "n",   # 6  ㄶ
    "t",   # 7  ㄷ
    "l",   # 8  ㄹ
    "k",   # 9  ㄺ
    "m",   # 10 ㄻ
    "p",   # 11 ㄼ
    "l",   # 12 ㄽ
    "k",   # 13 ㄾ
    "p",   # 14 ㄿ
    "l",   # 15 ㅀ
    "m",   # 16 ㅁ
    "p",   # 17 ㅂ
    "p",   # 18 ㅄ
    "t",   # 19 ㅅ
    "t",   # 20 ㅆ
    "ng",  # 21 ㅇ
    "t",   # 22 ㅈ
    "t",   # 23 ㅊ
    "k",   # 24 ㅋ
    "t",   # 25 ㅌ
    "p",   # 26 ㅍ
    "h",   # 27 ㅎ
]
HANGUL_START = 0xAC00


def romanize_korean(text: str) -> str:
    result = []
    for ch in text:
        code = ord(ch)
        if HANGUL_START <= code <= 0xD7A3:
            offset = code - HANGUL_START
            onset_idx = offset // (21 * 28)
            vowel_idx = (offset % (21 * 28)) // 28
            coda_idx = offset % 28
            result.append(ONSET[onset_idx] + VOWEL[vowel_idx] + CODA[coda_idx])
        else:
            result.append(ch.lower())
    return ''.join(result)


def romanize_title_to_s3_stem(title: str) -> str:
    """
    한국어 제목 → S3 파일명 stem (PascalCase per word).
    예: '봉화 북지리 마애여래좌상' → 'BonghwaBukjiriMaeyeoraejwasang'
    """
    parts = []
    for word in title.split():
        r = re.sub(r'[^a-z0-9]', '', romanize_korean(word))
        if r:
            parts.append(r[0].upper() + r[1:])
    return ''.join(parts)


def list_all_keys(s3_client, bucket, prefix):
    keys = []
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        resp = s3_client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            keys.append(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = resp["NextContinuationToken"]
    return keys


def build_image_map(s3_client):
    """
    Returns dict: { "KR-<City>/<stem>": "images/KR/<City>/<Filename>_1.jpg" }
    Only _1.jpg (primary) images are included.
    """
    print(f"Scanning s3://{IMAGE_BUCKET}/{IMAGE_PREFIX} ...", file=sys.stderr)
    all_keys = list_all_keys(s3_client, IMAGE_BUCKET, IMAGE_PREFIX)
    print(f"Found {len(all_keys)} objects.", file=sys.stderr)

    mapping = {}
    for key in all_keys:
        # key format: images/KR/<City>/<Stem>_N.jpg
        if not key.endswith("_1.jpg"):
            continue
        # parse city and stem
        # images/KR/Cheongdo/Cheongdobakmulwan_1.jpg
        parts = key.split("/")
        if len(parts) < 4:
            continue
        city_en = parts[2]          # e.g. "Cheongdo"
        filename = parts[3]          # e.g. "Cheongdobakmulwan_1.jpg"
        stem = filename[:-len("_1.jpg")]  # e.g. "Cheongdobakmulwan"

        map_key = f"KR-{city_en}/{stem}"
        mapping[map_key] = key

    print(f"Built {len(mapping)} primary image entries.", file=sys.stderr)
    return mapping


def main():
    parser = argparse.ArgumentParser(description="Build S3 image URL mapping JSON")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--output", default="scripts/image_map.json")
    args = parser.parse_args()

    try:
        import boto3
    except ImportError:
        print("boto3 is required. Run: pip install boto3", file=sys.stderr)
        sys.exit(1)

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = session.client("s3")

    mapping = build_image_map(s3)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"cdnBase": CDN_BASE, "images": mapping}, f, ensure_ascii=False, indent=2)

    print(f"Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
