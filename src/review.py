"""
review.py — interactive CLI to approve/reject AI suggestions in annotations.yaml.

Usage:
    python review.py --index scanr-publications         # review all pending suggestions
    python review.py -i scanr-publications -f authors.fullName             # review a single field

For each field:
    [a] accept suggestion as-is
    [e] edit then accept
    [s] skip (leave as draft)
    [r] reject (mark rejected, won't be re-enriched unless reset)
    [q] quit and save
"""

import argparse
import sys
from pathlib import Path

from src.utils import load_annotations, save_annotations, get_config


def print_field(path: str, info: dict):
    print(f"\n{'─'*60}")
    print(f"  Field : {path}")
    print(f"  Type  : {info.get('type', '?')}")
    print(f"  Status: {info.get('status', '?')}")
    print()
    if info.get("description"):
        print("  Current description:")
        print(f"    {info['description']}")
        print()
    sug = info.get("ai_suggestion", {})
    if sug:
        print("  AI suggestion:")
        print(f"    description : {sug.get('description','—')}")
        if sug.get("notes"):
            print(f"    notes       : {sug['notes']}")
    print(f"{'─'*60}")


def prompt_action(has_suggestion: bool) -> str:
    if has_suggestion:
        options = "[a]ccept  [e]dit  [s]kip  [r]eject  [q]uit"
    else:
        options = "[e]dit manually  [s]kip  [r]eject  [q]uit"
    while True:
        choice = input(f"  {options} > ").strip().lower()
        if choice in ("a", "e", "s", "r", "q"):
            return choice
        if not has_suggestion and choice == "a":
            continue
        print("  Invalid choice.")


def edit_description(current: str) -> str:
    print(f"  Current: {current!r}")
    print("  Enter new description (blank to keep current):")
    val = input("  > ").strip()
    return val if val else current


def main():
    parser = argparse.ArgumentParser(description="Interactive review of AI suggestions")
    parser.add_argument("--index", "-i", required=True, help="Index to review")
    parser.add_argument("--field", "-f", default=None, help="Review a single field")

    args = parser.parse_args()

    index = args.index
    config = get_config(index)
    annotations_path = f"annotations/{config['annotation']}"
    single_field = args.field

    if not Path(annotations_path).exists():
        print(f"[review] ERROR: {annotations_path} not found.", file=sys.stderr)
        sys.exit(1)

    data = load_annotations(annotations_path)
    fields = data.get("fields", {})

    if single_field:
        targets = [single_field] if single_field in fields else []
    else:
        targets = [p for p, info in fields.items() if info.get("ai_suggestion")]

    if not targets:
        print("[review] Nothing to review.")
        return

    print(f"[review] {len(targets)} field(s) to review")
    approved_count = 0

    for i, path in enumerate(targets, 1):
        info = fields[path]
        sug = info.get("ai_suggestion", {})
        print(f"\n  ({i}/{len(targets)})")
        print_field(path, info)

        action = prompt_action(has_suggestion=bool(sug))

        if action == "q":
            print("[review] Quitting — saving progress so far.")
            break

        if action == "s":
            continue

        if action == "r":
            fields[path]["status"] = "rejected"
            fields[path].pop("ai_suggestion", None)
            print("  → Rejected.")
            continue

        if action == "a":
            fields[path]["description"] = sug["description"]
            if sug.get("notes"):
                fields[path]["notes"] = sug["notes"]
            fields[path]["status"] = "approved"
            fields[path].pop("ai_suggestion", None)
            print("  → Approved.")
            approved_count += 1

        if action == "e":
            current_desc = sug.get("description") or info.get("description") or ""
            new_desc = edit_description(current_desc)
            if not new_desc:
                fields[path].pop("description", None)
            else:
                fields[path]["description"] = new_desc

            fields[path]["status"] = "approved"
            fields[path].pop("ai_suggestion", None)
            print("  → Approved with edits.")
            approved_count += 1

    # Recompute meta
    meta = data.get("_meta", {})
    meta["approved"] = sum(1 for f in fields.values() if f.get("status") == "approved")
    meta["draft"] = sum(1 for f in fields.values() if f.get("status") == "draft")
    meta["pending_review"] = sum(1 for f in fields.values() if f.get("ai_suggestion"))
    data["_meta"] = meta
    data["fields"] = fields
    save_annotations(data, annotations_path)

    print(f"\n[review] Session done — {approved_count} approved this session.")
    print(
        f"[review] Status: {meta['approved']} approved, {meta['draft']} draft, {meta.get('pending_review',0)} pending review"
    )

    if meta.get("pending_review", 0) > 0:
        print(f"[review] {meta['pending_review']} suggestions still pending — run review.py again.")
    else:
        print("[review] All fields annotated! Run 'python export.py' to generate schemas.")


if __name__ == "__main__":
    main()
