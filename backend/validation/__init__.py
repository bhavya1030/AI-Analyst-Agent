"""Dataset source validation for configured catalogs and registry URLs."""

from backend.validation.dataset_sources import (
    DatasetSourceValidator,
    SourceEntry,
    SourceValidationReport,
    SourceValidationResult,
    collect_configured_sources,
    deactivate_broken_registry_urls,
    generate_validation_report,
    run_validation,
    suggest_replacement,
)

__all__ = [
    "DatasetSourceValidator",
    "SourceEntry",
    "SourceValidationReport",
    "SourceValidationResult",
    "collect_configured_sources",
    "deactivate_broken_registry_urls",
    "generate_validation_report",
    "run_validation",
    "suggest_replacement",
]
