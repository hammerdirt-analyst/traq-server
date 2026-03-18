"""Alembic environment for the standalone TRAQ server repo."""

from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import load_settings
from app.db import Base
from app import db_models  # noqa: F401  Registers SQLAlchemy metadata.


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = load_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata
search_path = (os.environ.get("TRAQ_ALEMBIC_SEARCH_PATH") or "").strip() or None


def run_migrations_offline() -> None:
    """Run migrations without creating a live SQLAlchemy engine."""

    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        version_table_schema=search_path,
        include_schemas=bool(search_path),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a live SQLAlchemy connection."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if search_path:
            connection.execute(text(f'SET search_path TO "{search_path}"'))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            version_table_schema=search_path,
            include_schemas=bool(search_path),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
