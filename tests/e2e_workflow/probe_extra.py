"""Extra probes: open-data GDP, cache hit counts, registry."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
H = {"X-User-Id": "e2e-probe"}
ROOT = Path(__file__).resolve().parents[2]


def ask(q: str, sid: str, fp: str | None = None, timeout: int = 180):
    params = {"question": q, "session_id": sid}
    if fp:
        params["file_path"] = fp
    t0 = time.perf_counter()
    r = requests.get(f"{BASE}/v1/ask", params=params, headers=H, timeout=timeout)
    ms = (time.perf_counter() - t0) * 1000
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    return r.status_code, body, ms


def main():
    # Open-data style queries that match config DATASET_SOURCES
    for q, sid in [
        ("Analyze GDP trends using world bank open data", "probe-gdp-1"),
        ("Analyze population growth using open population dataset", "probe-pop-1"),
        ("find dataset about gold prices and analyze it", "probe-gold-1"),
    ]:
        print(f"\n=== {sid}: {q}")
        code, body, ms = ask(q, sid, timeout=240)
        print(
            f"  status={code} ms={ms:.0f} topic={body.get('dataset_topic')!r} "
            f"source={body.get('source')!r} needs={body.get('needs_user_data')} "
            f"charts={len(body.get('charts') or [])} forecast={bool(body.get('forecast'))}"
        )
        print(f"  discovery={body.get('dataset_discovery')}")
        print(f"  answer={(body.get('answer') or body.get('error') or '')[:180]!r}")

    # Same local file twice for cache hit observation
    fp = str((ROOT / "data" / "local_library" / "india_gdp.csv").resolve())
    print("\n=== cache same file twice")
    for i, sid in enumerate(["probe-cache-a", "probe-cache-b"]):
        code, body, ms = ask("Analyze India's GDP trend over time", sid, fp=fp, timeout=120)
        print(f"  run{i+1} status={code} ms={ms:.0f} charts={len(body.get('charts') or [])}")

    con = sqlite3.connect(str(ROOT / "memory.db"))
    cur = con.cursor()
    print("\n=== DB")
    print("analysis_cache", cur.execute("select count(*), coalesce(sum(hit_count),0) from analysis_cache").fetchone())
    print("kinds", cur.execute("select kind, count(*), coalesce(sum(hit_count),0) from analysis_cache group by kind").fetchall())
    print("registry", cur.execute("select count(*) from dataset_registry").fetchone())
    print("learned", cur.execute("select count(*) from learned_datasets").fetchone())
    print(
        "e2e_sessions",
        cur.execute(
            "select count(*) from analysis_sessions where session_id like 'e2e-%' or session_id like 'probe-%'"
        ).fetchone(),
    )
    print("messages", cur.execute("select count(*) from session_messages").fetchone())
    # sample registry rows
    try:
        rows = cur.execute(
            "select * from dataset_registry limit 3"
        ).fetchall()
        print("registry sample", rows)
    except Exception as e:
        print("registry sample err", e)
    con.close()


if __name__ == "__main__":
    main()
