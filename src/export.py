"""
export.py — generate api/schema.json and mcp/schema.json from approved annotations.

Usage:
    python export.py
    python export.py --include-draft    # include draft fields with empty description
"""

import json
import argparse
from pathlib import Path

from src.config import SCANR_INDEXES, SCHEMAS_FOLDER, ANNOTATIONS_FOLDER
from src.utils import load_annotations


def _build_nested_properties(properties: dict, keys: list[str], infos: dict, include_mcp_extensions: bool) -> dict:
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
        props = infos_to_schema(infos, include_mcp_extensions)
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
            _build_nested_properties(node["items"]["properties"], remaining_keys, infos, include_mcp_extensions)
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
            _build_nested_properties(node["properties"], remaining_keys, infos, include_mcp_extensions)

    return properties


def infos_to_schema(info: dict, include_mcp_extensions: bool) -> dict:
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
    if info.get("notes") and include_mcp_extensions:
        schema["description"] = (schema.get("description", "") + " " + info["notes"]).strip()

    # MCP extensions
    if include_mcp_extensions:
        schema["x-primary"] = info.get("primary", False)
        if info.get("cross_ref"):
            schema["x-cross-ref"] = info["cross_ref"]

    return schema


def build_schema(index, annotations: dict, include_mcp_extensions: bool = False, include_draft: bool = False) -> dict:
    fields = annotations.get("fields", {})

    # Filter fields
    selected = {
        path: info
        for path, info in fields.items()
        if info.get("status") == "approved" or (include_draft and info.get("status") == "draft")
    }

    # Build top-level JSON Schema
    properties = {}
    for dotted_key, infos in sorted(selected.items()):
        keys = dotted_key.split(".")
        properties.update(_build_nested_properties(properties, keys, infos, include_mcp_extensions))

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "description": SCANR_INDEXES[index]["content"],
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
    args = parser.parse_args()

    index = args.index
    if index not in SCANR_INDEXES:
        raise ValueError(f"Index {index} not found in SCANR_INDEXES")
    annotations_path = f"{ANNOTATIONS_FOLDER}/{SCANR_INDEXES[index]['annotation']}"

    out_dir = Path(SCHEMAS_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)

    annotations = load_annotations(annotations_path)
    meta = annotations.get("_meta", {})

    approved = meta.get("approved", 0)
    draft = meta.get("draft", 0)
    print(f"[export] {approved} approved fields, {draft} draft {'(skipped)' if not args.include_draft else ''}")

    # 1. API schema (clean JSON Schema, no extensions)
    api_schema = build_schema(index, annotations, include_mcp_extensions=False, include_draft=args.include_draft)
    api_path = out_dir.joinpath("api", SCANR_INDEXES[index]["schema"])  # type: ignore
    save_schema(api_schema, api_path)
    print(f"[export] API schema → {api_path}")

    # 2. MCP schema (JSON Schema + x-primary + x-cross-ref)
    mcp_schema = build_schema(index, annotations, include_mcp_extensions=True, include_draft=args.include_draft)
    mcp_path = out_dir.joinpath("mcp", SCANR_INDEXES[index]["schema"])  # type: ignore
    save_schema(mcp_schema, mcp_path)
    print(f"[export] MCP schema → {mcp_path}")

    # 3. Summary stats
    fields = annotations.get("fields", {})
    primary_count = sum(1 for f in fields.values() if f.get("primary") and f.get("status") == "approved")
    crossref_count = sum(1 for f in fields.values() if f.get("cross_ref") and f.get("status") == "approved")
    print(f"[export] {primary_count} primary fields, {crossref_count} cross-referenced fields")

    if draft > 0:
        print(f"[export] NOTE: {draft} fields still need enrichment — run enrich.py + review.py")


if __name__ == "__main__":
    main()
