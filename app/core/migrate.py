"""Bring the database schema to the latest Alembic revision on startup."""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.database import Base, engine
import app.models  # noqa: F401  (registers models)

logger = logging.getLogger("migrate")

ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001"
# Tables in the 0001 baseline. Databases created by the old create_all() may lack some of them.
BASELINE_TABLES = (
    "agents", "appointments", "audit_logs", "call_logs", "call_turn_metrics", "campaigns",
    "cms_faqs", "cms_media", "cms_pages", "cms_prompts", "leads", "tenants", "users",
    "workflows", "campaign_leads", "lead_activities", "workflow_logs",
)


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def run_migrations() -> None:
    cfg = _config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables and "users" in tables:
            logger.info("Existing database without migration history: adopting it at the baseline revision.")
            missing = [Base.metadata.tables[name] for name in BASELINE_TABLES if name not in tables]
            if missing:
                Base.metadata.create_all(connection, tables=missing)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
