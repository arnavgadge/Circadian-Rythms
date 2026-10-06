"""Central application configuration.

Configuration is loaded from environment variables (optionally
populated from a ``.env`` file in the project root) with sensible
defaults for local development. This is the single place later
phases should read settings from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


@dataclass(frozen=True)
class AppConfig:
    """Immutable snapshot of application configuration."""

    environment: str
    database_url: str
    data_dir: Path
    raw_data_dir: Path
    synthetic_data_dir: Path
    processed_data_dir: Path
    model_dir: Path
    log_level: str

    @property
    def required_directories(self) -> tuple[Path, ...]:
        """Directories the application expects to exist at runtime."""
        return (
            self.data_dir,
            self.raw_data_dir,
            self.synthetic_data_dir,
            self.processed_data_dir,
            self.model_dir,
        )


def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from environment variables and defaults."""

    data_dir = Path(os.getenv("CIRCADIANIQ_DATA_DIR", str(PROJECT_ROOT / "data")))

    return AppConfig(
        environment=os.getenv("CIRCADIANIQ_ENV", "development"),
        database_url=os.getenv(
            "CIRCADIANIQ_DATABASE_URL",
            f"sqlite:///{PROJECT_ROOT / 'data' / 'circadianiq.db'}",
        ),
        data_dir=data_dir,
        raw_data_dir=Path(os.getenv("CIRCADIANIQ_RAW_DATA_DIR", str(data_dir / "raw"))),
        synthetic_data_dir=Path(
            os.getenv("CIRCADIANIQ_SYNTHETIC_DATA_DIR", str(data_dir / "synthetic"))
        ),
        processed_data_dir=Path(
            os.getenv("CIRCADIANIQ_PROCESSED_DATA_DIR", str(data_dir / "processed"))
        ),
        model_dir=Path(os.getenv("CIRCADIANIQ_MODEL_DIR", str(PROJECT_ROOT / "models"))),
        log_level=os.getenv("CIRCADIANIQ_LOG_LEVEL", "INFO"),
    )
