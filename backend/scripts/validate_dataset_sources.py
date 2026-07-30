#!/usr/bin/env python3
"""CLI: validate configured dataset sources; exit 1 if any broken (CI gate)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root on path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate dataset download sources")
    parser.add_argument(
        "--include-registry",
        action="store_true",
        default=True,
        help="Also validate active registry download_url rows (default: on)",
    )
    parser.add_argument(
        "--no-registry",
        action="store_true",
        help="Skip registry URL validation",
    )
    parser.add_argument(
        "--deactivate-registry",
        action="store_true",
        help="Mark broken registry sources inactive",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for JSON/Markdown reports",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout seconds (default 20)",
    )
    parser.add_argument(
        "--fail-on-broken",
        action="store_true",
        default=True,
        help="Exit non-zero when critical downloadable sources are broken (default: on)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail on advisory catalog landing pages",
    )
    parser.add_argument(
        "--allow-broken",
        action="store_true",
        help="Always exit 0 (report only)",
    )
    args = parser.parse_args(argv)

    from backend.validation.dataset_sources import run_validation

    report = run_validation(
        include_registry=not args.no_registry,
        deactivate_registry=args.deactivate_registry,
        output_dir=args.output_dir,
        timeout=args.timeout,
    )
    payload = report.to_dict()
    totals = payload["totals"]
    print(
        f"Dataset sources: checked={totals['checked']} "
        f"healthy={totals['healthy']} broken={totals['broken']} "
        f"critical_broken={totals.get('critical_broken', 0)} "
        f"advisory_broken={totals.get('advisory_broken', 0)}"
    )
    if report.broken:
        print("Broken sources:")
        for b in report.broken:
            tier = "CRITICAL" if b.origin in {"config", "catalog", "github_map", "world_bank_map", "registry"} else "advisory"
            print(f"  - [{tier}/{b.origin}] {b.key}: {b.reason} :: {b.url}")
            if b.suggested_replacement:
                print(f"      suggested: {b.suggested_replacement}")
    if report.registry_deactivated:
        print(f"Registry deactivated: {len(report.registry_deactivated)}")

    if args.allow_broken:
        return 0
    if not args.fail_on_broken:
        return 0
    if args.strict and report.broken:
        return 1
    if not report.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
