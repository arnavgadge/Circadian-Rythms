"""Startup health checks for the CircadianIQ application.

Verifies that configuration loads, required directories exist
(creating them if missing), and that a database connection object can
be instantiated for the configured engine. This does not require a
live database connection for engines not yet implemented in Phase 1
(e.g. PostgreSQL) -- only that the abstraction can be constructed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.config.settings import AppConfig, load_config
from app.database.connection import create_connection

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Outcome of a startup health check."""

    config_loaded: bool = False
    directories_ready: bool = False
    database_ready: bool = False
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether every check passed with no errors recorded."""
        return (
            self.config_loaded
            and self.directories_ready
            and self.database_ready
            and not self.errors
        )


def _ensure_directories(config: AppConfig) -> None:
    for directory in config.required_directories:
        directory.mkdir(parents=True, exist_ok=True)


def run_health_check(config: Optional[AppConfig] = None) -> HealthCheckResult:
    """Run startup checks and return a :class:`HealthCheckResult`."""

    result = HealthCheckResult()

    try:
        config = config or load_config()
        result.config_loaded = True
    except Exception as exc:  # pragma: no cover - defensive
        result.errors.append(f"Configuration failed to load: {exc}")
        return result

    try:
        _ensure_directories(config)
        result.directories_ready = True
    except Exception as exc:
        result.errors.append(f"Required directories could not be created: {exc}")

    try:
        create_connection(config.database_url)
        result.database_ready = True
    except Exception as exc:
        result.errors.append(f"Database connection could not be instantiated: {exc}")

    if result.ok:
        logger.info("CircadianIQ health check passed.")
    else:
        logger.warning("CircadianIQ health check reported issues: %s", result.errors)

    return result
