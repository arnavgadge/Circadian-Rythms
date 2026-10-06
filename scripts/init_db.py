"""Initialize the CircadianIQ database schema via Alembic migrations.

This runs ``alembic upgrade head`` against the configured database
(``CIRCADIANIQ_DATABASE_URL`` / ``.env``), then seeds the static
recommendation catalogue. Alembic is the source of truth for schema
changes so existing data survives future revisions; this script never
calls ``Base.metadata.create_all`` directly.

Run with: python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from alembic import command
from alembic.config import Config

from app.config.settings import load_config
from app.database.engine import create_app_engine, create_session_factory, session_scope
from app.database.seed import seed_reference_data
from app.logging_config import setup_logging


def main() -> int:
    config = load_config()
    setup_logging(config.log_level)

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(alembic_cfg, "head")

    engine = create_app_engine(config)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        inserted = seed_reference_data(session)

    print(f"Schema migrated to head. Seeded {inserted} new recommendation(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
