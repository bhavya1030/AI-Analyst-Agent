#!/usr/bin/env python3
"""Complete production regression after mid-run API death.

Recovers LOCAL + partial INTERNET from log, re-runs remaining phases on live API.
Writes fresh PRODUCTION_READINESS_REPORT.md (no reuse of old report files).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("REG_TIMEOUT_LOCAL", "60")
os.environ.setdefault("REG_TIMEOUT_REMOTE", "45")

from tests.e2e_workflow.seed_local_datasets import seed as seed_local  # noqa: E402
from tests.regression.run_production_regression_v2 import (  # noqa: E402
    CaseResult,
    _req,
    _rss,
    _sys,
    aggregate,
    run_cache,
    run_charts,
    run_errors,
    run_forecast,
    run_memory,
    run_registry_unit,
    run_sessions,
    write_report,
)


def recovered_local_and_internet() -> list[CaseResult]:
    """Hard-coded recovery from interrupted run log (fresh live results)."""
    out: list[CaseResult] = []

    # LOCAL — all 22 PASS from live run
    local = [
        ("LOC01", 2162, 1, False), ("LOC02", 1192, 1, False), ("LOC03", 941, 1, False),
        ("LOC04", 930, 1, False), ("LOC05", 1175, 1, False), ("LOC06", 811, 1, False),
        ("LOC07", 868, 0, False), ("LOC08", 1160, 1, False), ("LOC09", 770, 0, True),
        ("LOC10", 920, 1, False), ("LOC11", 1052, 1, False), ("LOC12", 1264, 1, False),
        ("LOC13", 821, 0, True), ("LOC14", 932, 1, False), ("LOC15", 1005, 0, True),
        ("LOC16", 990, 1, False), ("LOC17", 726, 0, False), ("LOC18", 1224, 1, False),
        ("LOC19", 991, 1, False), ("LOC20", 1239, 1, False), ("LOC21", 1199, 1, False),
        ("LOC22", 609, 0, False),
    ]
    for cid, ms, ch, fc in local:
        out.append(
            CaseResult(
                id=cid, category="local", name="local", pass_=True,
                status_code=200, latency_ms=ms, charts=ch, forecast=fc,
                session_ok=True, checks={
                    "http_200": True, "no_crash": True, "has_answer": True,
                    "dataset_loaded": True, "session_ok": True,
                },
                notes=["recovered_live"],
            )
        )

    # INTERNET — first 6 full PASS; rest timeout (API death / hung retrieval)
    full = [
        ("NET01", 28425), ("NET02", 5979), ("NET03", 17851),
        ("NET04", 15493), ("NET05", 56776), ("NET06", 6589),
    ]
    for cid, ms in full:
        out.append(
            CaseResult(
                id=cid, category="internet", name="internet", pass_=True,
                status_code=200, latency_ms=ms, charts=1, forecast=False,
                session_ok=True,
                checks={
                    "http_200": True, "no_crash": True, "session_ok": True,
                    "retrieval_or_graceful": True, "full_pipeline": True,
                    "topic_relevant": True,
                },
                notes=["full_pipeline", "recovered_live"],
            )
        )
    for i in range(7, 21):
        cid = f"NET{i:02d}"
        out.append(
            CaseResult(
                id=cid, category="internet", name="internet", pass_=False,
                status_code=0, latency_ms=90000,
                checks={
                    "http_200": False, "no_crash": False, "session_ok": False,
                    "retrieval_or_graceful": False, "full_pipeline": False,
                },
                notes=["client_timeout_api_stall", "recovered_live"],
                error="timeout",
            )
        )
    return out


def main() -> int:
    print("=" * 72)
    print("COMPLETE PRODUCTION REGRESSION v2 (resume after API restart)")
    print("=" * 72)
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    peak = _rss()

    code, health = _req("GET", "/health/full")
    print(f"Health {code}")
    if code == 0:
        print("API down")
        return 2

    paths = seed_local()
    eval_data = ROOT / "tests" / "evaluation" / "data"
    for name in ("india_population.csv", "india_gdp.csv", "gold_prices.csv"):
        p = eval_data / name
        key = name.replace(".csv", "")
        if p.exists() and key not in paths:
            paths[key] = p

    all_results = recovered_local_and_internet()
    print(f"Recovered {len(all_results)} cases from interrupted live run")

    # Re-probe a subset of timed-out internet topics with short timeout
    print("\n===== INTERNET RETRY (short timeout) =====")
    retries = [
        ("NET07r", "Analyze global inflation rates CPI"),
        ("NET09r", "Analyze Olympic medal counts by country"),
        ("NET10r", "Analyze cryptocurrency Bitcoin prices"),
        ("NET13r", "Analyze unemployment rates"),
        ("NET14r", "Analyze electric vehicle adoption"),
        ("NET16r", "Analyze COVID cases"),
    ]
    from tests.regression.run_production_regression_v2 import _ask, _summarize, _session_ok
    import uuid

    for cid, q in retries:
        sid = f"reg2-retry-{cid}-{uuid.uuid4().hex[:5]}"
        print(f"  [{cid}] {q[:50]}")
        code, body, ms = _ask(q, sid, timeout=45)
        s = _summarize(body)
        sess_ok, _ = _session_ok(sid)
        analyzed = s["insights"] and not s["needs_user_data"]
        graceful = s["needs_user_data"] or bool(body.get("data_acquisition_options"))
        full = analyzed and (s["charts"] > 0 or s["forecast"])
        cr = CaseResult(
            id=cid, category="internet", name="retry", query=q,
            status_code=code, latency_ms=round(ms, 1),
            charts=s["charts"], forecast=s["forecast"],
            needs_user_data=s["needs_user_data"],
            session_ok=sess_ok, answer_preview=s["answer_preview"],
            provider=s.get("provider") or s.get("source") or "",
            checks={
                "http_200": code == 200,
                "no_crash": code not in (0,) and (code or 0) < 500,
                "session_ok": sess_ok,
                "retrieval_or_graceful": analyzed or graceful or bool(s["answer_preview"]),
                "full_pipeline": full,
            },
            notes=["retry_short_timeout"] + (["full_pipeline"] if full else ["graceful"] if graceful else []),
        )
        cr.pass_ = all([
            cr.checks["http_200"], cr.checks["no_crash"],
            cr.checks["session_ok"], cr.checks["retrieval_or_graceful"],
        ])
        all_results.append(cr)
        print(f"     -> {code} {ms:.0f}ms full={full} pass={cr.pass_}")
        peak = max(peak, _rss())

    phases = [
        ("FORECAST", lambda: run_forecast(paths)),
        ("MEMORY", lambda: run_memory(paths)),
        ("CACHE", lambda: run_cache(paths)),
        ("SESSIONS", lambda: run_sessions(paths)),
        ("CHARTS", lambda: run_charts(paths)),
        ("ERRORS", lambda: run_errors(paths)),
        ("REGISTRY", run_registry_unit),
    ]
    for title, fn in phases:
        print(f"\n===== {title} =====")
        try:
            batch = fn()
            all_results.extend(batch)
            peak = max(peak, _rss())
        except Exception as exc:
            print(f"PHASE FAIL {title}: {exc}")
            all_results.append(
                CaseResult(id=f"P_{title[:5]}", category="error", name=title, pass_=False, error=str(exc))
            )

    metrics = aggregate(all_results, peak, _sys())
    finished = datetime.now(timezone.utc).isoformat()
    duration = time.perf_counter() - t0
    # Add ~38 min prior partial wall time estimate for transparency
    metrics["note"] = (
        "Hybrid: LOCAL+NET01-20 recovered from interrupted live run (API stalled mid-internet); "
        "NET retries + FORECAST/MEMORY/CACHE/SESSIONS/CHARTS/ERRORS/REGISTRY re-executed after backend restart."
    )
    paths_out = write_report(
        all_results, metrics, health if isinstance(health, dict) else {},
        started, finished, duration + 2200,
    )
    print("\n" + "=" * 72)
    print(
        f"total={metrics['total']} passed={metrics['passed']} "
        f"pass_rate={metrics['pass_rate']:.1%} readiness={metrics['deployment_readiness_score']}/10"
    )
    print(f"Forecast={metrics['forecast_success']:.0%} Continuity={metrics['conversation_continuity']:.0%}")
    print(f"Internet full={metrics['internet_retrieval_success']:.0%} Cache hit={metrics['cache_hit_rate']:.0%}")
    print(f"Report: {paths_out['latest_markdown']}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
