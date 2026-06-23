# @file src/shared/logger.py
# @description Standardized tag-based logger for Lovv Lambda handlers.
# @lastModified 2026-06-18

"""Standardized tag-based logger for the Lovv backend.

Writes to stdout/stderr through the stdlib ``logging`` module, which AWS Lambda
forwards to Amazon CloudWatch Logs. Every line is prefixed with a standardized
tag (e.g. ``[AUTH]``) so logs can be filtered in CloudWatch Logs Insights:

    fields @timestamp, @message
    | filter @message like /\\[AUTH\\]/
    | sort @timestamp desc

Usage
-----
    from shared.logger import get_logger, Tag

    LOGGER = get_logger(__name__)
    LOGGER.info(Tag.AUTH, "Social login initiated for %s", "google")

    try:
        ...
    except Exception:
        LOGGER.exception(Tag.SYSTEM, "Unhandled error")

Optionally attach a per-invocation request id at the top of a handler:

    from shared.logger import set_request_id
    set_request_id(getattr(context, "aws_request_id", None))
"""

from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from enum import Enum
from typing import Any, Optional


class Tag(str, Enum):
    """Standard log tags. Mirror this list in the frontend logger.ts."""

    AUTH = "AUTH"        # Login, logout, token verification, session refresh
    PREF = "PREF"        # Onboarding theme/profile changes, preference updates
    PLAN = "PLAN"        # Plan draft generation, AI chatbot, itinerary saves
    CITY = "CITY"        # City listing, marker queries, S3 raw details loading
    DB = "DB"            # Aurora MySQL connections, queries, commit/rollback
    SYSTEM = "SYSTEM"    # Server exceptions, uncaught errors, env setup

    def __str__(self) -> str:  # so f"{Tag.AUTH}" -> "AUTH"
        return self.value


_request_id: ContextVar[Optional[str]] = ContextVar("lovv_request_id", default=None)


def set_request_id(request_id: Optional[str]) -> None:
    """Attach a request/correlation id to every subsequent log line."""
    _request_id.set(request_id)


def clear_request_id() -> None:
    _request_id.set(None)


class _RequestIdFilter(logging.Filter):
    """Injects the active request id so the formatter can render it."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _request_id.get()
        record.request_id = f" req={rid}" if rid else ""
        return True


# Format: 2026-06-18 09:00:00,123 INFO req=abc-123 [AUTH] message...
_FORMAT = "%(asctime)s %(levelname)-8s%(request_id)s %(message)s"


class TaggedLogger:
    """Thin wrapper around a stdlib logger that prepends a standardized tag."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    @staticmethod
    def _fmt(tag: Tag, message: str) -> str:
        return f"[{tag}] {message}"

    def debug(self, tag: Tag, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(self._fmt(tag, message), *args, **kwargs)

    def info(self, tag: Tag, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(self._fmt(tag, message), *args, **kwargs)

    def warning(self, tag: Tag, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(self._fmt(tag, message), *args, **kwargs)

    warn = warning

    def error(self, tag: Tag, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(self._fmt(tag, message), *args, **kwargs)

    def exception(self, tag: Tag, message: str, *args: Any, **kwargs: Any) -> None:
        """Like error() but attaches the active exception traceback."""
        kwargs.setdefault("exc_info", True)
        self._logger.error(self._fmt(tag, message), *args, **kwargs)


def _configure_root_once() -> None:
    """Set level + formatting once.

    Lambda installs its own root handler, so we attach our formatter/filter to
    existing handlers instead of adding a duplicate (which would double-print
    every line). Only when no handler exists do we add our own stdout handler.
    """
    root = logging.getLogger()
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    if any(getattr(handler, "_lovv", False) for handler in root.handlers):
        return

    formatter = logging.Formatter(_FORMAT)
    request_filter = _RequestIdFilter()

    if root.handlers:
        for handler in root.handlers:
            handler.setFormatter(formatter)
            handler.addFilter(request_filter)
            handler._lovv = True  # type: ignore[attr-defined]
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        handler.addFilter(request_filter)
        handler._lovv = True  # type: ignore[attr-defined]
        root.addHandler(handler)


def get_logger(name: str) -> TaggedLogger:
    """Return a TaggedLogger for the given module name (pass __name__)."""
    _configure_root_once()
    return TaggedLogger(logging.getLogger(name))
