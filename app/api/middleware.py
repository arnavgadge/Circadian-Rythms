"""Correlation-ID + structured request logging middleware.

Never logs sensitive personal details, raw behavioral data,
credentials, or environment secrets -- only endpoint/event, participant
ID (when present in the path), correlation ID, duration, and outcome.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.api")

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        started_at = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - started_at) * 1000
            logger.exception(
                "request failed method=%s path=%s correlation_id=%s duration_ms=%.1f",
                request.method, request.url.path, correlation_id, duration_ms,
            )
            raise

        duration_ms = (time.monotonic() - started_at) * 1000
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        logger.info(
            "request completed method=%s path=%s correlation_id=%s status_code=%s duration_ms=%.1f",
            request.method, request.url.path, correlation_id, response.status_code, duration_ms,
        )
        return response
