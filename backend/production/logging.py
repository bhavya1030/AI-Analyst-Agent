"""Structured production logging with request-id correlation."""

from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

_request_id_var: ContextVar[str] = ContextVar("production_request_id", default="")
_trace_id_var: ContextVar[str] = ContextVar("production_trace_id", default="")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id or "")


def get_request_id() -> str:
    return _request_id_var.get() or ""


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id or "")


def get_trace_id() -> str:
    return _trace_id_var.get() or ""


def clear_context() -> None:
    _request_id_var.set("")
    _trace_id_var.set("")


class StructuredFormatter(logging.Formatter):
    """JSON log lines with request_id / trace_id when present."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = get_request_id()
        tid = get_trace_id()
        if rid:
            payload["request_id"] = rid
        if tid:
            payload["trace_id"] = tid
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Attach extra fields (non-standard LogRecord attrs)
        reserved = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "asctime",
        }
        for key, value in record.__dict__.items():
            if key in reserved or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)

        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False
_config_lock = threading.Lock()


def configure_structured_logging(
    *,
    level: str = "INFO",
    logger_name: str | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure root or named logger with structured JSON formatting."""
    global _configured
    with _config_lock:
        logger = logging.getLogger(logger_name)
        if _configured and not force and logger_name is None:
            return logging.getLogger("backend.production")

        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        # Avoid duplicate handlers on reconfigure
        if force or not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            if force:
                logger.handlers.clear()
            logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.propagate = False if logger_name else True
        if logger_name is None:
            _configured = True
        return logging.getLogger(logger_name or "backend.production")


def get_production_logger(name: str = "backend.production") -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    message: str,
    *,
    level: str = "INFO",
    **fields: Any,
) -> None:
    """Emit a structured log event with optional extra fields."""
    logger = get_production_logger()
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.log(lvl, message, extra=fields)
