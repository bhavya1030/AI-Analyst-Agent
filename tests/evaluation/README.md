# AI Analytics Copilot — Evaluation Framework

End-to-end **system evaluation** (not unit tests). Exercises existing modules without modifying them.

## Run

```bash
# Full 100-case suite (component mode, offline-friendly)
python tests/evaluation/evaluation_runner.py

# Smoke (one case per category)
python tests/evaluation/evaluation_runner.py --smoke

# Filter
python tests/evaluation/evaluation_runner.py --category 4_forecasting
python tests/evaluation/evaluation_runner.py --ids 1,11,21,31

# Include live retrieval + optional LangGraph (slower)
python tests/evaluation/evaluation_runner.py --mode full
set EVAL_LIVE_RETRIEVAL=1
python tests/evaluation/evaluation_runner.py --mode component
```

## Outputs

Written to `tests/evaluation/reports/`:

| File | Description |
|------|-------------|
| `evaluation_report.md` | Markdown summary |
| `evaluation_results.csv` | Per-case CSV |
| `evaluation_dashboard.html` | Visual dashboard |
| `evaluation_full.json` | Full records + metrics |

## Modes

- **component** (default): multi-dataset planner, research planner, tool selection, conversation context, explainability, execution merge probes, fixture-backed datasets. Fast and offline-friendly.
- **full**: also invokes LangGraph for analysis-style cases; set `EVAL_LIVE_RETRIEVAL=1` for live DatasetRetrievalService / semantic search.

## Suite

100 cases across 10 categories:

1. Single dataset (1–10)  
2. Comparison (11–20)  
3. Correlation (21–30)  
4. Forecasting (31–40)  
5. Multi-dataset (41–50)  
6. Follow-up conversation (51–60)  
7. Dataset discovery (61–70)  
8. Explainability (71–80)  
9. Edge cases (81–90)  
10. Stress tests (91–100)  

The runner **continues on failure** and always produces reports.
