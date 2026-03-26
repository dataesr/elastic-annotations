"""
enrich.py — send draft fields to Claude, write suggestions back to annotations.yaml.
Never overwrites approved or rejected entries.

Usage:
    python enrich.py                          # enrich all draft fields
    python enrich.py --dry-run                # print prompts, don't call API
    python enrich.py --field authors.fullName # enrich a single field
    python enrich.py --re-draft               # re-suggest even approved fields
"""

from src.mistral import mistral_completion

import json
import argparse
import sys
import time
from pathlib import Path

from src.utils import load_annotations, save_annotations, get_config

BATCH_SIZE = 10

SYSTEM_PROMPT = """You are a technical writer helping document an Elasticsearch index for:
- A REST API reference (needs clear, precise, developer-friendly descriptions)
- An MCP (Model Context Protocol) server (needs descriptions that help an LLM agent
  understand what the field contains and when to use it)

Index context:
{index_content}

For each field you receive, respond ONLY with a valid JSON object (no markdown, no preamble).
The JSON must have exactly these keys:
  "description"  — one clear sentence (max 120 chars) describing the field's content and purpose
  "notes"        — optional extra sentence for MCP agents about edge cases or usage hints
                   (omit key if nothing useful to add)

Be consistent with the style of the example descriptions provided.
"""

FIELD_PROMPT_TEMPLATE = """Here are {n_examples} already-approved fields for style reference:
{examples}

Now describe these {n_fields} field(s). For each, output one JSON object on its own line:
{fields}
"""


def pick_examples(fields: dict, n: int = 5) -> list[dict]:
    """Return up to n approved fields with descriptions as prompt examples."""
    examples = []
    for path, info in fields.items():
        if info.get("status") == "approved" and info.get("description"):
            examples.append({"path": path, "type": info.get("type", ""), "description": info["description"]})
        if len(examples) >= n:
            break
    return examples


def format_examples(examples: list[dict]) -> str:
    return "\n".join(f'  - path: "{e["path"]}" (type: {e["type"]})\n    description: "{e["description"]}"' for e in examples)


def format_fields_for_prompt(batch: list[tuple]) -> str:
    """batch: list of (path, info_dict)"""
    lines = []
    for path, info in batch:
        parts = [f'path: "{path}"', f'type: {info.get("type", "unknown")}']
        if info.get("enum"):
            parts.append(f'allowed values: {info["enum"]}')
        if info.get("cross_ref"):
            parts.append(f'references index: {info["cross_ref"]["index"]}')
        lines.append("  - " + ", ".join(parts))
    return "\n".join(lines)


def parse_response(text: str, batch: list[tuple]) -> list[dict | None]:
    """
    Parse one JSON object per line from LLM's response.
    Returns a list aligned with batch (None on parse failure).
    """
    results = []
    lines = [line.strip() for line in text.strip().splitlines() if line.strip().startswith("{")]
    for i, (path, _) in enumerate(batch):
        if i < len(lines):
            try:
                results.append(json.loads(lines[i]))
            except json.JSONDecodeError:
                print(f"[enrich] WARNING: could not parse JSON for field {path}: {lines[i]!r}")
                results.append(None)
        else:
            print(f"[enrich] WARNING: no response for field {path}")
            results.append(None)
    return results


def main():
    parser = argparse.ArgumentParser(description="AI-enrich index draft fields in annotations.yaml")
    parser.add_argument("--index", "-i", required=True, help="Index to enrich")
    parser.add_argument("--field", "-f", default=None, help="Enrich a single field path")
    parser.add_argument("--force", action="store_true", help="Force re-enrichment of existing ai_suggestion")
    args = parser.parse_args()

    index = args.index
    config = get_config(index)
    annotations_path = f"annotations/{config['annotation']}"
    single_field = args.field

    if not Path(annotations_path).exists():
        print(f"[enrich] ERROR: {annotations_path} not found. Run merge.py first.", file=sys.stderr)
        sys.exit(1)

    # 1. Load annotations
    data = load_annotations(annotations_path)
    fields = data.get("fields", {})
    meta = data.get("_meta", {})

    # 2. Select fields to enrich
    if single_field:
        targets = [(single_field, fields[single_field])] if single_field in fields else []
        if not targets:
            print(f"[enrich] Field '{single_field}' not found in annotations")
            return
    else:
        targets = [
            (path, info)
            for path, info in fields.items()
            if not info.get("exclude", False)
            and (info.get("status") == "draft")
            and (args.force or info.get("ai_suggestion") is None)
        ]

    if not targets:
        print("[enrich] Nothing to enrich — all fields are approved or rejected.")
        return

    print(f"[enrich] {len(targets)} field(s) to enrich, batch size {BATCH_SIZE}")

    # 3. Enrich with LLM
    examples = pick_examples(fields)
    total_enriched = 0
    for batch_start in range(0, len(targets), BATCH_SIZE):
        batch = targets[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(targets) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[enrich] Batch {batch_num}/{total_batches}: {[p for p, _ in batch]}")

        prompt = FIELD_PROMPT_TEMPLATE.format(
            n_examples=len(examples),
            examples=format_examples(examples),
            n_fields=len(batch),
            fields=format_fields_for_prompt(batch),
        )
        system = SYSTEM_PROMPT.format(index_content=config["content"])
        response_text = mistral_completion(system=system, user=prompt)
        parsed = parse_response(response_text, batch)

        for (path, info), suggestion in zip(batch, parsed):
            if suggestion is None:
                continue
            fields[path]["ai_suggestion"] = {
                "description": suggestion.get("description", ""),
            }
            if suggestion.get("notes"):
                fields[path]["ai_suggestion"]["notes"] = suggestion["notes"]

            total_enriched += 1

        # Avoid hammering the API
        if batch_start + BATCH_SIZE < len(targets):
            time.sleep(0.5)

    # 4. Merge and save
    meta["draft"] = sum(1 for f in fields.values() if f.get("status") == "draft")
    meta["approved"] = sum(1 for f in fields.values() if f.get("status") == "approved")
    meta["pending_review"] = sum(1 for f in fields.values() if f.get("ai_suggestion"))
    data["_meta"] = meta
    data["fields"] = fields
    save_annotations(data, annotations_path)
    print(f"[enrich] {meta['total_fields']} fields → {total_enriched} enriched")
    print(f"[enrich] {meta['pending_review']} ai suggestions pending review")
    print(f"[enrich] Saved to {annotations_path}")


if __name__ == "__main__":
    main()
