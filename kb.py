"""Knowledge base: ingest PDFs / web pages / text into tenant-scoped chunks and search them.

Storage lives in the application database (app/models/kb.py): Postgres + pgvector in production,
SQLite locally. Embeddings are multilingual (Gemini `gemini-embedding-001`, 768 dimensions) so a
Telugu or Hindi question can retrieve English content. Keyword matching is script-aware.
Every read and write is scoped to a tenant; searches without a tenant return nothing.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import ipaddress
import json
import logging
import math
import mimetypes
import os
import re
import threading
import time
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import numpy as np
import tiktoken
import trafilatura
from pypdf import PdfReader

logger = logging.getLogger("kb")

KB_SOURCE_TYPES = {"pdf_upload", "web_url", "text"}
KB_JOB_TYPES = {"ingest", "reindex"}
KB_MAX_JOB_ATTEMPTS = 3
KB_CACHE_TTL_SECONDS = 45
KB_EMBEDDING_DIMENSIONS = 768  # fixed: matches the vector(768) column
KB_DEFAULT_EMBED_PROVIDER = "gemini"
KB_DEFAULT_EMBED_MODEL = "gemini-embedding-001"
_LEGACY_ENGLISH_MODELS = {"baai/bge-small-en-v1.5", ""}
KB_EMBED_BATCH_SIZE = 100
KB_MAX_SITEMAP_URLS = 250
KB_MAX_SITEMAPS = 25
# Dense-only matches (no shared keywords, e.g. a Telugu question over English text) must reach this
# cosine similarity to count. Calibrated with scripts/kb_multilingual_eval.py on gemini-embedding-001
# (2026-09-25): relevant Te/Hi/En/code-mixed questions >= 0.668 (median 0.722, recall@1 15/15);
# unrelated questions <= 0.560.
KB_DEFAULT_MIN_DENSE_SIMILARITY = 0.62

_TOKENIZER = tiktoken.get_encoding("cl100k_base")

KB_QUERY_HINTS = {
    "price", "pricing", "cost", "plan", "plans", "feature", "features", "service",
    "services", "product", "products", "availability", "available", "status",
    "location", "address", "hours", "timing", "policy", "support", "setup",
    "integration", "integrations", "demo", "booking", "appointment", "contact",
    "refund", "shipping", "delivery", "warranty", "terms", "fee", "fees",
}
KB_TEXT_HINTS = {
    "about", "details", "overview", "features", "describe", "document", "pdf",
    "website", "link", "explain", "guide", "brochure", "page", "sitemap",
}
KB_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "and", "or", "of", "for", "to",
    "in", "on", "at", "me", "you", "i", "we", "our", "your", "their", "it", "this",
    "that", "with", "from", "please", "can", "could", "would", "should", "want",
    "need", "know", "tell", "show", "give", "about", "some", "any", "there", "have",
    "has", "had", "into", "than", "then", "what", "which", "when", "where", "who", "how",
}


class EmbeddingUnavailableError(RuntimeError):
    """No real embedding provider could produce vectors."""


def _app_env() -> str:
    return os.getenv("APP_ENV", "local").strip().lower()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_runtime_config(config: dict | None = None) -> dict[str, Any]:
    config = config or {}

    def get_value(key: str, env_key: str, default: Any) -> Any:
        value = config.get(key)
        if value not in (None, ""):
            return value
        return os.getenv(env_key, default)

    data_dir = str(get_value("kb_data_dir", "KB_DATA_DIR", "data/kb") or "data/kb").strip()
    provider = str(get_value("kb_embedding_provider", "KB_EMBEDDING_PROVIDER", KB_DEFAULT_EMBED_PROVIDER) or KB_DEFAULT_EMBED_PROVIDER).strip().lower()
    model = str(get_value("kb_embedding_model", "KB_EMBEDDING_MODEL", "") or "").strip()
    if provider == "local" and model.lower() in _LEGACY_ENGLISH_MODELS:
        # The old default was an English-only local model that cannot serve Telugu/Hindi queries.
        provider, model = KB_DEFAULT_EMBED_PROVIDER, KB_DEFAULT_EMBED_MODEL
    if provider == "gemini" and (not model or "/" in model):
        model = KB_DEFAULT_EMBED_MODEL
    return {
        "kb_enabled": parse_bool(get_value("kb_enabled", "KB_ENABLED", True), True),
        "kb_backend": "database",
        "kb_data_dir": data_dir,
        "kb_top_k": max(1, parse_int(get_value("kb_top_k", "KB_TOP_K", 4), 4)),
        "kb_min_dense_similarity": parse_float(
            get_value("kb_min_dense_similarity", "KB_MIN_DENSE_SIMILARITY", KB_DEFAULT_MIN_DENSE_SIMILARITY),
            KB_DEFAULT_MIN_DENSE_SIMILARITY),
        "kb_context_char_budget": max(400, parse_int(get_value("kb_context_char_budget", "KB_CONTEXT_CHAR_BUDGET", 2800), 2800)),
        "kb_live_timeout_ms": max(50, parse_int(get_value("kb_live_timeout_ms", "KB_LIVE_TIMEOUT_MS", 150), 150)),
        "kb_live_context_char_budget": max(280, parse_int(get_value("kb_live_context_char_budget", "KB_LIVE_CONTEXT_CHAR_BUDGET", 900), 900)),
        "kb_cache_ttl_seconds": max(5, parse_int(get_value("kb_cache_ttl_seconds", "KB_CACHE_TTL_SECONDS", KB_CACHE_TTL_SECONDS), KB_CACHE_TTL_SECONDS)),
        "kb_chunk_size": max(120, parse_int(get_value("kb_chunk_size", "KB_CHUNK_SIZE", 400), 400)),
        "kb_chunk_overlap": max(20, parse_int(get_value("kb_chunk_overlap", "KB_CHUNK_OVERLAP", 60), 60)),
        "kb_worker_poll_seconds": max(5, parse_int(get_value("kb_worker_poll_seconds", "KB_WORKER_POLL_SECONDS", 20), 20)),
        "kb_embedding_provider": provider,
        "kb_embedding_model": model or KB_DEFAULT_EMBED_MODEL,
        "kb_embedding_dimensions": KB_EMBEDDING_DIMENSIONS,
        "google_api_key": str(get_value("google_api_key", "GOOGLE_API_KEY", "") or "").strip(),
        "google_genai_use_vertexai": parse_bool(get_value("google_genai_use_vertexai", "GOOGLE_GENAI_USE_VERTEXAI", False), False),
        "google_cloud_project": str(get_value("google_cloud_project", "GOOGLE_CLOUD_PROJECT", "") or "").strip(),
        "google_cloud_location": str(get_value("google_cloud_location", "GOOGLE_CLOUD_LOCATION", "us-central1") or "us-central1").strip(),
        "google_application_credentials": str(get_value("google_application_credentials", "GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip(),
    }


# ── Text processing (works for every script) ─────────────────────────
def _is_word_char(ch: str) -> bool:
    # Letters, combining marks (Indic vowel signs, Arabic diacritics), and digits.
    return unicodedata.category(ch)[0] in ("L", "M", "N")


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    text = "".join(ch if _is_word_char(ch) or ch.isspace() else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize_keywords(value: str | None) -> list[str]:
    return [t for t in _normalize_text(value).split(" ") if len(t) >= 2 and t not in KB_STOPWORDS]


_SCRIPT_LANGUAGES = (
    ((0x0C00, 0x0C7F), "te"), ((0x0900, 0x097F), "hi"), ((0x0B80, 0x0BFF), "ta"),
    ((0x0C80, 0x0CFF), "kn"), ((0x0D00, 0x0D7F), "ml"), ((0x0600, 0x06FF), "ar"),
    ((0x3040, 0x30FF), "ja"), ((0xAC00, 0xD7AF), "ko"), ((0x4E00, 0x9FFF), "zh"),
)


def detect_language(text: str | None) -> str | None:
    """Dominant script → language code (Latin → en). Good enough to tag sources; not a full classifier."""
    counts: Counter[str] = Counter()
    for ch in str(text or "")[:20000]:
        if not ch.isalpha():
            continue
        code = ord(ch)
        for (start, end), lang in _SCRIPT_LANGUAGES:
            if start <= code <= end:
                counts[lang] += 1
                break
        else:
            if code < 0x0250:
                counts["en"] += 1
    if not counts:
        return None
    # Japanese text mixes kana with CJK ideographs.
    if counts.get("ja") and counts.get("zh"):
        counts["ja"] += counts.pop("zh")
    return counts.most_common(1)[0][0]


def _has_non_latin_letters(text: str) -> bool:
    return any(ch.isalpha() and ord(ch) >= 0x0250 for ch in text)


def _preview(value: str, limit: int = 280) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _normalize_vector(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=np.float32)
    if arr.shape[0] != KB_EMBEDDING_DIMENSIONS:
        raise EmbeddingUnavailableError(
            f"Embedding has {arr.shape[0]} dimensions; the knowledge base stores {KB_EMBEDDING_DIMENSIONS}.")
    norm = float(np.linalg.norm(arr))
    return (arr / norm).tolist() if norm > 0 else arr.tolist()


# ── Embeddings ───────────────────────────────────────────────────────
_GEMINI_CLIENTS: dict[str, Any] = {}
_FASTEMBED_MODELS: dict[str, Any] = {}
_EMBED_LOCK = threading.Lock()
_QUERY_EMBED_CACHE: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()
_QUERY_EMBED_CACHE_SIZE = 512


def _hashed_embedding(text: str) -> list[float]:
    """Deterministic token hashing. Not semantic; only for local development without a provider."""
    vec = np.zeros(KB_EMBEDDING_DIMENSIONS, dtype=np.float32)
    for token in _tokenize_keywords(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vec[int.from_bytes(digest[:4], "little") % KB_EMBEDDING_DIMENSIONS] += 1.0 if digest[4] % 2 else -1.0
    norm = float(np.linalg.norm(vec))
    return (vec / norm).tolist() if norm > 0 else vec.tolist()


def _google_genai_client_kwargs(runtime: dict[str, Any]) -> dict[str, Any] | None:
    """Client settings for Vertex AI (service account / ADC) or an API key; None when neither is configured."""
    if runtime.get("google_genai_use_vertexai"):
        credentials_path = str(runtime.get("google_application_credentials") or "").strip()
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        kwargs: dict[str, Any] = {"vertexai": True, "location": str(runtime.get("google_cloud_location") or "us-central1")}
        if runtime.get("google_cloud_project"):
            kwargs["project"] = str(runtime["google_cloud_project"])
        return kwargs
    api_key = str(runtime.get("google_api_key") or "").strip()
    return {"api_key": api_key} if api_key else None


def _embed_gemini(texts: list[str], *, runtime: dict[str, Any], is_query: bool) -> list[list[float]]:
    client_kwargs = _google_genai_client_kwargs(runtime)
    if client_kwargs is None:
        raise EmbeddingUnavailableError("GOOGLE_API_KEY is not set and Vertex AI is off, so Gemini embeddings are unavailable.")
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # pragma: no cover - dependency is pinned
        raise EmbeddingUnavailableError(f"google-genai is not installed: {exc}") from exc
    with _EMBED_LOCK:
        cache_key = repr(sorted(client_kwargs.items()))
        client = _GEMINI_CLIENTS.get(cache_key)
        if client is None:
            client = _GEMINI_CLIENTS[cache_key] = genai.Client(**client_kwargs)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), KB_EMBED_BATCH_SIZE):
        batch = [str(t or "") for t in texts[start:start + KB_EMBED_BATCH_SIZE]]
        try:
            response = client.models.embed_content(
                model=runtime["kb_embedding_model"],
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT",
                    output_dimensionality=KB_EMBEDDING_DIMENSIONS,
                ),
            )
        except Exception as exc:
            raise EmbeddingUnavailableError(f"Gemini embedding request failed: {exc}") from exc
        embeddings = response.embeddings or []
        if len(embeddings) != len(batch):
            raise EmbeddingUnavailableError(f"Gemini returned {len(embeddings)} embeddings for {len(batch)} inputs.")
        vectors.extend(_normalize_vector(list(e.values or [])) for e in embeddings)
    return vectors


def _embed_local(texts: list[str], *, runtime: dict[str, Any], is_query: bool) -> list[list[float]]:
    model_name = runtime["kb_embedding_model"]
    try:
        from fastembed import TextEmbedding
    except Exception as exc:
        raise EmbeddingUnavailableError(f"fastembed is not installed: {exc}") from exc
    with _EMBED_LOCK:
        model = _FASTEMBED_MODELS.get(model_name)
        if model is None:
            cache_dir = Path(runtime["kb_data_dir"]).expanduser() / "model_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            model = _FASTEMBED_MODELS[model_name] = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))
    prefix = "query: " if is_query else "passage: "
    return [_normalize_vector(list(v)) for v in model.embed([prefix + str(t or "") for t in texts])]


def embedding_model_id(config: dict | None = None) -> str:
    """Identifier stored with each chunk. Vectors are only compared when identifiers match."""
    runtime = get_runtime_config(config)
    if runtime["kb_embedding_provider"] == "hashed":
        return f"hashed@{KB_EMBEDDING_DIMENSIONS}"
    return f"{runtime['kb_embedding_provider']}:{runtime['kb_embedding_model']}@{KB_EMBEDDING_DIMENSIONS}"


def embed_texts(texts: list[str], *, config: dict | None = None, is_query: bool = False) -> tuple[list[list[float]], str]:
    """Returns (vectors, model_id). Falls back to hashed vectors only when APP_ENV=local."""
    runtime = get_runtime_config(config)
    provider = runtime["kb_embedding_provider"]
    if not texts:
        return [], embedding_model_id(config)
    try:
        if provider == "gemini":
            return _embed_gemini(texts, runtime=runtime, is_query=is_query), embedding_model_id(config)
        if provider == "local":
            return _embed_local(texts, runtime=runtime, is_query=is_query), embedding_model_id(config)
        if provider != "hashed":
            raise EmbeddingUnavailableError(f"Unknown embedding provider '{provider}'.")
    except EmbeddingUnavailableError as exc:
        if _app_env() != "local":
            raise
        logger.warning(f"[KB] {exc} Using hashed development embeddings (APP_ENV=local).")
    return [_hashed_embedding(t) for t in texts], f"hashed@{KB_EMBEDDING_DIMENSIONS}"


def _embed_query(query: str, config: dict | None) -> tuple[list[float], str]:
    model_id = embedding_model_id(config)
    key = (model_id, query)
    cached = _QUERY_EMBED_CACHE.get(key)
    if cached is not None:
        _QUERY_EMBED_CACHE.move_to_end(key)
        return cached, model_id
    vectors, used_model = embed_texts([query], config=config, is_query=True)
    if used_model == model_id:
        _QUERY_EMBED_CACHE[key] = vectors[0]
        if len(_QUERY_EMBED_CACHE) > _QUERY_EMBED_CACHE_SIZE:
            _QUERY_EMBED_CACHE.popitem(last=False)
    return vectors[0], used_model


def parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _data_dir(config: dict | None = None) -> Path:
    return Path(get_runtime_config(config)["kb_data_dir"]).expanduser()


def _files_dir(config: dict | None = None) -> Path:
    return _data_dir(config) / "files"


def _ensure_dirs(config: dict | None = None) -> None:
    _files_dir(config).mkdir(parents=True, exist_ok=True)


# ── Files, URL safety, and text extraction (unchanged) ──────────────
def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _managed_files_root(config: dict | None = None) -> Path:
    return _files_dir(config).expanduser().resolve()


def _validate_public_http_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only http:// and https:// URLs are allowed.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL host is required.")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Localhost URLs are not allowed.")
    try:
        ip_addr = ipaddress.ip_address(host)
    except ValueError:
        return parsed.geturl()
    if (
        ip_addr.is_private
        or ip_addr.is_loopback
        or ip_addr.is_link_local
        or ip_addr.is_reserved
        or ip_addr.is_multicast
        or ip_addr.is_unspecified
    ):
        raise ValueError("Private or local network URLs are not allowed.")
    return parsed.geturl()


MAX_REDIRECTS = 5


def _ensure_resolves_publicly(url: str) -> None:
    """The host must resolve only to public addresses; a public-looking name can point inside the network."""
    import socket
    parsed = urlparse(url)
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve {parsed.hostname}.") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("Private or local network URLs are not allowed.")


def _safe_get(url: str, *, timeout: float) -> httpx.Response:
    """GET a public URL, following redirects by hand so every hop is checked the same way."""
    current = _validate_public_http_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        _ensure_resolves_publicly(current)
        response = httpx.get(current, follow_redirects=False, timeout=timeout)
        if response.is_redirect and response.headers.get("location"):
            current = _validate_public_http_url(urljoin(current, response.headers["location"]))
            continue
        return response
    raise ValueError("Too many redirects.")


def _coerce_jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return json.loads(json.dumps(value, default=str))


def _sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _safe_title(value: str | None, fallback: str = "Untitled source") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:220] if text else fallback


def _resolve_managed_storage_path(storage_path: str, *, config: dict | None = None) -> Path:
    base = _managed_files_root(config)
    raw_path = Path(str(storage_path or "").strip()).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()
    if not _is_relative_to(resolved, base):
        raise ValueError("KB file path must stay inside the managed kb files directory.")
    return resolved


def _validate_source_payload(
    source_type: str,
    *,
    source_url: str | None = None,
    raw_text: str | None = None,
    storage_path: str | None = None,
    config: dict | None = None,
) -> None:
    url_text = str(source_url or "").strip()
    path_text = str(storage_path or "").strip()

    if source_type == "web_url":
        if not url_text:
            raise ValueError("Web KB sources require source_url.")
        _validate_public_http_url(url_text)
        return
    if source_type == "pdf_upload":
        if path_text:
            _resolve_managed_storage_path(path_text, config=config)
            return
        if not url_text:
            raise ValueError("PDF KB sources require storage_path or a downloadable source_url.")
        if urlparse(url_text).scheme in {"http", "https"}:
            _validate_public_http_url(url_text)
            return
        _resolve_managed_storage_path(url_text, config=config)
        return


def save_uploaded_file(filename: str, content: bytes, *, mime_type: str | None = None, config: dict | None = None) -> dict[str, Any]:
    if not filename:
        raise ValueError("File name is required.")
    _ensure_dirs(config)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    rel_dir = Path(datetime.now(timezone.utc).strftime("%Y/%m"))
    rel_path = rel_dir / f"{uuid.uuid4().hex}_{safe_name}"
    full_path = _files_dir(config) / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    guessed_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return {
        "storage_bucket": "local-kb-files",
        "storage_path": rel_path.as_posix(),
        "source_url": rel_path.as_posix(),
        "mime_type": guessed_mime,
        "metadata": {"original_name": filename, "size_bytes": len(content), "local_path": rel_path.as_posix()},
    }


def _resolve_storage_path(storage_path: str, *, config: dict | None = None) -> Path:
    return _resolve_managed_storage_path(storage_path, config=config)


def _download_source_bytes(source: dict[str, Any], *, config: dict | None = None) -> bytes:
    path_text = str(source.get("storage_path") or "").strip()
    if path_text:
        path = _resolve_storage_path(path_text, config=config)
        if path.exists():
            return path.read_bytes()
    url = str(source.get("source_url") or "").strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            response = _safe_get(url, timeout=35.0)
            response.raise_for_status()
            return response.content
        local_path = _resolve_storage_path(url, config=config)
        if local_path.exists():
            return local_path.read_bytes()
    raise RuntimeError("KB source is missing a local file path or downloadable URL.")


def _extract_pdf_text_from_bytes(content: bytes) -> str:
    if not content:
        return ""
    try:
        import pymupdf4llm

        text = pymupdf4llm.to_markdown(io.BytesIO(content))
        if str(text or "").strip():
            return str(text).strip()
    except Exception:
        pass
    try:
        import fitz

        doc = fitz.open(stream=content, filetype="pdf")
        parts = [page.get_text("text").strip() for page in doc if page.get_text("text").strip()]
        if parts:
            return "\n\n".join(parts).strip()
    except Exception:
        pass
    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts).strip()


def _fetch_url_response(url: str, *, timeout: float = 30.0) -> httpx.Response:
    response = _safe_get(url, timeout=timeout)
    response.raise_for_status()
    return response


def _extract_text_from_html(html: str, *, url: str) -> str:
    extracted = trafilatura.extract(
        html,
        url=url,
        include_links=True,
        include_tables=True,
        favor_precision=True,
    )
    return str(extracted or "").strip()


def _html_title(html: str, fallback_url: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    if match:
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip()
        if title:
            return _safe_title(title, _title_from_web_url(fallback_url))
    return _title_from_web_url(fallback_url)


def _title_from_web_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    path = parsed.path.strip("/")
    if not path:
        return parsed.netloc or "Website page"
    leaf = path.rsplit("/", 1)[-1] or path
    leaf = re.sub(r"\.[a-zA-Z0-9]{1,8}$", "", leaf)
    leaf = re.sub(r"[-_]+", " ", leaf).strip()
    return _safe_title(leaf.title() if leaf else parsed.netloc, "Website page")


def _xml_tag_name(tag: str) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _same_site_url(candidate: str, root_url: str) -> bool:
    candidate_host = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
    root_host = (urlparse(root_url).hostname or "").lower().removeprefix("www.")
    return bool(candidate_host and root_host and candidate_host == root_host)


def _is_sitemap_response(url: str, response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text.lstrip()[:500].lower()
    parsed_path = urlparse(str(response.url or url)).path.lower()
    return (
        "xml" in content_type
        or parsed_path.endswith(".xml")
        or parsed_path.endswith(".xml.gz")
        or "<urlset" in text
        or "<sitemapindex" in text
    )


def _parse_sitemap_locs(xml_text: str, *, base_url: str) -> tuple[list[str], list[str]]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Unable to parse sitemap XML: {exc}") from exc

    root_tag = _xml_tag_name(root.tag)
    sitemap_urls: list[str] = []
    page_urls: list[str] = []
    if root_tag == "sitemapindex":
        target = sitemap_urls
    elif root_tag == "urlset":
        target = page_urls
    else:
        target = page_urls

    for loc in root.findall(".//{*}loc"):
        value = str(loc.text or "").strip()
        if not value:
            continue
        absolute_url = _validate_public_http_url(urljoin(base_url, value))
        if _same_site_url(absolute_url, base_url):
            target.append(absolute_url)
    return sitemap_urls, page_urls


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        clean = str(url or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _collect_sitemap_page_urls(sitemap_url: str) -> list[str]:
    root_url = _validate_public_http_url(sitemap_url)
    pending = [root_url]
    seen_sitemaps: set[str] = set()
    page_urls: list[str] = []

    while pending and len(seen_sitemaps) < KB_MAX_SITEMAPS and len(page_urls) < KB_MAX_SITEMAP_URLS:
        current = pending.pop(0)
        if current in seen_sitemaps:
            continue
        seen_sitemaps.add(current)
        response = _fetch_url_response(current, timeout=35.0)
        nested_sitemaps, nested_pages = _parse_sitemap_locs(response.text, base_url=current)
        pending.extend(url for url in _dedupe_urls(nested_sitemaps) if url not in seen_sitemaps)
        for page_url in _dedupe_urls(nested_pages):
            if len(page_urls) >= KB_MAX_SITEMAP_URLS:
                break
            if page_url not in page_urls:
                page_urls.append(page_url)

    return page_urls


def _extract_web_documents(source_url: str) -> list[dict[str, Any]]:
    response = _fetch_url_response(source_url)
    final_url = str(response.url)
    documents: list[dict[str, Any]] = []

    if _is_sitemap_response(source_url, response):
        page_urls = _collect_sitemap_page_urls(final_url)
        for page_url in page_urls:
            try:
                page_response = _fetch_url_response(page_url)
                page_text = _extract_text_from_html(page_response.text, url=str(page_response.url))
            except Exception as exc:
                logger.warning(f"[KB] Failed to crawl sitemap page {page_url}: {exc}")
                continue
            if not page_text:
                continue
            page_final_url = str(page_response.url)
            documents.append(
                {
                    "external_id": f"url:{page_final_url}",
                    "title": _html_title(page_response.text, page_final_url),
                    "body_text": page_text,
                    "metadata": {"source_url": page_final_url, "sitemap_url": final_url},
                }
            )
        return documents

    page_text = _extract_text_from_html(response.text, url=final_url)
    if page_text:
        documents.append(
            {
                "external_id": f"url:{final_url}",
                "title": _html_title(response.text, final_url),
                "body_text": page_text,
                "metadata": {"source_url": final_url},
            }
        )
    return documents



# ── Storage (application database) ───────────────────────────────────
@contextlib.contextmanager
def _session(tenant_id: str | None = None):
    from app.core.database import SessionLocal
    from app.core.tenancy import bind_session_to_tenant

    db = SessionLocal()
    try:
        if tenant_id:
            bind_session_to_tenant(db, tenant_id)
        yield db
    finally:
        db.close()


def _iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _source_dict(src) -> dict[str, Any]:
    return {
        "id": src.id, "tenant_id": src.tenant_id, "created_at": _iso(src.created_at), "updated_at": _iso(src.updated_at),
        "source_type": src.source_type, "title": src.title, "source_url": src.source_url,
        "storage_bucket": src.storage_bucket, "storage_path": src.storage_path, "mime_type": src.mime_type,
        "checksum": src.checksum, "status": src.status, "enabled": bool(src.enabled), "language": src.language,
        "last_synced_at": _iso(src.last_synced_at), "sync_error": src.sync_error, "metadata": dict(src.meta or {}),
    }


def _job_dict(job) -> dict[str, Any]:
    return {
        "id": job.id, "tenant_id": job.tenant_id, "source_id": job.source_id, "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at), "source_type": job.source_type, "job_type": job.job_type,
        "status": job.status, "payload": dict(job.payload or {}), "error_text": job.error_text,
        "attempts": job.attempts, "started_at": _iso(job.started_at), "finished_at": _iso(job.finished_at),
        "last_result": dict(job.last_result or {}),
    }


def _source_type_from_payload(payload: dict[str, Any]) -> str:
    source_type = str(payload.get("source_type") or payload.get("type") or "").strip().lower()
    aliases = {"url": "web_url", "web": "web_url", "website": "web_url", "sitemap": "web_url",
               "pdf": "pdf_upload", "manual": "text", "faq": "text"}
    source_type = aliases.get(source_type, source_type)
    if source_type not in KB_SOURCE_TYPES:
        raise ValueError(f"Unsupported KB source_type: {source_type}")
    return source_type


def _require_tenant(tenant_id: str | None) -> str:
    if not tenant_id:
        raise ValueError("A tenant is required for knowledge base operations.")
    return tenant_id


def list_sources(limit: int = 200, *, config: dict | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
    from app.models.kb import KBSource

    tenant_id = _require_tenant(tenant_id)
    with _session(tenant_id) as db:
        rows = (db.query(KBSource).filter(KBSource.tenant_id == tenant_id)
                .order_by(KBSource.updated_at.desc()).limit(limit).all())
        return [_source_dict(r) for r in rows]


def get_source(source_id: str | int, *, config: dict | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
    from app.models.kb import KBSource

    tenant_id = _require_tenant(tenant_id)
    with _session(tenant_id) as db:
        row = db.query(KBSource).filter(KBSource.id == parse_int(source_id, -1), KBSource.tenant_id == tenant_id).first()
        return _source_dict(row) if row else None


def create_source(payload: dict[str, Any], *, queue_sync: bool = True, config: dict | None = None,
                  tenant_id: str | None = None) -> dict[str, Any]:
    from app.models.kb import KBSource

    tenant_id = _require_tenant(tenant_id)
    source_type = _source_type_from_payload(payload)
    title = _safe_title(payload.get("title"), f"{source_type.replace('_', ' ').title()} Source")
    source_url = str(payload.get("source_url") or payload.get("url") or "").strip() or None
    raw_text = str(payload.get("raw_text") or payload.get("text") or payload.get("content") or "").strip() or None
    storage_path = str(payload.get("storage_path") or "").strip() or None
    if source_type == "text":
        if not raw_text:
            raise ValueError("Text KB sources require raw_text.")
        if len(raw_text) > 200_000:
            raise ValueError("Text KB sources are limited to 200,000 characters.")
    else:
        _validate_source_payload(source_type, source_url=source_url, raw_text=raw_text, storage_path=storage_path, config=config)
    with _session(tenant_id) as db:
        src = KBSource(
            tenant_id=tenant_id, source_type=source_type, title=title, source_url=source_url, raw_text=raw_text,
            storage_bucket=str(payload.get("storage_bucket") or "").strip() or None, storage_path=storage_path,
            mime_type=str(payload.get("mime_type") or "").strip() or None,
            checksum=_sha256_text(f"{source_url or ''}\n{raw_text or ''}\n{storage_path or ''}\n{title}"),
            status="pending", enabled=parse_bool(payload.get("enabled", True), True),
            meta=_coerce_jsonable(payload.get("metadata") or {}),
        )
        db.add(src)
        db.commit()
        db.refresh(src)
        result = _source_dict(src)
    if queue_sync:
        queue_job(source_id=result["id"], source_type=source_type, job_type="ingest", config=config, tenant_id=tenant_id)
    return result


def update_source(source_id: str | int, payload: dict[str, Any], *, config: dict | None = None,
                  tenant_id: str | None = None) -> dict[str, Any]:
    """User-editable fields only (title, URL, text, enabled, metadata). Status is owned by the ingest pipeline."""
    from app.models.kb import KBSource

    tenant_id = _require_tenant(tenant_id)
    with _session(tenant_id) as db:
        src = db.query(KBSource).filter(KBSource.id == parse_int(source_id, -1), KBSource.tenant_id == tenant_id).first()
        if src is None:
            raise ValueError(f"KB source {source_id} was not found.")
        content_changed = False
        if "title" in payload:
            src.title = _safe_title(payload.get("title"), src.title)
        new_url = payload.get("source_url", payload.get("url"))
        if new_url is not None and str(new_url).strip() != (src.source_url or ""):
            src.source_url = str(new_url).strip() or None
            content_changed = True
        if "raw_text" in payload and src.source_type == "text":
            src.raw_text = str(payload.get("raw_text") or "").strip() or None
            content_changed = True
        if "metadata" in payload:
            src.meta = _coerce_jsonable(payload.get("metadata") or {})
        if "enabled" in payload:
            src.enabled = parse_bool(payload.get("enabled"), src.enabled)
            if not src.enabled:
                src.status = "disabled"
            elif src.status == "disabled":
                src.status = "ready" if src.last_synced_at else "pending"
        if content_changed and src.source_type != "text":
            _validate_source_payload(src.source_type, source_url=src.source_url, raw_text=src.raw_text,
                                     storage_path=src.storage_path, config=config)
        src.checksum = _sha256_text(f"{src.source_url or ''}\n{src.raw_text or ''}\n{src.storage_path or ''}\n{src.title}")
        db.commit()
        db.refresh(src)
        result = _source_dict(src)
    _invalidate_tenant_index(tenant_id)
    if content_changed:
        queue_job(source_id=result["id"], source_type=result["source_type"], job_type="ingest", config=config, tenant_id=tenant_id)
    return result


def delete_source(source_id: str | int, *, config: dict | None = None, tenant_id: str | None = None) -> bool:
    from app.models.kb import KBChunk, KBDocument, KBIngestJob, KBSource

    tenant_id = _require_tenant(tenant_id)
    with _session(tenant_id) as db:
        src = db.query(KBSource).filter(KBSource.id == parse_int(source_id, -1), KBSource.tenant_id == tenant_id).first()
        if src is None:
            return False
        storage_path = src.storage_path
        # Explicit child deletes: SQLite doesn't enforce ON DELETE CASCADE by default.
        db.query(KBChunk).filter(KBChunk.source_id == src.id).delete()
        db.query(KBDocument).filter(KBDocument.source_id == src.id).delete()
        db.query(KBIngestJob).filter(KBIngestJob.source_id == src.id).delete()
        db.delete(src)
        db.commit()
    if storage_path:
        try:
            path = _resolve_managed_storage_path(storage_path, config=config)
            if path.is_file():
                path.unlink()
        except Exception as exc:
            logger.warning(f"[KB] Could not remove stored file for source {source_id}: {exc}")
    _invalidate_tenant_index(tenant_id)
    return True


def queue_job(*, source_id: str | int | None, source_type: str, job_type: str = "ingest",
              payload: dict[str, Any] | None = None, config: dict | None = None,
              tenant_id: str | None = None) -> dict[str, Any]:
    from app.models.kb import KBIngestJob, KBSource

    if job_type not in KB_JOB_TYPES:
        raise ValueError(f"Unsupported KB job_type: {job_type}")
    tenant_id = _require_tenant(tenant_id)
    with _session(tenant_id) as db:
        if source_id is not None and not db.query(KBSource).filter(
                KBSource.id == parse_int(source_id, -1), KBSource.tenant_id == tenant_id).first():
            raise ValueError(f"KB source {source_id} was not found.")
        job = KBIngestJob(tenant_id=tenant_id, source_id=parse_int(source_id, 0) if source_id is not None else None,
                          source_type=source_type, job_type=job_type, status="pending", payload=payload or {})
        db.add(job)
        db.commit()
        db.refresh(job)
        return _job_dict(job)


def list_jobs(limit: int = 100, *, config: dict | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
    from app.models.kb import KBIngestJob

    tenant_id = _require_tenant(tenant_id)
    with _session(tenant_id) as db:
        rows = (db.query(KBIngestJob).filter(KBIngestJob.tenant_id == tenant_id)
                .order_by(KBIngestJob.created_at.desc()).limit(limit).all())
        return [_job_dict(r) for r in rows]


def _set_source_state(source_id: int, **fields: Any) -> None:
    from app.models.kb import KBSource

    with _session() as db:
        src = db.query(KBSource).filter(KBSource.id == source_id).first()
        if src is None:
            return
        meta_patch = fields.pop("metadata_patch", None)
        for key, value in fields.items():
            setattr(src, key, value)
        if meta_patch:
            src.meta = {**(src.meta or {}), **meta_patch}
        db.commit()


# ── Chunking ─────────────────────────────────────────────────────────
def _split_into_chunks(text: str, *, chunk_size: int, overlap: int) -> list[dict[str, Any]]:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    tokens = _TOKENIZER.encode(clean) if clean else []
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 0
    while start < len(tokens):
        end = min(len(tokens), start + chunk_size)
        piece = _TOKENIZER.decode(tokens[start:end]).strip()
        if piece:
            chunks.append({"chunk_index": index, "content": piece, "token_count": end - start})
            index += 1
        if end >= len(tokens):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_text(text: str, *, chunk_size: int = 400, overlap: int = 60, config: dict | None = None) -> list[dict[str, Any]]:
    """Split text into overlapping chunks and embed them (kept for callers of the old API)."""
    chunks = _split_into_chunks(text, chunk_size=chunk_size, overlap=overlap)
    vectors, model_id = embed_texts([c["content"] for c in chunks], config=config, is_query=False)
    for chunk, vector in zip(chunks, vectors):
        chunk.update(embedding=vector, embedding_model=model_id, checksum=_sha256_text(chunk["content"]))
    return chunks


# ── Ingestion ────────────────────────────────────────────────────────
def _extract_documents(source: dict[str, Any], *, config: dict | None) -> list[dict[str, Any]]:
    source_type = source["source_type"]
    title = _safe_title(source.get("title"), "Knowledge Source")
    if source_type == "web_url":
        return _extract_web_documents(str(source.get("source_url") or "").strip())
    if source_type == "text":
        return [{"external_id": f"source:{source['id']}", "title": title, "body_text": source.get("raw_text") or "", "metadata": {}}]
    if source_type == "pdf_upload":
        mime = str(source.get("mime_type") or "").lower()
        file_bytes = _download_source_bytes(source, config=config)
        if "markdown" in mime or "text" in mime or title.lower().endswith((".md", ".txt")):
            content = file_bytes.decode("utf-8", errors="replace")
        else:
            content = _extract_pdf_text_from_bytes(file_bytes)
        return [{"external_id": f"source:{source['id']}", "title": title, "body_text": content,
                 "metadata": {"source_url": source.get("source_url")}}]
    raise RuntimeError(f"Unsupported KB ingest source type: {source_type}")


def _ingest_source(source_id: int, *, config: dict | None, job_id: int | None = None) -> dict[str, Any]:
    from app.models.kb import KBChunk, KBDocument, KBSource

    runtime = get_runtime_config(config)
    with _session() as db:
        src = db.query(KBSource).filter(KBSource.id == source_id).first()
        if src is None:
            raise RuntimeError(f"KB source {source_id} was not found.")
        source = {**_source_dict(src), "raw_text": src.raw_text}
    tenant_id = source["tenant_id"]
    _set_source_state(source_id, status="syncing", sync_error=None,
                      metadata_patch={"sync_progress": {"phase": "extract", "label": "Extracting text", "percent": 0}})

    documents = [d for d in _extract_documents(source, config=config) if str(d.get("body_text") or "").strip()]
    if not documents:
        raise RuntimeError("No text could be extracted from this source.")

    prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for doc in documents:
        pieces = _split_into_chunks(doc["body_text"], chunk_size=runtime["kb_chunk_size"], overlap=runtime["kb_chunk_overlap"])
        prepared.append((doc, pieces))
    all_pieces = [p for _, pieces in prepared for p in pieces]
    _set_source_state(source_id, metadata_patch={"sync_progress": {
        "phase": "embed", "label": f"Embedding {len(all_pieces)} chunks", "percent": 40}})
    vectors, model_id = embed_texts([p["content"] for p in all_pieces], config=config, is_query=False)
    for piece, vector in zip(all_pieces, vectors):
        piece["embedding"] = vector

    languages: Counter[str] = Counter()
    with _session(tenant_id) as db:
        existing = {d.external_id: d for d in db.query(KBDocument).filter(KBDocument.source_id == source_id).all()}
        seen: set[str] = set()
        for doc, pieces in prepared:
            external_id = str(doc.get("external_id") or f"source:{source_id}:{len(seen)}")
            if external_id in seen:
                continue
            seen.add(external_id)
            doc_title = _safe_title(doc.get("title"), source["title"])
            language = detect_language(doc["body_text"])
            if language:
                languages[language] += len(doc["body_text"])
            doc_meta = {**dict(doc.get("metadata") or {})}
            row = existing.get(external_id)
            if row is None:
                row = KBDocument(tenant_id=tenant_id, source_id=source_id, external_id=external_id)
                db.add(row)
            row.document_type, row.title, row.body_text = source["source_type"], doc_title, doc["body_text"]
            row.checksum, row.language, row.meta = _sha256_text(doc["body_text"]), language, doc_meta
            db.flush()
            db.query(KBChunk).filter(KBChunk.document_id == row.id).delete()
            chunk_meta = {"source_type": source["source_type"], "title": doc_title,
                          "source_url": doc_meta.get("source_url") or source.get("source_url")}
            for piece in pieces:
                db.add(KBChunk(
                    tenant_id=tenant_id, source_id=source_id, document_id=row.id, chunk_index=piece["chunk_index"],
                    title=doc_title, content=piece["content"],
                    search_tokens=" ".join(_tokenize_keywords(f"{doc_title} {piece['content']}")),
                    checksum=_sha256_text(piece["content"]), token_count=piece["token_count"],
                    language=detect_language(piece["content"]) or language,
                    embedding=piece["embedding"], embedding_model=model_id, meta=chunk_meta,
                ))
        for external_id, row in existing.items():
            if external_id not in seen:
                db.query(KBChunk).filter(KBChunk.document_id == row.id).delete()
                db.delete(row)
        db.commit()

    finished = _utcnow()
    result = {"document_count": len(seen), "chunk_count": len(all_pieces),
              "character_count": sum(len(d["body_text"]) for d in documents), "embedding_model": model_id}
    _set_source_state(source_id, status="ready" if source["enabled"] else "disabled", sync_error=None,
                      last_synced_at=finished, language=languages.most_common(1)[0][0] if languages else None,
                      metadata_patch={**result, "sync_progress": {"phase": "done", "label": "Available", "percent": 100}})
    _invalidate_tenant_index(tenant_id)
    return {**result, "finished_at": _iso(finished)}


def _reembed_source(source_id: int, *, config: dict | None) -> dict[str, Any]:
    """Recompute embeddings for chunks produced by a different model (no re-download)."""
    from app.models.kb import KBChunk

    model_id = embedding_model_id(config)
    with _session() as db:
        chunks = db.query(KBChunk).filter(KBChunk.source_id == source_id).all()
        stale = [c for c in chunks if c.embedding_model != model_id]
        vectors, used_model = embed_texts([c.content for c in stale], config=config, is_query=False)
        for chunk, vector in zip(stale, vectors):
            chunk.embedding, chunk.embedding_model = vector, used_model
            chunk.search_tokens = " ".join(_tokenize_keywords(f"{chunk.title} {chunk.content}"))
        tenant_id = chunks[0].tenant_id if chunks else None
        db.commit()
    if tenant_id:
        _invalidate_tenant_index(tenant_id)
    return {"reembedded": len(stale), "embedding_model": used_model if stale else model_id}


def _claim_jobs(limit: int) -> list[int]:
    """Atomically move due jobs to 'processing' so the API and the worker never run the same job."""
    from sqlalchemy import or_

    from app.models.kb import KBIngestJob

    now = _utcnow()
    claimed: list[int] = []
    with _session() as db:
        candidates = [j.id for j in db.query(KBIngestJob).filter(or_(
            KBIngestJob.status == "pending",
            (KBIngestJob.status == "failed") & (KBIngestJob.attempts < KB_MAX_JOB_ATTEMPTS)
            & (KBIngestJob.next_attempt_at <= now),
        )).order_by(KBIngestJob.created_at).limit(limit).all()]
        for job_id in candidates:
            updated = db.query(KBIngestJob).filter(
                KBIngestJob.id == job_id, KBIngestJob.status.in_(["pending", "failed"])
            ).update({KBIngestJob.status: "processing", KBIngestJob.started_at: now,
                      KBIngestJob.attempts: KBIngestJob.attempts + 1, KBIngestJob.error_text: None},
                     synchronize_session=False)
            db.commit()
            if updated:
                claimed.append(job_id)
    return claimed


def _finish_job(job_id: int, **fields: Any) -> None:
    from app.models.kb import KBIngestJob

    with _session() as db:
        job = db.query(KBIngestJob).filter(KBIngestJob.id == job_id).first()
        if job is not None:
            for key, value in fields.items():
                setattr(job, key, value)
            db.commit()


def process_pending_jobs(config: dict | None = None, *, limit: int = 5) -> list[dict[str, Any]]:
    from app.models.kb import KBIngestJob

    processed: list[dict[str, Any]] = []
    for job_id in _claim_jobs(limit):
        with _session() as db:
            job = db.query(KBIngestJob).filter(KBIngestJob.id == job_id).first()
            source_id, job_type, attempts = job.source_id, job.job_type, job.attempts
        try:
            if source_id is None:
                raise RuntimeError("Job has no source.")
            result = (_reembed_source(source_id, config=config) if job_type == "reindex"
                      else _ingest_source(source_id, config=config, job_id=job_id))
            _finish_job(job_id, status="completed", finished_at=_utcnow(), last_result=_coerce_jsonable(result))
            processed.append({"job_id": job_id, "status": "completed", "result": result})
        except Exception as exc:
            final = attempts >= KB_MAX_JOB_ATTEMPTS
            logger.error(f"[KB] Job {job_id} failed (attempt {attempts}/{KB_MAX_JOB_ATTEMPTS}): {exc}")
            _finish_job(job_id, status="failed", finished_at=_utcnow(), error_text=str(exc)[:2000],
                        next_attempt_at=None if final else _utcnow() + timedelta(minutes=2 ** attempts))
            if source_id is not None:
                _set_source_state(source_id, status="error", sync_error=str(exc)[:2000],
                                  metadata_patch={"sync_progress": {"phase": "error", "label": "Failed", "percent": 0}})
            processed.append({"job_id": job_id, "status": "failed", "error": str(exc)})
    return processed


def reindex_stale_sources(*, config: dict | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Queue re-embedding for every source whose chunks were embedded with a different model."""
    from sqlalchemy import or_

    from app.models.kb import KBChunk, KBSource

    tenant_id = _require_tenant(tenant_id)
    model_id = embedding_model_id(config)
    with _session(tenant_id) as db:
        stale_ids = {sid for (sid,) in db.query(KBChunk.source_id).filter(
            KBChunk.tenant_id == tenant_id,
            or_(KBChunk.embedding_model != model_id, KBChunk.embedding_model.is_(None))).distinct()}
        sources = db.query(KBSource).filter(KBSource.id.in_(stale_ids)).all() if stale_ids else []
        targets = [(s.id, s.source_type) for s in sources]
    return [queue_job(source_id=sid, source_type=stype, job_type="reindex", config=config, tenant_id=tenant_id)
            for sid, stype in targets]


# ── Search ───────────────────────────────────────────────────────────
_TENANT_INDEX: dict[str, dict[str, Any]] = {}
_TENANT_INDEX_LOCK = threading.Lock()


def _invalidate_tenant_index(tenant_id: str) -> None:
    with _TENANT_INDEX_LOCK:
        _TENANT_INDEX.pop(tenant_id, None)


def _is_postgres() -> bool:
    from app.core.database import engine

    return engine.dialect.name == "postgresql"


def _chunk_row(chunk, source_type_by_id: dict[int, str] | None = None) -> dict[str, Any]:
    meta = dict(chunk.meta or {})
    return {"id": chunk.id, "title": chunk.title, "content": chunk.content, "language": chunk.language,
            "source_id": chunk.source_id, "source_type": meta.get("source_type") or "unknown",
            "source_url": meta.get("source_url"), "_tokens": (chunk.search_tokens or "").split()}


def _memory_index(tenant_id: str, config: dict | None) -> dict[str, Any]:
    """Local (SQLite) search: tenant chunks, vectors, and BM25 statistics cached in memory."""
    from app.models.kb import KBChunk, KBSource

    ttl = get_runtime_config(config)["kb_cache_ttl_seconds"]
    with _TENANT_INDEX_LOCK:
        cached = _TENANT_INDEX.get(tenant_id)
        if cached and time.monotonic() - cached["at"] < ttl:
            return cached
    with _session(tenant_id) as db:
        rows = (db.query(KBChunk).join(KBSource, KBSource.id == KBChunk.source_id)
                .filter(KBChunk.tenant_id == tenant_id, KBSource.enabled.is_(True)).all())
        chunks = [(_chunk_row(c), c.embedding, c.embedding_model) for c in rows]
    doc_freq: Counter[str] = Counter()
    for row, _, _ in chunks:
        doc_freq.update(set(row["_tokens"]))
    lengths = [len(row["_tokens"]) for row, _, _ in chunks]
    index = {
        "at": time.monotonic(), "rows": [r for r, _, _ in chunks], "embeddings": [e for _, e, _ in chunks],
        "models": [m for _, _, m in chunks], "doc_freq": doc_freq,
        "avgdl": (sum(lengths) / len(lengths)) if lengths else 0.0,
    }
    with _TENANT_INDEX_LOCK:
        _TENANT_INDEX[tenant_id] = index
    return index


def _bm25(query_tokens: list[str], tokens: list[str], *, doc_freq: Counter[str], n_docs: int, avgdl: float) -> float:
    if not query_tokens or not tokens:
        return 0.0
    counts = Counter(tokens)
    k1, b, score = 1.5, 0.75, 0.0
    for token in query_tokens:
        tf = counts.get(token, 0)
        if tf:
            df = doc_freq.get(token, 0)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (len(tokens) / avgdl if avgdl else 1.0)))
    return score


def _candidates_memory(tenant_id: str, query_tokens: list[str], query_vec: list[float] | None, query_model: str | None,
                       limit: int, config: dict | None) -> list[tuple[dict[str, Any], float, float]]:
    index = _memory_index(tenant_id, config)
    rows = index["rows"]
    dense = [0.0] * len(rows)
    if query_vec is not None:
        usable = [i for i, (e, m) in enumerate(zip(index["embeddings"], index["models"])) if e and m == query_model]
        if usable:
            matrix = np.asarray([index["embeddings"][i] for i in usable], dtype=np.float32)
            sims = matrix @ np.asarray(query_vec, dtype=np.float32)
            for i, sim in zip(usable, sims.tolist()):
                dense[i] = float(sim)
    keyword = [_bm25(query_tokens, r["_tokens"], doc_freq=index["doc_freq"], n_docs=len(rows), avgdl=index["avgdl"])
               for r in rows]
    top = set(sorted(range(len(rows)), key=lambda i: dense[i], reverse=True)[:limit * 8])
    top |= {i for i in sorted(range(len(rows)), key=lambda i: keyword[i], reverse=True)[:limit * 8] if keyword[i] > 0}
    return [(rows[i], dense[i], keyword[i]) for i in top]


def _candidates_postgres(tenant_id: str, query_tokens: list[str], query_vec: list[float] | None, query_model: str | None,
                         limit: int) -> list[tuple[dict[str, Any], float, float]]:
    from sqlalchemy import func

    from app.models.kb import KBChunk, KBSource

    found: dict[int, list] = {}
    with _session(tenant_id) as db:
        base = (db.query(KBChunk).join(KBSource, KBSource.id == KBChunk.source_id)
                .filter(KBChunk.tenant_id == tenant_id, KBSource.enabled.is_(True)))
        if query_vec is not None:
            from pgvector.sqlalchemy import Vector
            from sqlalchemy import Float, literal

            from app.models.kb import EMBEDDING_DIMENSIONS
            distance = KBChunk.embedding.op("<=>", return_type=Float)(literal(query_vec, type_=Vector(EMBEDDING_DIMENSIONS)))
            for chunk, dist in (base.filter(KBChunk.embedding_model == query_model)
                                .add_columns(distance).order_by(distance).limit(limit * 8).all()):
                found[chunk.id] = [_chunk_row(chunk), 1.0 - float(dist), 0.0]
        if query_tokens:
            # Any query word may match (like BM25); tokens contain only letters, marks, and digits.
            tsquery = func.websearch_to_tsquery("simple", " or ".join(query_tokens))
            tsvector = func.to_tsvector("simple", KBChunk.search_tokens)
            rank = func.ts_rank(tsvector, tsquery)
            for chunk, score in (base.filter(tsvector.op("@@")(tsquery)).add_columns(rank)
                                 .order_by(rank.desc()).limit(limit * 8).all()):
                entry = found.setdefault(chunk.id, [_chunk_row(chunk), 0.0, 0.0])
                # ts_rank is ~0..1; scale into the BM25-like range the scorer expects.
                entry[2] = float(score) * 10.0
    return [tuple(v) for v in found.values()]


def _keyword_overlap(query_tokens: list[str], tokens: list[str]) -> float:
    if not query_tokens or not tokens:
        return 0.0
    q, c = Counter(query_tokens), Counter(tokens)
    return sum(min(n, c.get(t, 0)) for t, n in q.items()) / sum(q.values())


def search_chunks(query: str, *, limit: int = 4, config: dict | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
    if not tenant_id:
        logger.error("[KB] Search without a tenant refused.")
        return []
    runtime = get_runtime_config(config)
    query_norm = _normalize_text(query)
    query_tokens = _tokenize_keywords(query)
    try:
        query_vec, query_model = _embed_query(query, config)
    except EmbeddingUnavailableError as exc:
        # Keep answering live calls with keyword search rather than failing the turn.
        logger.error(f"[KB] Vector search unavailable, using keyword search only: {exc}")
        query_vec, query_model = None, None

    candidates = (_candidates_postgres(tenant_id, query_tokens, query_vec, query_model, limit) if _is_postgres()
                  else _candidates_memory(tenant_id, query_tokens, query_vec, query_model, limit, config))
    min_dense = runtime["kb_min_dense_similarity"]
    scored: list[tuple[float, dict[str, Any], float]] = []
    for row, dense, keyword in candidates:
        overlap = _keyword_overlap(query_tokens, row["_tokens"])
        exact = bool(query_norm) and query_norm in _normalize_text(f"{row['title']} {row['content']}")
        # Semantic similarity alone must clear min_dense; with shared keywords it only adds support.
        dense_term = dense if (dense >= min_dense or overlap > 0 or exact) else 0.0
        score = (1.8 if exact else 0.0) + overlap * 2.6 + max(0.0, dense_term) * 2.2 + min(3.0, keyword) * 0.75
        if score >= 0.65:
            scored.append((score, row, dense))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [{
        "score": round(score, 4), "similarity": round(dense, 4), "title": row["title"], "content": row["content"],
        "preview": _preview(row["content"], limit=340), "source_type": row["source_type"],
        "source_url": row["source_url"], "source_id": row["source_id"], "language": row["language"],
    } for score, row, dense in scored[:limit]]


def search_hybrid(query: str, *, config: dict | None = None, tenant_id: str | None = None) -> dict[str, Any]:
    runtime = get_runtime_config(config)
    return {"query": query, "chunk_hits": search_chunks(query, limit=runtime["kb_top_k"], config=config, tenant_id=tenant_id)}


def is_kb_query(query: str) -> bool:
    """English questions need a knowledge-base keyword; other scripts always search (and rely on scoring)."""
    if not _normalize_text(query):
        return False
    if _has_non_latin_letters(query):
        return True
    return bool(set(_tokenize_keywords(query)) & (KB_QUERY_HINTS | KB_TEXT_HINTS))


def build_grounding_text(query: str, *, config: dict | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
    runtime = get_runtime_config(config)
    if not runtime["kb_enabled"] or not tenant_id or not is_kb_query(query):
        return None
    chunk_hits = search_hybrid(query, config=config, tenant_id=tenant_id)["chunk_hits"]
    if not chunk_hits:
        if _has_non_latin_letters(query) and not (set(_tokenize_keywords(query)) & (KB_QUERY_HINTS | KB_TEXT_HINTS)):
            return None  # likely small talk in another language; don't inject a "no match" rule
        return {"query": query, "chunk_hits": [], "grounding_text": (
            "Knowledge base rule: this looks like a knowledge-base question, but there is no confirmed "
            "match in the knowledge base for this turn. Do not guess. Say you do not have confirmed information.")}
    parts = [
        "Knowledge base grounding rules:",
        "1. Use only the confirmed facts below for this turn.",
        "2. If the exact fact is missing below, say you do not have confirmed information.",
        "3. The excerpts may be in a different language from the caller; answer in the caller's language.",
        "",
        "Knowledge excerpts:",
    ]
    for i, item in enumerate(chunk_hits, start=1):
        title = f"{item['title']}: " if item.get("title") else ""
        parts.append(f"{i}. [{item['source_type']}] {title}{item['preview']}")
    grounding_text = "\n".join(parts).strip()
    if len(grounding_text) > runtime["kb_context_char_budget"]:
        grounding_text = grounding_text[: runtime["kb_context_char_budget"]].rstrip() + "..."
    return {"query": query, "chunk_hits": chunk_hits, "grounding_text": grounding_text}


def search_for_agent(query: str, *, config: dict | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
    return build_grounding_text(query, config=config, tenant_id=tenant_id)


# ── Status ───────────────────────────────────────────────────────────
def kb_runtime_issue_payload(exc: Exception | str, *, config: dict | None = None) -> dict[str, Any]:
    runtime = get_runtime_config(config)
    return {"status": "error", "message": str(exc), "kb_enabled": runtime["kb_enabled"],
            "backend": runtime["kb_backend"], "counts": {"sources": 0, "jobs": 0, "chunks": 0}}


def get_status(config: dict | None = None, *, tenant_id: str | None = None) -> dict[str, Any]:
    from sqlalchemy import func, or_

    from app.models.kb import KBChunk, KBIngestJob, KBSource

    runtime = get_runtime_config(config)
    try:
        tenant_id = _require_tenant(tenant_id)
        model_id = embedding_model_id(config)
        with _session(tenant_id) as db:
            sources = db.query(func.count(KBSource.id)).filter(KBSource.tenant_id == tenant_id).scalar()
            jobs = db.query(func.count(KBIngestJob.id)).filter(KBIngestJob.tenant_id == tenant_id).scalar()
            chunks = db.query(func.count(KBChunk.id)).filter(KBChunk.tenant_id == tenant_id).scalar()
            stale = db.query(func.count(KBChunk.id)).filter(
                KBChunk.tenant_id == tenant_id,
                or_(KBChunk.embedding_model != model_id, KBChunk.embedding_model.is_(None))).scalar()
    except Exception as exc:
        return kb_runtime_issue_payload(exc, config=config)
    provider_ready = runtime["kb_embedding_provider"] != "gemini" or _google_genai_client_kwargs(runtime) is not None
    return {
        "status": "ok",
        "kb_enabled": runtime["kb_enabled"],
        "backend": "Postgres + pgvector" if _is_postgres() else "SQLite (local)",
        "runtime": "Postgres + pgvector" if _is_postgres() else "SQLite (local)",
        "embedding_provider": runtime["kb_embedding_provider"],
        "embedding_model": runtime["kb_embedding_model"],
        "embedding_ready": provider_ready,
        "embedding_issue": None if provider_ready else "GOOGLE_API_KEY is not set; embeddings are unavailable.",
        "vector_count": chunks,
        "stale_vector_count": stale,
        "counts": {"sources": sources, "jobs": jobs, "chunks": chunks},
    }
