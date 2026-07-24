"""End-to-end evaluation framework for AI Analytics Copilot.

This is system evaluation (not unit tests). It exercises existing modules
without redesigning them.

Run:
  python tests/evaluation/evaluation_runner.py
  python tests/evaluation/evaluation_runner.py --smoke
  python tests/evaluation/evaluation_runner.py --category 4_forecasting
"""

from tests.evaluation.metrics import EvaluationMetrics, aggregate_metrics
from tests.evaluation.report_generator import ReportGenerator

# Lazy re-exports to avoid double-import warnings when running as __main__
def run_evaluation(*args, **kwargs):
    from tests.evaluation.evaluation_runner import run_evaluation as _run

    return _run(*args, **kwargs)


def EvaluationRunner(*args, **kwargs):  # type: ignore[misc]
    from tests.evaluation.evaluation_runner import EvaluationRunner as _ER

    return _ER(*args, **kwargs)


__all__ = [
    "EvaluationRunner",
    "run_evaluation",
    "EvaluationMetrics",
    "aggregate_metrics",
    "ReportGenerator",
]
