"""Application service for the health endpoint. Never exposes internal
paths -- only booleans and version/environment labels."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.config import APIConfig
from app.api.schemas.health import HealthResponse
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG


class HealthService:
    def __init__(self, api_config: APIConfig, session: Session):
        self.api_config = api_config
        self.session = session

    def check(self) -> HealthResponse:
        database_connected = self._check_database()
        model_artifacts_available = self._check_model_artifacts()

        return HealthResponse(
            application_available=True,
            database_connected=database_connected,
            model_artifacts_available=model_artifacts_available,
            configuration_loaded=True,
            api_version=self.api_config.api_version,
            environment=self.api_config.app_config.environment,
        )

    def _check_database(self) -> bool:
        try:
            self.session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def _check_model_artifacts(self) -> bool:
        version = DEFAULT_PIPELINE_CONFIG.xgboost_model_version
        models_dir = self.api_config.app_config.model_dir
        sin_path = Path(models_dir) / f"xgboost_dlmo_sin_v{version}.pkl"
        cos_path = Path(models_dir) / f"xgboost_dlmo_cos_v{version}.pkl"
        return sin_path.exists() and cos_path.exists()
