"""Validate production configuration before serving traffic."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse


@dataclass
class ConfigIssue:
    key: str
    message: str
    severity: str = "error"  # error | warning

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "message": self.message, "severity": self.severity}


@dataclass
class ConfigValidationResult:
    ok: bool
    issues: list[ConfigIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ConfigIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ConfigIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "issues": [i.to_dict() for i in self.issues],
        }


class ConfigValidator:
    """Validate application settings for production readiness."""

    def validate(self, settings: Any = None) -> ConfigValidationResult:
        if settings is None:
            try:
                from backend.config import settings as app_settings

                settings = app_settings
            except Exception as exc:
                return ConfigValidationResult(
                    ok=False,
                    issues=[
                        ConfigIssue(
                            key="settings",
                            message=f"Cannot load settings: {exc}",
                            severity="error",
                        )
                    ],
                )

        issues: list[ConfigIssue] = []

        # DATABASE_URL
        db_url = str(getattr(settings, "DATABASE_URL", "") or "")
        if not db_url:
            issues.append(
                ConfigIssue("DATABASE_URL", "DATABASE_URL is required", "error")
            )
        elif not (
            db_url.startswith("sqlite:")
            or db_url.startswith("postgresql")
            or db_url.startswith("mysql")
        ):
            issues.append(
                ConfigIssue(
                    "DATABASE_URL",
                    f"Unrecognized DATABASE_URL scheme: {db_url[:32]}",
                    "warning",
                )
            )

        # DATA_DIR
        data_dir = getattr(settings, "DATA_DIR", None)
        if data_dir is not None:
            try:
                p = Path(data_dir)
                if not p.exists():
                    issues.append(
                        ConfigIssue(
                            "DATA_DIR",
                            f"DATA_DIR does not exist: {p}",
                            "warning",
                        )
                    )
            except Exception as exc:
                issues.append(
                    ConfigIssue("DATA_DIR", f"Invalid DATA_DIR: {exc}", "error")
                )

        # Ollama URL
        ollama = str(getattr(settings, "OLLAMA_SERVER_URL", "") or "")
        if ollama:
            parsed = urlparse(ollama)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                issues.append(
                    ConfigIssue(
                        "OLLAMA_SERVER_URL",
                        f"Invalid OLLAMA_SERVER_URL: {ollama}",
                        "error",
                    )
                )
        else:
            issues.append(
                ConfigIssue(
                    "OLLAMA_SERVER_URL",
                    "OLLAMA_SERVER_URL empty; LLM features disabled",
                    "warning",
                )
            )

        model = str(getattr(settings, "OLLAMA_MODEL", "") or "").strip()
        if not model:
            issues.append(
                ConfigIssue("OLLAMA_MODEL", "OLLAMA_MODEL is empty", "warning")
            )

        # Numeric ranges
        try:
            horizon = int(getattr(settings, "FORECAST_HORIZON", 10))
            if horizon < 1 or horizon > 1000:
                issues.append(
                    ConfigIssue(
                        "FORECAST_HORIZON",
                        f"FORECAST_HORIZON out of range: {horizon}",
                        "warning",
                    )
                )
        except Exception:
            issues.append(
                ConfigIssue("FORECAST_HORIZON", "FORECAST_HORIZON must be int", "error")
            )

        try:
            thr = float(getattr(settings, "SEMANTIC_MIN_SCORE", 0.35))
            if thr < 0 or thr > 1:
                issues.append(
                    ConfigIssue(
                        "SEMANTIC_MIN_SCORE",
                        f"SEMANTIC_MIN_SCORE should be in [0,1], got {thr}",
                        "error",
                    )
                )
        except Exception:
            issues.append(
                ConfigIssue(
                    "SEMANTIC_MIN_SCORE",
                    "SEMANTIC_MIN_SCORE must be numeric",
                    "error",
                )
            )

        log_level = str(getattr(settings, "LOG_LEVEL", "INFO") or "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            issues.append(
                ConfigIssue(
                    "LOG_LEVEL",
                    f"Unknown LOG_LEVEL: {log_level}",
                    "warning",
                )
            )

        ok = not any(i.severity == "error" for i in issues)
        return ConfigValidationResult(ok=ok, issues=issues)


def validate_config(settings: Any = None) -> ConfigValidationResult:
    return ConfigValidator().validate(settings)
