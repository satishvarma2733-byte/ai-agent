"""Tests run against their own database, never the development one.

Some tests wipe whole tables in setUp, so the database is chosen here, before any test module
imports the app. TEST_DATABASE_URL overrides it (e.g. a Postgres test database in CI)."""
import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[2] / "avnagent_test.db"

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_DEFAULT.as_posix()}"
os.environ.setdefault("APP_ENV", "local")
if not os.environ.get("TEST_DATABASE_URL"):
    # A fresh file per run keeps runs independent of each other.
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{_DEFAULT}{suffix}").unlink(missing_ok=True)


def assert_test_database() -> None:
    """Call before deleting data in bulk: refuses to run against anything but a test database."""
    from app.core.database import engine
    if "test" not in str(engine.url).lower():
        raise RuntimeError(f"Refusing to wipe tables: {engine.url} is not a test database.")
