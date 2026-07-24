"""Generate Markdown, CSV, and HTML dashboard reports from evaluation runs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tests.evaluation.metrics import EvaluationMetrics, aggregate_metrics


class ReportGenerator:
    """Write evaluation artifacts to an output directory."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        records: list[dict[str, Any]],
        metrics: EvaluationMetrics | None = None,
        *,
        run_meta: dict[str, Any] | None = None,
    ) -> dict[str, Path]:
        metrics = metrics or aggregate_metrics(records)
        meta = run_meta or {}
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        paths = {
            "markdown": self.output_dir / f"evaluation_report_{ts}.md",
            "csv": self.output_dir / f"evaluation_results_{ts}.csv",
            "dashboard": self.output_dir / f"evaluation_dashboard_{ts}.html",
            "json": self.output_dir / f"evaluation_full_{ts}.json",
            "latest_markdown": self.output_dir / "evaluation_report.md",
            "latest_csv": self.output_dir / "evaluation_results.csv",
            "latest_dashboard": self.output_dir / "evaluation_dashboard.html",
            "latest_json": self.output_dir / "evaluation_full.json",
        }

        md = self._render_markdown(records, metrics, meta)
        paths["markdown"].write_text(md, encoding="utf-8")
        paths["latest_markdown"].write_text(md, encoding="utf-8")

        self._write_csv(paths["csv"], records)
        self._write_csv(paths["latest_csv"], records)

        html = self._render_dashboard(records, metrics, meta)
        paths["dashboard"].write_text(html, encoding="utf-8")
        paths["latest_dashboard"].write_text(html, encoding="utf-8")

        payload = {
            "meta": meta,
            "metrics": metrics.to_dict(),
            "records": records,
        }
        paths["json"].write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        paths["latest_json"].write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

        return paths

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def _render_markdown(
        self,
        records: list[dict[str, Any]],
        metrics: EvaluationMetrics,
        meta: dict[str, Any],
    ) -> str:
        lines: list[str] = []
        lines.append("# AI Analytics Copilot — Evaluation Report")
        lines.append("")
        lines.append(f"- Generated (UTC): `{meta.get('finished_at') or datetime.now(timezone.utc).isoformat()}`")
        lines.append(f"- Mode: `{meta.get('mode', 'component')}`")
        lines.append(f"- Duration (s): `{meta.get('total_duration', 'n/a')}`")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total tests | {metrics.total_tests} |")
        lines.append(f"| Passed | {metrics.passed} |")
        lines.append(f"| Failed | {metrics.failed} |")
        lines.append(f"| Warnings | {metrics.warnings} |")
        lines.append(f"| Success rate | {metrics.success_rate:.1%} |")
        lines.append(f"| Avg response time (s) | {metrics.average_response_time:.3f} |")
        lines.append(f"| Avg retrieval time (s) | {metrics.average_retrieval_time:.3f} |")
        lines.append(f"| Avg acquisition time (s) | {metrics.average_acquisition_time:.3f} |")
        lines.append(f"| Avg analysis time (s) | {metrics.average_analysis_time:.3f} |")
        lines.append(f"| Avg confidence | {metrics.average_confidence:.3f} |")
        lines.append(f"| P95 response time (s) | {metrics.p95_response_time:.3f} |")
        lines.append(f"| Peak memory (MB) | {metrics.peak_memory_mb:.1f} |")
        lines.append("")
        lines.append("## Capability Scores (0–1)")
        lines.append("")
        lines.append("| Capability | Score |")
        lines.append("|------------|-------|")
        for label, val in [
            ("Dataset Retrieval Accuracy", metrics.dataset_retrieval_accuracy),
            ("Dataset Selection Accuracy", metrics.dataset_selection_accuracy),
            ("Semantic Search Accuracy", metrics.semantic_search_accuracy),
            ("Planner Accuracy", metrics.planner_accuracy),
            ("Context Resolution Accuracy", metrics.context_resolution_accuracy),
            ("Join Accuracy", metrics.join_accuracy),
            ("Forecast Execution", metrics.forecast_execution),
            ("Chart Generation", metrics.chart_generation),
            ("Explanation Quality", metrics.explanation_quality),
            ("Failure Recovery", metrics.failure_recovery),
        ]:
            lines.append(f"| {label} | {val:.3f} |")
        lines.append("")
        lines.append("## By Category")
        lines.append("")
        lines.append("| Category | Total | Passed | Failed | Warnings | Pass rate |")
        lines.append("|----------|-------|--------|--------|----------|-----------|")
        for cat, stats in sorted(metrics.by_category.items()):
            lines.append(
                f"| {cat} | {stats.get('total', 0)} | {stats.get('passed', 0)} | "
                f"{stats.get('failed', 0)} | {stats.get('warnings', 0)} | "
                f"{stats.get('pass_rate', 0):.1%} |"
            )
        lines.append("")
        if metrics.failure_reasons:
            lines.append("## Failure Reasons")
            lines.append("")
            for fr in metrics.failure_reasons[:50]:
                errs = "; ".join(str(e) for e in (fr.get("errors") or [])[:3]) or "n/a"
                lines.append(
                    f"- **#{fr.get('id')}** ({fr.get('category')}): "
                    f"{fr.get('question')} — {errs}"
                )
            lines.append("")
        lines.append("## Case Results")
        lines.append("")
        lines.append("| ID | Category | Status | Time (s) | Confidence | Question |")
        lines.append("|----|----------|--------|----------|------------|----------|")
        for r in records:
            q = (r.get("question") or "").replace("|", "\\|")[:80]
            lines.append(
                f"| {r.get('id')} | {r.get('category')} | {r.get('status')} | "
                f"{float(r.get('execution_time') or 0):.2f} | "
                f"{float(r.get('confidence') or 0):.2f} | {q} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("_Generated by `tests/evaluation` framework. Modules under test were not modified._")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def _write_csv(self, path: Path, records: list[dict[str, Any]]) -> None:
        fields = [
            "id",
            "category",
            "status",
            "question",
            "execution_time",
            "retrieval_time",
            "acquisition_time",
            "analysis_time",
            "confidence",
            "retrieval_status",
            "acquisition_success",
            "mean_score",
            "n_datasets",
            "n_tools",
            "n_charts",
            "has_explanation",
            "errors",
            "warnings",
        ]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for r in records:
                scores = r.get("scores") or {}
                row = {
                    "id": r.get("id"),
                    "category": r.get("category"),
                    "status": r.get("status"),
                    "question": r.get("question"),
                    "execution_time": r.get("execution_time"),
                    "retrieval_time": r.get("retrieval_time"),
                    "acquisition_time": r.get("acquisition_time"),
                    "analysis_time": r.get("analysis_time"),
                    "confidence": r.get("confidence"),
                    "retrieval_status": r.get("retrieval_status"),
                    "acquisition_success": r.get("acquisition_success"),
                    "mean_score": scores.get("mean"),
                    "n_datasets": len(r.get("retrieved_datasets") or []),
                    "n_tools": len(r.get("selected_tools") or []),
                    "n_charts": len(r.get("generated_charts") or []),
                    "has_explanation": bool(r.get("explanation")),
                    "errors": " | ".join(str(e) for e in (r.get("errors") or [])[:5]),
                    "warnings": " | ".join(str(w) for w in (r.get("warnings") or [])[:5]),
                }
                writer.writerow(row)

    # ------------------------------------------------------------------
    # HTML dashboard
    # ------------------------------------------------------------------

    def _render_dashboard(
        self,
        records: list[dict[str, Any]],
        metrics: EvaluationMetrics,
        meta: dict[str, Any],
    ) -> str:
        # Simple self-contained dashboard (no external CDN required)
        cat_rows = "".join(
            f"<tr><td>{cat}</td><td>{s.get('total',0)}</td><td>{s.get('passed',0)}</td>"
            f"<td>{s.get('failed',0)}</td><td>{s.get('warnings',0)}</td>"
            f"<td>{s.get('pass_rate',0):.1%}</td></tr>"
            for cat, s in sorted(metrics.by_category.items())
        )
        case_rows = "".join(
            f"<tr class='{r.get('status')}'><td>{r.get('id')}</td>"
            f"<td>{r.get('category')}</td><td>{r.get('status')}</td>"
            f"<td>{float(r.get('execution_time') or 0):.2f}</td>"
            f"<td>{float(r.get('confidence') or 0):.2f}</td>"
            f"<td>{_html_escape((r.get('question') or '')[:100])}</td></tr>"
            for r in records
        )
        capability = [
            ("Retrieval", metrics.dataset_retrieval_accuracy),
            ("Selection", metrics.dataset_selection_accuracy),
            ("Semantic", metrics.semantic_search_accuracy),
            ("Planner", metrics.planner_accuracy),
            ("Context", metrics.context_resolution_accuracy),
            ("Join", metrics.join_accuracy),
            ("Forecast", metrics.forecast_execution),
            ("Charts", metrics.chart_generation),
            ("Explain", metrics.explanation_quality),
            ("Recovery", metrics.failure_recovery),
        ]
        bars = "".join(
            f"<div class='bar-row'><span>{name}</span>"
            f"<div class='bar'><div style='width:{max(0,min(100,val*100)):.1f}%'></div></div>"
            f"<span>{val:.2f}</span></div>"
            for name, val in capability
        )
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>AI Analytics Copilot — Evaluation Dashboard</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; background: #0f1419; color: #e7ecf3; }}
  h1,h2 {{ color: #fff; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(160px,1fr)); gap: 12px; }}
  .card {{ background: #1a2332; border-radius: 10px; padding: 14px; }}
  .card .v {{ font-size: 1.6rem; font-weight: 700; }}
  .passed {{ color: #3dd68c; }}
  .failed {{ color: #f07178; }}
  .warning {{ color: #ffcc66; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.9rem; }}
  th, td {{ border-bottom: 1px solid #2a3548; padding: 8px; text-align: left; }}
  th {{ color: #9fb3c8; }}
  tr.passed td:nth-child(3) {{ color: #3dd68c; }}
  tr.failed td:nth-child(3) {{ color: #f07178; }}
  tr.warning td:nth-child(3) {{ color: #ffcc66; }}
  .bar-row {{ display: grid; grid-template-columns: 100px 1fr 48px; gap: 8px; align-items: center; margin: 6px 0; }}
  .bar {{ background: #2a3548; border-radius: 6px; height: 10px; overflow: hidden; }}
  .bar > div {{ background: linear-gradient(90deg,#3d8bfd,#3dd68c); height: 100%; }}
  .meta {{ color: #9fb3c8; margin-bottom: 18px; }}
</style>
</head>
<body>
  <h1>AI Analytics Copilot — Evaluation Dashboard</h1>
  <div class="meta">Mode: { _html_escape(str(meta.get('mode','component'))) } ·
    Finished: { _html_escape(str(meta.get('finished_at',''))) } ·
    Duration: { _html_escape(str(meta.get('total_duration',''))) }s</div>
  <div class="cards">
    <div class="card"><div>Total</div><div class="v">{metrics.total_tests}</div></div>
    <div class="card"><div>Passed</div><div class="v passed">{metrics.passed}</div></div>
    <div class="card"><div>Failed</div><div class="v failed">{metrics.failed}</div></div>
    <div class="card"><div>Warnings</div><div class="v warning">{metrics.warnings}</div></div>
    <div class="card"><div>Success rate</div><div class="v">{metrics.success_rate:.1%}</div></div>
    <div class="card"><div>Avg latency</div><div class="v">{metrics.average_response_time:.2f}s</div></div>
    <div class="card"><div>Avg confidence</div><div class="v">{metrics.average_confidence:.2f}</div></div>
    <div class="card"><div>Peak mem</div><div class="v">{metrics.peak_memory_mb:.0f} MB</div></div>
  </div>
  <h2>Capability scores</h2>
  {bars}
  <h2>By category</h2>
  <table>
    <tr><th>Category</th><th>Total</th><th>Passed</th><th>Failed</th><th>Warnings</th><th>Pass rate</th></tr>
    {cat_rows}
  </table>
  <h2>Cases</h2>
  <table>
    <tr><th>ID</th><th>Category</th><th>Status</th><th>Time (s)</th><th>Conf</th><th>Question</th></tr>
    {case_rows}
  </table>
</body>
</html>
"""


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
