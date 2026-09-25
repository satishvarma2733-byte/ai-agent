# 2. Technical Requirements Document (TRD)

## 1. Platforms

| Surface | Target | Status |
|---|---|---|
| Web dashboard (Agent Studio, CRM, analytics) | Evergreen desktop browsers; responsive down to 375 px | 🟡 desktop-first, partial mobile nav |
| Embeddable website widget | Any site, Shadow-DOM isolated, ≤ 60 KB gzipped initial JS | ❌ |
| Phone | PSTN via Vobiz SIP → LiveKit SIP | ✅ |
| Public API | REST + SSE, versioned `/api/v1` | ❌ (internal `/api/*` only) |
| Mobile apps | Out of scope v1 | — |

## 2. Frontend and hosting

| Item | Choice | Status / note |
|---|---|---|
| Framework | React 19 + TypeScript 6 + Vite 8 | ✅ |
| Styling | Tailwind 4 `@theme` tokens + CSS variables per theme | 🟡 tokens defined, pages use inline hex |
| State | Zustand 5 (UI state); add **TanStack Query** for server state/caching | 🟡 ad-hoc `useEffect` fetches |
| Routing | React Router 7 | ✅ |
| Canvas | **`@xyflow/react`** for workflow editor | ❌ hand-rolled SVG |
| Realtime | **`livekit-client`** for browser voice/avatar; `EventSource`/fetch-stream for SSE | ❌ |
| Forms/validation | **react-hook-form + zod** (shared schemas with API via OpenAPI codegen) | ❌ |
| Testing | Vitest + Testing Library; Playwright E2E | ❌ |
| Hosting | Static build on CDN (Cloudflare Pages / Coolify static) with SPA fallback | 🟡 `dist/` built manually |
| Widget | Separate Vite library build → `widget.js` on CDN, versioned path + `latest` alias | ❌ |

## 3. Backend and database

| Item | Choice | Status / note |
|---|---|---|
| API | FastAPI (`app/`), Python **3.12** pinned in both venv and Docker | 🟡 3.14 local vs 3.11 Docker |
| Legacy API | `backend_api.py` — retire after porting config, campaigns, recordings, integrations, media file routes | 🟡 |
| ORM / migrations | SQLAlchemy 2 + **Alembic** | 🟡 `create_all()` on boot |
| Database | **PostgreSQL 16** with **pgvector**; no silent SQLite fallback in staging/prod (fail fast) | 🟡 silent fallback |
| Vector store | pgvector (HNSW) per tenant-filtered index; FAISS kept only for local dev | 🟡 FAISS + SQLite on local disk (not horizontally scalable) |
| Queue / jobs | **Redis + arq** (async) for workflow steps, KB ingest, webhooks, test runs, campaigns | 🟡 in-process `asyncio.Queue`, SQLite job polling, threads |
| Cache / rate limit | Redis | ❌ |
| Object storage | S3-compatible (Supabase Storage / R2) for recordings, uploads, KB files; signed URLs | 🟡 local `data/` + optional Supabase S3 |
| Voice worker | LiveKit Agents 1.5 (`agent.py`) as its own deployable, horizontally scaled | ✅ code / ❌ not started by Dockerfile |
| Region | Primary `ap-south-1` (Mumbai) pending D6 | — |

## 4. Authentication and roles

| Item | Requirement | Status |
|---|---|---|
| Sign-in | Email + password (bcrypt), Google OAuth (P1) | 🟡 email/password only |
| Tokens | Access JWT 15 min; refresh token **opaque, stored hashed, rotated, httpOnly Secure SameSite=Lax cookie** | 🟡 refresh JWT in localStorage and in query string |
| Secret | `SECRET_KEY` required from env; boot fails if missing | ❌ hardcoded default |
| Signup | Creates tenant + Admin; **server ignores client `tenant_id`/`role`** | ❌ **critical: client can pass any `tenant_id` and `role`** |
| Invites | Admin invites by email → token link → user joins that tenant with the assigned role | ❌ |
| Email verification, password reset | Required | ❌ |
| MFA | TOTP for Admins (P1) | ❌ |
| Roles | Owner, Admin, Manager (Builder), Agent (human), Viewer; permission matrix in Schema §7 | 🟡 Admin/Manager/Agent |
| API keys | Per tenant, scoped (`chat:write`, `leads:read` …), shown once, stored hashed, prefix-identifiable | ❌ |
| Widget auth | Public deployment id + Origin allow-list → short-lived session token | ❌ |
| Dev bypass | Remove auto dev-token in `App.tsx`; dev uses seeded user | ❌ |

## 5. External services and APIs

| Provider | Purpose | Limits / cost driver | Credentials owner | Status |
|---|---|---|---|---|
| Google Gemini (Live, Flash, TTS, Embedding) | LLM, realtime voice, TTS, embeddings, language detection | RPM/TPM per key; per-token + per-audio-second | aVn (platform key), optional BYO per tenant | ✅ |
| Google Cloud Speech | STT fallback | per-minute | aVn | 🟡 dependency present |
| LiveKit Cloud | Realtime rooms, SIP, agent dispatch | concurrent participants, minutes | aVn | ✅ |
| Vobiz | SIP trunk, Indian DIDs | per-minute | aVn / tenant | ✅ |
| Google Calendar, Zoho Calendar | Booking sync | API quotas | tenant (OAuth) | ❌ not integrated |
| Avatar (D2) | Realtime video avatar | per-minute | aVn | ❌ |
| WhatsApp (D3) | Template + session messages | template approval, per-conversation | tenant (WABA) | ❌ (fake log) |
| Email (D4) | Transactional + workflow email | per-message | aVn | ❌ |
| Telegram | Internal notifications | — | aVn | ✅ |
| Supabase | Legacy DB/storage | — | aVn | 🟡 to reduce to storage or remove (D8) |
| Sentry | Errors + performance | events/month | aVn | ❌ installed, not initialised |
| Stripe / Razorpay | Billing (P1) | — | aVn | ❌ |

All tenant-provided credentials are stored encrypted (envelope encryption, KMS or libsodium sealed with a master key from env) and never returned to clients.

## 6. Architecture

```
            ┌──────────── Browser ─────────────┐        ┌── Customer website ──┐
            │ Dashboard / Agent Studio (React) │        │ widget.js (ShadowDOM)│
            └───────┬─────────────┬────────────┘        └────┬──────────┬─────┘
          REST/SSE  │     LiveKit │ WebRTC            REST/SSE│   WebRTC │
                    ▼             ▼                           ▼          ▼
            ┌──────────────┐   ┌──────────────┐   PSTN ─ Vobiz SIP ─► LiveKit SIP
            │  API (FastAPI│   │ LiveKit Cloud│◄──────────────────────────┘
            │  app/)       │   └──────┬───────┘
            │ - auth/tenancy│         │ job dispatch (agent_id, version_id)
            │ - studio/CRUD │         ▼
            │ - ConversationService ◄─── Voice worker (agent.py, LiveKit Agents)
            │ - public API  │         uses same ConversationService via internal API
            └──┬────┬────┬──┘
               │    │    │ enqueue
               │    │    ▼
               │    │  Redis ──► Workers (arq): workflow steps · KB ingest ·
               │    │                           webhooks · test runs · campaigns
               ▼    ▼
        PostgreSQL+pgvector   S3 storage         Gemini · Avatar · WhatsApp · Email
```

**Key flows**
1. **Conversation turn** (any channel): input → `ConversationService` loads production (or requested draft) `agent_version` → language detect → workflow executor advances conversation graph → KB retrieval (pgvector + BM25, tenant + agent filter) → Gemini → streamed events (`token`, `step`, `tool`, `done`) → persist message + run steps → emit analytics event → fire webhooks.
2. **Voice**: LiveKit room; worker receives `agent_id`/`version_id` in dispatch metadata; Gemini Live handles STT/LLM/TTS with barge-in; tools call the API for KB/workflow/CRM; turn metrics persisted.
3. **Automation**: domain event (`lead.created`, `call.completed`, …) → outbox table → worker matches active automation workflows → executes steps; Delay nodes schedule a future job, not `sleep`.
4. **Versioning**: all edits create/modify a draft version; Activate runs regression suite → gate → flip `agents.production_version_id` atomically.

## 7. Security and privacy

| Area | Requirement | Current |
|---|---|---|
| Tenant isolation | Every table has non-null `tenant_id` FK; repository layer enforces filter; Postgres RLS as defence in depth; tests per router | 🟡 nullable, filter by convention; seeded admin has `tenant_id = NULL` |
| Sensitive data | Phone, email, transcripts, recordings, KB files = PII/confidential | — |
| Encryption | TLS everywhere; at-rest DB + bucket encryption; integration secrets envelope-encrypted | 🟡 |
| Access | RBAC per Schema §7; signed, expiring URLs for recordings/files | 🟡 recordings served by filename |
| Input safety | Upload type/size limits, AV scan (ClamAV) for uploads, SSRF guard on URL ingest (exists: `_validate_public_http_url`) | 🟡 |
| Prompt injection | KB content and user input delimited; tools require server-side authorization; Copilot changes always via preview | ❌ |
| CORS | Explicit allow-list for dashboard; widget endpoints validate `Origin` against deployment | ❌ `*` + credentials |
| Rate limiting | Per IP (auth), per API key, per deployment (widget) | ❌ |
| Audit | Every config change, role change, activation, export, delete → `audit_logs` | ❌ table never written |
| Retention | Transcripts/recordings default 180 days, configurable per tenant; hard delete job; export on request (DPDP) | ❌ |
| Consent | Configurable recording disclosure line at call start; widget privacy notice | ❌ |
| Secrets | `.env` never committed; `.env.example` maintained; production secrets in Coolify/secret manager | 🟡 `.env.example` deleted in working tree |
| Dependency hygiene | `pip-audit`, `npm audit` in CI; pinned versions | ❌ several unpinned (`faiss-cpu`, `fastembed`, `grpcio`, `pymupdf`) |

## 8. Performance and reliability targets

| Metric | Target |
|---|---|
| Voice turn latency (user end-of-speech → first agent audio) | p50 ≤ 800 ms, p95 ≤ 1.5 s |
| Barge-in stop time | ≤ 300 ms |
| Chat first token | p50 ≤ 1.2 s, p95 ≤ 2.5 s |
| Dashboard API (CRUD) | p95 ≤ 300 ms |
| KB ingest 20-page PDF | ≤ 60 s to Available |
| Workflow step scheduling drift | ≤ 5 s |
| Webhook first attempt | ≤ 10 s after event |
| Uptime | API 99.5%, voice worker 99.5% monthly |
| Concurrency (v1) | 100 concurrent voice sessions, 1,000 concurrent chat sessions per region |
| Backups | Postgres PITR, daily snapshot, 30-day retention; RPO ≤ 15 min, RTO ≤ 4 h; restore drill quarterly |
| Observability | Structured JSON logs with `tenant_id`, `request_id`, `session_id`; OpenTelemetry traces (deps present); Sentry; metrics dashboard + alerts (error rate, latency, queue depth, LiveKit failures) |

## 9. Environments and delivery

| Env | Purpose | Data | Deploy |
|---|---|---|---|
| Local | Dev | seeded fixtures, docker-compose (Postgres, Redis) | `make dev` |
| Preview | Per-PR frontend | staging API | auto on PR |
| Staging | Pre-prod, E2E | anonymised | auto on merge to `main` |
| Production | Customers | real | manual promote of a staging build (same image digest) |

**CI (GitHub Actions)**: lint (ruff, eslint), type-check (mypy on `app/`, `tsc`), unit tests (pytest, vitest), OpenAPI → TS client generation drift check, Alembic migration check, container build, `pip-audit`/`npm audit`, Playwright E2E against staging.
**Containers**: separate images/processes for `api`, `voice-worker`, `jobs-worker`; one `Dockerfile` with targets or three process groups. Health checks per process.
**Rollback**: redeploy previous image digest; migrations must be backward-compatible (expand → migrate → contract).
**Current**: no repo for UI, no CI, manual Coolify deploy, Dockerfile runs only the API.

## 10. Key technical decisions and tradeoffs

| # | Decision | Reason | Alternative considered |
|---|---|---|---|
| D1 | Keep `app/` FastAPI, retire `backend_api.py` | Has tenancy, JWT, SQLAlchemy models, tests; Dockerfile already targets it; only ~13 routes to port (config ×2, campaigns ×7, recordings, integrations ×2, media file) | Keep legacy: faster short-term but JSON stores and fake auth are not production-safe |
| T1 | Postgres + pgvector instead of SQLite + FAISS files | One transactional store, tenant filters in SQL, horizontal scaling, backups | Qdrant/Pinecone: better at huge scale, extra service to run |
| T2 | Redis + arq job queue | Durable delays, retries, separate worker scaling | Celery (heavier, sync-first); Postgres `SKIP LOCKED` queue (fewer services, less throughput) |
| T3 | One `ConversationService` for all channels | Identical behaviour across chat/voice/widget/tests | Per-channel logic: faster first ship, divergence guaranteed |
| T4 | Gemini behind `LLMProvider` interface | Existing investment; Indian-language quality; keep option to add others | Multi-provider now: more work before value |
| T5 | Versions as immutable JSON snapshots | Easy diff, rollback, and reproducible tests | Row-per-field history: harder diffing |
| T6 | React Flow for canvas | Mature pan/zoom/minimap/connect, saves weeks | Custom SVG: full control, high cost |
| T7 | SSE for streaming | Works through proxies, simple clients | WebSockets: bidirectional, more infra |
| T8 | Browser voice via LiveKit room + same worker | Reuses barge-in, metrics, language logic | Direct Gemini Live from browser: exposes keys / needs ephemeral tokens, duplicates logic |
| T9 | Outbox table for domain events | Events not lost if worker is down | Fire-and-forget in request: current approach, loses events |
| T10 | OpenAPI-generated TS client | Removes hand-written shape mismatches (seen in workflows) | Hand-written: current source of bugs |
