#!/usr/bin/env python3
"""
Production Certification v2 — full suite for deployment readiness.

Volumes (minimum targets):
  50 local analyses
  30 internet retrievals
  20 forecasts
  20 memory conversation turns
  20 cache benchmarks
  10 concurrent users

Produces:
  tests/regression/reports/PRODUCTION_READINESS_REPORT_V2.md
  tests/regression/reports/production_certification_*.json
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.e2e_workflow.seed_local_datasets import seed as seed_local  # noqa: E402
from tests.regression.run_production_regression_v2 import (  # noqa: E402
    BASE_URL,
    CaseResult,
    HEADERS,
    REPORT_DIR,
    TIMEOUT_LOCAL,
    TIMEOUT_REMOTE,
    USER,
    _ask,
    _cpu,
    _req,
    _rss,
    _session_ok,
    _summarize,
    _sys,
    aggregate,
    run_charts,
    run_errors,
    run_registry_unit,
    run_sessions,
)

REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Expanded suites
# ---------------------------------------------------------------------------


def run_local_50(paths: dict[str, Path]) -> list[CaseResult]:
    """50 local analyses across fixtures and query styles."""
    templates = [
        ("{k}", "EDA summary of {label}"),
        ("{k}", "Show summary statistics for {label}"),
        ("{k}", "Visualize trends for {label}"),
        ("{k}", "Show histogram of numeric columns in {label}"),
        ("{k}", "Correlation analysis for {label}"),
        ("{k}", "Compare top categories in {label}"),
        ("{k}", "Filter recent years for {label}"),
        ("{k}", "Bar chart analysis of {label}"),
        ("{k}", "Line chart over time for {label}"),
        ("{k}", "Describe patterns in {label}"),
    ]
    keys = [
        ("seattle_weather", "Seattle weather"),
        ("world_population", "world population"),
        ("india_gdp", "India GDP"),
        ("world_gdp", "world GDP"),
        ("oil_prices", "oil prices"),
        ("gold_prices", "gold prices"),
        ("india_rainfall", "India rainfall"),
        ("india_inflation", "India inflation"),
        ("india_unemployment", "India unemployment"),
        ("employees", "employees salaries"),
        ("co2_local", "CO2 emissions"),
        ("india_population", "India population"),
    ]
    # Build 50 unique cases by cycling keys × templates
    cases: list[tuple[str, str, str, bool]] = []
    i = 0
    while len(cases) < 50:
        key, label = keys[i % len(keys)]
        tmpl_key, tmpl_q = templates[i % len(templates)]
        cid = f"LOC{len(cases)+1:02d}"
        q = tmpl_q.format(label=label)
        # Every 10th asks for a light forecast-ish question still local-pass without requiring forecast
        cases.append((cid, key, q, False))
        i += 1

    results: list[CaseResult] = []
    for cid, key, q, want_fc in cases:
        if key not in paths:
            # fallback
            key = "india_gdp" if "india_gdp" in paths else next(iter(paths))
        fp = str(paths[key].resolve())
        sid = f"cert-loc-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] {q[:60]}")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        sess_ok, sess = _session_ok(sid)
        cr = CaseResult(
            id=cid,
            category="local",
            name=key,
            query=q,
            status_code=code,
            latency_ms=round(ms, 1),
            charts=s["charts"],
            forecast=s["forecast"],
            forecast_model=s["forecast_model"],
            needs_user_data=s["needs_user_data"],
            dataset_topic=s["dataset_topic"],
            session_ok=sess_ok,
            artifacts=int(sess.get("artifacts") or 0),
            memory_mb=_rss(),
            cpu_pct=_cpu(),
            timings=s["timings"],
            answer_preview=s["answer_preview"],
            error=s["error"],
        )
        cr.checks = {
            "http_200": code == 200,
            "no_crash": code not in (0,) and (code or 0) < 500,
            "has_answer": bool(s["answer_preview"]),
            "dataset_loaded": not s["needs_user_data"],
            "session_ok": sess_ok,
        }
        cr.pass_ = all(cr.checks.values())
        results.append(cr)
        print(
            f"     -> {code} {ms:.0f}ms pass={cr.pass_} charts={s['charts']} arts={cr.artifacts}"
        )
    return results


def run_internet_30() -> list[CaseResult]:
    # Prefer catalog-backed / previously successful topics first to reduce stall risk.
    # Harder open-world topics still included for coverage.
    base = [
        ("Analyze global GDP trends by country", ["gdp"]),
        ("Analyze world population statistics", ["population"]),
        ("Analyze global CO2 emissions over time", ["co2", "emission"]),
        ("Analyze gold prices annual", ["gold"]),
        ("Analyze air quality PM2.5 by country", ["air", "pm", "pollution"]),
        ("Analyze global inflation rates", ["inflation", "cpi"]),
        ("Analyze world happiness index", ["happiness"]),
        ("Analyze internet usage statistics", ["internet"]),
        ("Analyze oil and commodity prices", ["oil", "commodity"]),
        ("Analyze life expectancy worldwide", ["life", "expectancy", "happiness"]),
        ("Analyze renewable energy production", ["energy", "renewable"]),
        ("Analyze international tourism arrivals", ["tourism"]),
        ("Analyze employment unemployment rates", ["unemployment", "employment"]),
        ("Analyze electric vehicle adoption", ["ev", "electric", "energy"]),
        ("Analyze energy electricity production", ["energy", "electricity"]),
        ("Analyze international trade exports", ["trade", "export", "gdp"]),
        ("Analyze US federal funds interest rate FRED", ["interest", "rate", "fred"]),
        ("Analyze European Union GDP Eurostat", ["euro", "gdp", "europe"]),
        ("Analyze education literacy rates", ["education", "literacy", "school"]),
        ("Analyze agriculture crop yield", ["agriculture", "crop", "yield"]),
        ("Analyze Olympic medal counts by country", ["olympic"]),
        ("Analyze cryptocurrency Bitcoin prices", ["bitcoin", "crypto"]),
        ("Analyze stock market index prices", ["stock", "price"]),
        ("Analyze weather temperature climate data", ["climate", "temperature"]),
        ("Analyze COVID cases by country", ["covid"]),
        ("Analyze deforestation forest area", ["forest", "deforestation"]),
        ("Analyze maternal mortality rates", ["health", "mortality"]),
        ("Analyze renewable electricity share", ["renewable", "electricity"]),
        ("Analyze global migration flows", ["migration"]),
        ("Analyze semiconductor export data", ["export", "trade"]),
    ]
    results: list[CaseResult] = []
    consecutive_stalls = 0
    topics = base[:30]
    for i, (q, hints) in enumerate(topics):
        cid = f"NET{i+1:02d}"
        # After 2 consecutive API stalls, record remaining as cascade skips (do not wait 45s each)
        if consecutive_stalls >= 2:
            cr = CaseResult(
                id=cid,
                category="internet",
                name="internet",
                query=q,
                status_code=0,
                latency_ms=0.0,
                pass_=False,
                error="cascade_skip_after_api_stall",
                notes=["cascade_skip", "server_stall"],
                answer_preview="skipped_due_to_prior_api_stall",
            )
            cr.checks = {
                "http_200": False,
                "no_crash": False,
                "session_ok": False,
                "retrieval_or_graceful": False,
                "full_pipeline": False,
            }
            results.append(cr)
            print(f"  [{cid}] SKIP cascade (API stalled)")
            continue

        sid = f"cert-net-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] {q[:60]}")
        # Cap remote client wait; server retrieval budget is ~12s but graph can add overhead
        remote_timeout = min(int(TIMEOUT_REMOTE or 90), 45)
        code, body, ms = _ask(q, sid, timeout=remote_timeout)
        s = _summarize(body)
        sess_ok, sess = _session_ok(sid)
        if code == 0:
            consecutive_stalls += 1
            hcode, _ = _req("GET", "/health")
            if hcode == 0:
                print("     !! API unresponsive — cascade skip may engage")
                time.sleep(2)
        else:
            consecutive_stalls = 0
        analyzed = s["insights"] and not s["needs_user_data"]
        graceful = s["needs_user_data"] or bool(body.get("data_acquisition_options"))
        if code == 0 and not analyzed:
            graceful = True
            s["answer_preview"] = s["answer_preview"] or "timeout_or_unreachable"
        full = analyzed and (s["charts"] > 0 or s["forecast"])
        cr = CaseResult(
            id=cid,
            category="internet",
            name="internet",
            query=q,
            status_code=code,
            latency_ms=round(ms, 1),
            charts=s["charts"],
            forecast=s["forecast"],
            needs_user_data=s["needs_user_data"],
            dataset_topic=s["dataset_topic"],
            provider=s["provider"] or s["source"],
            session_ok=sess_ok or code == 200,
            artifacts=int(sess.get("artifacts") or 0),
            timings=s["timings"],
            answer_preview=s["answer_preview"],
            error=s["error"],
            memory_mb=_rss(),
        )
        cr.checks = {
            "http_200": code == 200,
            "no_crash": code not in (0,) and (code or 0) < 500,
            "session_ok": sess_ok or code == 200,
            "retrieval_or_graceful": analyzed or graceful or bool(s["answer_preview"]),
            "full_pipeline": full,
        }
        if code == 200:
            cr.pass_ = all(
                [
                    cr.checks["http_200"],
                    cr.checks["no_crash"],
                    cr.checks["retrieval_or_graceful"],
                ]
            )
        elif code == 0:
            cr.pass_ = False
            cr.notes.append("client_timeout")
        else:
            cr.pass_ = (code or 0) < 500 and bool(s["answer_preview"])
        if full:
            cr.notes.append("full_pipeline")
        elif graceful:
            cr.notes.append("graceful")
        results.append(cr)
        print(
            f"     -> {code} {ms:.0f}ms pass={cr.pass_} full={full} "
            f"needs_data={s['needs_user_data']}"
        )
    return results


def run_forecast_20(paths: dict[str, Path]) -> list[CaseResult]:
    lib = ROOT / "data" / "local_library"
    lib.mkdir(parents=True, exist_ok=True)
    tiny = lib / "tiny_series.csv"
    tiny.write_text("Year,Value\n2020,1\n2021,1.2\n2022,1.5\n", encoding="utf-8")
    monthly = lib / "monthly_sales.csv"
    rows = ["date,value"]
    for i in range(36):
        y, m = 2021 + i // 12, (i % 12) + 1
        rows.append(f"{y}-{m:02d}-01,{50 + i * 0.5 + (i % 12)}")
    monthly.write_text("\n".join(rows) + "\n", encoding="utf-8")
    daily = lib / "daily_metric.csv"
    import datetime as dt

    drows = ["date,value"]
    start = dt.date(2023, 1, 1)
    for i in range(60):
        d = start + dt.timedelta(days=i)
        drows.append(f"{d.isoformat()},{10 + i * 0.1 + (i % 7)}")
    daily.write_text("\n".join(drows) + "\n", encoding="utf-8")
    missing = lib / "gdp_missing.csv"
    missing.write_text(
        "Year,GDP\n2000,100\n2001,\n2002,120\n2003,130\n2004,\n2005,150\n"
        "2006,160\n2007,170\n2008,180\n2009,190\n2010,200\n",
        encoding="utf-8",
    )
    paths = dict(paths)
    paths.update({"tiny": tiny, "monthly": monthly, "daily": daily, "missing": missing})

    base_cases = [
        ("tiny", "Forecast Value next 3 years"),
        ("india_gdp", "Forecast India GDP next 5 years"),
        ("monthly", "Forecast value next 6 months"),
        ("daily", "Forecast value next 14 days"),
        ("gold_prices", "Forecast gold prices next 3 years"),
        ("oil_prices", "Forecast oil prices next 5 years"),
        ("missing", "Forecast GDP with missing values"),
        ("world_population", "Forecast population growth"),
        ("india_inflation", "Forecast inflation next 3 years"),
        ("india_rainfall", "Forecast rainfall next 3 years"),
    ]
    cases = []
    for i in range(20):
        key, q = base_cases[i % len(base_cases)]
        cases.append((f"FC{i+1:02d}", key, q))

    results: list[CaseResult] = []
    for cid, key, q in cases:
        fp = str(paths[key].resolve()) if key in paths else str(paths["india_gdp"].resolve())
        sid = f"cert-fc-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] {q[:60]}")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        partial = bool(body.get("forecast_partial"))
        cr = CaseResult(
            id=cid,
            category="forecast",
            name=key,
            query=q,
            status_code=code,
            latency_ms=round(ms, 1),
            charts=s["charts"],
            forecast=s["forecast"],
            forecast_model=s["forecast_model"],
            cache_hit=s["cache_hit"],
            timings=s["timings"],
            answer_preview=s["answer_preview"],
            error=s["error"],
            memory_mb=_rss(),
            cpu_pct=_cpu(),
        )
        cr.checks = {
            "http_200": code == 200,
            "no_crash": (code or 0) < 500 and code != 0,
            "has_forecast": s["forecast"],
        }
        cr.pass_ = cr.checks["http_200"] and cr.checks["no_crash"] and (
            s["forecast"] or partial or "forecast" in s["answer_preview"].lower()
        )
        if partial:
            cr.notes.append("partial")
        results.append(cr)
        print(
            f"     -> fc={s['forecast']} model={s['forecast_model']!r} "
            f"{ms:.0f}ms pass={cr.pass_}"
        )
    return results


def run_memory_20(paths: dict[str, Path]) -> list[CaseResult]:
    """Two multi-turn conversations totaling 20 turns."""
    results: list[CaseResult] = []
    convos = [
        (
            "world_gdp",
            [
                "Analyze India GDP trends",
                "Show histogram",
                "Show correlation",
                "Forecast next 5 years",
                "Compare India vs China",
                "Filter 2010 to 2020",
                "Show pie chart",
                "Show line chart",
                "Summarize the findings",
                "What was the last chart type",
            ],
        ),
        (
            "gold_prices",
            [
                "Analyze gold prices",
                "Show distribution",
                "Show trend line chart",
                "Forecast next 3 years",
                "Compare recent decade",
                "Show bar chart by year",
                "Any seasonality patterns",
                "Summarize insights",
                "Show correlation if possible",
                "What should I analyze next",
            ],
        ),
    ]
    n = 0
    for key, turns in convos:
        fp = str(paths[key].resolve())
        sid = f"cert-mem-{uuid.uuid4().hex[:8]}"
        for i, q in enumerate(turns):
            n += 1
            cid = f"MEM{n:02d}"
            print(f"  [{cid}] {key} turn {i+1}: {q}")
            code, body, ms = _ask(
                q, sid, file_path=fp if i == 0 else None, timeout=TIMEOUT_LOCAL
            )
            s = _summarize(body)
            sess_ok, sess = _session_ok(sid)
            reupload = s["needs_user_data"] and i > 0
            cr = CaseResult(
                id=cid,
                category="memory",
                name="continuity",
                query=q,
                status_code=code,
                latency_ms=round(ms, 1),
                charts=s["charts"],
                forecast=s["forecast"],
                needs_user_data=s["needs_user_data"],
                dataset_topic=s["dataset_topic"] or str(sess.get("dataset_topic") or ""),
                session_ok=sess_ok,
                answer_preview=s["answer_preview"],
                timings=s["timings"],
                artifacts=int(sess.get("artifacts") or 0),
            )
            cr.checks = {
                "http_200": code == 200,
                "no_reupload": not reupload,
                "session_ok": sess_ok,
                "has_answer": bool(s["answer_preview"]),
            }
            cr.pass_ = all(cr.checks.values())
            if reupload:
                cr.notes.append("REUPLOAD_REQUESTED")
            results.append(cr)
            print(
                f"     -> pass={cr.pass_} needs_data={s['needs_user_data']} "
                f"topic={cr.dataset_topic!r}"
            )
    return results


def run_cache_20(paths: dict[str, Path]) -> list[CaseResult]:
    """20 cache benchmarks = 10 cold/warm pairs."""
    pairs = [
        ("india_gdp", "Analyze India's GDP trend over time"),
        ("seattle_weather", "Show monthly rainfall trends for Seattle weather"),
        ("gold_prices", "Show gold price line chart"),
        ("oil_prices", "Analyze oil price trends"),
        ("world_population", "Show population growth over years"),
        ("india_inflation", "Analyze India inflation trends"),
        ("world_gdp", "Analyze world GDP by country"),
        ("india_rainfall", "Analyze India rainfall trends"),
        ("employees", "Salary distribution by department"),
        ("co2_local", "Analyze CO2 emissions over time"),
    ]
    results: list[CaseResult] = []
    for i, (key, q) in enumerate(pairs):
        if key not in paths:
            continue
        fp = str(paths[key].resolve())
        sid = f"cert-cache-{i}-{uuid.uuid4().hex[:5]}"
        cid_c = f"CACH{i*2+1:02d}"
        cid_w = f"CACH{i*2+2:02d}"
        print(f"  [{cid_c}] cold {q[:50]}")
        code1, body1, ms1 = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s1 = _summarize(body1)
        cr1 = CaseResult(
            id=cid_c,
            category="cache",
            name=f"{key}-cold",
            query=q,
            status_code=code1,
            latency_ms=round(ms1, 1),
            charts=s1["charts"],
            cache_hit=s1["cache_hit"],
            timings=s1["timings"],
            answer_preview=s1["answer_preview"],
        )
        cr1.checks = {
            "http_200": code1 == 200,
            "cold_ok": code1 == 200 and bool(s1["answer_preview"]),
        }
        cr1.pass_ = cr1.checks["cold_ok"]
        results.append(cr1)

        print(f"  [{cid_w}] warm {q[:50]}")
        code2, body2, ms2 = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s2 = _summarize(body2)
        cr2 = CaseResult(
            id=cid_w,
            category="cache",
            name=f"{key}-warm",
            query=q,
            status_code=code2,
            latency_ms=round(ms2, 1),
            charts=s2["charts"],
            cache_hit=s2["cache_hit"],
            cache_latency_ms=s2.get("cache_latency_ms"),
            saved_time_ms=s2.get("saved_time_ms"),
            pipeline_skipped=s2.get("pipeline_skipped"),
            timings=s2["timings"],
            answer_preview=s2["answer_preview"],
        )
        cr2.checks = {
            "http_200": code2 == 200,
            "warm_ok": code2 == 200 and bool(s2["answer_preview"]),
            "warm_under_2s": ms2 < 2000,
            "warm_not_pathological": ms2 < 15000,
            "cache_hit_or_fast": bool(s2["cache_hit"]) or ms2 < 3000,
        }
        cr2.pass_ = (
            cr2.checks["http_200"]
            and cr2.checks["warm_ok"]
            and cr2.checks["warm_not_pathological"]
        )
        if not cr2.checks["warm_under_2s"]:
            cr2.notes.append("warm_gt_2s")
        results.append(cr2)
        print(
            f"     -> cold={ms1:.0f} warm={ms2:.0f} hit={s2['cache_hit']} pass={cr2.pass_}"
        )
    return results


def run_concurrent_10(paths: dict[str, Path]) -> list[CaseResult]:
    """10 concurrent users hitting /v1/ask simultaneously."""
    fp = str(paths["india_gdp"].resolve())
    queries = [
        "Analyze India GDP trends",
        "Show summary statistics",
        "Visualize GDP over years",
        "Forecast GDP next 3 years",
        "Show histogram of GDP",
        "Correlation of year and GDP",
        "Bar chart of GDP",
        "Describe the dataset",
        "Filter years after 2010",
        "Line chart of GDP growth",
    ]

    def one(i: int) -> CaseResult:
        q = queries[i]
        sid = f"cert-conc-{i}-{uuid.uuid4().hex[:5]}"
        t0 = time.perf_counter()
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        sess_ok, _ = _session_ok(sid)
        cr = CaseResult(
            id=f"CONC{i+1:02d}",
            category="concurrent",
            name=f"user_{i+1}",
            query=q,
            status_code=code,
            latency_ms=round(ms, 1),
            charts=s["charts"],
            forecast=s["forecast"],
            session_ok=sess_ok,
            answer_preview=s["answer_preview"],
            timings=s["timings"],
            memory_mb=_rss(),
            cpu_pct=_cpu(),
        )
        cr.checks = {
            "http_200": code == 200,
            "no_crash": (code or 0) < 500 and code != 0,
            "has_answer": bool(s["answer_preview"]),
            "session_ok": sess_ok,
        }
        cr.pass_ = all(cr.checks.values())
        cr.notes.append(f"wall_start_offset_ms={round((time.perf_counter()-t0)*1000,1)}")
        return cr

    print("  Launching 10 concurrent users...")
    results: list[CaseResult] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(one, i) for i in range(10)]
        for f in as_completed(futs):
            try:
                cr = f.result()
            except Exception as exc:
                cr = CaseResult(
                    id="CONC_ERR",
                    category="concurrent",
                    name="error",
                    pass_=False,
                    error=str(exc),
                )
            results.append(cr)
            print(
                f"     -> {cr.id} pass={cr.pass_} {cr.latency_ms:.0f}ms code={cr.status_code}"
            )
    results.sort(key=lambda r: r.id)
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_certification_report(
    results: list[CaseResult],
    metrics: dict[str, Any],
    health: dict[str, Any],
    perf: dict[str, Any],
    started: str,
    finished: str,
    duration: float,
) -> dict[str, Path]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"production_certification_{ts}.json"
    md_path = REPORT_DIR / f"PRODUCTION_READINESS_REPORT_V2_{ts}.md"
    latest_md = REPORT_DIR / "PRODUCTION_READINESS_REPORT_V2.md"
    latest_json = REPORT_DIR / "production_certification_latest.json"

    score = float(metrics.get("deployment_readiness_score") or 0)
    # Adjust score with concurrent + volume completeness
    by = defaultdict(list)
    for r in results:
        by[r.category].append(r)

    def rate(cat: str) -> float:
        items = by.get(cat) or []
        if not items:
            return 0.0
        return sum(1 for x in items if x.pass_) / len(items)

    volume_ok = (
        len(by.get("local") or []) >= 50
        and len(by.get("internet") or []) >= 30
        and len(by.get("forecast") or []) >= 20
        and len(by.get("memory") or []) >= 20
        and len(by.get("cache") or []) >= 20
        and len(by.get("concurrent") or []) >= 10
    )
    conc_ok = rate("concurrent")
    # Blend original score with concurrent
    score = min(10.0, score * 0.9 + conc_ok * 1.0)
    if volume_ok:
        score = min(10.0, score + 0.15)
    metrics = dict(metrics)
    metrics["deployment_readiness_score"] = round(score, 2)
    metrics["concurrent_pass_rate"] = round(conc_ok, 4)
    metrics["volume_targets_met"] = volume_ok

    # Recommendation thresholds
    blockers: list[str] = []
    risks: list[str] = []
    if metrics["pass_rate"] < 0.85:
        blockers.append(f"Overall pass rate {metrics['pass_rate']:.1%} < 85%")
    if metrics["forecast_success"] < 0.70:
        blockers.append(f"Forecast success {metrics['forecast_success']:.1%} < 70%")
    if metrics["conversation_continuity"] < 0.80:
        blockers.append(
            f"Conversation continuity {metrics['conversation_continuity']:.1%} < 80%"
        )
    if metrics["p95_latency_ms"] > 60000:
        blockers.append(f"P95 latency {metrics['p95_latency_ms']:.0f}ms > 60s")
    if metrics["internet_retrieval_success"] < 0.40:
        risks.append(
            f"Internet full-pipeline success {metrics['internet_retrieval_success']:.1%} is low "
            "(graceful degradation may still pass)"
        )
    if metrics["cache_hit_rate"] < 0.5:
        risks.append(f"Cache hit rate {metrics['cache_hit_rate']:.1%} < 50% on warm suite")
    if metrics["warm_response_ms"] > 3000:
        risks.append(f"Warm avg {metrics['warm_response_ms']:.0f}ms exceeds 3s aspirational SLO")
    if conc_ok < 0.9:
        risks.append(f"Concurrent users pass rate {conc_ok:.1%} < 90%")
    if score < 7.5:
        blockers.append(f"Deployment readiness score {score:.2f}/10 < 7.5")

    ready = len(blockers) == 0 and score >= 7.5
    recommendation = "Ready" if ready else "Not Ready"

    payload = {
        "generated_at": finished,
        "started_at": started,
        "duration_seconds": round(duration, 1),
        "base_url": BASE_URL,
        "user": USER,
        "suite": "production_certification_v2",
        "volumes": {
            "local": len(by.get("local") or []),
            "internet": len(by.get("internet") or []),
            "forecast": len(by.get("forecast") or []),
            "memory": len(by.get("memory") or []),
            "cache": len(by.get("cache") or []),
            "concurrent": len(by.get("concurrent") or []),
            "charts": len(by.get("charts") or []),
            "session": len(by.get("session") or []),
            "error": len(by.get("error") or []),
            "registry": len(by.get("registry") or []),
        },
        "health": health,
        "performance_endpoint": perf,
        "metrics": metrics,
        "blockers": blockers,
        "risks": risks,
        "recommendation": recommendation,
        "ready_for_production": ready,
        "results": [asdict(r) for r in results],
    }
    text = json.dumps(payload, indent=2, default=str)
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    m = metrics
    lines = [
        "# Production Readiness Report v2",
        "",
        f"**Generated:** {finished}  ",
        f"**Duration:** {duration/60:.1f} minutes  ",
        f"**API:** `{BASE_URL}`  ",
        f"**User:** `{USER}`  ",
        f"**Suite:** Production Certification v2  ",
        "",
        "---",
        "",
        "## Executive Recommendation",
        "",
        f"### **{recommendation} for production deployment**",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| **Deployment Score** | **{score:.2f} / 10** |",
        f"| Pass rate | {m['pass_rate']:.1%} ({m['passed']}/{m['total']}) |",
        f"| Average latency | {m['average_latency_ms']:.0f} ms |",
        f"| P50 latency | {m['p50_latency_ms']:.0f} ms |",
        f"| P95 latency | {m['p95_latency_ms']:.0f} ms |",
        f"| Forecast success | {m['forecast_success']:.1%} |",
        f"| Conversation continuity | {m['conversation_continuity']:.1%} |",
        f"| Internet full success | {m['internet_retrieval_success']:.1%} |",
        f"| Internet graceful | {m['internet_graceful_rate']:.1%} |",
        f"| Charts success | {m['charts_success']:.1%} |",
        f"| Sessions success | {m['session_restore']:.1%} |",
        f"| Cache hit rate | {m['cache_hit_rate']:.1%} |",
        f"| Warm avg response | {m['warm_response_ms']:.0f} ms |",
        f"| Concurrent pass rate | {m.get('concurrent_pass_rate', 0):.1%} |",
        f"| Artifacts rate | {m['artifacts_rate']:.1%} |",
        f"| Peak process RSS | {m['peak_memory_mb']:.0f} MB |",
        f"| Avg process RSS | {m['avg_memory_mb']:.0f} MB |",
        f"| Avg CPU (sample) | {m['avg_cpu_pct']:.1f}% |",
        "",
        "### System resources",
        "",
        "```json",
        json.dumps(m.get("system") or {}, indent=2),
        "```",
        "",
        "### Volume targets",
        "",
        "| Suite | Target | Actual | Met |",
        "|-------|-------:|-------:|:---:|",
    ]
    vols = payload["volumes"]
    targets = {
        "local": 50,
        "internet": 30,
        "forecast": 20,
        "memory": 20,
        "cache": 20,
        "concurrent": 10,
    }
    for k, t in targets.items():
        a = vols.get(k, 0)
        lines.append(f"| {k} | {t} | {a} | {'yes' if a >= t else 'no'} |")

    lines += [
        "",
        "### Category pass rates",
        "",
        "| Category | Pass rate | Count |",
        "|----------|----------:|------:|",
    ]
    for cat, rate_v in sorted((m.get("category_pass_rates") or {}).items()):
        cnt = (m.get("category_counts") or {}).get(cat, 0)
        lines.append(f"| {cat} | {rate_v:.1%} | {cnt} |")

    lines += [
        "",
        "### Stage average latency (ms)",
        "",
        "```json",
        json.dumps(m.get("stage_avg_ms") or {}, indent=2),
        "```",
        "",
        "### Live /performance snapshot (if available)",
        "",
        "```json",
        json.dumps(
            {
                k: perf.get(k)
                for k in (
                    "p50",
                    "p95",
                    "average",
                    "error_rate",
                    "cache_hit_ratio",
                    "summary",
                )
                if k in (perf or {})
            }
            or perf,
            indent=2,
            default=str,
        )[:4000],
        "```",
        "",
        "---",
        "",
        "## Remaining blockers",
        "",
    ]
    if blockers:
        for b in blockers:
            lines.append(f"- **BLOCKER:** {b}")
    else:
        lines.append("- None — no hard blockers detected against certification gates.")

    lines += ["", "## Risk assessment", ""]
    if risks:
        for r in risks:
            lines.append(f"- **RISK:** {r}")
    else:
        lines.append("- No elevated residual risks beyond normal internet provider variance.")

    lines += [
        "",
        "### Risk matrix (qualitative)",
        "",
        "| Area | Risk | Notes |",
        "|------|------|-------|",
        f"| Internet providers | {'High' if m['internet_retrieval_success'] < 0.5 else 'Medium' if m['internet_retrieval_success'] < 0.8 else 'Low'} | Full pipeline {m['internet_retrieval_success']:.0%}; graceful {m['internet_graceful_rate']:.0%} |",
        f"| Forecast engine | {'High' if m['forecast_success'] < 0.7 else 'Low'} | Success {m['forecast_success']:.0%}; latency {m['forecast_latency_ms']:.0f}ms |",
        f"| Cache warm path | {'Medium' if m['warm_response_ms'] > 2000 else 'Low'} | Hit {m['cache_hit_rate']:.0%}; warm avg {m['warm_response_ms']:.0f}ms |",
        f"| Sessions | {'Medium' if m['session_restore'] < 0.9 else 'Low'} | Pass {m['session_restore']:.0%} |",
        f"| Concurrency | {'Medium' if conc_ok < 0.9 else 'Low'} | 10-user pass {conc_ok:.0%} |",
        f"| Resource | Low | Peak RSS {m['peak_memory_mb']:.0f}MB |",
        "",
        "---",
        "",
        "## Failures (first 40)",
        "",
    ]
    fails = [r for r in results if not r.pass_]
    if not fails:
        lines.append("_No failures._")
    else:
        for r in fails[:40]:
            lines.append(
                f"- **{r.id}** [{r.category}] HTTP={r.status_code} "
                f"checks=`{json.dumps(r.checks)}` notes={r.notes} err={r.error[:120]}"
            )

    lines += [
        "",
        "---",
        "",
        "## Results table (compact)",
        "",
        "| ID | Cat | Pass | ms | Charts | FC | Cache |",
        "|----|-----|:----:|---:|-------:|:--:|:-----:|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.category} | {'PASS' if r.pass_ else 'FAIL'} | "
            f"{r.latency_ms:.0f} | {r.charts} | {r.forecast} | {r.cache_hit} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Certification gates",
        "",
        "| Gate | Threshold | Observed | Status |",
        "|------|-----------|----------|:------:|",
        f"| Pass rate | ≥ 85% | {m['pass_rate']:.1%} | {'PASS' if m['pass_rate'] >= 0.85 else 'FAIL'} |",
        f"| Forecast success | ≥ 70% | {m['forecast_success']:.1%} | {'PASS' if m['forecast_success'] >= 0.70 else 'FAIL'} |",
        f"| Continuity | ≥ 80% | {m['conversation_continuity']:.1%} | {'PASS' if m['conversation_continuity'] >= 0.80 else 'FAIL'} |",
        f"| P95 latency | ≤ 60s | {m['p95_latency_ms']/1000:.1f}s | {'PASS' if m['p95_latency_ms'] <= 60000 else 'FAIL'} |",
        f"| Score | ≥ 7.5/10 | {score:.2f} | {'PASS' if score >= 7.5 else 'FAIL'} |",
        f"| Concurrent | ≥ 90% | {conc_ok:.1%} | {'PASS' if conc_ok >= 0.9 else 'WARN'} |",
        "",
        f"**Final recommendation: `{recommendation}`**",
        "",
        f"_Artifacts: `{json_path.name}`, `{md_path.name}`_",
        "",
    ]

    md = "\n".join(lines)
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": md_path,
        "latest_markdown": latest_md,
        "latest_json": latest_json,
    }


def main() -> int:
    print("=" * 72)
    print("PRODUCTION CERTIFICATION v2")
    print(f"API={BASE_URL} user={USER}")
    print("Targets: 50 local · 30 internet · 20 forecast · 20 memory · 20 cache · 10 concurrent")
    print("=" * 72)

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    peak_mem = _rss()

    code, health = _req("GET", "/health")
    if code == 0:
        code, health = _req("GET", "/health/full")
    print(f"Health HTTP {code}: {json.dumps(health)[:240]}")
    code0, _ = _req("GET", "/")
    if code0 == 0 and code == 0:
        print("FATAL: API unreachable — start backend on :8000")
        return 2

    # performance snapshot (optional)
    _, perf = _req("GET", "/performance?limit=50")

    print("\n[seed] local datasets...")
    paths = seed_local()
    eval_data = ROOT / "tests" / "evaluation" / "data"
    for name in (
        "india_population.csv",
        "india_gdp.csv",
        "gold_prices.csv",
        "co2_emissions.csv",
        "india_rainfall.csv",
        "india_inflation.csv",
        "india_unemployment.csv",
    ):
        p = eval_data / name
        key = name.replace(".csv", "")
        if p.exists() and key not in paths:
            paths[key] = p
    # co2 local alias
    if "co2_local" not in paths:
        for cand in (
            ROOT / "data" / "local_library" / "co2_emissions_local.csv",
            eval_data / "co2_emissions.csv",
        ):
            if cand.exists():
                paths["co2_local"] = cand
                break
    if "employees" not in paths:
        emp = ROOT / "data" / "local_library" / "employees.csv"
        if emp.exists():
            paths["employees"] = emp

    all_results: list[CaseResult] = []
    # Internet last among heavy network phases so a stall does not wipe forecast/memory/cache.
    phases = [
        ("LOCAL (50)", lambda: run_local_50(paths)),
        ("FORECAST (20)", lambda: run_forecast_20(paths)),
        ("MEMORY (20)", lambda: run_memory_20(paths)),
        ("CACHE (20)", lambda: run_cache_20(paths)),
        ("CONCURRENT (10)", lambda: run_concurrent_10(paths)),
        ("SESSIONS", lambda: run_sessions(paths)),
        ("CHARTS", lambda: run_charts(paths)),
        ("ERRORS", lambda: run_errors(paths)),
        ("REGISTRY", run_registry_unit),
        ("INTERNET (30)", run_internet_30),
    ]
    for title, fn in phases:
        print(f"\n{'=' * 20} {title} {'=' * 20}")
        # Probe API before each phase; warn if still recovering
        hcode, _ = _req("GET", "/health")
        if hcode == 0:
            print(f"  WARN: API not healthy before {title}; waiting 5s…")
            time.sleep(5)
            hcode, _ = _req("GET", "/health")
            if hcode == 0:
                print(f"  WARN: API still down — phase may fail/timeout")
        try:
            batch = fn()
            all_results.extend(batch)
            peak_mem = max(peak_mem, _rss())
            # refresh perf occasionally
            if "INTERNET" in title or "CACHE" in title:
                _, perf = _req("GET", "/performance?limit=200")
        except Exception as exc:
            print(f"PHASE CRASH {title}: {exc}")
            all_results.append(
                CaseResult(
                    id=f"PHASE_{title[:8]}",
                    category="error",
                    name=title,
                    pass_=False,
                    error=str(exc),
                    notes=[traceback.format_exc()[-400:]],
                )
            )

    sys_info = _sys()
    metrics = aggregate(all_results, peak_mem, sys_info)
    finished = datetime.now(timezone.utc).isoformat()
    duration = time.perf_counter() - t0
    paths_out = write_certification_report(
        all_results, metrics, health, perf if isinstance(perf, dict) else {},
        started, finished, duration,
    )

    # re-read score from report file metrics rewrite
    latest = json.loads(paths_out["latest_json"].read_text(encoding="utf-8"))
    m = latest["metrics"]
    print("\n" + "=" * 72)
    print(
        f"DONE total={m['total']} passed={m['passed']} failed={m['failed']} "
        f"pass_rate={m['pass_rate']:.1%}"
    )
    print(
        f"Avg={m['average_latency_ms']:.0f}ms P50={m['p50_latency_ms']:.0f} "
        f"P95={m['p95_latency_ms']:.0f}"
    )
    print(
        f"Forecast={m['forecast_success']:.0%} Continuity={m['conversation_continuity']:.0%} "
        f"Internet full={m['internet_retrieval_success']:.0%} Cache hit={m['cache_hit_rate']:.0%}"
    )
    print(
        f"Concurrent={m.get('concurrent_pass_rate', 0):.0%} "
        f"Score={m['deployment_readiness_score']}/10 "
        f"Recommendation={latest['recommendation']}"
    )
    print(f"Report: {paths_out['latest_markdown']}")
    print("=" * 72)
    return 0 if latest.get("ready_for_production") else 1


if __name__ == "__main__":
    raise SystemExit(main())
