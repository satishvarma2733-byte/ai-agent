"""Knowledge base storage: sources → documents → chunks (with embeddings), plus ingest jobs."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import TypeDecorator

from app.core.database import Base

EMBEDDING_DIMENSIONS = 768


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EmbeddingVector(TypeDecorator):
    """pgvector `vector(768)` on Postgres (indexed similarity search); JSON list elsewhere (local SQLite)."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(EMBEDDING_DIMENSIONS))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return [float(v) for v in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(v) for v in value]


class KBSource(Base):
    __tablename__ = "kb_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)
    source_type = Column(String(30), nullable=False)  # pdf_upload | web_url | text
    title = Column(String(300), default="", nullable=False)
    source_url = Column(Text, nullable=True)
    raw_text = Column(Text, nullable=True)
    storage_bucket = Column(String(100), nullable=True)
    storage_path = Column(Text, nullable=True)
    mime_type = Column(String(120), nullable=True)
    checksum = Column(String(64), nullable=True)
    # pending | syncing | ready | error | disabled
    status = Column(String(20), default="pending", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    language = Column(String(10), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    sync_error = Column(Text, nullable=True)
    meta = Column("metadata", JSON, default=dict, nullable=False)


class KBDocument(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    source_id = Column(Integer, ForeignKey("kb_sources.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)
    external_id = Column(String(500), nullable=False)
    document_type = Column(String(30), default="generic", nullable=False)
    title = Column(String(300), default="", nullable=False)
    body_text = Column(Text, default="", nullable=False)
    checksum = Column(String(64), nullable=True)
    language = Column(String(10), nullable=True)
    meta = Column("metadata", JSON, default=dict, nullable=False)


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    source_id = Column(Integer, ForeignKey("kb_sources.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id = Column(Integer, ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    title = Column(String(300), default="", nullable=False)
    content = Column(Text, default="", nullable=False)
    # Normalised keyword tokens (script-aware), used for keyword matching in every language.
    search_tokens = Column(Text, default="", nullable=False)
    checksum = Column(String(64), nullable=True)
    token_count = Column(Integer, default=0, nullable=False)
    language = Column(String(10), nullable=True)
    embedding = Column(EmbeddingVector, nullable=True)
    # Which model produced `embedding`; vectors from different models are never compared.
    embedding_model = Column(String(120), nullable=True)
    meta = Column("metadata", JSON, default=dict, nullable=False)


class KBIngestJob(Base):
    __tablename__ = "kb_ingest_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    source_id = Column(Integer, ForeignKey("kb_sources.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)
    source_type = Column(String(30), default="generic", nullable=False)
    job_type = Column(String(20), default="ingest", nullable=False)  # ingest | reindex
    # pending | processing | completed | failed
    status = Column(String(20), default="pending", index=True, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    error_text = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_result = Column(JSON, default=dict, nullable=False)
