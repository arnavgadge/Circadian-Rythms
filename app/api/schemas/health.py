from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    application_available: bool = Field(description="The API process itself is running.")
    database_connected: bool = Field(description="A database connection could be established.")
    model_artifacts_available: bool = Field(description="The configured Phase 5 XGBoost model version is loadable.")
    configuration_loaded: bool = Field(description="Application configuration loaded successfully.")
    api_version: str
    environment: str
