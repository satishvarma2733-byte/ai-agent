import os
import socket
from urllib.parse import urlparse
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.settings import settings

DATABASE_URL = settings.database_url

def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0) as conn:
            return True
    except (OSError, ConnectionRefusedError):
        return False

# Local development only: fall back to SQLite when Postgres isn't running.
# Anywhere else an unreachable database must stop the process, not silently switch stores.
use_sqlite = False
if DATABASE_URL.startswith("postgresql") and settings.is_local:
    try:
        parsed = urlparse(DATABASE_URL)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        if not is_port_open(host, port):
            print(f"[Database] PostgreSQL at {host}:{port} is unreachable. Falling back to local SQLite database.")
            use_sqlite = True
    except Exception as e:
        print(f"[Database] Error checking PostgreSQL status ({e}). Falling back to SQLite.")
        use_sqlite = True

if use_sqlite or DATABASE_URL.startswith("sqlite"):
    if use_sqlite:
        DATABASE_URL = "sqlite:///./avnagent.db"
    # SQLite fallback creation
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # Connect engine. Using standard pools appropriate for multi-threaded applications
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Deterministic constraint names so migrations can alter/drop them (required for SQLite batch mode).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))

def get_db():
    """FastAPI Dependency injection provider for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

