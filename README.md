# Schema Enrichment Pipeline

Semi-automated pipeline to annotate Elasticsearch index fields for:
- **API documentation** → `schema.api.json` (clean JSON Schema draft-07)
- **MCP server** → `schema.mcp.json` (+ `x-primary` and `x-cross-ref` extensions)

## Install

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## Setup

Edit `config.py`:
- Set `ES_HOST` and `ES_INDEX`
- Set `INDEX_CONTEXT` (one paragraph describing what the index contains)
- Fill `PRIMARY_FIELDS` (dotted paths that are essential for a minimal response)
- Fill `INDEX_CROSSREFS` (fields that reference other indices)

## Workflow

```
ES index ──► merge.py ──► annotations.yaml ──► enrich.py ──► review.py ──► export.py
                                ▲                                  │
                                └──────────── iterate ─────────────┘
```

### Step 1 — merge

Pull ES mapping + merge with your existing JSON schema:

```bash
python merge.py --schema my_schema.json
```

This creates `annotations.yaml`. Fields already described in your schema are
marked `status: approved`. Missing ones are `status: draft`.

To skip the ES call (use a pre-exported mapping):
```bash
python merge.py --schema my_schema.json --mapping mapping.json
```

### Step 2 — enrich

Send all `draft` fields to Claude in batches:

```bash
python enrich.py
```

Suggestions are written into `annotations.yaml` under `ai_suggestion:`.
Nothing is approved yet — you control that.

Options:
```bash
python enrich.py --dry-run               # print prompts, no API calls
python enrich.py --field authors.fullName  # single field
python enrich.py --re-draft              # re-suggest already-approved fields
```

### Step 3 — review

Interactive CLI to approve/reject each suggestion:

```bash
python review.py
```

For each field:
- `[a]` accept suggestion as-is
- `[e]` edit then accept  
- `[s]` skip (stays draft)
- `[r]` reject (won't be re-enriched)
- `[q]` quit and save

Repeat steps 2+3 until all fields are annotated.

### Step 4 — export

```bash
python export.py
```

Produces:
- `schema.api.json` — standard JSON Schema, suitable for OpenAPI / Swagger
- `schema.mcp.json` — same + `x-primary` and `x-cross-ref` per field

## annotations.yaml structure

This file is the source of truth. Commit it to git.

```yaml
_meta:
  index: productions
  total_fields: 42
  approved: 38
  draft: 4

fields:
  id:
    status: approved          # approved | draft | rejected
    es_type: keyword
    description: "Main PID of the production..."
    primary: true

  authors.fullName:
    status: draft
    es_type: text
    primary: true
    ai_suggestion:            # written by enrich.py, removed after review
      description: "Full name of the author as a single string."
      primary: true
      notes: "Prefer over firstName+lastName for display."

  authors.affiliations.id:
    status: approved
    es_type: keyword
    description: "Internal identifier of the affiliated organization."
    primary: false
    cross_ref:                # from config.INDEX_CROSSREFS
      index: organizations
      join_field: id
      note: "Resolves to a full organization record."
```

## MCP schema extensions

In `schema.mcp.json`, every field has two extra properties:

```json
"x-primary": true,
"x-cross-ref": {
  "index": "organizations",
  "join_field": "id",
  "note": "Resolves to a full organization record."
}
```

Your MCP server can use `x-primary: true` to build a lightweight projection
for initial queries, then fetch cross-referenced fields on demand.