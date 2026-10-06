"""Manual entry point to verify the local CircadianIQ environment.

Run with: python scripts/check_environment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import load_config
from app.health import run_health_check
from app.logging_config import setup_logging


def main() -> int:
    config = load_config()
    setup_logging(config.log_level)

    result = run_health_check(config)

    print(f"environment:        {config.environment}")
    print(f"database_url:       {config.database_url}")
    print(f"config_loaded:      {result.config_loaded}")
    print(f"directories_ready:  {result.directories_ready}")
    print(f"database_ready:     {result.database_ready}")

    if result.errors:
        print("errors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
