# Schema Enrichment Pipeline

Semi-automated pipeline to annotate Elasticsearch index fields for:
- **API documentation** → `schemas/<index>.json` (clean JSON Schema draft-07)

## Install

```bash
uv sync
```

## Environment variables

ES_URL: URL of the Elasticsearch cluster
ES_API_KEY: API key for Elasticsearch
MISTRAL_COMPLETION_URL: URL of the Mistral API (chat completions endpoint)
MISTRAL_API_KEY: API key for Mistral

## Setup

The pipeline uses index-specific configuration files located in the `configs/` directory.

### 1. Fill a configuration file
Create `configs/<index-name>.yaml`:
```yaml
<index-name>:
  schema: <index_name>.json
  annotation: <index_name>.yaml
  content: "Description of what this index contains for AI context."
  primary_fields:
    - id
    - title.default
    - year
  excludes:
    - secret_field.*
  includes:
    - secret_field.public_part
  cross_refs:
    organization_id:
      index: scanr-organizations
      join_field: id
```

## Workflow

```
ES index ──► merge.py ──► annotations/<index>.yaml ──► enrich.py ──► review.py ──► export.py
                                 ▲                                     │
                                 └───────────── iterate ───────────────┘
```

### Step 1 — merge

Pull ES mapping and merge with an optional existing JSON schema (from `schemas/backup/`):

```bash
python -m src.merge --index scanr-publications
```

Options:
- `--index`, `-i`: (Required) The ES index name.
- `--schema`, `-s`: Override the default backup schema path.

This creates/updates `annotations/<index>.yaml`. Existing approved descriptions are preserved.

### Step 2 — enrich

Send all `draft` fields to Mistral in batches for description suggestions:

```bash
python -m src.enrich --index scanr-publications
```

Options:
- `--index`, `-i`: (Required) The ES index name.
- `--field`, `-f`: Restrict to a single dotted field path.
- `--force`: Force re-enrichment of fields that already have an AI suggestion.

Suggestions are written into `annotations/<index>.yaml` under `ai_suggestion:`.

### Step 3 — review

Interactive CLI to approve/reject AI suggestions:

```bash
python -m src.review --index scanr-publications
```

For each field:
- `[a]` accept suggestion as-is
- `[e]` edit then accept  
- `[s]` skip (stays draft)
- `[r]` reject (stays draft, suggestion removed)
- `[q]` quit and save

Options:
- `--index`, `-i`: (Required) The ES index name.
- `--field`, `-f`: Review a specific field.

### Step 4 — export

Generate the final JSON Schema:

```bash
python -m src.export --index scanr-publications
```

Options:
- `--index`, `-i`: (Required) The ES index name.
- `--include-draft`: Include fields even if they are still in `draft` status.
- `--include-ai-suggestion`: Use AI suggestions for descriptions if no approved description exists.
- `--output`, `-o`: Override the output filename in `schemas/`.

## annotations.yaml structure

Located in `annotations/`, this file is the source of truth for field documentation.

```yaml
_meta:
  index: scanr-publications
  total_fields: 42
  approved: 38
  draft: 4

fields:
  id:
    status: approved          # approved | draft
    type: keyword
    description: "Main PID of the publication..."
    primary: true

  authors.fullName:
    status: draft
    type: text
    primary: true
    ai_suggestion:            # written by enrich.py, removed after review
      description: "Full name of the author as a single string."

  affiliations.id:
    status: approved
    type: keyword
    description: "Internal identifier of the affiliated organization."
    cross_ref:                # from configs/<index>.yaml
      index: scanr-organizations
      join_field: id
```
