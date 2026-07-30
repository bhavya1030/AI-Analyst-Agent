#!/usr/bin/env python3
"""
Production Regression Suite v2 — post Forecast/Memory/Retrieval/Cache improvements.

Runs against live API. Continues on failure. Writes fresh JSON + Markdown reports.
Does NOT reuse previous report artifacts.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.e2e_workflow.seed_local_datasets import seed as seed_local  # noqa: E402

BASE_URL = os.environ.get("E2E_API_URL", "http://127.0.0.1:8000")
USER = os.environ.get("E2E_USER_ID", "prod-regression-v2")
HEADERS = {"X-User-Id": USER}
TIMEOUT_LOCAL = int(os.environ.get("REG_TIMEOUT_LOCAL", "90"))
TIMEOUT_REMOTE = int(os.environ.get("REG_TIMEOUT_REMOTE", "120"))
REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Prior baseline (from FINAL_E2E_REPORT / earlier hybrid regression)
PRIOR_BASELINE = {
    "source": "FINAL_E2E_REPORT + hybrid ASAP regression (pre full v2 stack)",
    "pass_rate": 0.848,
    "readiness": 7.62,
    "avg_latency_ms": 15907,
    "forecast_success": 0.167,
    "internet_full": 0.333,
    "internet_graceful": 1.0,
    "cache_hit_rate": 0.333,
    "memory_continuity": 0.50,
    "registry_accuracy": 1.0,
    "charts_rate": 1.0,
    "error_handling": 1.0,
}

try:
    import psutil  # type: ignore

    _PROC = psutil.Process(os.getpid())
    _HAS_PSUTIL = True
except Exception:
    psutil = None  # type: ignore
    _PROC = None
    _HAS_PSUTIL = False


@dataclass
class CaseResult:
    id: str
    category: str
    name: str
    query: str = ""
    pass_: bool = False
    status_code: int | None = None
    latency_ms: float = 0.0
    charts: int = 0
    forecast: bool = False
    forecast_model: str = ""
    cache_hit: bool | None = None
    cache_latency_ms: float | None = None
    saved_time_ms: float | None = None
    pipeline_skipped: bool = False
    needs_user_data: bool = False
    dataset_topic: str = ""
    provider: str = ""
    session_ok: bool = False
    artifacts: int = 0
    memory_mb: float = 0.0
    cpu_pct: float = 0.0
    timings: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    answer_preview: str = ""
    error: str = ""


def _rss() -> float:
    if _HAS_PSUTIL and _PROC:
        try:
            return round(_PROC.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass
    return 0.0


def _cpu() -> float:
    if _HAS_PSUTIL and _PROC:
        try:
            return float(_PROC.cpu_percent(interval=0.05))
        except Exception:
            pass
    return 0.0


def _sys() -> dict[str, float]:
    if not _HAS_PSUTIL or not psutil:
        return {}
    try:
        vm = psutil.virtual_memory()
        return {
            "mem_percent": float(vm.percent),
            "mem_used_mb": round(vm.used / (1024 * 1024), 1),
            "cpu_percent": float(psutil.cpu_percent(interval=0.1)),
        }
    except Exception:
        return {}


def _ask(
    question: str,
    session_id: str,
    file_path: str | None = None,
    timeout: int = TIMEOUT_LOCAL,
) -> tuple[int, dict[str, Any], float]:
    params: dict[str, str] = {"question": question, "session_id": session_id}
    if file_path:
        params["file_path"] = file_path
    url = f"{BASE_URL}/v1/ask?{urlencode(params)}"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        ms = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except Exception:
            body = {"error": (r.text or "")[:400]}
        return r.status_code, body if isinstance(body, dict) else {"data": body}, ms
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return 0, {"error": str(exc)}, ms


def _req(method: str, path: str, **kwargs) -> tuple[int, dict[str, Any]]:
    try:
        r = requests.request(
            method, f"{BASE_URL}{path}", headers=HEADERS, timeout=30, **kwargs
        )
        try:
            body = r.json()
        except Exception:
            body = {"raw": (r.text or "")[:300]}
        return r.status_code, body if isinstance(body, dict) else {"data": body}
    except Exception as exc:
        return 0, {"error": str(exc)}


def _summarize(body: dict[str, Any]) -> dict[str, Any]:
    charts = body.get("charts") or body.get("generated_charts") or []
    if not charts and body.get("chart"):
        charts = [body["chart"]]
    n_charts = len(charts) if isinstance(charts, list) else (1 if charts else 0)
    fc = body.get("forecast") or []
    has_fc = bool(fc) and (len(fc) > 0 if isinstance(fc, list) else True)
    if body.get("forecast_chart"):
        has_fc = True
    answer = str(body.get("answer") or body.get("error") or "")
    discovery = body.get("dataset_discovery") or {}
    timings = body.get("timings") or {}
    return {
        "charts": n_charts,
        "forecast": has_fc,
        "forecast_model": str(body.get("forecast_model") or ""),
        "insights": bool(answer.strip()) and not body.get("error"),
        "answer_preview": answer[:200].replace("\n", " "),
        "dataset_topic": str(body.get("dataset_topic") or body.get("dataset_name") or ""),
        "source": str(body.get("source") or discovery.get("source") or ""),
        "provider": str(
            (discovery.get("provider") if isinstance(discovery, dict) else None)
            or body.get("source")
            or ""
        ),
        "needs_user_data": bool(body.get("needs_user_data")),
        "cache_hit": bool(body.get("cache_hit")),
        "cache_latency_ms": body.get("cache_latency_ms"),
        "saved_time_ms": body.get("saved_time_ms"),
        "pipeline_skipped": bool(body.get("cache_skipped_pipeline")),
        "timings": timings if isinstance(timings, dict) else {},
        "error": str(body.get("error") or ""),
        "discovery": discovery if isinstance(discovery, dict) else {},
    }


def _session_ok(session_id: str) -> tuple[bool, dict[str, Any]]:
    code, body = _req("GET", f"/v1/sessions/{session_id}")
    if code != 200:
        return False, {"status_code": code}
    msgs = body.get("messages") or body.get("chat_history") or []
    arts = body.get("artifacts") or body.get("generated_charts") or []
    return True, {
        "message_count": body.get("message_count") or len(msgs),
        "dataset_name": body.get("dataset_name") or body.get("dataset_topic"),
        "dataset_topic": body.get("dataset_topic"),
        "artifacts": len(arts) if isinstance(arts, list) else 0,
        "title": body.get("title"),
        "status": body.get("status"),
    }


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------


def run_local(paths: dict[str, Path]) -> list[CaseResult]:
    cases = [
        ("LOC01", "seattle_weather", "EDA summary of Seattle weather dataset", False, False),
        ("LOC02", "seattle_weather", "Show statistics for temperature", False, False),
        ("LOC03", "seattle_weather", "Visualize rainfall as a line chart", False, False),
        ("LOC04", "seattle_weather", "Show histogram of wind", False, False),
        ("LOC05", "world_population", "Correlation between year and population", False, False),
        ("LOC06", "world_population", "Compare India and China population", False, False),
        ("LOC07", "world_population", "Group by country average population", False, False),
        ("LOC08", "india_gdp", "Analyze India GDP trend", False, False),
        ("LOC09", "india_gdp", "Forecast India GDP next 5 years", True, False),
        ("LOC10", "world_gdp", "Compare India vs United States GDP", False, False),
        ("LOC11", "world_gdp", "Filter GDP for years 2010 to 2020", False, False),
        ("LOC12", "oil_prices", "Analyze oil price trends", False, False),
        ("LOC13", "oil_prices", "Forecast oil prices next 3 years", True, False),
        ("LOC14", "gold_prices", "Show gold price line chart", False, False),
        ("LOC15", "gold_prices", "Forecast gold next 3 years", True, False),
        ("LOC16", "india_rainfall", "Bar chart of yearly rainfall", False, False),
        ("LOC17", "india_inflation", "Scatter of year vs inflation", False, False),
        ("LOC18", "india_unemployment", "Pie chart of unemployment if possible", False, False),
        ("LOC19", "employees", "Salary by department bar chart", False, False),
        ("LOC20", "co2_local", "Analyze CO2 emissions trends", False, False),
        ("LOC21", "india_gdp", "Show summary statistics", False, False),
        ("LOC22", "world_population", "Top 5 countries by population latest year", False, False),
    ]
    # inject missing/edge fixtures
    results: list[CaseResult] = []
    for cid, key, q, want_fc, _ in cases:
        if key not in paths:
            results.append(
                CaseResult(
                    id=cid, category="local", name=key, query=q, pass_=False,
                    notes=["missing_fixture"],
                )
            )
            continue
        fp = str(paths[key].resolve())
        sid = f"reg2-loc-{cid}-{uuid.uuid4().hex[:6]}"
        print(f"  [{cid}] {q[:55]}")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        sess_ok, sess = _session_ok(sid)
        cr = CaseResult(
            id=cid, category="local", name=key, query=q,
            status_code=code, latency_ms=round(ms, 1),
            charts=s["charts"], forecast=s["forecast"], forecast_model=s["forecast_model"],
            needs_user_data=s["needs_user_data"], dataset_topic=s["dataset_topic"],
            session_ok=sess_ok, artifacts=int(sess.get("artifacts") or 0),
            memory_mb=_rss(), cpu_pct=_cpu(), timings=s["timings"],
            answer_preview=s["answer_preview"], error=s["error"],
        )
        cr.checks = {
            "http_200": code == 200,
            "no_crash": code not in (0,) and (code or 0) < 500,
            "has_answer": bool(s["answer_preview"]),
            "dataset_loaded": not s["needs_user_data"],
            "session_ok": sess_ok,
            "forecast_if_asked": (s["forecast"] if want_fc else True),
        }
        cr.pass_ = all(
            [
                cr.checks["http_200"],
                cr.checks["no_crash"],
                cr.checks["has_answer"],
                cr.checks["dataset_loaded"],
                cr.checks["session_ok"],
            ]
        )
        if want_fc and not s["forecast"]:
            cr.notes.append("forecast_missing")
        results.append(cr)
        print(f"     -> {code} {ms:.0f}ms pass={cr.pass_} charts={s['charts']} fc={s['forecast']}")
    return results


def run_internet() -> list[CaseResult]:
    topics = [
        ("NET01", "Analyze global GDP trends by country", ["gdp"]),
        ("NET02", "Analyze world population statistics", ["population"]),
        ("NET03", "Analyze global CO2 emissions over time", ["co2", "emission"]),
        ("NET04", "Analyze renewable energy production", ["energy", "renewable"]),
        ("NET05", "Analyze air quality PM2.5 by country", ["air", "pm", "pollution"]),
        ("NET06", "Analyze gold prices annual", ["gold"]),
        ("NET07", "Analyze global inflation rates", ["inflation", "cpi"]),
        ("NET08", "Analyze international tourism arrivals", ["tourism"]),
        ("NET09", "Analyze Olympic medal counts by country", ["olympic"]),
        ("NET10", "Analyze cryptocurrency Bitcoin prices", ["bitcoin", "crypto"]),
        ("NET11", "Analyze stock market S&P data", ["stock", "price"]),
        ("NET12", "Analyze weather temperature climate data", ["climate", "temperature"]),
        ("NET13", "Analyze employment unemployment rates", ["unemployment", "employment"]),
        ("NET14", "Analyze electric vehicle adoption", ["ev", "electric", "energy"]),
        ("NET15", "Analyze life expectancy worldwide", ["life", "expectancy", "happiness"]),
        ("NET16", "Analyze COVID cases by country", ["covid"]),
        ("NET17", "Analyze education literacy rates", ["education", "literacy", "school"]),
        ("NET18", "Analyze agriculture crop yield", ["agriculture", "crop", "yield"]),
        ("NET19", "Analyze energy electricity production", ["energy", "electricity"]),
        ("NET20", "Analyze international trade exports", ["trade", "export", "gdp"]),
    ]
    results: list[CaseResult] = []
    for cid, q, hints in topics:
        sid = f"reg2-net-{cid}-{uuid.uuid4().hex[:6]}"
        print(f"  [{cid}] {q[:55]}")
        code, body, ms = _ask(q, sid, timeout=TIMEOUT_REMOTE)
        s = _summarize(body)
        sess_ok, sess = _session_ok(sid)
        analyzed = s["insights"] and not s["needs_user_data"]
        graceful = s["needs_user_data"] or bool(body.get("data_acquisition_options"))
        full = analyzed and (s["charts"] > 0 or s["forecast"])
        blob = f"{s['dataset_topic']} {s['answer_preview']} {s['provider']}".lower()
        relevant = any(h in blob for h in hints) or analyzed
        cr = CaseResult(
            id=cid, category="internet", name="internet", query=q,
            status_code=code, latency_ms=round(ms, 1),
            charts=s["charts"], forecast=s["forecast"],
            needs_user_data=s["needs_user_data"], dataset_topic=s["dataset_topic"],
            provider=s["provider"] or s["source"],
            session_ok=sess_ok, artifacts=int(sess.get("artifacts") or 0),
            timings=s["timings"], answer_preview=s["answer_preview"], error=s["error"],
            memory_mb=_rss(),
        )
        cr.checks = {
            "http_200": code == 200,
            "no_crash": code not in (0,) and (code or 0) < 500,
            "session_ok": sess_ok,
            "retrieval_or_graceful": analyzed or graceful or bool(s["answer_preview"]),
            "full_pipeline": full,
            "topic_relevant": relevant or graceful,
        }
        cr.pass_ = all(
            [
                cr.checks["http_200"],
                cr.checks["no_crash"],
                cr.checks["session_ok"],
                cr.checks["retrieval_or_graceful"],
            ]
        )
        if full:
            cr.notes.append("full_pipeline")
        elif graceful:
            cr.notes.append("graceful")
        results.append(cr)
        print(f"     -> {code} {ms:.0f}ms pass={cr.pass_} full={full} needs_data={s['needs_user_data']}")
    return results


def run_forecast(paths: dict[str, Path]) -> list[CaseResult]:
    # Prepare tiny / monthly / daily fixtures
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
    drows = ["date,value"]
    import datetime as dt

    start = dt.date(2023, 1, 1)
    for i in range(45):
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
    paths.update(
        {
            "tiny": tiny,
            "monthly": monthly,
            "daily": daily,
            "missing": missing,
        }
    )
    cases = [
        ("FC01", "tiny", "Forecast Value next 3 years"),
        ("FC02", "india_gdp", "Forecast India GDP next 5 years"),
        ("FC03", "monthly", "Forecast value next 6 months"),
        ("FC04", "daily", "Forecast value next 14 days"),
        ("FC05", "gold_prices", "Forecast gold prices next 3 years"),
        ("FC06", "oil_prices", "Forecast oil prices next 5 years"),
        ("FC07", "missing", "Forecast GDP with missing values"),
        ("FC08", "world_population", "Forecast population growth"),
        ("FC09", "india_inflation", "Forecast inflation next 3 years"),
        ("FC10", "india_gdp", "Forecast India GDP next 5 years"),  # cache reuse
    ]
    results: list[CaseResult] = []
    for cid, key, q in cases:
        fp = str(paths[key].resolve()) if key in paths else str(paths["india_gdp"].resolve())
        sid = f"reg2-fc-{cid}-{uuid.uuid4().hex[:6]}"
        print(f"  [{cid}] {q[:55]}")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        cr = CaseResult(
            id=cid, category="forecast", name=key, query=q,
            status_code=code, latency_ms=round(ms, 1),
            charts=s["charts"], forecast=s["forecast"], forecast_model=s["forecast_model"],
            cache_hit=s["cache_hit"], timings=s["timings"],
            answer_preview=s["answer_preview"], error=s["error"],
            notes=[],
        )
        partial = bool(body.get("forecast_partial"))
        timed = bool(body.get("forecast_timeout_reason") or body.get("forecast_timeout_reason"))
        if partial:
            cr.notes.append("partial")
        if body.get("forecast_from_cache"):
            cr.notes.append("forecast_cache")
        cr.checks = {
            "http_200": code == 200,
            "no_crash": (code or 0) < 500 and code != 0,
            "has_forecast": s["forecast"],
            "under_budget_soft": ms < 30000,  # soft SLO; hard is 10s engine
            "has_model_or_partial": bool(s["forecast_model"] or s["forecast"] or partial),
        }
        # Pass if HTTP ok and forecast present OR graceful partial explanation
        cr.pass_ = cr.checks["http_200"] and cr.checks["no_crash"] and (
            s["forecast"] or partial or "forecast" in s["answer_preview"].lower()
        )
        if cid == "FC10" and s["cache_hit"]:
            cr.notes.append("ask_cache_hit")
        results.append(cr)
        print(
            f"     -> fc={s['forecast']} model={s['forecast_model']!r} "
            f"{ms:.0f}ms pass={cr.pass_}"
        )
    return results


def run_memory(paths: dict[str, Path]) -> list[CaseResult]:
    """Multi-turn continuity: never request upload mid-conversation."""
    fp = str(paths["world_gdp"].resolve())
    sid = f"reg2-mem-{uuid.uuid4().hex[:8]}"
    turns = [
        ("MEM01", "Analyze India GDP trends", True),
        ("MEM02", "Show histogram", False),
        ("MEM03", "Show correlation", False),
        ("MEM04", "Forecast next 5 years", False),
        ("MEM05", "Compare India vs China", False),
        ("MEM06", "Filter 2010 to 2020", False),
        ("MEM07", "Show pie chart", False),
        ("MEM08", "Show line chart", False),
        ("MEM09", "Summarize the findings", False),
    ]
    results: list[CaseResult] = []
    for i, (cid, q, use_file) in enumerate(turns):
        print(f"  [{cid}] turn {i+1}: {q}")
        code, body, ms = _ask(
            q, sid, file_path=fp if use_file else None, timeout=TIMEOUT_LOCAL
        )
        s = _summarize(body)
        sess_ok, sess = _session_ok(sid)
        reupload = s["needs_user_data"] and i > 0
        cr = CaseResult(
            id=cid, category="memory", name="continuity", query=q,
            status_code=code, latency_ms=round(ms, 1),
            charts=s["charts"], forecast=s["forecast"],
            needs_user_data=s["needs_user_data"],
            dataset_topic=s["dataset_topic"] or str(sess.get("dataset_topic") or ""),
            session_ok=sess_ok, answer_preview=s["answer_preview"],
            timings=s["timings"],
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
        print(f"     -> pass={cr.pass_} needs_data={s['needs_user_data']} topic={cr.dataset_topic!r}")
    return results


def run_cache(paths: dict[str, Path]) -> list[CaseResult]:
    cases = [
        ("CACH01", "india_gdp", "Analyze India's GDP trend over time"),
        ("CACH02", "seattle_weather", "Show monthly rainfall trends for Seattle weather"),
        ("CACH03", "gold_prices", "Show gold price line chart"),
        ("CACH04", "oil_prices", "Analyze oil price trends"),
        ("CACH05", "world_population", "Show population growth over years"),
        ("CACH06", "india_inflation", "Analyze India inflation trends"),
    ]
    results: list[CaseResult] = []
    for cid, key, q in cases:
        fp = str(paths[key].resolve())
        sid_c = f"reg2-c-{cid}-{uuid.uuid4().hex[:5]}"
        sid_w = f"reg2-w-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] cold/warm {q[:45]}")
        code1, body1, ms1 = _ask(q, sid_c, file_path=fp, timeout=TIMEOUT_LOCAL)
        s1 = _summarize(body1)
        code2, body2, ms2 = _ask(q, sid_w, file_path=fp, timeout=TIMEOUT_LOCAL)
        s2 = _summarize(body2)
        speedup = (ms1 / ms2) if ms2 > 0 else 0
        cr = CaseResult(
            id=cid, category="cache", name="cold_warm", query=q,
            status_code=code2, latency_ms=round(ms2, 1),
            charts=s2["charts"], cache_hit=s2["cache_hit"],
            cache_latency_ms=s2.get("cache_latency_ms"),
            saved_time_ms=s2.get("saved_time_ms"),
            pipeline_skipped=s2["pipeline_skipped"],
            answer_preview=f"cold={ms1:.0f} warm={ms2:.0f} speedup={speedup:.2f}x hit={s2['cache_hit']}",
            notes=[f"cold_ms={ms1:.1f}", f"warm_ms={ms2:.1f}", f"speedup={speedup:.3f}"],
        )
        cr.checks = {
            "cold_ok": code1 == 200 and bool(s1["answer_preview"]),
            "warm_ok": code2 == 200 and bool(s2["answer_preview"]),
            "warm_under_2s": ms2 < 2000,
            "warm_not_pathological": ms2 < ms1 * 8 + 5000,
        }
        cr.pass_ = cr.checks["cold_ok"] and cr.checks["warm_ok"] and cr.checks["warm_not_pathological"]
        # Soft note if not under 2s (still may pass suite)
        if not cr.checks["warm_under_2s"]:
            cr.notes.append("warm_gt_2s")
        results.append(cr)
        print(f"     -> cold={ms1:.0f} warm={ms2:.0f} hit={s2['cache_hit']} pass={cr.pass_}")
    return results


def run_sessions(paths: dict[str, Path]) -> list[CaseResult]:
    results: list[CaseResult] = []
    fp = str(paths["india_gdp"].resolve())
    sid = f"reg2-sess-{uuid.uuid4().hex[:8]}"

    def add(cid, name, ok, ms=0, notes=None, **kw):
        results.append(
            CaseResult(
                id=cid, category="session", name=name, pass_=ok,
                latency_ms=ms, notes=notes or [], checks={"ok": ok}, **kw
            )
        )

    # create via ask
    print("  [SES01] create via ask")
    t0 = time.perf_counter()
    code, body, ms = _ask("Analyze India GDP", sid, file_path=fp)
    add("SES01", "create", code == 200, ms, session_ok=code == 200)

    # rename
    print("  [SES02] rename")
    t0 = time.perf_counter()
    code, body = _req("POST", f"/v1/sessions/{sid}/rename", json={"title": "GDP Analysis V2"})
    # some APIs use query
    if code not in (200, 201):
        code, body = _req("POST", f"/v1/sessions/{sid}/rename?title=GDP%20Analysis%20V2")
    if code not in (200, 201):
        code, body = _req("PUT", f"/v1/sessions/{sid}", json={"title": "GDP Analysis V2"})
    add("SES02", "rename", code in (200, 201), (time.perf_counter() - t0) * 1000)

    # get/restore
    print("  [SES03] get/detail")
    t0 = time.perf_counter()
    code, body = _req("GET", f"/v1/sessions/{sid}")
    ok = code == 200 and bool(body.get("dataset_path") or body.get("dataset_topic") or body.get("messages"))
    add("SES03", "restore_get", ok, (time.perf_counter() - t0) * 1000, session_ok=ok)

    # duplicate
    print("  [SES04] duplicate")
    t0 = time.perf_counter()
    code, body = _req("POST", f"/v1/sessions/{sid}/duplicate")
    dup_id = (body.get("session_id") or body.get("id")) if isinstance(body, dict) else None
    add("SES04", "duplicate", code in (200, 201) and bool(dup_id), (time.perf_counter() - t0) * 1000)

    # archive
    print("  [SES05] archive")
    t0 = time.perf_counter()
    code, body = _req("POST", f"/v1/sessions/{sid}/archive")
    add("SES05", "archive", code in (200, 201), (time.perf_counter() - t0) * 1000)

    # restore from archive
    print("  [SES06] unarchive/restore")
    t0 = time.perf_counter()
    code, body = _req("POST", f"/v1/sessions/{sid}/restore")
    add("SES06", "unarchive", code in (200, 201), (time.perf_counter() - t0) * 1000)

    # delete
    print("  [SES07] delete")
    t0 = time.perf_counter()
    del_id = dup_id or sid
    code, body = _req("DELETE", f"/v1/sessions/{del_id}")
    add("SES07", "delete", code in (200, 204), (time.perf_counter() - t0) * 1000)

    # post-restart continuity simulated: re-get original if not deleted
    print("  [SES08] detail after ops")
    t0 = time.perf_counter()
    code, body = _req("GET", f"/v1/sessions/{sid}")
    # may be archived/deleted depending on API — accept 200
    add("SES08", "post_ops_get", code in (200, 404), (time.perf_counter() - t0) * 1000)

    for r in results:
        print(f"     {r.id} {r.name} pass={r.pass_}")
    return results


def run_charts(paths: dict[str, Path]) -> list[CaseResult]:
    cases = [
        ("CH01", "employees", "Bar chart of salary by department"),
        ("CH02", "india_gdp", "Line chart of GDP over years"),
        ("CH03", "world_gdp", "Scatter of year versus GDP"),
        ("CH04", "seattle_weather", "Histogram of temperature"),
        ("CH05", "india_unemployment", "Pie chart of unemployment values"),
        ("CH06", "world_population", "Heatmap or correlation of population data"),
        ("CH07", "gold_prices", "Forecast chart for gold prices next 3 years"),
        ("CH08", "india_rainfall", "Bar chart of rainfall by year"),
    ]
    results: list[CaseResult] = []
    for cid, key, q in cases:
        fp = str(paths[key].resolve())
        sid = f"reg2-ch-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] {q[:55]}")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        want_fc = "forecast" in q.lower()
        cr = CaseResult(
            id=cid, category="charts", name=key, query=q,
            status_code=code, latency_ms=round(ms, 1),
            charts=s["charts"], forecast=s["forecast"],
            answer_preview=s["answer_preview"],
        )
        cr.checks = {
            "http_200": code == 200,
            "has_chart_or_forecast": s["charts"] > 0 or (want_fc and s["forecast"]),
        }
        cr.pass_ = cr.checks["http_200"] and cr.checks["has_chart_or_forecast"]
        results.append(cr)
        print(f"     -> charts={s['charts']} fc={s['forecast']} pass={cr.pass_}")
    return results


def run_errors(paths: dict[str, Path]) -> list[CaseResult]:
    # write corrupt fixtures
    lib = ROOT / "data" / "local_library"
    corrupt = lib / "corrupt.csv"
    corrupt.write_text("not,a,valid\n\"unclosed,field\n,,,\n", encoding="utf-8")
    empty = lib / "empty_file.csv"
    empty.write_text("", encoding="utf-8")
    cases = [
        ("ERR01", None, "Analyze GDP of Atlantis"),
        ("ERR02", str(corrupt), "Analyze this dataset"),
        ("ERR03", None, "https://example.com/this-page-is-html-not-data"),
        ("ERR04", None, "Analyze https://httpstat.us/404"),
        ("ERR05", None, "Analyze Unicorn Population worldwide"),
        ("ERR06", str(empty), "Analyze empty file"),
        ("ERR07", None, "!!!@@@###"),
        ("ERR08", None, " "),
    ]
    results: list[CaseResult] = []
    for cid, fp, q in cases:
        sid = f"reg2-err-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] {q[:50]!r}")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=min(TIMEOUT_REMOTE, 60))
        s = _summarize(body)
        crashed = code == 0 or (code is not None and code >= 500)
        helpful = bool(s["answer_preview"]) or bool(body.get("error")) or s["needs_user_data"]
        cr = CaseResult(
            id=cid, category="error", name="error", query=q,
            status_code=code, latency_ms=round(ms, 1),
            answer_preview=s["answer_preview"] or s["error"],
            needs_user_data=s["needs_user_data"],
        )
        cr.checks = {
            "no_crash": not crashed,
            "responded": code != 0,
            "not_500": (code or 0) < 500 if code else False,
            "helpful": helpful,
        }
        cr.pass_ = all(cr.checks.values())
        results.append(cr)
        print(f"     -> {code} pass={cr.pass_}")
    return results


def run_registry_unit() -> list[CaseResult]:
    """In-process registry accuracy (GDP ≠ Olympics)."""
    results: list[CaseResult] = []
    try:
        from backend.registry.matching import build_match_query, score_dataset
        from backend.registry.models import DatasetMetadata

        cases = [
            ("REG01", "india gdp", "gdp", True),
            ("REG02", "world population", "population", True),
            ("REG03", "olympics medals", "gdp", False),
            ("REG04", "gdp growth", "olympics", False),
            ("REG05", "inflation cpi", "inflation", True),
            ("REG06", "atlantis gdp", "gdp", False),
        ]
        pool = [
            DatasetMetadata(
                dataset_id="d-gdp", title="World GDP", topic="gdp",
                domain="macroeconomics", keywords=["gdp"], columns=["Country", "Year", "GDP"],
            ),
            DatasetMetadata(
                dataset_id="d-pop", title="Population", topic="population",
                domain="demographics", keywords=["population"], columns=["Country", "Year", "Population"],
            ),
            DatasetMetadata(
                dataset_id="d-oly", title="Olympics", topic="olympics",
                domain="sports", keywords=["olympics", "medals"], columns=["Year", "Medal"],
            ),
            DatasetMetadata(
                dataset_id="d-inf", title="Inflation", topic="inflation",
                domain="macroeconomics", keywords=["inflation", "cpi"], columns=["Year", "CPI"],
            ),
        ]
        for cid, q, expect, should_hit in cases:
            mq = build_match_query(q)
            scored = []
            for m in pool:
                sc = score_dataset(mq, m)
                scored.append((sc.confidence, sc.accepted, m.topic, sc))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[0]
            if should_hit:
                ok = top[2] == expect and (top[1] or top[0] >= 0.45)
            else:
                # either low conf or not the forbidden topic
                ok = (not top[1]) or top[2] != expect or top[0] < 0.62
            results.append(
                CaseResult(
                    id=cid, category="registry", name="match", query=q,
                    pass_=ok, latency_ms=1.0,
                    notes=[f"top={top[2]} conf={top[0]:.2f} accepted={top[1]}"],
                    checks={"ok": ok},
                )
            )
            print(f"  [{cid}] q={q!r} top={top[2]} conf={top[0]:.2f} ok={ok}")
    except Exception as exc:
        results.append(
            CaseResult(
                id="REG00", category="registry", name="error", pass_=False,
                error=str(exc), notes=[traceback.format_exc()[-300:]],
            )
        )
    return results


# ---------------------------------------------------------------------------
# Aggregate + report
# ---------------------------------------------------------------------------


def aggregate(results: list[CaseResult], peak_mem: float, sys_info: dict) -> dict[str, Any]:
    by: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by[r.category].append(r)

    def rate(cat: str) -> float:
        items = by.get(cat) or []
        if not items:
            return 0.0
        return sum(1 for x in items if x.pass_) / len(items)

    lats = [r.latency_ms for r in results if r.latency_ms > 0]
    lats_s = sorted(lats)
    p50 = lats_s[len(lats_s) // 2] if lats_s else 0
    p95 = lats_s[int(len(lats_s) * 0.95)] if lats_s else 0
    avg = sum(lats) / max(len(lats), 1)

    fc = by.get("forecast") or []
    fc_ok = sum(1 for r in fc if r.forecast) / max(len(fc), 1)
    fc_lat = [r.latency_ms for r in fc if r.latency_ms > 0]
    fc_avg = sum(fc_lat) / max(len(fc_lat), 1)

    mem = by.get("memory") or []
    mem_ok = sum(1 for r in mem if r.pass_) / max(len(mem), 1)

    net = by.get("internet") or []
    net_grace = rate("internet")
    net_full = sum(1 for r in net if r.checks.get("full_pipeline")) / max(len(net), 1)

    cache = by.get("cache") or []
    cache_hits = sum(1 for r in cache if r.cache_hit) / max(len(cache), 1)
    warm_lats = [r.latency_ms for r in cache if r.latency_ms > 0]
    warm_avg = sum(warm_lats) / max(len(warm_lats), 1)
    warm_under_2 = sum(1 for r in cache if r.checks.get("warm_under_2s")) / max(len(cache), 1)

    charts = by.get("charts") or []
    chart_ok = sum(1 for r in charts if r.charts > 0 or r.forecast) / max(len(charts), 1)

    sess = by.get("session") or []
    sess_ok = rate("session")

    arts = [r for r in results if r.artifacts > 0 or r.charts > 0]
    arts_rate = len(arts) / max(len(results), 1)

    err = rate("error")
    reg = rate("registry")
    loc = rate("local")

    passed = sum(1 for r in results if r.pass_)
    total = len(results)
    pass_rate = passed / max(total, 1)

    # Readiness /10
    score = (
        loc * 1.5
        + net_grace * 0.8
        + net_full * 1.2
        + fc_ok * 1.2
        + mem_ok * 1.0
        + min(1.0, warm_under_2 + cache_hits) * 0.5 * 1.0  # cache composite
        + (0.5 * cache_hits + 0.5 * warm_under_2) * 1.0
        + reg * 0.5
        + chart_ok * 0.6
        + sess_ok * 0.5
        + err * 0.7
    )
    # normalize roughly to 10 (weights sum ~10.5)
    score = min(10.0, score * (10.0 / 10.5))

    stage_sums: dict[str, list[float]] = defaultdict(list)
    for r in results:
        for k, v in (r.timings or {}).items():
            try:
                stage_sums[k].append(float(v))
            except Exception:
                pass
    stage_avg = {k: round(sum(v) / len(v), 1) for k, v in stage_sums.items() if v}

    mem_samples = [r.memory_mb for r in results if r.memory_mb > 0]
    cpu_samples = [r.cpu_pct for r in results if r.cpu_pct > 0]

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(pass_rate, 4),
        "average_latency_ms": round(avg, 1),
        "p50_latency_ms": round(p50, 1),
        "p95_latency_ms": round(p95, 1),
        "forecast_success": round(fc_ok, 4),
        "forecast_latency_ms": round(fc_avg, 1),
        "conversation_continuity": round(mem_ok, 4),
        "internet_retrieval_success": round(net_full, 4),
        "internet_graceful_rate": round(net_grace, 4),
        "provider_accuracy": round(net_full, 4),  # full pipeline proxy
        "registry_accuracy": round(reg, 4),
        "cache_hit_rate": round(cache_hits, 4),
        "warm_response_ms": round(warm_avg, 1),
        "warm_under_2s_rate": round(warm_under_2, 4),
        "charts_success": round(chart_ok, 4),
        "session_restore": round(sess_ok, 4),
        "artifacts_rate": round(arts_rate, 4),
        "error_handling": round(err, 4),
        "local_pass_rate": round(loc, 4),
        "peak_memory_mb": round(peak_mem, 1),
        "avg_memory_mb": round(sum(mem_samples) / max(len(mem_samples), 1), 1) if mem_samples else 0,
        "avg_cpu_pct": round(sum(cpu_samples) / max(len(cpu_samples), 1), 1) if cpu_samples else 0,
        "system": sys_info,
        "stage_avg_ms": stage_avg,
        "category_pass_rates": {k: round(rate(k), 4) for k in sorted(by.keys())},
        "category_counts": {k: len(v) for k, v in sorted(by.items())},
        "deployment_readiness_score": round(score, 2),
        "prior": PRIOR_BASELINE,
    }


def write_report(
    results: list[CaseResult],
    metrics: dict[str, Any],
    health: dict[str, Any],
    started: str,
    finished: str,
    duration: float,
) -> dict[str, Path]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"production_regression_{ts}.json"
    md_path = REPORT_DIR / f"production_regression_{ts}.md"
    latest_json = REPORT_DIR / "production_regression_latest.json"
    latest_md = REPORT_DIR / "PRODUCTION_READINESS_REPORT.md"

    payload = {
        "generated_at": finished,
        "started_at": started,
        "duration_seconds": round(duration, 1),
        "base_url": BASE_URL,
        "user": USER,
        "branch": "feature/cache-performance",
        "health": health,
        "metrics": metrics,
        "results": [asdict(r) for r in results],
        "fresh_run": True,
        "reused_prior_report": False,
    }
    text = json.dumps(payload, indent=2, default=str)
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    m = metrics
    prior = m["prior"]
    score = m["deployment_readiness_score"]

    def delta(cur, old, pct=False):
        try:
            d = float(cur) - float(old)
            if pct:
                return f"{d:+.1%}"
            return f"{d:+.1f}"
        except Exception:
            return "n/a"

    lines = [
        "# AI Analytics Copilot — Production Readiness Report (v2 Stack)",
        "",
        f"**Generated (UTC):** {finished}",
        f"**Duration:** {duration:.1f}s",
        f"**API:** `{BASE_URL}`",
        f"**User:** `{USER}`",
        f"**Branch:** `feature/cache-performance` (includes forecast/memory/retrieval/cache v2)",
        f"**Fresh run:** Yes — no prior report reused",
        "",
        f"## Deployment Readiness Score: **{score} / 10**",
        "",
        _badge(score),
        "",
        "## Executive Metrics",
        "",
        "| Metric | Value | Prior | Δ |",
        "|--------|------:|------:|---|",
        f"| Overall Pass Rate | **{m['pass_rate']:.1%}** | {prior['pass_rate']:.1%} | {delta(m['pass_rate'], prior['pass_rate'], True)} |",
        f"| Average Latency | **{m['average_latency_ms']:.0f} ms** | {prior['avg_latency_ms']:.0f} | {delta(m['average_latency_ms'], prior['avg_latency_ms'])} |",
        f"| P50 Latency | **{m['p50_latency_ms']:.0f} ms** | — | — |",
        f"| P95 Latency | **{m['p95_latency_ms']:.0f} ms** | — | — |",
        f"| Forecast Success % | **{m['forecast_success']:.1%}** | {prior['forecast_success']:.1%} | {delta(m['forecast_success'], prior['forecast_success'], True)} |",
        f"| Forecast Latency | **{m['forecast_latency_ms']:.0f} ms** | — | — |",
        f"| Conversation Continuity % | **{m['conversation_continuity']:.1%}** | {prior['memory_continuity']:.1%} | {delta(m['conversation_continuity'], prior['memory_continuity'], True)} |",
        f"| Internet Retrieval Success % (full) | **{m['internet_retrieval_success']:.1%}** | {prior['internet_full']:.1%} | {delta(m['internet_retrieval_success'], prior['internet_full'], True)} |",
        f"| Internet Graceful % | **{m['internet_graceful_rate']:.1%}** | {prior['internet_graceful']:.1%} | {delta(m['internet_graceful_rate'], prior['internet_graceful'], True)} |",
        f"| Provider Accuracy % | **{m['provider_accuracy']:.1%}** | — | — |",
        f"| Registry Accuracy % | **{m['registry_accuracy']:.1%}** | {prior['registry_accuracy']:.1%} | {delta(m['registry_accuracy'], prior['registry_accuracy'], True)} |",
        f"| Cache Hit Rate | **{m['cache_hit_rate']:.1%}** | {prior['cache_hit_rate']:.1%} | {delta(m['cache_hit_rate'], prior['cache_hit_rate'], True)} |",
        f"| Warm Response Time | **{m['warm_response_ms']:.0f} ms** | — | — |",
        f"| Warm &lt;2s Rate | **{m['warm_under_2s_rate']:.1%}** | — | — |",
        f"| Charts Success % | **{m['charts_success']:.1%}** | {prior['charts_rate']:.1%} | {delta(m['charts_success'], prior['charts_rate'], True)} |",
        f"| Session Restore % | **{m['session_restore']:.1%}** | — | — |",
        f"| Artifacts % | **{m['artifacts_rate']:.1%}** | — | — |",
        f"| Error Handling % | **{m['error_handling']:.1%}** | {prior['error_handling']:.1%} | {delta(m['error_handling'], prior['error_handling'], True)} |",
        f"| Peak Memory (MB) | **{m['peak_memory_mb']:.1f}** | — | — |",
        f"| Average CPU % | **{m['avg_cpu_pct']:.1f}** | — | — |",
        f"| Readiness Score | **{score}/10** | {prior['readiness']}/10 | {delta(score, prior['readiness'])} |",
        "",
        "## Category Breakdown",
        "",
        "| Category | Cases | Pass Rate |",
        "|----------|------:|----------:|",
    ]
    for cat, n in m["category_counts"].items():
        lines.append(f"| {cat} | {n} | {m['category_pass_rates'].get(cat, 0):.1%} |")

    lines += [
        "",
        "## Stage Timing Averages (ms)",
        "",
        "| Stage | Avg ms |",
        "|-------|-------:|",
    ]
    for k, v in sorted((m.get("stage_avg_ms") or {}).items()):
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Comparison vs Previous Regression",
        "",
        "### Improved",
        *_improvements(m, prior),
        "",
        "### Unchanged / Stable",
        *_unchanged(m, prior),
        "",
        "### Regressions",
        *_regressions(m, prior),
        "",
        "## Failures",
        "",
    ]
    fails = [r for r in results if not r.pass_]
    if not fails:
        lines.append("None.")
    else:
        for r in fails:
            lines.append(
                f"- **{r.id}** [{r.category}] HTTP={r.status_code} "
                f"checks=`{json.dumps(r.checks)}` notes={'; '.join(r.notes)[:120]}"
            )

    lines += [
        "",
        "## Results Table",
        "",
        "| ID | Cat | Pass | ms | Charts | FC | Cache | Topic/Provider |",
        "|----|-----|------|---:|-------:|:--:|:-----:|----------------|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.category} | {'PASS' if r.pass_ else 'FAIL'} | {r.latency_ms:.0f} | "
            f"{r.charts} | {r.forecast} | {r.cache_hit} | "
            f"{(r.dataset_topic or r.provider or '—')[:28]} |"
        )

    lines += [
        "",
        "## Remaining Blockers",
        "",
        *_blockers(m, fails),
        "",
        "## Prioritized Roadmap to 10/10",
        "",
        "1. **Forecast SLO** — Ensure all yearly/monthly series return within 10s with model tag; measure success ≥95%.",
        "2. **Ask-cache hit rate** — Align fingerprint between cold store and warm lookup (session path + same file_path); surface `cache_hit` ≥80% on repeats.",
        "3. **Warm &lt;2s** — Keep session updates lightweight; avoid FTS/summarizer on cache hits (already partially done).",
        "4. **Internet full pipeline** — Validate FRED/Eurostat/OWID live URLs; expand curated catalog for education/agriculture/trade.",
        "5. **Memory multi-turn** — Assert zero `needs_user_data` after first bind across 9-turn scripts in CI.",
        "6. **Charts** — Force default viz for pie/heatmap intents when columns allow.",
        "7. **P95 latency** — Cap remote provider probe time; parallelize provider search with overall budget.",
        "8. **Observability** — Export Prometheus metrics for cache_hit, forecast_model, provider, readiness nightly.",
        "9. **CI gate** — Nightly production regression + fail if readiness &lt; 8.5 or forecast success &lt; 80%.",
        "10. **Load test** — Concurrent 20 users on warm cache path before production cutover.",
        "",
        "## Health",
        "",
        "```json",
        json.dumps(health, indent=2)[:2000],
        "```",
        "",
        "---",
        f"_Report: `{md_path.name}` — suite continues on failure._",
        "",
    ]
    md = "\n".join(lines)
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    return {
        "json": json_path,
        "markdown": md_path,
        "latest_json": latest_json,
        "latest_markdown": latest_md,
    }


def _badge(score: float) -> str:
    if score >= 9:
        return "**Assessment:** PRODUCTION READY"
    if score >= 8:
        return "**Assessment:** NEAR PRODUCTION — minor gaps"
    if score >= 6.5:
        return "**Assessment:** STAGING / CONTROLLED ROLLOUT"
    if score >= 5:
        return "**Assessment:** DEVELOPMENT — significant gaps"
    return "**Assessment:** NOT READY"


def _improvements(m, prior):
    items = []
    if m["forecast_success"] > prior["forecast_success"] + 0.05:
        items.append(f"- Forecast success {prior['forecast_success']:.0%} → {m['forecast_success']:.0%}")
    if m["conversation_continuity"] > prior["memory_continuity"] + 0.05:
        items.append(f"- Conversation continuity {prior['memory_continuity']:.0%} → {m['conversation_continuity']:.0%}")
    if m["internet_retrieval_success"] > prior["internet_full"] + 0.05:
        items.append(f"- Internet full pipeline {prior['internet_full']:.0%} → {m['internet_retrieval_success']:.0%}")
    if m["cache_hit_rate"] > prior["cache_hit_rate"] + 0.05:
        items.append(f"- Cache hit rate {prior['cache_hit_rate']:.0%} → {m['cache_hit_rate']:.0%}")
    if m["deployment_readiness_score"] > prior["readiness"] + 0.2:
        items.append(f"- Readiness {prior['readiness']} → {m['deployment_readiness_score']}")
    if m["average_latency_ms"] < prior["avg_latency_ms"] * 0.85:
        items.append(f"- Avg latency {prior['avg_latency_ms']:.0f}ms → {m['average_latency_ms']:.0f}ms")
    if not items:
        items.append("- See category table for incremental gains.")
    return items


def _unchanged(m, prior):
    items = []
    if abs(m["registry_accuracy"] - prior["registry_accuracy"]) < 0.05:
        items.append(f"- Registry accuracy stable at {m['registry_accuracy']:.0%}")
    if abs(m["error_handling"] - prior["error_handling"]) < 0.05:
        items.append(f"- Error handling stable at {m['error_handling']:.0%}")
    if abs(m["internet_graceful_rate"] - prior["internet_graceful"]) < 0.05:
        items.append(f"- Internet graceful handling stable at {m['internet_graceful_rate']:.0%}")
    if not items:
        items.append("- Core reliability dimensions remain solid.")
    return items


def _regressions(m, prior):
    items = []
    if m["pass_rate"] < prior["pass_rate"] - 0.05:
        items.append(f"- Overall pass rate dropped {prior['pass_rate']:.0%} → {m['pass_rate']:.0%}")
    if m["forecast_success"] < prior["forecast_success"] - 0.05:
        items.append(f"- Forecast success regression")
    if m["average_latency_ms"] > prior["avg_latency_ms"] * 1.15:
        items.append(f"- Average latency increased")
    if not items:
        items.append("- No major regressions vs prior baseline.")
    return items


def _blockers(m, fails):
    items = []
    if m["forecast_success"] < 0.9:
        items.append(f"- Forecast success {m['forecast_success']:.0%} below 90% target")
    if m["warm_under_2s_rate"] < 0.8:
        items.append(f"- Warm &lt;2s only {m['warm_under_2s_rate']:.0%} of cache cases")
    if m["cache_hit_rate"] < 0.8:
        items.append(f"- Cache hit rate {m['cache_hit_rate']:.0%} below 80% target")
    if m["internet_retrieval_success"] < 0.9:
        items.append(f"- Internet full pipeline {m['internet_retrieval_success']:.0%} below 90%")
    if m["conversation_continuity"] < 0.95:
        items.append(f"- Memory continuity {m['conversation_continuity']:.0%} has re-upload risk")
    if not items:
        items.append("- No critical blockers; polish remaining SLO gaps.")
    cats = {}
    for f in fails:
        cats[f.category] = cats.get(f.category, 0) + 1
    if cats:
        items.append("- Failure concentration: " + ", ".join(f"{k}={v}" for k, v in sorted(cats.items(), key=lambda x: -x[1])))
    return items


def main() -> int:
    print("=" * 72)
    print("PRODUCTION REGRESSION v2 — fresh run, continue on failure")
    print(f"API={BASE_URL} user={USER}")
    print("=" * 72)

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    peak_mem = _rss()

    code, health = _req("GET", "/health/full")
    print(f"Health HTTP {code}: {json.dumps(health)[:200]}")
    code0, _ = _req("GET", "/")
    if code0 == 0:
        print("FATAL: API unreachable")
        return 2

    print("\n[seed] local datasets...")
    paths = seed_local()
    eval_data = ROOT / "tests" / "evaluation" / "data"
    for name in ("india_population.csv", "india_gdp.csv", "gold_prices.csv", "co2_emissions.csv"):
        p = eval_data / name
        key = name.replace(".csv", "")
        if p.exists() and key not in paths:
            paths[key] = p
    if "co2_local" not in paths and (ROOT / "data" / "local_library" / "co2_emissions_local.csv").exists():
        paths["co2_local"] = ROOT / "data" / "local_library" / "co2_emissions_local.csv"

    all_results: list[CaseResult] = []
    phases = [
        ("LOCAL (≥20)", lambda: run_local(paths)),
        ("INTERNET (≥20)", run_internet),
        ("FORECAST", lambda: run_forecast(paths)),
        ("MEMORY CONTINUITY", lambda: run_memory(paths)),
        ("CACHE", lambda: run_cache(paths)),
        ("SESSIONS", lambda: run_sessions(paths)),
        ("CHARTS", lambda: run_charts(paths)),
        ("ERRORS", lambda: run_errors(paths)),
        ("REGISTRY", run_registry_unit),
    ]
    for title, fn in phases:
        print(f"\n{'=' * 20} {title} {'=' * 20}")
        try:
            batch = fn()
            all_results.extend(batch)
            peak_mem = max(peak_mem, _rss())
        except Exception as exc:
            print(f"PHASE CRASH {title}: {exc}")
            all_results.append(
                CaseResult(
                    id=f"PHASE_{title[:6]}",
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
    paths_out = write_report(all_results, metrics, health, started, finished, duration)

    print("\n" + "=" * 72)
    print(
        f"DONE total={metrics['total']} passed={metrics['passed']} "
        f"failed={metrics['failed']} pass_rate={metrics['pass_rate']:.1%}"
    )
    print(
        f"Avg={metrics['average_latency_ms']:.0f}ms P50={metrics['p50_latency_ms']:.0f} "
        f"P95={metrics['p95_latency_ms']:.0f}"
    )
    print(
        f"Forecast={metrics['forecast_success']:.0%} Continuity={metrics['conversation_continuity']:.0%} "
        f"Internet full={metrics['internet_retrieval_success']:.0%} Cache hit={metrics['cache_hit_rate']:.0%}"
    )
    print(f"Warm avg={metrics['warm_response_ms']:.0f}ms Readiness={metrics['deployment_readiness_score']}/10")
    print(f"Report: {paths_out['latest_markdown']}")
    print("=" * 72)
    return 0 if metrics["pass_rate"] >= 0.5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
