# 6. Implementation Plan

Ordered build sequence. Each task lists **owner** (Owner = human decision/credentials, Agent = AI coding agent, Dev = human engineer review), **inputs**, **output**, **definition of done (DoD)**, and **dependency**. IDs are referenced across milestones.

**Rule between milestones:** run the app, verify that milestone's acceptance criteria from the PRD, and record unresolved issues in `docs/product/issues.md` before moving on.

Estimate: ~20–26 developer-weeks for one full-time engineer with an AI coding agent; milestones 3 and 4 have parallelisable tracks.

---

## Milestone 1 — Project setup (≈ 1.5 weeks)

Goal: one repo, one backend, reproducible environments, CI, nothing fake running silently.

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 1.0 | Resolve open questions D1, D5, D6, D8 | Owner | PRD §10 | Decisions recorded in PRD | All four answered | — |
| 1.1 | Monorepo: move the UI → `apps/web`, backend → `apps/api`, voice worker → `apps/voice`; init git at repo root (not home dir) | Agent | current folders | `ai-voice-agent/` repo with `apps/*`, root README | `git log` shows history; both apps start from root scripts | 1.0 |
| 1.2 | Pin Python 3.12 (`.python-version`, Docker base), `uv` lockfile; pin unpinned deps | Agent | requirements*.txt | `pyproject.toml` + `uv.lock` | Clean install in Docker and locally; `pip-audit` clean or waived | 1.1 |
| 1.3 | `docker-compose.dev.yml`: Postgres 16 + pgvector, Redis, MinIO | Agent | TRD §3 | compose file, `make dev` | `make dev` brings up API + web + deps on a fresh machine | 1.1 |
| 1.4 | Remove silent fallbacks: SQLite fallback only when `ENV=local`; embeddings fail → source `blocked` | Agent | `app/core/database.py`, `kb.py` | fail-fast config | Staging boot without DB exits non-zero with clear message | 1.3 |
| 1.5 | Settings module (pydantic-settings) with required `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `APP_BASE_URL`, `CORS_ORIGINS`; restore `.env.example` | Agent | `.env` keys | `app/core/settings.py`, `.env.example` | Missing required var → boot error naming it | 1.1 |
| 1.6 | Port remaining legacy routes into `app/`: config ×2, campaigns ×7, recordings, integrations ×2, media file; delete `backend_api.py`, `db_backend.py`, `db.py` shims after parity; retire `start_stack.py`/`supervisord.conf` or repoint | Agent | `backend_api.py` | routers in `app/routers` | UI works against `app/` with no 404s (Playwright smoke over every page) | 1.5 |
| 1.7 | Process model: Dockerfile targets `api`, `voice`, `worker`; Coolify doc updated; health checks each | Agent | Dockerfile, coolify.md | 3 runnable images/commands | Staging runs all three; `/health` + worker health green | 1.6 |
| 1.8 | CI (GitHub Actions): ruff, mypy (app/), pytest, eslint, tsc, vitest, build, audits | Agent | — | `.github/workflows/ci.yml` | Green on `main`; required for merge | 1.2 |
| 1.9 | Observability baseline: JSON logging with request/tenant ids, Sentry init (api, worker, voice, web), OTel traces | Agent | sentry dsn (Owner) | logging/tracing module | Test error appears in Sentry with tenant tag | 1.5 |
| 1.10 | Staging environment on Coolify + managed Postgres/Redis/storage | Owner + Agent | 1.7 | staging URL | Deploy from `main` automatic | 1.7 |
| 1.11 | Delete `scratch_*.py`, `fix_dispatch.py`, stray checks; move useful scripts to `apps/api/scripts` | Agent | — | clean tree | No scratch files at root | 1.1 |

**Progress (2026-09-25):** D1 confirmed (`app/`).
- ✅ 1.6 Legacy routes ported: config (Admin-only, secrets masked), campaigns ×7 on new `campaigns`/`campaign_leads` tables + DB-backed worker, recordings (no fake sample fallback), calendar sync (honest 501). `app/` no longer imports `backend_api`; `start_stack.py`, `supervisord.conf`, `ui_server.py` run `app.main:app`. Test asserts every UI endpoint exists in `app/`.
- ✅ Voice worker writes call logs with `tenant_id`, `direction`, `agent_id` into the app DB (`app/services/call_store.py`); inbound calls use `DEFAULT_TENANT_ID` or the only tenant. Campaign completion keyed by `campaign_lead_id`.
- ✅ 1.7 (partial) Dockerfile: Python 3.12, `/app`, supervisord running api + voice worker + KB worker, healthcheck; `.dockerignore` excludes `*.db`.
- ✅ 1.1 (reduced) the UI is in the repo under `web/`. Monorepo move deferred: moving `Inbound-Agent` would break its `.venv`.
- Fixed along the way: `CallLog(status=...)` crash after dispatch; campaign list always empty in UI (response shape); legacy campaign dispatch used display name as LiveKit agent name; CMS media upload path traversal + cross-tenant overwrite; client error messages now read FastAPI `detail`.
- ✅ 1.2 All dependencies pinned in one `requirements.txt` (added the missing `psycopg2-binary`, `email-validator`, SQLAlchemy/alembic/passlib/bcrypt; removed the conflicting PyJWT/python-multipart downgrades in `requirements_postgres.txt`; `onnxruntime` 1.24.1 → 1.24.4 because fastembed excludes 1.24.1). `requirements-dev.txt` adds ruff + pytest. `.python-version` = 3.12. Lockfile tool (uv) deferred — not installed.
- ✅ 1.3 `docker-compose.yml` → Postgres 16 + pgvector on a new volume (`postgres16_data`). Redis/MinIO added when first used (T2 / object storage).
- ✅ 1.4 No silent fallbacks outside `APP_ENV=local`: no SQLite fallback; KB ingestion raises `EmbeddingUnavailableError` instead of hashed vectors; live KB search degrades to keyword (BM25) with an error log.
- ✅ 1.5 `app/core/settings.py` (pydantic-settings, loads `.env` — previously `.env` was only read as an import side effect, after `DATABASE_URL`); explicit `CORS_ORIGINS` (no `*`); `.env.example` restored with the new section.
- ✅ 1.8 GitHub Actions: backend (ruff errors-only, unittest discovery, pip-audit report-only, Docker build) and web (build gate, lint report-only — 142 existing errors).
- ✅ 1.9 (partial) Sentry for the API when `SENTRY_DSN` is set, PII off. Voice/KB workers and structured logging still to do.
- ✅ Verified: 20/20 tests on SQLite and on Postgres 16 (pgvector image).
- ⏳ Not yet: delete `backend_api.py` (has uncommitted local edits — owner to review), migrate legacy campaigns/leads (2.8), 1.10 staging (needs owner's Coolify + managed Postgres).

**Checkpoint M1:** fresh clone → `make dev` → dashboard loads with real login against `app/`; CI green; staging deployed.

---

## Milestone 2 — Data and auth (≈ 3 weeks)

Goal: production-safe tenancy, schema per `05-backend-schema.md`, migrations, permissions, tests.

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 2.1 | **Hotfix: signup ignores client `tenant_id`/`role`**; remove hardcoded JWT secret default | Agent | `app/routers/auth.py`, `security.py` | patched endpoints | Test: signup with foreign `tenant_id` creates a new tenant, role owner | — (do first) |
| 2.2 | Alembic init + baseline migration from current models | Agent | `app/models` | `migrations/` | `alembic upgrade head` on empty DB = current schema | 1.3 |
| 2.3 | Identity schema: tenants, users, memberships, invitations, auth_sessions, auth_tokens, api_keys | Agent | Schema §2 | models + migration | Migration up/down passes | 2.2 |
| 2.4 | Auth flows: signup, verify, login (rate-limited), refresh rotation via httpOnly cookie, logout, reset, invite, switch tenant | Agent | Schema §5, email provider (D4) | `auth` router + service | pytest covers each flow incl. refresh reuse detection | 2.3 |
| 2.5 | RBAC: `require(permission)` dependency from matrix; replace `RoleChecker` | Agent | Schema §6 | `app/core/permissions.py` | Table-driven test: every route × role → expected status | 2.4 |
| 2.6 | Tenant isolation: non-null `tenant_id` FKs, repository base class auto-filter, Postgres RLS | Agent | all models | migration + base repo | Isolation test suite (extend existing `qa_agent_test.py`) passes for every router | 2.5 |
| 2.7 | Core product schema: agents, agent_versions, agent_changes, lifecycle events, integrations, kb_*, workflows, runs/steps, scheduled_jobs, conversations, messages, leads + field defs, deployments, webhooks, deliveries, domain_events, analytics_events, training, tests, audit additions | Agent | Schema §2 | models + migrations | Upgrade/downgrade clean; ERD generated into docs | 2.6 |
| 2.8 | Data migration scripts from JSON stores, Supabase, SQLite KB, recordings | Agent | Schema §9 | `scripts/migrate_*.py` | Dry-run report on copy of current data; idempotent re-run | 2.7 |
| 2.9 | Audit helper + wiring on all mutating admin actions | Agent | — | `audit.record()` | Every write endpoint in RBAC test produces an audit row | 2.5 |
| 2.10 | Integration secrets encryption (envelope) | Agent | master key (Owner) | `app/core/crypto.py` | Secrets never returned by API (test) | 2.7 |
| 2.11 | OpenAPI → TS client generation (`openapi-typescript` + typed fetch) | Agent | FastAPI schema | `apps/web/src/api/generated` | CI fails on drift | 1.8 |
| 2.12 | Web: real login/signup/invite/reset screens, remove dev auto-login, TanStack Query, error normalisation (`detail`) | Agent | 2.4, 2.11 | updated `App.tsx`, `api/client.ts` | Logged-out user redirected to `/login`; 401 → refresh → retry works | 2.11 |
| 2.13 | Team & Settings pages wired (members, invites, roles, profile, theme pref) | Agent | 2.4 | real pages | No static arrays remain in Team/Settings | 2.12 |

**Progress (2026-09-25):**
- ✅ 2.1 Signup hotfix (earlier).
- ✅ 2.2 Alembic: `alembic.ini`, `migrations/` (0001 baseline of 17 tables, 0002 identity, 0003 Owner role data migration). `app/core/migrate.py` runs on startup, replacing `create_all()`; databases created by the old `create_all()` are adopted at the baseline automatically (verified on a copy of the local `avnagent.db`).
- ✅ 2.3 Identity tables: `auth_sessions`, `auth_tokens`, `invitations`; `users.email_verified_at`; `audit_logs.ip/user_agent`. **Deviation from schema doc:** still one tenant per user (`users.tenant_id`, `users.role`) instead of `memberships`; multi-workspace users deferred until needed.
- ✅ 2.4 Auth flows: sessions with rotating opaque refresh token in an httpOnly cookie (path `/api/auth`), replay detection revokes all sessions, access tokens bound to a live session (logout/revocation immediate), login rate limit (10 failures / 15 min per IP+email, in-process), email verification, forgot/reset password (always 202; resets end all sessions), invitations (preview, accept, revoke; 7-day single-use links). Mailer: Resend when `RESEND_API_KEY` + `EMAIL_FROM`; local logs emails; elsewhere reports `not_configured`.
- ✅ 2.5 Roles Owner > Admin > Manager > Agent > Viewer; `RoleChecker` uses the minimum listed role; Viewer is read-only on every route (global rule). Role/status changes revoke the member's sessions.
- ✅ 2.9 (partial) Audit: signup, login, failed login, logout, verification, password reset request/complete, invitations, member changes, config changes. Other entities follow with their features.
- ✅ 2.12 Web: login/signup rebuilt on a shared auth layout; forgot/reset password, accept invite, verify email pages; cookie refresh with single-flight; user menu with sign-out; unverified-email banner; client-side role switcher removed.
- ✅ 2.13 (partial) Team page on real data (members, invitations with copyable link, edit role/status, permissions that mirror server rules). Settings page still static.
- ✅ Verified: 33/33 tests on SQLite and Postgres 16; full flow through the Vite proxy.
- ✅ 2.6 Tenant integrity: every tenant table has `tenant_id NOT NULL` + FK to `tenants` (audit logs: nullable, SET NULL). Migration 0004 repairs rows first (inherit from parent row; otherwise the single tenant or a new "Unassigned data (migrated)" tenant; nothing deleted). Constraint naming convention added. Writers without a resolvable tenant (inbound call logs/metrics) now log an error and skip instead of storing ownerless rows.
- ✅ 2.6 Postgres row-level security (migration 0005) on 14 tenant data tables; each authenticated request's transactions are tagged with `app.tenant_id` (`app/core/tenancy.py`). Requires a non-superuser DB role; startup warns otherwise. Dev compose creates `avn_app`. Verified with a regular role: unfiltered queries see only own tenant, cross-tenant writes rejected.
- ✅ 2.10 Credentials in `data/config.json` encrypted at rest (Fernet, `SECRETS_ENCRYPTION_KEY`); plain text allowed only when `APP_ENV=local`; `python -m scripts.encrypt_config` converts an existing file. (Per-tenant `integrations` table comes with 2.7.)
- ✅ 2.11 `python -m scripts.export_openapi` writes the app/ schema to `openapi.json` (CI fails if stale); UI `npm run gen:api` generates `src/api/generated/schema.d.ts`; team/session clients use generated types (already caught Owner being assignable in the Team forms).
- ✅ Verified: 40 tests (37 + 3 RLS on Postgres) on SQLite and Postgres; migrations 0001→0005 applied to a copy of the local `avnagent.db`.
- ✅ 2.7 (part 1) + 3.1 + 3.7 (basic UI) Agent versioning: `agents` (identity) + `agent_versions` (validated config snapshot, `AgentConfig` schema) + `agent_changes` (who/when/why + field diff) + `agent_lifecycle_events`; migration 0006 moves each existing agent's voice/model into v1 **production** (behaviour unchanged) and adds RLS to the new tables. Lifecycle draft → testing → evaluation → approved → production, reject, rollback to a previously-live version, discard draft, disable/enable; roles: Manager edits/submits/evaluates, Admin approves/activates/rolls back. Existing `/api/agents` fields now persist (previously instructions, greeting, language, hours, fallback phone were silently dropped) and write to the draft. Agents page: lifecycle + live/draft version on cards, Versions panel (actions, compare with production, change log); **Deploy now pushes only the production version** (it used to push unpublished edits).
- ✅ Verified: 49 tests on SQLite and Postgres (regular role, RLS active); 0006 downgrade/upgrade round trip; local data copy migrates both agents to v1 production with their voices.
- ⏳ Not yet: 2.7 rest (KB in Postgres/pgvector, conversations/messages, deployments, webhooks, training/tests, `integrations`), 2.8 legacy data import, Settings page. Activation is not yet gated by regression tests (3.14).

**Checkpoint M2:** PRD US1, US2 acceptance criteria pass; isolation + RBAC suites green; migration of current data rehearsed on staging.

---

## Milestone 3 — Core user journey (≈ 8–10 weeks)

Goal: create → configure → knowledge → workflow → test (text + voice) → version → activate → deploy website → lead in CRM. Tracks A/B can run in parallel after 3.3.

### Track 0 — Design system (unblocks all UI)

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 3.0a | Token layer: CSS variables per UI brief §3, Light/Dark/System with no-flash script, Noto Indic/Arabic fonts | Agent | UI brief | `tokens.css`, theme provider | Toggle switches all shell + components; System follows OS | 2.12 |
| 3.0b | Tokenise shared components; add Tabs, Drawer, Tooltip, StatusPill, DiffView, StepTimeline, ChatThread, DataTable, CodeBlock, Empty/NotConfigured/Error states (Radix primitives) | Agent | UI brief §5 | `components/ui/*` | Storybook (or Ladle) pages in both themes; axe clean | 3.0a |
| 3.0c | ESLint rule banning hex literals in `.tsx`; migrate existing pages incrementally (tracked list) | Agent | — | lint rule | New code can't add hex; migration checklist in issues.md | 3.0b |

### Track A — Agent core

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 3.1 | Agent service: create (from template), draft editing via JSON Patch + reason → `agent_changes`, version numbering, lifecycle transitions with guards | Agent | Schema agents | `/api/agents/*` v2 | Unit tests for every transition; production immutable | 2.7 |
| 3.2 | Studio shell: `/agents/:id/*`, left nav (13 sections), Copilot slot, bottom timeline slot, draft/production banner | Agent | App Flow §2 | `pages/studio/*` | Deep links work; mobile layout per brief | 3.0b, 3.1 |
| 3.3 | Studio sections Overview, Instructions, Languages, Voice (real Gemini TTS preview), Tools | Agent | existing Agents wizard fields | sections | Edits create changes on draft; voice preview plays real audio or shows not-configured | 3.2 |
| 3.4 | Per-agent runtime: dispatch metadata `agent_id`/`version_id`; voice worker loads version config from API; phone_numbers → agent mapping; remove global `config.json` writes from "Deploy" | Agent | `agent_backend.py`, LiveKit dispatch | updated worker | Two agents on two numbers answer with their own greeting (manual test log) | 3.1 |
| 3.5 | `ConversationService` (language detect → workflow step → KB → Gemini stream → persist messages/steps → analytics event) behind `LLMProvider` | Agent | TRD §6 | `app/services/conversation/*` | Unit tests with fake provider; integration test with real Gemini in staging | 3.1 |
| 3.6 | Test Center › Text + Live Tester UI (streaming, step timeline, I/O, ms) | Agent | 3.5 | page | PRD US8 AC passes | 3.5, 3.0b |
| 3.7 | Versions page: list, diff (DiffView), submit for testing, approve, activate (gate hook), rollback, discard | Agent | 3.1 | page + endpoints | PRD US11/US12 AC pass (gate stubbed until 3.14) | 3.1 |

### Track B — Knowledge

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 3.8 | KB storage to Postgres/pgvector + object storage; multilingual embedding model; hybrid search (vector + tsvector) with tenant + agent filters | Agent | `kb.py` | `app/services/kb/*` | Retrieval eval: 30 Te/Hi questions over English docs, recall@5 ≥ 0.8 | 2.7 |
| 3.9 | Ingest pipeline as worker jobs with stages; add DOCX, TXT, CSV, FAQ, manual; language detection per doc; re-index; enable/disable | Agent | 3.8 | worker tasks | Each type ingests to Available in staging; failures show reason | 3.8 |
| 3.10 | Knowledge UI (tenant library + Studio assignment), preview, retrieval test | Agent | 3.9 | pages | PRD US5/US5b AC pass | 3.9, 3.2 |

### Track C — Workflows

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 3.11 | Shared node/trigger schema (JSON Schema → pydantic + TS); graph validator | Agent | Schema workflows | `packages/workflow-schema` | Same fixtures validate identically in py + ts tests | 2.7 |
| 3.12 | Executor: conversation mode (per turn inside ConversationService) and automation mode (outbox → worker); Condition/Filter/Loop; Delay via scheduled_jobs; real ai_call; run steps persisted | Agent | 3.11, 3.5 | `app/services/workflows/*` | Tests: branching, delay resume after worker restart, failure marks step FAILED | 3.11 |
| 3.13 | Editor on `@xyflow/react`: palette with search, drag, connect, edit, delete, duplicate, zoom/pan/fit, minimap, undo/redo, shortcuts, validation panel, node config forms per type; node-aware right panel with "Run Test" | Agent | 3.11 | `features/workflow-editor` | Keyboard-only build of sample flow works; PRD US6 AC | 3.0b, 3.11 |
| 3.13b | Replace current `/workflows` page with automation workflows on the same editor; migrate existing workflows; runs history from `workflow_runs` | Agent | 2.8, 3.13 | updated page | No `Math.random`/hardcoded stats remain | 3.13 |

### Track D — Quality gate, voice, deploy

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 3.14 | Training dataset CRUD/import/export; test cases; test runner (exact/contains/regex/llm_judge/workflow_path/kb_source); regression on submit; activation gate | Agent | 3.5, 3.12 | Training + Test Center Regression/Workflow/Knowledge/Multilingual tabs | PRD US10/US11 AC; mandatory En/Te/Hi + mixed + Arabic RTL suites seeded | 3.6, 3.7 |
| 3.15 | Browser Voice Test: LiveKit token endpoint, room join, worker data-channel status events, transcript/language/node/latency, barge-in | Agent | 3.4 | Test Center › Voice | PRD US9 AC measured (stop ≤ 300 ms) on staging | 3.4 |
| 3.16 | Deployments + public chat API `/api/v1/agents/{id}/chat` (JSON + SSE), API keys UI, widget session endpoint with origin check, rate limits | Agent | 3.5, 2.3 | endpoints + Settings › API keys | PRD US13/US14 AC; keys never logged | 3.5 |
| 3.17 | `widget.js`: chat, voice, language select/auto, lead capture (custom fields) → CRM lead, handoff, branding/position/theme, business hours; install verification | Agent | 3.16, 3.15 | `apps/widget` build to CDN | PRD US16 AC on a test site | 3.16 |
| 3.18 | Deploy › Website configurator with live preview + snippet from `APP_BASE_URL` | Agent | 3.17 | Studio section | Snippet works on staging test page | 3.17 |
| 3.19 | CRM: custom lead fields, lead source/agent linkage, conversation link on lead | Agent | 2.8 | CRM updates | eWings fields render via definitions; no hardcoded MBBS logic in scorer (move to tenant prompt) | 2.8 |

**Progress 3.8–3.10 (2026-09-25):**
- ✅ Knowledge base moved into the application database (migration 0007: `kb_sources`, `kb_documents`, `kb_chunks`, `kb_ingest_jobs`; tenant FK + RLS; Postgres uses pgvector `vector(768)` with an HNSW index and a GIN keyword index). Local runs use SQLite with an in-memory index. The old `data/kb/kb.sqlite3` was empty, so nothing needed migrating. pgvector must be enabled once by a DB admin (`CREATE EXTENSION vector`); the dev compose init script does it.
- ✅ Multilingual retrieval: default embeddings `gemini-embedding-001` @768 (the old English-only `bge-small-en` default is upgraded automatically). Script-aware keyword tokenizer (Telugu/Hindi words were previously dropped entirely, so non-English questions never reached the KB). Evaluation `scripts/kb_multilingual_eval.py`: recall@1 15/15 for Te/Hi/En/code-mixed questions over English facts; relevant similarity ≥ 0.668, unrelated ≤ 0.560 → `KB_MIN_DENSE_SIMILARITY=0.62`.
- ✅ Each chunk records its embedding model; vectors from different models are never compared; `POST /api/kb/reindex` re-embeds stale chunks.
- ✅ Security/reliability fixes: voice agent searched every tenant's KB (now bound to the call's tenant; searches without a tenant return nothing); `/api/kb/jobs` and status were not tenant-scoped; failed jobs retried forever (now 3 attempts with backoff); API and worker could process the same job (atomic claim); uploads restricted to PDF/TXT/MD with a real PDF check.
- ✅ New source type "text" (paste FAQs/policies); KB page shows embedding-provider problems and a Re-index button.
- ✅ Verified: 62 tests on SQLite and Postgres (pgvector + RLS, regular role); real Gemini end-to-end ingest + Telugu/Hindi search on a throwaway DB.
- ⏳ Watch: chunks mixing several topics lower similarity (a mixed fees+hostel chunk scored 0.632 for a Hindi hostel question). Re-run the evaluation on real customer documents; consider smaller chunks. DOCX/CSV ingest, per-agent source assignment in the UI, and PDF OCR are still to do.

**Checkpoint M3:** full primary journey in App Flow §3 executed manually on staging and recorded; PRD P0 ACs for US3–US14, US16 pass.

---

## Milestone 4 — Secondary features (≈ 4–5 weeks)

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 4.1 | Copilot: threads, streaming, stop/retry/copy, context payload, tools (propose_change → change_proposals with Apply/Reject; run_test; explain_failure; show_last_failed_run; kb_test) | Agent | 3.x | right panel + `/api/copilot` | "Add Telugu support" produces preview; Apply creates draft change with reason; Reject changes nothing | M3 |
| 4.2 | Webhooks: endpoints UI, HMAC signing, outbox dispatcher, retries with backoff, delivery logs, test event | Agent | 2.7 | Settings › Webhooks | PRD US15 AC | M3 |
| 4.3 | Analytics: events from all channels, daily rollups, tenant + agent dashboards (sessions by channel, leads, conversions, languages, response time, call duration, workflow completion, handoffs); replace hardcoded Overview/Analytics numbers | Agent | analytics_events | pages | Every number traceable to a query; empty states when no data | M3 |
| 4.4 | Avatar: provider adapter (D2), Avatar tab, Avatar Dashboard, Avatar Test, widget avatar toggle | Agent + Owner (account) | D2 | feature | Real video session on staging; without credentials shows "Avatar provider not configured" | D2, 3.15 |
| 4.5 | WhatsApp + email actions via providers (D3, D4), templates, consent checks | Agent + Owner | D3, D4 | integrations | Real message delivered in staging; not-configured state otherwise | D3, D4 |
| 4.6 | Live Calls page wired to LiveKit rooms / active conversations | Agent | 3.4 | page | Shows real active sessions; empty state otherwise | 3.4 |
| 4.7 | Billing: plans, usage metering, Stripe/Razorpay checkout, quota enforcement | Agent + Owner | D9 | Billing page + jobs | Usage matches conversation/call totals; quota blocks with message | M3 |
| 4.8 | Testing Agent: scheduled/manual job running all suites incl. API, streaming, webhooks, widget (headless); failure clustering; proposes training examples + draft version (never activates) | Agent | 3.14, 4.1 | worker + UI | Seeded failure → proposal created → regression rerun shows fix | 3.14 |
| 4.9 | Onboarding wizard + setup checklist + templates catalogue | Agent | App Flow §8 | pages | New signup reaches first text test in ≤ 15 min (timed run) | M3 |
| 4.10 | Retention jobs + DPDP export/erase tools | Agent | Schema §8 | worker jobs + admin UI | Test tenant data purged per policy in staging | 2.7 |

**Checkpoint M4:** PRD P1 features demonstrable; no remaining static-data pages (grep for mock arrays / `Math.random` returns none in `pages/`).

---

## Milestone 5 — Quality (≈ 2–3 weeks, overlapping M4)

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 5.1 | Error handling pass: every API error typed; UI shows cause + next step; retries idempotent (idempotency keys on POSTs that create) | Agent | — | — | Chaos test (kill worker, DB blip) shows recoverable UI states | M4 |
| 5.2 | Accessibility: axe in CI, keyboard canvas, labels, contrast script for tokens, reduced motion, 40 px touch targets | Agent | UI brief §8 | — | axe zero serious issues on all routes, both themes | 3.0c |
| 5.3 | Security: threat model, dependency audit, OWASP ASVS L2 checklist, prompt-injection tests on KB + Copilot tools, SSRF tests, upload scanning, CORS lock-down, secrets scan (gitleaks) | Agent + Dev | TRD §7 | report | No high findings open; external pentest scheduled | M4 |
| 5.4 | Performance: load test chat API (k6) and voice (LiveKit load tester) to TRD targets; DB indexes/EXPLAIN review; frontend bundle budget (code-split Studio, canvas) | Agent | TRD §8 | report | Targets met or issues logged with plan | M4 |
| 5.5 | Multilingual QA: human review of 100 conversations across En/Te/Hi/mixed/Arabic; font rendering; RTL | Owner + Agent | 3.14 | review sheet | ≥ 90% correct-language, correct-answer | M4 |
| 5.6 | E2E Playwright suite implementing the PRD critical scenario (create → … → verify analytics) against staging, nightly | Agent | spec §26 | `apps/e2e` | Green 5 nights in a row | M4 |
| 5.7 | Docs: user guide per Studio section, API reference (from OpenAPI), widget guide, runbooks | Agent | — | docs site | Reviewed by Owner | M4 |

**Checkpoint M5:** all P0 + P1 acceptance criteria pass in automated suites; security and performance reports signed off.

---

## Milestone 6 — Release (≈ 1 week)

| ID | Task | Owner | Inputs | Output | DoD | Dep |
|---|---|---|---|---|---|---|
| 6.1 | Production infra: region per D6, managed Postgres with PITR, Redis, storage, CDN for web + widget, DNS/TLS for app/api/cdn domains | Owner + Agent | D5, D6 | prod env | Health checks green; backups verified by restore drill | M5 |
| 6.2 | Monitoring & alerting: dashboards (latency, errors, queue depth, LiveKit failures, Gemini errors, webhook failures), on-call alerts, status page | Agent | 1.9 | dashboards + alerts | Synthetic failure pages on-call | 6.1 |
| 6.3 | Production data migration (2.8) with rehearsal, freeze window, verification queries | Agent + Owner | 2.8 | migrated prod | Row counts/checksums match; eWings agent answers calls on new stack | 6.1 |
| 6.4 | Release process: image promotion by digest, feature flags for Avatar/Copilot/Testing Agent, backward-compatible migrations | Agent | 1.8 | runbook | Dry-run promote + rollback on staging | 6.1 |
| 6.5 | Rollback plan: previous image redeploy ≤ 10 min; DB restore procedure; agent-level rollback via Versions | Agent | 6.4 | runbook | Rollback drill executed and timed | 6.4 |
| 6.6 | Launch checklist: legal (privacy policy, DPA, recording consent copy), support channel, pricing page | Owner | — | checklist | All items ticked | 6.1 |
| 6.7 | Post-launch: 2-week hypercare, daily review of errors/latency/regressions, PRD success metrics dashboard | Owner + Agent | 4.3 | dashboard | Metrics visible; issues triaged daily | 6.6 |

---

## Quick wins (can start today, no decision needed)

1. ✅ **2.1 signup security hotfix** (2026-09-25): signup ignores client `tenant_id`/`role`, password ≥ 10; refresh tokens rejected as access tokens; `SECRET_KEY` required outside `APP_ENV=local` (Docker defaults to production); admin seed only via `SEED_ADMIN_*` or local; tenantless admins backfilled. Tests: `app/tests/test_auth_security.py`.
2. ✅ Workflow builder visible bugs (2026-09-25): node icons render, canvas fits to nodes, no fake statuses, all 5 triggers shown, adding a trigger replaces the existing one.
3. ✅ Dev auto-login limited to dev builds (`VITE_DEV_AUTO_LOGIN=false` to test real login).
4. ✅ Text contrast (2026-09-25): `--color-text-muted` → `#7C849A` dark / `#6B7080` light; 258 text usages of `#4B5675` now use the token. Decorative icon usages remain for 3.0c.
5. ⏳ Switch KB embedding default to a multilingual model — needs re-indexing of existing sources; do with 3.8.
6. ⏳ Test isolation: `app/tests/qa_agent_test.py` wipes users/tenants/KB of whatever DB it points at. Always run with a throwaway `DATABASE_URL` and `KB_DATA_DIR` (now honoured for SQLite URLs).

## Dependency overview

```
M1 setup ─► M2 data/auth ─► 3.0 design system ─┬─► Track A agent core ─┬─► 3.14 quality gate ─► M4 ─► M5 ─► M6
                                               ├─► Track B knowledge ──┤
                                               └─► Track C workflows ──┘
                                     3.4 per-agent runtime ─► 3.15 voice test ─► 3.17 widget ─► 4.4 avatar
```
