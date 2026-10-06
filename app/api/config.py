"""Configuration for the Phase 15 application/API layer.

Builds on ``app.config.settings.AppConfig`` (database URL, model
directory, log level, environment) rather than duplicating it -- this
module only adds the handful of settings that are genuinely
API-specific (host/port, API version, dev-mode flag).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.config.settings import AppConfig, load_config


@dataclass(frozen=True)
class APIConfig:
    app_config: AppConfig
    host: str
    port: int
    api_version: str
    is_development: bool


def load_api_config() -> APIConfig:
    app_config = load_config()
    return APIConfig(
        app_config=app_config,
        host=os.getenv("CIRCADIANIQ_API_HOST", "127.0.0.1"),
        port=int(os.getenv("CIRCADIANIQ_API_PORT", "8000")),
        api_version="v1",
        is_development=app_config.environment != "production",
    )
