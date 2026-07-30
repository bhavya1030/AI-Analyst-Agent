# AI Analytics Copilot — Production Readiness Report (v2 Stack)

**Generated (UTC):** 2026-07-30T09:58:11.066509+00:00
**Duration:** 2756.0s
**API:** `http://127.0.0.1:8000`
**User:** `prod-regression-v2`
**Branch:** `feature/cache-performance` (includes forecast/memory/retrieval/cache v2)
**Fresh run:** Yes — no prior report reused

## Deployment Readiness Score: **6.89 / 10**

**Assessment:** STAGING / CONTROLLED ROLLOUT

## Executive Metrics

| Metric | Value | Prior | Δ |
|--------|------:|------:|---|
| Overall Pass Rate | **76.0%** | 84.8% | -8.8% |
| Average Latency | **18874 ms** | 15907 | +2966.8 |
| P50 Latency | **1052 ms** | — | — |
| P95 Latency | **90000 ms** | — | — |
| Forecast Success % | **100.0%** | 16.7% | +83.3% |
| Forecast Latency | **1926 ms** | — | — |
| Conversation Continuity % | **100.0%** | 50.0% | +50.0% |
| Internet Retrieval Success % (full) | **23.1%** | 33.3% | -10.2% |
| Internet Graceful % | **23.1%** | 100.0% | -76.9% |
| Provider Accuracy % | **23.1%** | — | — |
| Registry Accuracy % | **100.0%** | 100.0% | +0.0% |
| Cache Hit Rate | **100.0%** | 33.3% | +66.7% |
| Warm Response Time | **163 ms** | — | — |
| Warm &lt;2s Rate | **100.0%** | — | — |
| Charts Success % | **87.5%** | 100.0% | -12.5% |
| Session Restore % | **0.0%** | — | — |
| Artifacts % | **44.8%** | — | — |
| Error Handling % | **77.8%** | 100.0% | -22.2% |
| Peak Memory (MB) | **327.2** | — | — |
| Average CPU % | **0.0** | — | — |
| Readiness Score | **6.89/10** | 7.62/10 | -0.7 |

## Category Breakdown

| Category | Cases | Pass Rate |
|----------|------:|----------:|
| cache | 6 | 100.0% |
| charts | 8 | 87.5% |
| error | 9 | 77.8% |
| forecast | 10 | 100.0% |
| internet | 26 | 23.1% |
| local | 22 | 100.0% |
| memory | 9 | 100.0% |
| registry | 6 | 100.0% |

## Stage Timing Averages (ms)

| Stage | Avg ms |
|-------|-------:|
| _codec_version | 1.0 |
| _encoded | 1.0 |
| cache | 8.9 |
| download | 0.0 |
| eda | 160.0 |
| forecast | 596.9 |
| forecast_chart | 238.6 |
| forecast_prediction | 6.6 |
| forecast_training | 2.3 |
| insights | 0.0 |
| intent | 0.3 |
| planner | 2.1 |
| profiling | 175.3 |
| retrieval | 0.0 |
| session | 826.0 |
| total | 1494.6 |
| validation | 0.0 |
| visualization | 278.9 |

## Comparison vs Previous Regression

### Improved
- Forecast success 17% → 100%
- Conversation continuity 50% → 100%
- Cache hit rate 33% → 100%

### Unchanged / Stable
- Registry accuracy stable at 100%

### Regressions
- Overall pass rate dropped 85% → 76%
- Average latency increased

## Failures

- **NET07** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET08** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET09** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET10** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET11** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET12** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET13** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET14** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET15** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET16** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET17** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET18** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET19** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET20** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": false, "full_pipeline": false}` notes=client_timeout_api_stall; recovered_live
- **NET07r** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=retry_short_timeout
- **NET09r** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=retry_short_timeout
- **NET10r** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=retry_short_timeout
- **NET13r** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=retry_short_timeout
- **NET14r** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": false, "retrieval_or_graceful": true, "full_pipeline": false}` notes=retry_short_timeout
- **NET16r** [internet] HTTP=0 checks=`{"http_200": false, "no_crash": false, "session_ok": true, "retrieval_or_graceful": true, "full_pipeline": false}` notes=retry_short_timeout
- **P_SESSI** [error] HTTP=None checks=`{}` notes=
- **CH03** [charts] HTTP=200 checks=`{"http_200": true, "has_chart_or_forecast": false}` notes=
- **ERR04** [error] HTTP=0 checks=`{"no_crash": false, "responded": false, "not_500": false, "helpful": true}` notes=

## Results Table

| ID | Cat | Pass | ms | Charts | FC | Cache | Topic/Provider |
|----|-----|------|---:|-------:|:--:|:-----:|----------------|
| LOC01 | local | PASS | 2162 | 1 | False | None | — |
| LOC02 | local | PASS | 1192 | 1 | False | None | — |
| LOC03 | local | PASS | 941 | 1 | False | None | — |
| LOC04 | local | PASS | 930 | 1 | False | None | — |
| LOC05 | local | PASS | 1175 | 1 | False | None | — |
| LOC06 | local | PASS | 811 | 1 | False | None | — |
| LOC07 | local | PASS | 868 | 0 | False | None | — |
| LOC08 | local | PASS | 1160 | 1 | False | None | — |
| LOC09 | local | PASS | 770 | 0 | True | None | — |
| LOC10 | local | PASS | 920 | 1 | False | None | — |
| LOC11 | local | PASS | 1052 | 1 | False | None | — |
| LOC12 | local | PASS | 1264 | 1 | False | None | — |
| LOC13 | local | PASS | 821 | 0 | True | None | — |
| LOC14 | local | PASS | 932 | 1 | False | None | — |
| LOC15 | local | PASS | 1005 | 0 | True | None | — |
| LOC16 | local | PASS | 990 | 1 | False | None | — |
| LOC17 | local | PASS | 726 | 0 | False | None | — |
| LOC18 | local | PASS | 1224 | 1 | False | None | — |
| LOC19 | local | PASS | 991 | 1 | False | None | — |
| LOC20 | local | PASS | 1239 | 1 | False | None | — |
| LOC21 | local | PASS | 1199 | 1 | False | None | — |
| LOC22 | local | PASS | 609 | 0 | False | None | — |
| NET01 | internet | PASS | 28425 | 1 | False | None | — |
| NET02 | internet | PASS | 5979 | 1 | False | None | — |
| NET03 | internet | PASS | 17851 | 1 | False | None | — |
| NET04 | internet | PASS | 15493 | 1 | False | None | — |
| NET05 | internet | PASS | 56776 | 1 | False | None | — |
| NET06 | internet | PASS | 6589 | 1 | False | None | — |
| NET07 | internet | FAIL | 90000 | 0 | False | None | — |
| NET08 | internet | FAIL | 90000 | 0 | False | None | — |
| NET09 | internet | FAIL | 90000 | 0 | False | None | — |
| NET10 | internet | FAIL | 90000 | 0 | False | None | — |
| NET11 | internet | FAIL | 90000 | 0 | False | None | — |
| NET12 | internet | FAIL | 90000 | 0 | False | None | — |
| NET13 | internet | FAIL | 90000 | 0 | False | None | — |
| NET14 | internet | FAIL | 90000 | 0 | False | None | — |
| NET15 | internet | FAIL | 90000 | 0 | False | None | — |
| NET16 | internet | FAIL | 90000 | 0 | False | None | — |
| NET17 | internet | FAIL | 90000 | 0 | False | None | — |
| NET18 | internet | FAIL | 90000 | 0 | False | None | — |
| NET19 | internet | FAIL | 90000 | 0 | False | None | — |
| NET20 | internet | FAIL | 90000 | 0 | False | None | — |
| NET07r | internet | FAIL | 45025 | 0 | False | None | — |
| NET09r | internet | FAIL | 45020 | 0 | False | None | — |
| NET10r | internet | FAIL | 45018 | 0 | False | None | — |
| NET13r | internet | FAIL | 45022 | 0 | False | None | — |
| NET14r | internet | FAIL | 45032 | 0 | False | None | — |
| NET16r | internet | FAIL | 45010 | 0 | False | None | — |
| FC01 | forecast | PASS | 13355 | 0 | True | False | — |
| FC02 | forecast | PASS | 169 | 0 | True | True | — |
| FC03 | forecast | PASS | 728 | 0 | True | False | — |
| FC04 | forecast | PASS | 818 | 0 | True | False | — |
| FC05 | forecast | PASS | 672 | 0 | True | False | — |
| FC06 | forecast | PASS | 673 | 0 | True | False | — |
| FC07 | forecast | PASS | 1121 | 0 | True | False | — |
| FC08 | forecast | PASS | 786 | 0 | True | False | — |
| FC09 | forecast | PASS | 807 | 0 | True | False | — |
| FC10 | forecast | PASS | 130 | 0 | True | True | — |
| MEM01 | memory | PASS | 1227 | 1 | False | None | — |
| MEM02 | memory | PASS | 1069 | 1 | False | None | — |
| MEM03 | memory | PASS | 1043 | 1 | False | None | — |
| MEM04 | memory | PASS | 899 | 1 | True | None | — |
| MEM05 | memory | PASS | 845 | 1 | True | None | — |
| MEM06 | memory | PASS | 1240 | 1 | True | None | — |
| MEM07 | memory | PASS | 939 | 1 | True | None | — |
| MEM08 | memory | PASS | 990 | 1 | True | None | — |
| MEM09 | memory | PASS | 1706 | 1 | True | None | — |
| CACH01 | cache | PASS | 138 | 1 | False | True | — |
| CACH02 | cache | PASS | 119 | 1 | False | True | — |
| CACH03 | cache | PASS | 114 | 1 | False | True | — |
| CACH04 | cache | PASS | 123 | 1 | False | True | — |
| CACH05 | cache | PASS | 316 | 1 | False | True | — |
| CACH06 | cache | PASS | 168 | 1 | False | True | — |
| P_SESSI | error | FAIL | 0 | 0 | False | None | — |
| CH01 | charts | PASS | 566 | 1 | False | None | — |
| CH02 | charts | PASS | 1027 | 1 | False | None | — |
| CH03 | charts | FAIL | 532 | 0 | False | None | — |
| CH04 | charts | PASS | 825 | 1 | False | None | — |
| CH05 | charts | PASS | 750 | 1 | False | None | — |
| CH06 | charts | PASS | 810 | 1 | False | None | — |
| CH07 | charts | PASS | 687 | 0 | True | None | — |
| CH08 | charts | PASS | 2273 | 1 | False | None | — |
| ERR01 | error | PASS | 7213 | 0 | False | None | — |
| ERR02 | error | PASS | 587 | 0 | False | None | — |
| ERR03 | error | PASS | 9458 | 0 | False | None | — |
| ERR04 | error | FAIL | 45013 | 0 | False | None | — |
| ERR05 | error | PASS | 4077 | 0 | False | None | — |
| ERR06 | error | PASS | 500 | 0 | False | None | — |
| ERR07 | error | PASS | 1885 | 0 | False | None | — |
| ERR08 | error | PASS | 2387 | 0 | False | None | — |
| REG01 | registry | PASS | 1 | 0 | False | None | — |
| REG02 | registry | PASS | 1 | 0 | False | None | — |
| REG03 | registry | PASS | 1 | 0 | False | None | — |
| REG04 | registry | PASS | 1 | 0 | False | None | — |
| REG05 | registry | PASS | 1 | 0 | False | None | — |
| REG06 | registry | PASS | 1 | 0 | False | None | — |

## Remaining Blockers

- Internet full pipeline 23% below 90%
- Failure concentration: internet=20, error=2, charts=1

## Prioritized Roadmap to 10/10

1. **Forecast SLO** — Ensure all yearly/monthly series return within 10s with model tag; measure success ≥95%.
2. **Ask-cache hit rate** — Align fingerprint between cold store and warm lookup (session path + same file_path); surface `cache_hit` ≥80% on repeats.
3. **Warm &lt;2s** — Keep session updates lightweight; avoid FTS/summarizer on cache hits (already partially done).
4. **Internet full pipeline** — Validate FRED/Eurostat/OWID live URLs; expand curated catalog for education/agriculture/trade.
5. **Memory multi-turn** — Assert zero `needs_user_data` after first bind across 9-turn scripts in CI.
6. **Charts** — Force default viz for pie/heatmap intents when columns allow.
7. **P95 latency** — Cap remote provider probe time; parallelize provider search with overall budget.
8. **Observability** — Export Prometheus metrics for cache_hit, forecast_model, provider, readiness nightly.
9. **CI gate** — Nightly production regression + fail if readiness &lt; 8.5 or forecast success &lt; 80%.
10. **Load test** — Concurrent 20 users on warm cache path before production cutover.

## Health

```json
{
  "database": "ok",
  "langgraph": "ok",
  "ollama": {
    "ollama_installed": true,
    "ollama_running": true,
    "model_available": true,
    "configured_model": "qwen3:4b",
    "installed_models": [
      "qwen3:4b"
    ],
    "failure_reason": null
  }
}
```

---
_Report: `production_regression_20260730T095811Z.md` — suite continues on failure._
