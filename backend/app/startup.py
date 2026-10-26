"""Bring the schema to head and seed January 2026 before the API serves requests.

Hosts without a release phase (e.g. Render's free tier) would otherwise start the API on
an empty database. Both steps are no-ops once done, so running them on every boot is safe.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.ingestion import has_data, sync_january_data

logger = logging.getLogger(__name__)
_MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
# Arbitrary key for pg_advisory_lock: serialises start-up across instances sharing a DB.
_INIT_LOCK_KEY = 2026_01_31


def run_migrations() -> None:
    # No ini file: alembic.ini's logging config would replace uvicorn's loggers.
    # env.py reads the URL from DATABASE_URL via the app settings.
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    command.upgrade(config, "head")


def initialise_database(
    bind: Engine = engine,
    session_factory: Callable[[], Session] = SessionLocal,
    migrate: Callable[[], None] = run_migrations,
    sync: Callable[..., dict[str, int]] = sync_january_data,
) -> None:
    """Migrate, then load Elexon data if none is present.

    A migration failure propagates so the process exits and the deploy is marked failed.
    An Elexon failure is logged but not raised: the API still starts on an empty dataset
    and a later sync (nightly task, manual trigger or next restart) fills it in.
    """
    with bind.connect() as lock_connection:
        postgres = lock_connection.dialect.name == "postgresql"
        if postgres:
            logger.info("Startup: waiting for database initialisation lock")
            lock_connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _INIT_LOCK_KEY})
        try:
            logger.info("Startup: applying database migrations")
            migrate()
            logger.info("Startup: database schema is up to date")
            if has_data(session_factory):
                logger.info("Startup: wind data already present; skipping Elexon import")
                return
            logger.info("Startup: database is empty; importing January 2026 data from Elexon")
            try:
                result = sync(session_factory=session_factory)
            except Exception:
                logger.exception(
                    "Startup: Elexon import failed; serving without data until the next sync"
                )
            else:
                logger.info("Startup: Elexon import finished: %s", result)
        finally:
            if postgres:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": _INIT_LOCK_KEY}
                )
