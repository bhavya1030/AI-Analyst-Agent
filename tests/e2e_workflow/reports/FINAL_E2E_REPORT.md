# AI Analytics Copilot — Comprehensive End-to-End Workflow Test Report

**Date (UTC):** 2026-07-29  
**Branch:** `feature/analysis-cache`  
**API:** `http://127.0.0.1:8000`  
**LLM:** Ollama `qwen3:4b` (healthy)  
**Harness:** `tests/e2e_workflow/run_e2e_suite.py`, `probe_extra.py`, `run_remote_retry.py`  
**Artifacts:** `tests/e2e_workflow/reports/e2e_report_latest.md`, `remote_retry_latest.json`

---

## 1. Test Summary

| Suite | Tests | Pass criteria met | Full analytical pipeline |
|-------|------:|------------------:|-------------------------:|
| Local file analysis | 15 | **15 (100%)** | **~80%** charts; forecasts when asked |
| Internet / open retrieval (primary) | 10 | **10 graceful** | **0 full auto-download** |
| Internet retry + catalog probes | 12 | 12 HTTP-OK | **3 full** (GDP, population, false-positive Olympics) |
| Cache cold/warm | 4 pairs | Timing OK | **Low L2 hit reuse** (see §4) |
| Error / fictional topics | 4 | **4 graceful** | N/A |
| **Overall harness (primary 33)** | **33** | **29 / 33 (87.9%)** | See readiness |

### Overall readiness score: **6.5 / 10**

| Dimension | Score contribution | Notes |
|-----------|-------------------|--------|
| Local analysis reliability | Strong (3.0/3.0) | File → EDA → chart/forecast → session |
| Remote graceful handling | Strong (2.0/2.0) | No crashes; acquisition options returned |
| Remote full auto pipeline | Weak (0.0/2.0) | OECD 403 / bad URLs / thin catalog |
| Cache effectiveness | Weak (0.0/1.5)* | Writes lots; few hits |
| Error handling | Strong (1.5/1.5) | No 500s; helpful messages |

\*Harness marked cache cases FAIL due to strict insight-flag + lack of clear speedup; cold/warm both succeed functionally.

---

## 2. Architecture exercised

```
User Query → Session ensure + message append
  → Memory hierarchy load
  → Optional checkpoint resume
  → LangGraph: conversation_context → planner → intent/topic
       → dataset retrieve / load file
       → prepare → profile → EDA → viz → insight → forecast
  → Analysis cache put (profile/eda/chart/forecast/embedding)
  → Session assistant turn + artifacts
  → Memory hierarchy persist + turn checkpoint
```

**Verified components:** Planner routing, intent handling, dataset retrieval agent, acquisition/download path, registry hits, dataset library files, analysis cache tables, EDA, visualization, insights text, forecasting agent, session persistence (messages + artifacts + FTS), memory hierarchy, graph checkpoints.

---

## 3. Local dataset tests (15)

Seeded under `data/local_library/`: Seattle weather, world population, world/India GDP, oil, gold, rainfall, unemployment, inflation, employees, CO₂ local.

| ID | Query | Dataset file | ms | Charts | Forecast | Session | Result |
|----|-------|--------------|---:|-------:|---------:|---------|--------|
| L01 | Seattle monthly rainfall | seattle_weather.csv | 1383 | 1 | No | Yes | **PASS** |
| L02 | Seattle temperature trends | seattle_weather.csv | 705 | 1 | No | Yes | **PASS** |
| L03 | Seattle wind distribution | seattle_weather.csv | 587 | 1 | No | Yes | **PASS** |
| L04 | Population growth | world_population.csv | 675 | 1 | No | Yes | **PASS** |
| L05 | India vs China population | world_population.csv | 2499 | 1 | No | Yes | **PASS** |
| L06 | Top 10 populated countries | world_population.csv | 98514 | 0 | No | Yes | **PASS*** |
| L07 | India GDP trend | india_gdp.csv | 985 | 1 | No | Yes | **PASS** |
| L08 | India vs US GDP | world_gdp.csv | 1409 | 1 | No | Yes | **PASS** |
| L09 | Forecast India GDP 5y | india_gdp.csv | 104202 | 0 | **Yes** | Yes | **PASS** |
| L10 | Oil prices + forecast | oil_prices.csv | 93701 | 0 | **Yes** | Yes | **PASS** |
| L11 | Gold prices + forecast | gold_prices.csv | 90094 | 0 | **Yes** | Yes | **PASS** |
| L12 | Rainfall EDA + viz | india_rainfall.csv | 850 | 1 | No | Yes | **PASS** |
| L13 | Salary by department chart | employees.csv | 1007 | 1 | No | Yes | **PASS** |
| L14 | India inflation trends | india_inflation.csv | 946 | 1 | No | Yes | **PASS** |
| L15 | Unemployment visualization | india_unemployment.csv | 1084 | 1 | No | Yes | **PASS** |

\*L06 completed with insights text but **no chart** (QA-style aggregation path).

### Local verification checklist

| Check | Status |
|-------|--------|
| Correct local file loaded (`file_path`) | ✓ |
| Intent / planner ran (session + graph checkpoints) | ✓ |
| EDA / pattern text in answer | ✓ (most cases) |
| Charts generated | ✓ 11/15 explicit charts |
| Forecast when requested | ✓ L09–L11 |
| Session updated (messages + artifacts) | ✓ |
| Analysis cache rows written | ✓ (grew 30 → 81+ during suite) |
| Dataset topic naming | ⚠ Generic `"user provided dataset"` |

---

## 4. Internet retrieval tests

### 4.1 Primary 10 topics (no file_path)

| ID | Topic | ms | Download | Full pipeline | Outcome |
|----|-------|---:|----------|---------------|---------|
| R01 | Electric Vehicle Sales | 28513 | Fail / needs data | No | Graceful **PASS** |
| R02 | Global CO₂ Emissions | 6368 | Fail | No | Graceful **PASS** |
| R03 | Renewable Energy | 6398 | Fail | No | Graceful **PASS** |
| R04 | World Happiness Index | 11179 | Fail | No | Graceful **PASS** |
| R05 | Air Quality Index | 7600 | Fail | No | Graceful **PASS** |
| R06 | Global Inflation | 5718 | Fail | No | Graceful **PASS** |
| R07 | Cryptocurrency Prices | 12469 | Fail | No | Graceful **PASS** |
| R08 | Olympic Medal Counts | 7793 | Fail | No | Graceful **PASS** |
| R09 | Global Internet Usage | 6862 | Fail | No | Graceful **PASS** |
| R10 | International Tourism | 7516 | Fail | No | Graceful **PASS** |

All returned HTTP 200, `needs_user_data=true`, and structured **acquisition options** (upload / direct URL / connect source / open search). **No crashes.**

### 4.2 Retry suite (open-data phrasing + catalog probes)

| ID | Topic | Source | Charts | Full pipeline | Root cause if fail |
|----|-------|--------|-------:|---------------|--------------------|
| RR01 | EV Sales | — | 0 | No | OECD search URL **HTTP 403** (not a file) |
| RR02 | CO₂ | — | 0 | No | OECD **403** |
| RR03 | Renewable | — | 0 | No | OECD **403** |
| RR04 | Happiness | — | 0 | No | OECD **403** |
| RR05 | AQI | — | 0 | No | OECD **403** |
| RR06 | Inflation | — | 0 | No | GitHub CPI URL **404** (`datasets/inflation`) |
| RR07 | Crypto | — | 0 | No | OECD **403** |
| RR08 | Olympics | `registry_hit` | 1 | **Yes*** | **Wrong dataset** — GDP series reused (13979 rows, GDP-like values) |
| RR09 | Internet | — | 0 | No | OECD **403** |
| RR10 | Tourism | — | 0 | No | OECD **403** |
| RR11 | World GDP | `registry_hit` | 1 | **Yes** | Known World Bank GDP CSV |
| RR12 | Population | `registry_hit` | 1 | **Yes** | Known population CSV |

**Probe confirmation:**  
- `Analyze GDP trends using world bank open data` → **965 ms**, 13 979 rows, chart, `source=registry_hit`  
- `Analyze population growth using open population dataset` → **903 ms**, 17 195 rows, chart  

### Internet pipeline verdict

| Stage | Status |
|-------|--------|
| Planner selects retrieval | ✓ (remote path entered) |
| Internet / catalog search executed | ✓ (attempts logged) |
| Correct dataset discovered | ⚠ Only for strong catalog matches (GDP/population) |
| Dataset downloaded | ⚠ Fails on portal HTML search pages (403) / dead raw URLs |
| Validated & stored locally | ⚠ When download succeeds |
| Profile / EDA / Viz / Insights | ✓ On successful load |
| Forecast when applicable | ⚠ Not covered on successful remotes in this run |
| Registry entry | ✓ On success; **topic pollution** on mismatch |
| Graceful failure UX | ✓ |

---

## 5. Cache testing

### Measured state (end of probes)

| Metric | Value |
|--------|------:|
| `analysis_cache` rows | 86 |
| Sum of `hit_count` | 3 |
| Rows with any hit | 3 |
| **Entry hit ratio** | **3 / 86 ≈ 3.5%** |
| Kinds stored | profile (22), embedding (18), chart (20), eda (14), forecast (12) |

### Cold vs warm (same file + same question, new sessions)

| ID | Query | Cold ms | Warm ms | Speedup | Notes |
|----|-------|--------:|--------:|--------:|-------|
| C01 | India GDP trend | 555 | 553 | 1.00× | Both success; charts=1 |
| C02 | Seattle rainfall | 496 | 536 | 0.92× | Both success |
| C03 | Population growth | 538 | 534 | 1.01× | Both success |
| C04 | Oil + forecast | 78374 | 75544 | 1.04× | Forecast path still ~75–78s |

**Interpretation**

- Fast local non-forecast paths (~0.5–1.5s) already dominate; second run does **not** show large wall-clock wins.
- Forecast remains expensive (~75–100s) even on repeat → **forecast cache not short-circuiting the full graph**.
- Cache **writes** work (row growth); **reads rarely increment** → graph still re-executes most stages; L1/L2 reuse is partial.

**Expected vs actual**

| Expectation | Actual |
|-------------|--------|
| No unnecessary download (local file) | ✓ |
| No repeated profiling | ⚠ Unclear — hit_count on profile≈1 total |
| EDA/forecast/charts reused | ⚠ Mostly re-generated |
| Only session state updated | ⚠ Full pipeline often re-runs |

---

## 6. Error tests

| ID | Query | HTTP | Crash | Helpful response | Notes |
|----|-------|-----:|:-----:|:----------------:|-------|
| E01 | GDP of Atlantis | 200 | No | Yes | May **incorrectly bind** World Bank GDP (registry topic `gdp atlantis`) |
| E02 | Unicorn Population | 200 | No | Yes | Risk of population catalog **false match** |
| E03 | Dragon Population | 200 | No | Yes | Graceful |
| E04 | XYZABC123 dataset | 200 | No | Yes | Graceful (~11s) |

**Verdict:** No process crashes or 500s. Fictional geography/species topics sometimes **over-match** macro open datasets (semantic / keyword leakage) — correctness bug, not stability bug.

---

## 7. Performance

| Path | Typical latency |
|------|-----------------|
| Local chart/EDA (file_path) | **0.5 – 2.5 s** |
| Local heavy QA (top-10 countries) | **~98 s** |
| Local forecast | **~90 – 105 s** |
| Remote acquisition failure | **~6 – 12 s** (search + failed download retries) |
| Remote registry hit (GDP/pop) | **~0.9 – 1.2 s** |
| Stage-level timings (planner/retrieve/eda/viz) | **Not exposed** in `/v1/ask` JSON |

Cold vs cached wall-clock: **≈1×** for light local asks; forecast **≈1.04×**.

---

## 8. Validation (cross-cutting)

| Check | Result |
|-------|--------|
| No server crashes during 33+ probes | ✓ |
| Session corruption | Not observed; messages/artifacts consistent |
| Cache table corruption | Not observed |
| Duplicate registry entries for same topic | ⚠ Multiple topical mislabels; count small (3) |
| Duplicate downloads | ⚠ OECD retries ×3 per failed topic |
| Memory leaks | Not instrumented long-run; process stable during ~11 min suite |
| Unhandled exceptions to client | None observed (always JSON body) |

### Final DB snapshot (approx.)

| Table | Count |
|-------|------:|
| analysis_sessions | 94 |
| session_messages | 151 |
| session_artifacts | 241 |
| analysis_cache | 86 |
| dataset_registry | 3 |
| learned_datasets | 1 |

---

## 9. Bugs discovered

### P0 / High

1. **Open-data download uses portal search HTML (OECD) → HTTP 403**  
   - *Symptom:* EV, CO₂, renewables, happiness, AQI, crypto, tourism, internet all fail.  
   - *Cause:* Retrieval resolves to `data.oecd.org/searchresults?...` instead of raw CSV/API.  
   - *Impact:* Auto internet pipeline non-functional for most novel topics.

2. **Registry semantic false positives**  
   - Olympics query analyzed **World Bank GDP** (13 979 rows, GDP-scale values).  
   - Atlantis/Unicorn can map to GDP/population topics.  
   - *Cause:* Weak topic→dataset matching / overly loose registry search.

3. **Broken catalog URL for inflation**  
   - `raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv` → **404**.

### Medium

4. **Analysis cache low hit rate (~3.5%)** — puts without effective graph short-circuit.  
5. **Forecast path always slow** (~90s) even when cache rows for `forecast` exist.  
6. **Generic dataset topic** `"user provided dataset"` for all local files — hurts session UX/search.  
7. **Wikipedia HTML stored as “dataset”** for some searches (invalid CSV path).

### Low

8. L06 (top-10 countries) produced insight text without chart.  
9. Harness insight flag false-negative when body contains `error: null` (fixed in harness after suite).

---

## 10. Root cause analysis

| Failure class | Root cause |
|---------------|------------|
| Remote full pipeline 0% (primary) | Searchers return **non-downloadable** HTML search pages; downloader treats them as files. |
| Registry wrong topic | Matching on partial tokens (country, open, data) without entity constraints. |
| Cache no speedup | Cache is **stage-level store**, not end-to-end ask memoization; agents re-run LLM/plotting. |
| Forecast latency | Time-series + LLM explanation path heavy on `qwen3:4b`; cache not applied at graph entry. |
| Inflation 404 | Stale hard-coded `DATASET_SOURCES` / catalog URL. |

---

## 11. Recommended fixes (priority order)

1. **Download allowlist:** only accept direct file URLs (content-type / extension / magic bytes); never fetch portal search HTML.  
2. **Curated topic → raw URL map** for EV, CO₂, renewables, tourism, AQI, crypto (Our World in Data, World Bank indicators, etc.).  
3. **Registry matching:** require embedding/topic similarity threshold + reject mismatches when column schemas disagree with intent (e.g. medals vs GDP).  
4. **Ask-level analysis cache key** `(dataset_fingerprint, normalized_question, intent)` short-circuit before graph.  
5. **Fix inflation URL** and validate all `DATASET_SOURCES` in CI.  
6. **Propagate real dataset title** from filename / registry into `dataset_topic`.  
7. **Expose stage timings** in `/v1/ask` for ops (`planner_ms`, `retrieve_ms`, `eda_ms`, `viz_ms`, `forecast_ms`, `cache_hit`).  
8. **Fictional entity guard:** if NER detects mythical place/species and no high-confidence dataset, return `not_found` without registry bind.

---

## 12. Every query executed (index)

See detailed logs:

- `tests/e2e_workflow/reports/e2e_report_latest.md` — L01–L15, R01–R10, C01–C04, E01–E04  
- `tests/e2e_workflow/reports/remote_retry_latest.json` — RR01–RR12  
- Probes: World Bank GDP open, population open, gold Wikipedia fail, dual India GDP cache runs  

**Total analytical asks in this campaign:** 33 (primary) + 12 (retry) + 5 (probes) ≈ **50** graph invocations.

---

## 13. Pass / Fail matrix (primary)

| Category | Pass | Fail |
|----------|-----:|-----:|
| Local | 15 | 0 |
| Remote graceful | 10 | 0 |
| Remote full pipeline | 0 | 10 |
| Cache harness | 0 | 4* |
| Errors | 4 | 0 |

\*Functional success on both cold and warm; fail vs strict “cache wins” criteria.

---

## 14. Overall project readiness: **6.5 / 10**

### Strengths
- Rock-solid **local file → multi-agent analysis → charts/forecast → session persistence**  
- Production plumbing: auth header, sessions, artifacts, checkpoints, memory hierarchy, cache tables  
- Graceful degradation with acquisition options when data missing  
- Fast path when registry/catalog hit is correct  

### Gaps blocking “full autonomous analyst” claim
- Internet retrieval **rarely completes** for arbitrary topics (portal 403 / bad URLs)  
- Registry can return **wrong datasets** with high confidence UI  
- Analysis **cache underutilized** for end-to-end latency  
- Forecast UX slow on small local models  

### Readiness by use case

| Use case | Score |
|----------|------:|
| Upload / path-based analytics | **8.5/10** |
| Known open GDP/population | **8/10** |
| Arbitrary web topics auto-fetch | **3/10** |
| Cache-accelerated repeats | **4/10** |
| Enterprise session memory | **8/10** |

---

## 15. How to reproduce

```powershell
# Terminal 1
venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2
$env:E2E_API_URL="http://127.0.0.1:8000"
$env:E2E_TIMEOUT_LOCAL="240"
$env:E2E_TIMEOUT_REMOTE="360"
venv\Scripts\python.exe tests\e2e_workflow\run_e2e_suite.py
venv\Scripts\python.exe tests\e2e_workflow\run_remote_retry.py
venv\Scripts\python.exe tests\e2e_workflow\probe_extra.py
```

Reports land in `tests/e2e_workflow/reports/`.

---

*End of report. No application feature code was modified for this testing campaign (only test harness + local seed CSVs under `data/local_library/` and `tests/e2e_workflow/`).*
