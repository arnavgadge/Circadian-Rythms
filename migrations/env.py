import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import load_config  # noqa: E402
from app.database.models import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# disable_existing_loggers=False: fileConfig()'s default (True) silently
# disables every logger already created in this process that isn't
# explicitly listed in alembic.ini's [loggers] section. When Alembic
# runs in-process (scripts/init_db.py calls alembic.command.upgrade()
# directly, not via a subprocess), that would permanently disable the
# application's own loggers (e.g. app.pipeline.orchestrator) for the
# rest of the process -- discovered via an AUDIT 1/23 test that ran
# alembic upgrade head in-process ahead of a failure-injection test and
# found the pipeline's error logging had gone silent.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The database URL is owned by app.config.settings (env vars / .env),
# not duplicated as a literal in alembic.ini.
config.set_main_option("sqlalchemy.url", load_config().database_url)

# CircadianIQ ORM metadata, for autogenerate support.
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
