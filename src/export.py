"""
export.py — generate api/schema.json and mcp/schema.json from approved annotations.

Usage:
    python export.py
    python export.py --include-draft    # include draft fields with empty description
"""

import json
import argparse
from pathlib import Path

from src.utils import load_annotations, get_config


def _build_nested_properties(properties: dict, keys: list[str], infos: dict) -> dict:
    """
    Helper to recursively build nested properties.

    For a dotted path like "authors.affiliations.name", this produces valid JSON Schema.
    """
    current_key = keys[0]
    remaining_keys = keys[1:]

    if current_key not in properties:
        properties[current_key] = {}

    if len(remaining_keys) == 0:
        # Leaf node: apply the schema info directly
        if infos.get("type") == "array":
            if "items" not in properties[current_key]:
                properties[current_key]["items"] = {}
            if infos.get("has_keyword", False):
                properties[current_key]["items"].update({"type": "string"})
        props = infos_to_schema(infos)
        properties[current_key].update(props)
    else:
        node = properties[current_key]
        if node.get("type") == "array":
            # Array type: children go into items.properties
            if "items" not in node:
                node["items"] = {"type": "object"}
            if "properties" not in node["items"]:
                node["items"]["properties"] = {}
            if "required" not in node["items"]:
                node["items"]["required"] = []
            if len(remaining_keys) == 1:
                node["items"]["required"].append(remaining_keys[0])
            _build_nested_properties(node["items"]["properties"], remaining_keys, infos)
        else:
            # Object type (default): children go into properties
            if "type" not in node:
                node["type"] = "object"
            if "properties" not in node:
                node["properties"] = {}
            if "required" not in node:
                node["required"] = []
            if len(remaining_keys) == 1:
                node["required"].append(remaining_keys[0])
            _build_nested_properties(node["properties"], remaining_keys, infos)

    return properties


def infos_to_schema(info: dict) -> dict:
    type = info.get("type", "object")
    description = info.get("description", "")

    type_map = {
        "text": "string",
        "keyword": "string",
        "long": "integer",
        "integer": "integer",
        "short": "integer",
        "byte": "integer",
        "double": "number",
        "float": "number",
        "boolean": "boolean",
        "date": "string",
        "object": "object",
        "array": "array",
        "nested": "array",
        "ip": "string",
        "geo_point": "object",
    }
    json_type = type_map.get(type, "object")

    schema = {"type": json_type}
    if description:
        schema["description"] = description
    if info.get("enum"):
        schema["enum"] = info["enum"]
    if info.get("example"):
        schema["example"] = info["example"]

    return schema


def build_json_schema(index, annotations: dict, include_draft: bool = False, include_ai_suggestion: bool = False) -> dict:
    fields = annotations.get("fields", {})

    # Filter fields
    selected = {
        path: info
        for path, info in fields.items()
        if info.get("status") == "approved" or (include_draft and info.get("status") == "draft")
    }

    # Add ai_suggestion to description if include_ai_suggestion is True
    if include_ai_suggestion:
        for path, info in selected.items():
            if not info.get("description") and info.get("ai_suggestion", {}).get("description"):
                info["description"] = info["ai_suggestion"]["description"]

    # Build top-level JSON Schema
    properties = {}
    for dotted_key, infos in sorted(selected.items()):
        keys = dotted_key.split(".")
        properties.update(_build_nested_properties(properties, keys, infos))

    config = get_config(index)
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "description": config["content"],
        "properties": properties,
    }

    return schema


def save_schema(schema: dict, path: Path):
    with open(path, "w") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Export annotations to JSON Schema files")
    parser.add_argument("--index", "-i", required=True, help="Index to export")
    parser.add_argument("--include-draft", action="store_true", help="Include draft fields with empty description")
    parser.add_argument("--include-ai-suggestion", action="store_true", help="Include AI suggestions in the schema")
    args = parser.parse_args()

    index = args.index
    config = get_config(index)
    annotations_path = f"annotations/{config['annotation']}"

    out_dir = Path("schemas")
    out_dir.mkdir(parents=True, exist_ok=True)

    annotations = load_annotations(annotations_path)
    meta = annotations.get("_meta", {})

    approved = meta.get("approved", 0)
    draft = meta.get("draft", 0)
    print(f"[export] {approved} approved fields, {draft} draft {'(skipped)' if not args.include_draft else ''}")

    # 1. API schema (clean JSON Schema, no extensions)
    api_schema = build_json_schema(
        index, annotations, include_draft=args.include_draft, include_ai_suggestion=args.include_ai_suggestion
    )
    api_path = out_dir.joinpath(config["schema"])
    save_schema(api_schema, api_path)
    print(f"[export] API schema → {api_path}")

    # 2. Summary stats
    fields = annotations.get("fields", {})
    primary_count = sum(1 for f in fields.values() if f.get("primary") and f.get("status") == "approved")
    crossref_count = sum(1 for f in fields.values() if f.get("cross_ref") and f.get("status") == "approved")
    print(f"[export] {primary_count} primary fields, {crossref_count} cross-referenced fields")

    if draft > 0:
        print(f"[export] NOTE: {draft} fields still need enrichment — run enrich.py + review.py")


if __name__ == "__main__":
    main()
