from small_cities.mapper import build_city_api_record


DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 120
MAX_PAGE_SIZE = 120


def normalize_search_text(value):
    return value.casefold() if isinstance(value, str) else ""


def get_search_blob(record):
    values = [
        record.get("id"),
        record.get("country_label"),
        record.get("region"),
        record.get("name_ko"),
        record.get("name_local"),
        record.get("summary"),
        record.get("detail"),
        *(record.get("themes") or []),
        *(record.get("highlights") or []),
        *(record.get("route_seed") or []),
    ]
    return normalize_search_text(" ".join(value for value in values if isinstance(value, str)))


class SmallCityService:
    def __init__(self, repository, city_records=None):
        self.repository = repository
        self.city_records = city_records

    def list_cities(self, country=None, query=None, themes=None, page=DEFAULT_PAGE, page_size=DEFAULT_PAGE_SIZE):
        records = list(self._load_city_records())
        selected_themes = themes or []
        normalized_query = normalize_search_text(query or "")

        if country:
            records = [record for record in records if record.get("country") == country]

        if selected_themes:
            records = [
                record
                for record in records
                if any(theme in (record.get("themes") or []) for theme in selected_themes)
            ]

        if normalized_query:
            records = [record for record in records if normalized_query in get_search_blob(record)]

        total = len(records)
        start = (page - 1) * page_size
        end = start + page_size
        page_records = records[start:end]

        return {
            "data": page_records,
            "page": {
                "page": page,
                "pageSize": page_size,
                "total": total,
                "hasNext": end < total,
            },
        }

    def list_markers(self, country=None, query=None, themes=None, page=DEFAULT_PAGE, page_size=DEFAULT_PAGE_SIZE):
        result = self.list_cities(country=country, query=query, themes=themes, page=page, page_size=page_size)
        return {
            "data": [marker_from_city(record) for record in result["data"]],
            "page": result["page"],
        }

    def get_city(self, city_id):
        if self.city_records is not None:
            return next((record for record in self.city_records if record.get("id") == city_id), None)

        return self.repository.get_city_record(city_id)

    def get_city_places(self, city_id):
        if self.repository is None or not hasattr(self.repository, "get_city_places"):
            return None
        return self.repository.get_city_places(city_id)

    def _load_city_records(self):
        if self.city_records is not None:
            return self.city_records

        return self.repository.list_city_records()

    @staticmethod
    def build_record_from_items(metadata, items):
        return build_city_api_record(metadata, items)


def marker_from_city(record):
    return {
        "cityId": record.get("id"),
        "name": record.get("name_ko"),
        "country": record.get("country"),
        "countryLabel": record.get("country_label"),
        "region": record.get("region"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "imageUrl": record.get("image_url"),
    }
