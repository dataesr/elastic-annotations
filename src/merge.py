"""
merge.py — join the flattened ES mapping with your existing JSON schema.
Produces (or updates) annotations.yaml without overwriting approved entries.

Usage:
    python merge.py --index scanr-publications
    python merge.py --index scanr-publications --schema my_schema.json --out custom_annotations.yaml
"""

import json
import argparse

from src.elastic import es_get_flat_mapping
from src.utils import load_annotations, save_annotations, match_patterns, get_config


def flatten_json_schema(schema: dict, prefix: str = "") -> dict:
    """
    Walk a JSON Schema and return {dotted_path: {"description": ..., "enum": ...}}.
    Handles properties, items.properties, and nested $ref-less schemas.
    """
    result = {}
    props = schema.get("properties", {})
    required = schema.get("required", [])

    for field_name, field_def in props.items():
        path = f"{prefix}.{field_name}" if prefix else field_name
        entry = {}
        if "type" in field_def:
            entry["type"] = field_def["type"]
        if "description" in field_def:
            entry["description"] = field_def["description"]
        if "enum" in field_def:
            entry["enum"] = field_def["enum"]
        if field_name in required:
            entry["required"] = True
        if "example" in field_def:
            entry["example"] = field_def["example"]
        if entry:
            result[path] = entry

        # Recurse into nested objects
        if "properties" in field_def:
            result.update(flatten_json_schema(field_def, prefix=path))

        # Recurse into array items
        items = field_def.get("items", {})
        if isinstance(items, dict) and "properties" in items:
            result.update(flatten_json_schema(items, prefix=path))

    return result


def build_annotations(index: str, es_fields: dict, schema_fields: dict, existing: dict) -> dict:
    """
    Merge all three sources on ES fields.
    Priority:
      1. existing annotations (never overwrite approved/rejected)
      2. JSON schema descriptions
      3. blank → status: draft (needs enrichment)
    """
    fields = {}
    all_paths = sorted(set(es_fields))

    for path in all_paths:
        ex = existing.get(path, {})
        es = es_fields.get(path, {})
        sc = schema_fields.get(path, {})

        status = ex.get("status", "")
        type = ex.get("type", sc.get("type", es.get("type", "unknown")))
        description = ex.get("description", sc.get("description"))
        status = "approved" if description else "draft"
        entry = {"status": status, "type": type}

        if description:
            entry["description"] = description

        if "keyword" in es.get("fields", {}):
            entry["has_keyword"] = True

        if es.get("analyzer"):
            entry["analyzer"] = es["analyzer"]

        config = get_config(index)
        if es.get("exclude", False) or (
            (match_patterns(path, config.get("excludes", []))) and (path not in config.get("includes", []))
        ):
            entry["exclude"] = True

        if path in config.get("primary_fields", []):
            entry["primary"] = True

        enum = ex.get("enum", sc.get("enum"))
        if enum:
            entry["enum"] = enum

        required = ex.get("required", sc.get("required"))
        if required:
            entry["required"] = required

        example = ex.get("example", sc.get("example"))
        if example:
            entry["example"] = example

        ai_suggestion = ex.get("ai_suggestion")
        if ai_suggestion:
            entry["ai_suggestion"] = ai_suggestion

        # TODO: add cross_ref

        fields[path] = entry

    return fields


def merge_annotations(index, fields: dict, path: str):
    total = len(fields)
    approved = sum(1 for f in fields.values() if f.get("status") == "approved")
    draft = sum(1 for f in fields.values() if f.get("status") == "draft")
    config = get_config(index)

    data = {
        "_meta": {
            "index": index,
            "description": config["content"],
            "total_fields": total,
            "approved": approved,
            "draft": draft,
        },
        "fields": fields,
    }
    save_annotations(data, path)
    print(f"[merge] {total} fields → {approved} approved, {draft} need enrichment")
    print(f"[merge] Saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Merge ES mapping + JSON schema → annotations.yaml")
    parser.add_argument("--index", "-i", required=True, help="ES index name")
    parser.add_argument("--schema", "-s", help="Override default path to JSON schema file")
    args = parser.parse_args()

    index = args.index
    config = get_config(index)
    schema_path = args.schema or f"schemas/backup/{config['schema']}"
    annotations_path = f"annotations/{config['annotation']}"

    # 1. Load ES fields
    print(f"[merge] Fetching mapping from {index}")
    es_fields = es_get_flat_mapping(index)
    print(f"[merge] {len(es_fields)} fields from ES mapping")

    # 2. Load JSON schema
    with open(schema_path) as f:
        schema = json.load(f)
    schema_fields = flatten_json_schema(schema)
    print(f"[merge] {len(schema_fields)} fields with descriptions in JSON schema")

    # 3. Load existing annotations (if any)
    annotations = load_annotations(annotations_path, missing_ok=True)
    existing = annotations.get("fields", {})
    if existing:
        print(f"[merge] {len(existing)} existing annotations loaded (approved entries preserved)")

    # 4. Merge and save
    fields = build_annotations(index, es_fields, schema_fields, existing)
    merge_annotations(index, fields, annotations_path)


if __name__ == "__main__":
    main()
