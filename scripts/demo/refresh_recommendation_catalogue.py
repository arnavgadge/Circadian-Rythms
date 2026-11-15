"""Bring the configured database's recommendation catalogue up to date
with the project's own reference definitions.

    python scripts/demo/refresh_recommendation_catalogue.py           # show the diff only
    python scripts/demo/refresh_recommendation_catalogue.py --apply   # back up the DB file, then update

Why this exists: ``app.database.seed.seed_reference_data`` is
insert-only -- it skips any intervention_code that already exists. A
database whose catalogue was seeded by an earlier version of that seed
(before the Phase 10 ``extra_metadata`` -- contributor_signals, targets,
templates -- existed) therefore keeps rows the recommendation engine
cannot use, and the real pipeline never selects a recommendation for
anyone. This script updates those existing rows **in place**, matched by
``intervention_code``, to exactly the values in
``app.database.seed._REFERENCE_RECOMMENDATIONS``:

* touches only the ``recommendations`` reference table;
* never inserts, deletes, or renumbers rows (ids, and so every
  ``intervention_log`` foreign key, stay as they are);
* no schema or application-code change;
* refuses non-development environments; ``--apply`` first copies the
  SQLite file into a ``backups/`` folder beside it (``data/backups/``
  for the default database).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, DEMO_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from seed_demo_participant import DemoSeedError, describe_target, guard_schema, guard_target  # noqa: E402

_SKIP = {"id", "created_at", "updated_at"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write the changes (default: show the diff only).")
    args = parser.parse_args(argv)

    from sqlalchemy import select

    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory
    from app.database.models import Recommendation
    from app.database.seed import _REFERENCE_RECOMMENDATIONS

    config = load_config()
    target = describe_target(config.database_url)
    print(f"Target database: {target['type']} -> {target['database']}  (CIRCADIANIQ_ENV={config.environment})")
    try:
        guard_target(config, target)
        engine = create_app_engine(config)
        guard_schema(engine)
    except DemoSeedError as exc:
        print(f"REFUSED: {exc}")
        return 2

    session = create_session_factory(engine)()
    try:
        rows = {r.intervention_code: r for r in session.execute(select(Recommendation)).scalars()}
        changes: dict = {}
        missing = []
        for entry in _REFERENCE_RECOMMENDATIONS:
            row = rows.get(entry["intervention_code"])
            if row is None:
                missing.append(entry["intervention_code"])
                continue
            diff = {k: (getattr(row, k), v) for k, v in entry.items() if k not in _SKIP and getattr(row, k) != v}
            if diff:
                changes[entry["intervention_code"]] = diff

        if missing:
            print(f"Not present (seed_reference_data / scripts/init_db.py inserts these): {missing}")
        if not changes:
            print("Catalogue already matches app/database/seed.py -- nothing to do.")
            return 0

        for code, diff in changes.items():
            print(f"\n{code} (id {rows[code].id}):")
            for field, (old, new) in diff.items():
                print(f"  {field}: {str(old)[:70]!s}  ->  {str(new)[:90]!s}")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to back up the database and write these updates.")
            return 0

        if target["type"] == "sqlite":
            backup_dir = Path(target["path"]).resolve().parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"{target['path'].stem}.pre-catalogue-refresh-{datetime.now():%Y%m%d-%H%M%S}.db"
            session.close()
            engine.dispose()
            shutil.copy2(target["path"], backup)
            print(f"\nBackup written: {backup}")
            engine = create_app_engine(config)
            session = create_session_factory(engine)()
            rows = {r.intervention_code: r for r in session.execute(select(Recommendation)).scalars()}

        for code, diff in changes.items():
            for field, (_old, new) in diff.items():
                setattr(rows[code], field, new)
        session.commit()
        print(f"Updated {len(changes)} catalogue row(s) in place.")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
