"""
Comprehensive end-to-end analytical workflow test suite.

Exercises /v1/ask for local datasets, internet retrieval, cache, errors, and timing.
Continues on failure. Writes a markdown + JSON report under tests/e2e_workflow/reports/.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import traceback
import uuid
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
USER = os.environ.get("E2E_USER_ID", "e2e-tester")
HEADERS = {"X-User-Id": USER}
TIMEOUT_LOCAL = int(os.environ.get("E2E_TIMEOUT_LOCAL", "180"))
TIMEOUT_REMOTE = int(os.environ.get("E2E_TIMEOUT_REMOTE", "300"))
REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TestResult:
    id: str
    category: str
    query: str
    session_id: str
    pass_: bool = False
    status_code: int | None = None
    total_ms: float = 0.0
    dataset_topic: str = ""
    dataset_source: str = ""
    retrieval_source: str = ""
    file_path_used: str = ""
    charts: int = 0
    forecast: bool = False
    insights: bool = False
    hypotheses: int = 0
    suggestions: int = 0
    answer_preview: str = ""
    needs_user_data: bool = False
    error: str = ""
    cache_run: str = ""  # cold | warm | n/a
    checks: dict[str, bool] = field(default_factory=dict)
    raw_keys: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


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
        elapsed = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except Exception:
            body = {"error": r.text[:500], "raw": True}
        return r.status_code, body if isinstance(body, dict) else {"data": body}, elapsed
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        return 0, {"error": str(exc)}, elapsed


def _summarize(body: dict[str, Any]) -> dict[str, Any]:
    charts = body.get("charts") or []
    if not charts and body.get("chart"):
        charts = [body["chart"]]
    forecast = body.get("forecast") or []
    hyps = body.get("hypotheses") or []
    steps = body.get("recommended_next_steps") or []
    discovery = body.get("dataset_discovery") or {}
    answer = body.get("answer") or body.get("error") or ""
    return {
        "dataset_topic": str(body.get("dataset_topic") or discovery.get("title") or ""),
        "source": str(body.get("source") or discovery.get("source") or ""),
        "discovery_status": str(discovery.get("status") or ""),
        "charts": len(charts) if isinstance(charts, list) else (1 if charts else 0),
        "forecast": bool(forecast) and (len(forecast) > 0 if isinstance(forecast, list) else True),
        "insights": bool(str(answer).strip()) and not body.get("error"),
        "hypotheses": len(hyps) if isinstance(hyps, list) else 0,
        "suggestions": len(steps) if isinstance(steps, list) else 0,
        "answer_preview": str(answer)[:240].replace("\n", " "),
        "needs_user_data": bool(body.get("needs_user_data")),
        "keys": sorted(list(body.keys()))[:40],
    }


def _session_ok(session_id: str) -> tuple[bool, dict[str, Any]]:
    try:
        r = requests.get(
            f"{BASE_URL}/sessions/{session_id}",
            headers=HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            return False, {"status_code": r.status_code}
        data = r.json()
        msgs = data.get("chat_history") or data.get("messages") or []
        return True, {
            "message_count": data.get("message_count") or len(msgs),
            "title": data.get("title"),
            "dataset_name": data.get("dataset_name") or data.get("dataset_topic"),
            "has_artifacts": bool(
                data.get("generated_charts")
                or data.get("artifacts")
                or data.get("analysis_results")
            ),
        }
    except Exception as exc:
        return False, {"error": str(exc)}


def _cache_stats() -> dict[str, Any]:
    db_path = ROOT / "memory.db"
    if not db_path.exists():
        return {"exists": False}
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        tables = [
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        stats: dict[str, Any] = {"exists": True, "tables": tables}
        if "analysis_cache" in tables:
            row = cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(hit_count),0), COALESCE(AVG(hit_count),0) "
                "FROM analysis_cache"
            ).fetchone()
            stats["analysis_cache_rows"] = row[0]
            stats["analysis_cache_total_hits"] = row[1]
            stats["analysis_cache_avg_hits"] = round(float(row[2] or 0), 3)
        if "analysis_sessions" in tables:
            stats["sessions"] = cur.execute(
                "SELECT COUNT(*) FROM analysis_sessions"
            ).fetchone()[0]
        if "session_messages" in tables:
            stats["messages"] = cur.execute(
                "SELECT COUNT(*) FROM session_messages"
            ).fetchone()[0]
        # registry-like tables
        for t in tables:
            if "registry" in t.lower() or "dataset" in t.lower():
                try:
                    stats[f"count_{t}"] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    pass
        con.close()
        return stats
    except Exception as exc:
        return {"exists": True, "error": str(exc)}


def _health() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        out["root"] = {"status_code": r.status_code, "body": r.text[:200]}
    except Exception as exc:
        return {"error": str(exc)}
    try:
        r2 = requests.get(f"{BASE_URL}/health/llm", timeout=30)
        out["llm"] = {
            "status_code": r2.status_code,
            "body": r2.json() if "json" in r2.headers.get("content-type", "") else r2.text[:200],
        }
    except Exception as exc:
        out["llm"] = {"error": str(exc)}
    return out


def evaluate_local(paths: dict[str, Path]) -> list[TestResult]:
    cases = [
        ("L01", "seattle_weather", "Show monthly rainfall trends for Seattle weather"),
        ("L02", "seattle_weather", "Analyze temperature trends in Seattle weather dataset"),
        ("L03", "seattle_weather", "Visualize wind distribution in Seattle weather"),
        ("L04", "world_population", "Show population growth over years"),
        ("L05", "world_population", "Compare population of India and China"),
        ("L06", "world_population", "What are the top 10 most populated countries in the latest year"),
        ("L07", "india_gdp", "Analyze India's GDP trend over time"),
        ("L08", "world_gdp", "Compare GDP of India with United States"),
        ("L09", "india_gdp", "Forecast India's GDP for next 5 years"),
        ("L10", "oil_prices", "Analyze oil price trends and forecast next 5 years"),
        ("L11", "gold_prices", "Show gold price trend and forecast next 3 years"),
        ("L12", "india_rainfall", "EDA on India rainfall and visualize yearly pattern"),
        ("L13", "employees", "Analyze salary by department and show a chart"),
        ("L14", "india_inflation", "Analyze India inflation trends"),
        ("L15", "india_unemployment", "Visualize India unemployment over years"),
    ]
    results: list[TestResult] = []
    for cid, key, q in cases:
        fp = str(paths[key].resolve())
        sid = f"e2e-local-{cid}-{uuid.uuid4().hex[:8]}"
        print(f"\n=== {cid} LOCAL: {q[:70]} ===")
        code, body, ms = _ask(q, sid, file_path=fp, timeout=TIMEOUT_LOCAL)
        s = _summarize(body)
        sess_ok, sess_meta = _session_ok(sid)
        tr = TestResult(
            id=cid,
            category="local",
            query=q,
            session_id=sid,
            status_code=code,
            total_ms=round(ms, 1),
            dataset_topic=s["dataset_topic"],
            dataset_source=s["source"],
            retrieval_source="local_file",
            file_path_used=fp,
            charts=s["charts"],
            forecast=s["forecast"],
            insights=s["insights"],
            hypotheses=s["hypotheses"],
            suggestions=s["suggestions"],
            answer_preview=s["answer_preview"],
            needs_user_data=s["needs_user_data"],
            error=str(body.get("error") or ""),
            cache_run="cold",
            raw_keys=s["keys"],
        )
        want_forecast = "forecast" in q.lower()
        tr.checks = {
            "http_200": code == 200,
            "has_answer": s["insights"] or bool(s["answer_preview"]),
            "has_charts": s["charts"] > 0 or not want_forecast,  # soft for forecast-only
            "charts_strict": s["charts"] > 0,
            "forecast_if_asked": (s["forecast"] if want_forecast else True),
            "session_persisted": sess_ok,
            "no_crash": code != 0 and "Traceback" not in str(body),
            "dataset_loaded": not s["needs_user_data"],
        }
        # Pass criteria for local: 200 + answer + no crash + session + dataset loaded
        tr.pass_ = all(
            [
                tr.checks["http_200"],
                tr.checks["has_answer"],
                tr.checks["no_crash"],
                tr.checks["session_persisted"],
                tr.checks["dataset_loaded"],
            ]
        )
        if want_forecast and not s["forecast"]:
            tr.notes.append("Forecast requested but not present")
        if s["charts"] == 0:
            tr.notes.append("No charts returned")
        tr.notes.append(f"session_meta={sess_meta}")
        results.append(tr)
        print(
            f"  -> {code} {ms:.0f}ms pass={tr.pass_} charts={s['charts']} "
            f"forecast={s['forecast']} topic={s['dataset_topic']!r}"
        )
    return results


def evaluate_remote() -> list[TestResult]:
    topics = [
        ("R01", "Analyze electric vehicle sales worldwide and show trends"),
        ("R02", "Analyze global CO2 emissions over time and visualize"),
        ("R03", "Analyze renewable energy production by country"),
        ("R04", "Analyze World Happiness Index scores"),
        ("R05", "Analyze Air Quality Index trends for major cities"),
        ("R06", "Analyze global inflation rates"),
        ("R07", "Analyze cryptocurrency prices for Bitcoin"),
        ("R08", "Analyze Olympic medal counts by country"),
        ("R09", "Analyze global internet usage statistics"),
        ("R10", "Analyze international tourism arrivals"),
    ]
    results: list[TestResult] = []
    for cid, q in topics:
        sid = f"e2e-remote-{cid}-{uuid.uuid4().hex[:8]}"
        print(f"\n=== {cid} REMOTE: {q[:70]} ===")
        code, body, ms = _ask(q, sid, file_path=None, timeout=TIMEOUT_REMOTE)
        s = _summarize(body)
        sess_ok, sess_meta = _session_ok(sid)
        discovery = body.get("dataset_discovery") or {}
        tr = TestResult(
            id=cid,
            category="remote",
            query=q,
            session_id=sid,
            status_code=code,
            total_ms=round(ms, 1),
            dataset_topic=s["dataset_topic"],
            dataset_source=s["source"],
            retrieval_source=str(
                discovery.get("status")
                or body.get("source")
                or ("needs_user_data" if s["needs_user_data"] else "unknown")
            ),
            charts=s["charts"],
            forecast=s["forecast"],
            insights=s["insights"],
            hypotheses=s["hypotheses"],
            suggestions=s["suggestions"],
            answer_preview=s["answer_preview"],
            needs_user_data=s["needs_user_data"],
            error=str(body.get("error") or ""),
            cache_run="cold",
            raw_keys=s["keys"],
        )
        # Remote pass: no crash, 200, and either analysis OR graceful acquisition path
        graceful = s["needs_user_data"] or bool(body.get("data_acquisition_options"))
        analyzed = s["insights"] and not s["needs_user_data"]
        tr.checks = {
            "http_200": code == 200,
            "no_crash": code != 0,
            "session_persisted": sess_ok,
            "retrieval_or_graceful": analyzed or graceful or bool(s["answer_preview"]),
            "dataset_discovered": analyzed or bool(discovery.get("status")),
            "charts_or_graceful": s["charts"] > 0 or graceful or analyzed,
            "full_pipeline": analyzed and s["charts"] > 0,
        }
        tr.pass_ = all(
            [
                tr.checks["http_200"],
                tr.checks["no_crash"],
                tr.checks["session_persisted"],
                tr.checks["retrieval_or_graceful"],
            ]
        )
        if not tr.checks["full_pipeline"]:
            tr.notes.append(
                "Partial pipeline: full download→EDA→chart path not confirmed"
            )
        tr.notes.append(f"session_meta={sess_meta}")
        tr.notes.append(f"discovery={discovery}")
        results.append(tr)
        print(
            f"  -> {code} {ms:.0f}ms pass={tr.pass_} full={tr.checks['full_pipeline']} "
            f"charts={s['charts']} needs_data={s['needs_user_data']} src={tr.retrieval_source}"
        )
    return results


def evaluate_cache(paths: dict[str, Path]) -> list[TestResult]:
    """Repeat a subset of local queries; expect faster second run and reuse."""
    cases = [
        ("C01", "india_gdp", "Analyze India's GDP trend over time"),
        ("C02", "seattle_weather", "Show monthly rainfall trends for Seattle weather"),
        ("C03", "world_population", "Show population growth over years"),
        ("C04", "oil_prices", "Analyze oil price trends and forecast next 5 years"),
    ]
    results: list[TestResult] = []
    for cid, key, q in cases:
        fp = str(paths[key].resolve())
        sid_cold = f"e2e-cache-cold-{cid}-{uuid.uuid4().hex[:6]}"
        sid_warm = f"e2e-cache-warm-{cid}-{uuid.uuid4().hex[:6]}"
        print(f"\n=== {cid} CACHE cold/warm: {q[:60]} ===")
        code1, body1, ms1 = _ask(q, sid_cold, file_path=fp, timeout=TIMEOUT_LOCAL)
        s1 = _summarize(body1)
        code2, body2, ms2 = _ask(q, sid_warm, file_path=fp, timeout=TIMEOUT_LOCAL)
        s2 = _summarize(body2)
        speedup = (ms1 / ms2) if ms2 > 0 else 0
        tr = TestResult(
            id=cid,
            category="cache",
            query=q,
            session_id=sid_warm,
            status_code=code2,
            total_ms=round(ms2, 1),
            dataset_topic=s2["dataset_topic"],
            retrieval_source="local_file",
            file_path_used=fp,
            charts=s2["charts"],
            forecast=s2["forecast"],
            insights=s2["insights"],
            answer_preview=f"cold={ms1:.0f}ms warm={ms2:.0f}ms speedup={speedup:.2f}x | {s2['answer_preview'][:120]}",
            cache_run="warm",
            checks={
                "cold_ok": code1 == 200 and s1["insights"],
                "warm_ok": code2 == 200 and s2["insights"],
                "warm_not_slower_5x": ms2 < ms1 * 5 + 5000,  # allow variance
                "both_have_output": s1["charts"] > 0 or s2["charts"] > 0 or s2["insights"],
            },
            notes=[
                f"cold_ms={ms1:.1f}",
                f"warm_ms={ms2:.1f}",
                f"speedup={speedup:.3f}",
                f"cold_charts={s1['charts']} warm_charts={s2['charts']}",
            ],
        )
        tr.pass_ = all(tr.checks.values())
        results.append(tr)
        # Also record cold as separate note in print
        print(f"  -> cold={ms1:.0f}ms warm={ms2:.0f}ms speedup={speedup:.2f}x pass={tr.pass_}")
    return results


def evaluate_errors() -> list[TestResult]:
    cases = [
        ("E01", "Analyze GDP of Atlantis"),
        ("E02", "Analyze Unicorn Population worldwide"),
        ("E03", "Analyze Dragon Population trends"),
        ("E04", "Analyze XYZABC123 dataset completely"),
    ]
    results: list[TestResult] = []
    for cid, q in cases:
        sid = f"e2e-err-{cid}-{uuid.uuid4().hex[:8]}"
        print(f"\n=== {cid} ERROR: {q} ===")
        code, body, ms = _ask(q, sid, timeout=TIMEOUT_REMOTE)
        s = _summarize(body)
        # Graceful: HTTP 200 with helpful message OR 4xx with error body; never 500/crash
        crashed = code == 0 or code >= 500
        helpful = bool(s["answer_preview"]) or bool(body.get("error")) or s["needs_user_data"]
        tr = TestResult(
            id=cid,
            category="error",
            query=q,
            session_id=sid,
            status_code=code,
            total_ms=round(ms, 1),
            answer_preview=s["answer_preview"] or str(body.get("error") or "")[:240],
            needs_user_data=s["needs_user_data"],
            error=str(body.get("error") or ""),
            retrieval_source="n/a",
            checks={
                "no_crash": not crashed,
                "responded": code != 0,
                "helpful_message": helpful,
                "not_500": code < 500 if code else False,
            },
            notes=[f"keys={s['keys']}"],
        )
        tr.pass_ = all(tr.checks.values())
        results.append(tr)
        print(f"  -> {code} {ms:.0f}ms pass={tr.pass_} helpful={helpful}")
    return results


def readiness_score(results: list[TestResult], cache_stats: dict) -> tuple[float, dict]:
    by_cat: dict[str, list[TestResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    def rate(cat: str) -> float:
        items = by_cat.get(cat) or []
        if not items:
            return 0.0
        return sum(1 for x in items if x.pass_) / len(items)

    local_r = rate("local")
    remote_r = rate("remote")
    cache_r = rate("cache")
    err_r = rate("error")
    full_remote = sum(
        1 for x in by_cat.get("remote", []) if x.checks.get("full_pipeline")
    )
    remote_full_r = full_remote / max(len(by_cat.get("remote", [])), 1)

    # Weighted readiness
    score = (
        local_r * 3.0
        + remote_r * 2.0
        + remote_full_r * 2.0
        + cache_r * 1.5
        + err_r * 1.5
    )
    # normalize to 10 (weights sum to 10)
    breakdown = {
        "local_pass_rate": round(local_r, 3),
        "remote_graceful_pass_rate": round(remote_r, 3),
        "remote_full_pipeline_rate": round(remote_full_r, 3),
        "cache_pass_rate": round(cache_r, 3),
        "error_pass_rate": round(err_r, 3),
        "cache_stats": cache_stats,
    }
    return round(score, 2), breakdown


def write_report(
    results: list[TestResult],
    health: dict,
    cache_before: dict,
    cache_after: dict,
    score: float,
    breakdown: dict,
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"e2e_report_{ts}.json"
    md_path = REPORT_DIR / f"e2e_report_{ts}.md"
    latest_md = REPORT_DIR / "e2e_report_latest.md"
    latest_json = REPORT_DIR / "e2e_report_latest.json"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "user": USER,
        "health": health,
        "cache_before": cache_before,
        "cache_after": cache_after,
        "readiness_score": score,
        "breakdown": breakdown,
        "results": [asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    passed = sum(1 for r in results if r.pass_)
    failed = len(results) - passed
    lines = [
        "# AI Analytics Copilot — End-to-End Workflow Test Report",
        "",
        f"**Generated (UTC):** {payload['generated_at']}",
        f"**API:** `{BASE_URL}`",
        f"**User:** `{USER}`",
        f"**Readiness score:** **{score} / 10**",
        "",
        "## 1. Test Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total tests | {len(results)} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Pass rate | {passed/max(len(results),1):.1%} |",
        f"| Local pass rate | {breakdown['local_pass_rate']:.1%} |",
        f"| Remote graceful pass rate | {breakdown['remote_graceful_pass_rate']:.1%} |",
        f"| Remote full pipeline rate | {breakdown['remote_full_pipeline_rate']:.1%} |",
        f"| Cache pass rate | {breakdown['cache_pass_rate']:.1%} |",
        f"| Error handling pass rate | {breakdown['error_pass_rate']:.1%} |",
        "",
        "### Health",
        "```json",
        json.dumps(health, indent=2)[:2000],
        "```",
        "",
        "### Cache stats (before → after)",
        "```json",
        json.dumps({"before": cache_before, "after": cache_after}, indent=2)[:3000],
        "```",
        "",
        "## 2. Results by query",
        "",
        "| ID | Cat | Pass | ms | Charts | Forecast | Insights | Source | Dataset |",
        "|----|-----|------|----|--------|----------|----------|--------|---------|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.category} | {'PASS' if r.pass_ else 'FAIL'} | {r.total_ms:.0f} | "
            f"{r.charts} | {r.forecast} | {r.insights} | {r.retrieval_source[:24]} | "
            f"{(r.dataset_topic or '-')[:28]} |"
        )

    lines += ["", "## 3. Detailed results", ""]
    for r in results:
        lines += [
            f"### {r.id} — {r.category} — {'PASS' if r.pass_ else 'FAIL'}",
            "",
            f"- **Query:** {r.query}",
            f"- **Session:** `{r.session_id}`",
            f"- **HTTP:** {r.status_code}",
            f"- **Time:** {r.total_ms:.1f} ms",
            f"- **Dataset:** {r.dataset_topic or '—'}",
            f"- **Retrieval source:** {r.retrieval_source}",
            f"- **File path:** `{r.file_path_used or '—'}`",
            f"- **Charts:** {r.charts} | **Forecast:** {r.forecast} | **Insights:** {r.insights}",
            f"- **Hypotheses:** {r.hypotheses} | **Suggestions:** {r.suggestions}",
            f"- **Cache run:** {r.cache_run}",
            f"- **Answer preview:** {r.answer_preview[:300]}",
            f"- **Error:** {r.error or '—'}",
            f"- **Checks:** `{json.dumps(r.checks)}`",
            f"- **Notes:** {'; '.join(r.notes) if r.notes else '—'}",
            "",
        ]

    # Performance section
    local_ms = [r.total_ms for r in results if r.category == "local"]
    remote_ms = [r.total_ms for r in results if r.category == "remote"]
    cache_notes = [r for r in results if r.category == "cache"]
    lines += [
        "## 4. Performance",
        "",
        f"- Local avg: {sum(local_ms)/max(len(local_ms),1):.0f} ms (n={len(local_ms)})",
        f"- Local min/max: {(min(local_ms) if local_ms else 0):.0f} / {(max(local_ms) if local_ms else 0):.0f} ms",
        f"- Remote avg: {sum(remote_ms)/max(len(remote_ms),1):.0f} ms (n={len(remote_ms)})",
        f"- Remote min/max: {(min(remote_ms) if remote_ms else 0):.0f} / {(max(remote_ms) if remote_ms else 0):.0f} ms",
        "",
        "### Cache cold vs warm",
        "",
    ]
    for r in cache_notes:
        note_txt = "; ".join(r.notes)
        lines.append(f"- {r.id}: {note_txt} pass={r.pass_}")

    # Bugs
    fails = [r for r in results if not r.pass_]
    lines += ["", "## 5. Bugs discovered", ""]
    if not fails:
        lines.append("No hard failures against pass criteria.")
    else:
        for r in fails:
            lines.append(
                f"- **{r.id}** ({r.category}): HTTP {r.status_code}, error=`{r.error[:120]}`, "
                f"checks={r.checks}, preview={r.answer_preview[:100]}"
            )

    lines += [
        "",
        "## 6. Root cause analysis",
        "",
        "Failures typically fall into:",
        "1. **Remote discovery gaps** — open-data search cannot find a clean downloadable CSV for niche topics.",
        "2. **LLM latency / timeouts** — planner or agents exceed client timeout under load.",
        "3. **Partial pipelines** — answer returned without charts/forecast when viz agent skipped.",
        "4. **Cache timing variance** — warm path may still re-run LLM for natural language wrapping.",
        "",
        "## 7. Recommended fixes",
        "",
        "1. Strengthen dataset search ranking and known-source catalogs for common topics (EV, tourism, AQI).",
        "2. Persist and surface stage-level timings (planner, retrieve, eda, viz, forecast) in `/v1/ask` response meta.",
        "3. Ensure analysis cache short-circuits full graph on identical fingerprint+question.",
        "4. For fictional topics, return a structured `not_found` discovery status with acquisition options (already partial).",
        "5. Add registry dedupe checks after remote download.",
        "",
        f"## 8. Overall readiness: **{score}/10**",
        "",
        json.dumps(breakdown, indent=2),
        "",
    ]

    md = "\n".join(lines)
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    print(f"\n[report] {md_path}")
    print(f"[report] {latest_md}")
    return latest_md


def main() -> int:
    print(f"E2E suite → {BASE_URL} user={USER}")
    health = _health()
    if health.get("error") or health.get("status_code") not in (200, None) and "error" in health:
        # status may vary
        if "error" in health:
            print(f"FATAL: API not reachable: {health}")
            print("Start backend: uvicorn backend.main:app --host 127.0.0.1 --port 8000")
            return 2

    print("Health:", json.dumps(health)[:300])
    paths = seed_local()
    cache_before = _cache_stats()
    print("Cache before:", cache_before)

    all_results: list[TestResult] = []
    try:
        all_results.extend(evaluate_local(paths))
    except Exception:
        traceback.print_exc()
    try:
        all_results.extend(evaluate_remote())
    except Exception:
        traceback.print_exc()
    try:
        all_results.extend(evaluate_cache(paths))
    except Exception:
        traceback.print_exc()
    try:
        all_results.extend(evaluate_errors())
    except Exception:
        traceback.print_exc()

    cache_after = _cache_stats()
    score, breakdown = readiness_score(all_results, cache_after)
    write_report(all_results, health, cache_before, cache_after, score, breakdown)

    passed = sum(1 for r in all_results if r.pass_)
    print(f"\nDONE passed={passed}/{len(all_results)} readiness={score}/10")
    return 0 if passed == len(all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
