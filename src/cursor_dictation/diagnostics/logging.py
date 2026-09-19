from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

_LOGGER_NAME: Final = "cursor_dictation"
_LOG_NAME: Final = "cursor-dictation.log"
_ALLOWED_FIELDS: Final = frozenset(
    {
        "duration_ms",
        "sample_count",
        "model_id",
        "state",
        "previous_state",
        "next_state",
        "error_type",
        "error_code",
        "delivery_method",
        "device_fallback",
        "history_enabled",
    }
)
_SafeValue = str | int | float | bool | None


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, _SafeValue] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "component": str(getattr(record, "component_name", "application")),
            "event": str(getattr(record, "event_name", "unspecified")),
        }
        safe_fields = getattr(record, "safe_fields", {})
        if isinstance(safe_fields, dict):
            for key, value in safe_fields.items():
                if key in _ALLOWED_FIELDS and isinstance(
                    value, (str, int, float, bool, type(None))
                ):
                    payload[key] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(log_directory: Path) -> logging.Logger:
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = (log_directory / _LOG_NAME).resolve()
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if (
        len(logger.handlers) == 1
        and isinstance(logger.handlers[0], RotatingFileHandler)
        and Path(logger.handlers[0].baseFilename).resolve() == log_path
    ):
        return logger

    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    return logger


class SafeEventLogger:
    def __init__(self, logger: logging.Logger, *, component: str) -> None:
        if not component.strip():
            raise ValueError("component must not be blank")
        self._logger = logger
        self._component = component

    def info(self, event: str, **fields: _SafeValue) -> None:
        self._write(logging.INFO, event, fields)

    def warning(self, event: str, **fields: _SafeValue) -> None:
        self._write(logging.WARNING, event, fields)

    def error(self, event: str, **fields: _SafeValue) -> None:
        self._write(logging.ERROR, event, fields)

    def _write(self, level: int, event: str, fields: dict[str, _SafeValue]) -> None:
        if not event.strip():
            raise ValueError("event must not be blank")
        disallowed = sorted(set(fields) - _ALLOWED_FIELDS)
        if disallowed:
            raise ValueError("Diagnostic fields are not allowed: " + ", ".join(disallowed))
        self._logger.log(
            level,
            event,
            extra={
                "component_name": self._component,
                "event_name": event,
                "safe_fields": fields,
            },
        )
