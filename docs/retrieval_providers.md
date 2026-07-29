# Open-data retrieval providers

## Problem

The previous internet path often returned **HTML search pages** (e.g. OECD `searchresults`) or **dead raw URLs** (404). Acquisition then treated those responses as datasets.

## Architecture

```
User query
  → Planner / topic detection
  → DatasetRetrievalAgent
       1. Session
       2. Registry
       3. Semantic registry
       4. OpenDataProvider  ← multi-provider orchestrator
       5. User upload (placeholder)
  → DatasetPrepareAgent → Acquisition (re-validates bytes) → Registry learn → EDA
```

### Package: `backend/retrieval/data_providers/`

| Module | Role |
|--------|------|
| `base.py` | `DataProvider`, `DatasetCandidate` |
| `topic.py` | Keyword / alias extraction |
| `catalog.py` | Curated direct download URLs (no HTML) |
| `validation.py` | Blocked URL patterns, Content-Type, magic bytes, size, redirects |
| `orchestrator.py` | Provider order, search, validate, **retry next provider** |
| `world_bank.py` | World Bank CSV + indicator JSON |
| `owid.py` | Our World in Data GitHub raw CSVs |
| `github_raw.py` | Trusted `raw.githubusercontent.com` |
| `huggingface.py` | HF **resolve** file URLs only |
| `data_gov.py` | data.gov CKAN **resource** files only |
| `kaggle.py` | Metadata only (no anonymous download) |
| `csv_url.py` | Explicit file URLs in the question |
| `json_api.py` | CoinGecko / JSON APIs |

### Validation rejects

- HTML (`text/html`, `<!DOCTYPE html>`, etc.)
- PDFs
- Login / search / Wikipedia paths
- OECD `searchresults` pages
- Empty / tiny / oversized bodies
- Unknown binary formats

### Stored provenance (registry)

On learn, metadata tags/summary include:

- `provider`
- `license`
- `dataset_version` / version
- `source_url` / download URL
- `download_timestamp`

## Logging

Orchestrator and acquisition emit structured logs for:

- Provider selected / search duration
- Validation duration + failure reason
- Retry count
- Final success URL

## Tests

```bash
venv/Scripts/python.exe -m pytest tests/test_retrieval_providers.py -q
venv/Scripts/python.exe -m pytest tests/test_dataset_retrieval_agent.py -q
```

## Ops notes

- Prefer **catalog** hits for common E2E topics (GDP, population, CO₂, energy, inflation, tourism, internet, crypto, olympics).
- Kaggle requires credentials; provider only returns search metadata.
- Acquisition **re-validates** every download even if retrieval already probed.
