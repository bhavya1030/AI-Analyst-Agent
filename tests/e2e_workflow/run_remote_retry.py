"""Retry remote topics with queries that exercise retrieval + known open sources."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
H = {"X-User-Id": "e2e-remote-retry"}
OUT = Path(__file__).resolve().parent / "reports"
OUT.mkdir(exist_ok=True)

# Topics: keep user intent, phrasing that encourages open-data acquisition
CASES = [
    ("RR01", "Electric Vehicle Sales", "Analyze electric vehicle sales dataset and show trends"),
    ("RR02", "Global CO2 Emissions", "Analyze CO2 emissions open data and visualize trends"),
    ("RR03", "Renewable Energy", "Analyze renewable energy production open dataset"),
    ("RR04", "World Happiness Index", "Analyze world happiness index dataset"),
    ("RR05", "Air Quality Index", "Analyze air quality index open data"),
    ("RR06", "Global Inflation", "Analyze global inflation rates open data"),
    ("RR07", "Cryptocurrency", "Analyze bitcoin cryptocurrency price dataset and forecast"),
    ("RR08", "Olympic Medals", "Analyze olympic medal counts by country open data"),
    ("RR09", "Internet Usage", "Analyze global internet usage statistics open data"),
    ("RR10", "International Tourism", "Analyze international tourism arrivals open data"),
    # known good catalog paths
    ("RR11", "GDP catalog", "Analyze world GDP open data trends"),
    ("RR12", "Population catalog", "Analyze world population open data growth"),
]


def main():
    results = []
    for cid, topic, q in CASES:
        sid = f"{cid}-{uuid.uuid4().hex[:6]}"
        print(f"\n=== {cid} {topic}")
        t0 = time.perf_counter()
        try:
            r = requests.get(
                f"{BASE}/v1/ask",
                params={"question": q, "session_id": sid},
                headers=H,
                timeout=300,
            )
            ms = (time.perf_counter() - t0) * 1000
            body = r.json()
            code = r.status_code
        except Exception as e:
            ms = (time.perf_counter() - t0) * 1000
            body = {"error": str(e)}
            code = 0
        charts = body.get("charts") or []
        row = {
            "id": cid,
            "topic": topic,
            "query": q,
            "status": code,
            "ms": round(ms, 1),
            "dataset_topic": body.get("dataset_topic"),
            "source": body.get("source"),
            "needs_user_data": body.get("needs_user_data"),
            "charts": len(charts) if isinstance(charts, list) else 0,
            "forecast": bool(body.get("forecast")),
            "answer": str(body.get("answer") or body.get("error") or "")[:200],
            "discovery": body.get("dataset_discovery"),
            "acquisition_options": body.get("data_acquisition_options"),
        }
        full = (
            code == 200
            and not body.get("needs_user_data")
            and bool(body.get("answer"))
            and not body.get("error")
        )
        row["full_pipeline"] = full and row["charts"] > 0
        row["analyzed"] = full
        results.append(row)
        print(
            f"  -> {code} {ms:.0f}ms analyzed={full} full={row['full_pipeline']} "
            f"src={row['source']} charts={row['charts']} needs={row['needs_user_data']}"
        )

    path = OUT / "remote_retry_latest.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    analyzed = sum(1 for r in results if r["analyzed"])
    full = sum(1 for r in results if r["full_pipeline"])
    print(f"\nanalyzed={analyzed}/{len(results)} full_pipeline={full}/{len(results)}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
