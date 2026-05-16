# Lineage Export

This page maps to `example/lineage_export.py`.

## What it covers
| Step | API |
| --- | --- |
| Track session creation | `lineage_journal_tracking()`. |
| Register sessions | `session_registry().register(session)`. |
| Export JSONL | `export_journal_jsonl(...)` and `export_jsonl_string(...)`. |

Run:

```bash
python example/lineage_export.py
jq '.lineage_operator' lineage_demo.jsonl
```

The JSONL format writes one session per line. `parent_session_ids` imply graph edges, so the file is easy to inspect with `jq` or convert into a Mermaid graph.

```json
{"id": "...", "parent_session_ids": ["..."], "lineage_operator": "Session.fork", "chunk_count": 1}
```

No LLM or sandbox is required.
