import os
import httpx
from dotenv import load_dotenv

load_dotenv()

ES_URL = os.getenv("ES_URL")
ES_API_KEY = os.getenv("ES_API_KEY")


def es_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if ES_API_KEY:
        headers["Authorization"] = ES_API_KEY
    return headers


def es_get_mapping(index: str) -> dict:
    url = f"{ES_URL}/{index}/_mapping"
    with httpx.Client() as client:
        response = client.get(url, headers=es_headers(), timeout=30)
        response.raise_for_status()
        return response.json()


def es_get_flat_mapping(index: str) -> dict:
    """
    Get the flat mapping for an index.
    """
    raw_mapping = es_get_mapping(index)
    actual_index = list(raw_mapping.keys())[0]
    properties = raw_mapping[actual_index]["mappings"].get("properties", {})
    excludes = raw_mapping[actual_index]["mappings"].get("_source", {}).get("excludes", [])
    return _flatten_properties(properties, excludes)


def _flatten_properties(properties: dict, excludes: list = [], prefix: str = "") -> dict:
    """
    Recursively flatten ES mapping properties to dotted paths.

    Returns a dict:
        { "authors.fullName": {"type": "text", "fields": {...}, ...}, ... }
    """
    result = {}
    for field_name, field_def in properties.items():
        path = f"{prefix}.{field_name}" if prefix else field_name
        es_type = field_def.get("type", "object")

        result[path] = {
            "type": es_type,
            "exclude": path in excludes,
            # keep useful ES-level metadata
            "fields": field_def.get("fields"),  # multi-fields (keyword, etc.)
            "format": field_def.get("format"),  # date formats
            "index": field_def.get("index", True),
            "store": field_def.get("store", False),
            "analyzer": field_def.get("analyzer"),
        }

        # Remove None values to keep the output clean
        result[path] = {k: v for k, v in result[path].items() if v is not None}

        # Recurse into nested / object properties
        nested = field_def.get("properties")
        if nested:
            result.update(_flatten_properties(nested, excludes, prefix=path))

        # Recurse into array items that have properties
        items_props = field_def.get("items", {}).get("properties")
        if items_props:
            result.update(_flatten_properties(items_props, excludes, prefix=path))

    return result
