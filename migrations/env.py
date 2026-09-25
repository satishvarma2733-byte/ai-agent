from alembic import context

from app.core.database import Base, engine
import app.models  # noqa: F401  (registers every model on Base.metadata)

target_metadata = Base.metadata

# Postgres-only indexes created with raw SQL in 0007 (pgvector HNSW, full-text GIN); no model declares them.
_RAW_SQL_INDEXES = {"ix_kb_chunks_embedding_hnsw", "ix_kb_chunks_search_tokens_fts"}


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    return not (type_ == "index" and name in _RAW_SQL_INDEXES)


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with engine.connect() as conn:
        _run(conn)
        conn.commit()


def _run(connection) -> None:
    # Batch mode lets ALTER TABLE work on SQLite (local dev) as well as Postgres.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
