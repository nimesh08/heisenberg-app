# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Alembic env.py for heisenberg-jobsvc.

- Reads the URL from `HEISENBERG_DATABASE_URL` (via jobsvc.config), never from
  alembic.ini, so production and dev share one source of truth.
- Imports `jobsvc.models` to populate `SQLModel.metadata` for autogenerate.
- Runs migrations *synchronously* (alembic's stable mode) by coercing any async
  driver URL down to a sync `psycopg`/`psycopg2` URL — async migrations are
  not worth the headaches at this scale.
- compare_type=True so column-type changes are picked up by autogenerate.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import jobsvc.models  # noqa: F401  -- side-effect: populate SQLModel.metadata
from jobsvc.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url() -> str:
    """Return a *sync* psycopg URL, regardless of how the app spells the URL.

    Alembic runs migrations on a regular sync engine; the app uses the async
    engine. Both point at the same Postgres.
    """
    url = os.environ.get("HEISENBERG_DATABASE_URL") or get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg_section = config.get_section(config.config_ini_section, {})
    cfg_section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
