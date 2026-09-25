# aVn Product Documents

Six documents that together define what aVn must become and how to build it. Each one marks the current state of the codebase so the gap is explicit.

| # | Document | Answers |
|---|---|---|
| 1 | [PRD](01-prd.md) | What the product does, for whom, and how success is measured |
| 2 | [TRD](02-trd.md) | Stack, architecture, security, performance, environments |
| 3 | [App Flow](03-app-flow.md) | Every screen, journey, and action state |
| 4 | [UI/UX Brief](04-ui-ux-brief.md) | Visual system, components, accessibility |
| 5 | [Backend Schema](05-backend-schema.md) | Tables, relationships, ownership, authorization |
| 6 | [Implementation Plan](06-implementation-plan.md) | Ordered milestones with tasks and definitions of done |

Status legend used throughout: **✅ Present** (works, keep) · **🟡 Partial** (exists but incomplete, fake, or wrong) · **❌ Missing**.

Baseline audited: 2026-09-25, `Inbound-Agent` (backend + voice worker) and `web/` (dashboard).

## Present vs. missing at a glance

| Capability | Status | Evidence |
|---|---|---|
| Phone voice agent (inbound/outbound, SIP transfer, voicemail) | ✅ | `agent.py`, `agent_backend.py`, `outbound_calls.py`, Vobiz SIP |
| Gemini Live voice, Hindi/Telugu/multilingual presets | ✅ | `agent_backend.py` `LANG_PRESET`, `get_language_instruction` |
| Per-turn latency metrics (STT/KB/LLM/TTS) | ✅ | `call_turn_metrics` |
| Knowledge ingest: PDF, URL, sitemap; hybrid FAISS + BM25 search | ✅ | `kb.py`, `kb_worker.py` |
| Cross-lingual retrieval (Telugu question → English doc) | ❌ | Default embedding model `BAAI/bge-small-en-v1.5` is English-only |
| Calendar booking during calls | 🟡 | `calendar_tools.py` books into the internal appointments table only; no Google/Zoho integration (UI "Connect" was a mock) |
| CRM leads, timeline, AI lead scoring | 🟡 | Works, but lead fields are hardcoded for one customer (NEET score, MBBS budget) |
| Campaigns (bulk outbound) | 🟡 | Only in legacy `backend_api.py` + `campaign_worker.py` |
| Appointments | ✅ | `app/routers/appointments.py` |
| CMS (pages, prompts, FAQs, media) | ✅ | `app/routers/cms.py` |
| Multi-tenant auth (JWT, roles Admin/Manager/Agent) | 🟡 | `app/` has it; UI bypasses it with a hardcoded dev token |
| Workflow automation | 🟡 | Linear engine, broken builder, vocabulary mismatches |
| Two parallel backends | 🟡 | `backend_api.py` (run locally) vs `app/main.py` (run by Dockerfile) |
| Light / Dark / System theme | 🟡 | Light overrides exist; pages hardcode ~80–120 hex colours each; no System |
| Billing, Team, Live Calls, Settings pages | 🟡 | UI only, zero API calls, static data |
| Agent versions, lifecycle, per-agent runtime | ❌ | "Deploy" overwrites one global `config.json` |
| Agent Studio workspace + Copilot | ❌ | — |
| Text chat / public chat API / streaming | ❌ | — |
| Browser voice test, avatar | ❌ | — |
| Training datasets, Test Center, regression, Testing Agent | ❌ | 4 backend unit tests only |
| Website widget, deployments, API keys, webhooks | ❌ | — |
| Real analytics across channels | 🟡 | Call analytics only; several dashboard numbers hardcoded |
| CI/CD, migrations, staging, monitoring | ❌ | `create_all` on boot, no Alembic, no CI, Sentry SDK installed but unused |

## Contradictions found (resolve before building)

1. **Which backend is production?** `start_stack.py` / `supervisord.conf` run `backend_api:app`; `Dockerfile` runs `app.main:app`. → Proposed: `app/` (see TRD §10, D1).
2. **Deployment doc vs. Dockerfile.** `docs/deployment/coolify.md` says the container runs three processes (API, LiveKit worker, KB worker); the `Dockerfile` starts only uvicorn. The voice worker and KB worker are not running in the documented production deploy.
3. **"Backend-only repo."** `docs/README.md` says there is no bundled dashboard; the dashboard (`web/`) exists and is the product UI.
4. **Two colour palettes.** Tokens in `index.css` use primary `#6D5DFE`, success `#22C55E`, danger `#EF4444`; pages hardcode `#7B61FF`, `#22D3A5`, `#FF4D6A`.
5. **"No fake data" requirement vs. current UI.** Workflow stats, run history (`Math.random`), seeded notifications, voice preview toast, Billing/Team/Settings/Live Calls are static.
6. **Silent degradation.** Postgres unreachable → silent SQLite fallback; embedding provider unavailable → hashed pseudo-embeddings. Both violate "show the correct configuration state".
7. **Python version.** Local venv is 3.14; Docker image is 3.11.
8. **Vertical-specific data model in a multi-tenant SaaS.** `leads` has `neet_score`, `rank`, `country_preference`, `parent_involved`; the lead scorer hardcodes MBBS logic.
9. **Single agent runtime vs. multi-agent product.** Every agent shares one runtime config; the spec requires one agent deployable independently across channels.

## Decisions the owner must make

Listed in full in [PRD §10](01-prd.md#10-open-questions). Blocking ones: backend choice (D1), avatar provider, WhatsApp/email providers, production domain, data residency.
