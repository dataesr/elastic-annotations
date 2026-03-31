import sys
import argparse
from pathlib import Path

# Add elastic-annotation root to sys.path so we can import src cleanly
# even when invoked from outside via uv run from another directory
TOOL_ROOT = Path(__file__).resolve().parent
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from src.merge import main as merge_main  # noqa: E402
from src.enrich import main as enrich_main  # noqa: E402
from src.export import main as export_main  # noqa: E402

INDEXES_ALIASES = {
    "scanr-all": [
        "scanr-publications",
        "scanr-organizations",
        "scanr-persons",
        "scanr-projects",
        "scanr-participations",
        "scanr-patents",
    ]
}


def get_indexes(indexes: list[str] | str) -> list[str]:
    """Resolve index aliases."""
    if isinstance(indexes, str):
        indexes = [indexes]
    resolved_indexes = []
    for index in indexes:
        if index in INDEXES_ALIASES:
            resolved_indexes.extend(INDEXES_ALIASES[index])
        else:
            resolved_indexes.append(index)
    return list(set(resolved_indexes))


def main(args=None):
    parser = argparse.ArgumentParser(description="Run the full elastic-annotation pipeline (merge -> enrich -> export)")

    # Accept multiple indexes via multiple --index args
    parser.add_argument("--index", "-i", action="append", help="Indices to process (can be specified multiple times)")
    parser.add_argument("--skip-enrich", action="store_true", help="Skip the AI enrichment step")
    parser.add_argument(
        "--include-draft",
        action="store_true",
        help="Include draft fields with empty description in the exported JSON schema",
    )
    parser.add_argument(
        "--include-ai-suggestion", action="store_true", help="Include AI suggestions in the exported JSON schema"
    )
    parsed_args, unknown = parser.parse_known_args(args)

    if not parsed_args.index:
        print("Please provide at least one index with --index")
        sys.exit(1)

    # Resolve aliases
    indexes = get_indexes(parsed_args.index)

    for index in indexes:
        print(f"\n{'='*60}")
        print(f"=== Processing Index: {index} ===")
        print(f"{'='*60}")

        # Step 1: Merge
        print("\n--- Step 1: Merge ---")
        merge_main(["--index", index])

        # Step 2: Enrich
        if not parsed_args.skip_enrich:
            print("\n--- Step 2: Enrich ---")
            enrich_main(["--index", index])
        else:
            print("\n--- Step 2: Enrich (SKIPPED) ---")

        # Step 3: Export
        print("\n--- Step 3: Export ---")
        export_args = ["--index", index]
        if parsed_args.include_draft:
            export_args.append("--include-draft")
        if parsed_args.include_ai_suggestion:
            export_args.append("--include-ai-suggestion")

        export_main(export_args)

    print(f"\n{'='*60}")
    print("=== Pipeline Complete ===")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
