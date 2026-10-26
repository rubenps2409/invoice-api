"""Logging setup: one line per event, JSON in production.

Nothing here (or in the request log) records invoice text, request bodies,
headers, query strings or client IPs: logs are kept far longer than requests.
"""

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any

from invoice_api.config import Environment

# Fields a log call may attach with `extra=` that the JSON format keeps.
_EXTRA_FIELDS = ("method", "path", "status", "duration_ms")

_TEXT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        data.update({f: getattr(record, f) for f in _EXTRA_FIELDS if hasattr(record, f)})
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def configure_logging(environment: Environment, level: str) -> None:
    formatter = (
        {"()": JsonFormatter}
        if environment is Environment.PRODUCTION
        else {"format": _TEXT_FORMAT}
    )
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": formatter},
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"}
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                # Uvicorn's own errors use our format. Its access log is replaced
                # by the request log (see middleware.py), so it is silenced.
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                "uvicorn.access": {"handlers": [], "propagate": False},
            },
        }
    )
