import json
import logging
from datetime import datetime
from typing import Any

from backend.config import settings
from backend.utils.json_safe import sanitize_for_json


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
        }

        for key, value in record.__dict__.items():
            if key in reserved:
                continue
            try:
                payload[key] = sanitize_for_json(value)
            except Exception:
                payload[key] = str(value)

        return json.dumps(payload, default=str)


def setup_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(handler)
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
