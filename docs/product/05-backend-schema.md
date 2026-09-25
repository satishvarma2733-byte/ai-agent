# 5. Backend Schema

Target: PostgreSQL 16 + pgvector, SQLAlchemy 2 models in `app/models`, Alembic migrations. Conventions:

- `id UUID PK DEFAULT gen_random_uuid()` (current: `String(50)` UUID text — migrate to native UUID).
- `tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE` on every tenant-owned table, indexed, and leading every composite index (current: nullable, no FK).
- `created_at`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`; `deleted_at TIMESTAMPTZ NULL` where soft delete applies.
- Timestamps as `TIMESTAMPTZ`, never strings (current: `appointments.scheduled_start`, `users.joined`, `leads.follow_up_date`, `call_logs.call_date` are strings).
- Enums as Postgres `TEXT` + `CHECK` constraint (easier migrations than native enums).
- JSON as `JSONB` (current: `actions_json`, `metadata_json` are `TEXT`).
- Postgres Row-Level Security policy `tenant_id = current_setting('app.tenant_id')::uuid` on all tenant tables as defence in depth.

## 1. Entities

| Entity | Represents | Status |
|---|---|---|
| tenants | Customer organisation (workspace) | ✅ |
| users | Person who can sign in | ✅ (fix: one tenant per user via memberships) |
| memberships | User ↔ tenant with role | ❌ |
| invitations | Pending invite | ❌ |
| auth_sessions | Refresh-token sessions | ❌ |
| auth_tokens | Email verification / password reset tokens | ❌ |
| api_keys | Programmatic access | ❌ |
| integrations | Connected providers + encrypted credentials | ❌ (runtime `config.json`) |
| agents | Agent identity + lifecycle + production pointer | 🟡 flat stats row |
| agent_versions | Immutable config snapshot | ❌ |
| agent_changes | Change log entries | ❌ |
| agent_lifecycle_events | Lifecycle transitions | ❌ |
| kb_sources / kb_documents / kb_chunks / kb_ingest_jobs | Knowledge | 🟡 SQLite in `kb.py` + Supabase SQL v5; not in `app/` models |
| agent_knowledge | Agent ↔ KB source | ❌ |
| workflows | Conversation or automation graph | 🟡 linear actions JSON |
| workflow_runs / workflow_run_steps | Executions and per-node steps | 🟡 `workflow_logs` (one row per run, no steps) |
| scheduled_jobs | Durable delayed steps (if Redis unavailable, also the source of truth) | ❌ |
| conversations / messages | Sessions across all channels | 🟡 calls only (`call_logs.transcript` text) |
| call_logs / call_turn_metrics | Phone/voice session detail | ✅ |
| leads / lead_activities / lead_field_definitions | CRM | 🟡 hardcoded vertical fields |
| appointments | Bookings | ✅ (fix types) |
| campaigns / campaign_leads | Bulk outbound | 🟡 Supabase v9 + legacy only |
| phone_numbers | DIDs mapped to agents | ❌ |
| training_examples | Training dataset | ❌ |
| test_cases / test_runs / test_results | Evaluation | ❌ |
| deployments | Channel deployments (website, api, voice, avatar) | ❌ |
| webhooks / webhook_deliveries | Outbound events | ❌ |
| domain_events (outbox) | Reliable event bus | ❌ |
| analytics_events | Fact table for analytics | ❌ |
| copilot_threads / copilot_messages / change_proposals | Copilot history and previews | ❌ |
| usage_records / subscriptions | Billing | ❌ |
| audit_logs | Who changed what | 🟡 table exists, never written |
| cms_pages / cms_prompts / cms_faqs / cms_media | CMS | ✅ (fix: `cms_pages.slug` unique globally → unique per tenant; prompts/FAQs to feed agent versions/KB) |

## 2. Tables

Required = NOT NULL. Only non-obvious defaults listed. Indexes beyond PK.

### Identity & access

**tenants** — `name text req`, `slug text req unique`, `plan text req default 'free' check in (free,growth,enterprise)`, `status text req default 'active' check in (active,suspended,deleted)`, `region text req default 'ap-south-1'`, `settings jsonb req default '{}'` (retention days, default languages, recording disclosure), `data_retention_days int req default 180`.

**users** — `email citext req unique`, `password_hash text null` (null for OAuth-only), `name text req`, `phone text null`, `email_verified_at timestamptz null`, `mfa_secret_enc bytea null`, `theme text req default 'system' check in (light,dark,system)`, `locale text req default 'en'`, `last_seen_at timestamptz null`, `status text req default 'active'`.
Remove from users: `role`, `tenant_id` (→ memberships), `calls`, `success` (→ analytics).

**memberships** — `tenant_id`, `user_id FK users`, `role text req check in (owner,admin,builder,agent,viewer)`. Unique `(tenant_id, user_id)`.

**invitations** — `tenant_id`, `email citext req`, `role text req`, `token_hash text req unique`, `invited_by FK users`, `expires_at req` (7 days), `accepted_at null`. Index `(tenant_id, email)`.

**auth_sessions** — `user_id`, `tenant_id`, `refresh_token_hash text req unique`, `user_agent`, `ip inet`, `expires_at req` (30 days), `rotated_from uuid null`, `revoked_at null`. Index `(user_id)`.

**auth_tokens** — `user_id`, `purpose text check in (verify_email,reset_password)`, `token_hash unique`, `expires_at` (1 h reset / 48 h verify), `used_at null`.

**api_keys** — `tenant_id`, `name req`, `prefix text req unique` (e.g. `avn_live_ab12`), `key_hash text req`, `scopes text[] req`, `agent_id null FK` (optional restriction), `last_used_at null`, `expires_at null`, `revoked_at null`, `created_by FK users`.

**integrations** — `tenant_id`, `provider text req check in (gemini,livekit,vobiz,whatsapp_meta,email_resend,google_calendar,zoho_calendar,avatar_tavus,avatar_heygen,avatar_simli,telegram,...)`, `status text req default 'disconnected' check in (connected,disconnected,error)`, `config jsonb req default '{}'` (non-secret), `secrets_enc bytea null` (envelope-encrypted), `last_checked_at`, `last_error text`. Unique `(tenant_id, provider)`.

### Agents

**agents** — `tenant_id`, `name text req (2–60)`, `slug text req`, `description text`, `lifecycle text req default 'draft' check in (draft,testing,evaluation,approved,production,disabled)`, `production_version_id uuid null FK agent_versions`, `draft_version_id uuid null FK agent_versions`, `template_key text null`, `created_by FK users`, `deleted_at`. Unique `(tenant_id, slug)`. Index `(tenant_id, lifecycle)`.
Remove from agents: `calls_today`, `calls_total`, `avg_duration`, `success_rate`, `last_active`, `status` (→ analytics / lifecycle).

**agent_versions** — `tenant_id`, `agent_id FK`, `number int req`, `status text req check in (draft,testing,evaluation,approved,production,superseded,discarded)`, `config jsonb req` (schema below), `config_hash text req`, `based_on_version_id uuid null`, `created_by FK users`, `approved_by null`, `approved_at null`, `activated_at null`. Unique `(agent_id, number)`. Partial unique: one `status='draft'` per agent. Immutable once status ≠ draft (trigger enforces).

`config` JSON schema (validated with pydantic, versioned `schema_version`):
```json
{
  "schema_version": 1,
  "persona": {"name": "Aria", "instructions": "...", "guardrails": ["..."]},
  "greetings": {"en": "Hello! ...", "te": "నమస్కారం! ..."},
  "languages": {"supported": ["en","te"], "default": "en", "auto_detect": true, "code_mixing": true},
  "llm": {"provider": "gemini", "model": "gemini-2.5-flash", "temperature": 0.6},
  "voice": {"provider": "gemini", "voice": "Puck", "live_model": "...", "speaking_rate": 1.0, "interruption": {"enabled": true, "min_words": 1}},
  "avatar": {"enabled": false, "provider": null, "avatar_id": null, "background": null, "style": null},
  "knowledge": {"source_ids": ["uuid"], "top_k": 5, "threshold": 0.35},
  "tools": [{"key": "calendar.book", "enabled": true, "config": {}}],
  "workflow_id": "uuid|null",
  "training": {"example_ids": ["uuid"], "max_examples_in_prompt": 20},
  "limits": {"max_turns": 40, "max_call_seconds": 600},
  "hours": {"tz": "Asia/Kolkata", "days": ["Mon","Tue"], "start": "09:00", "end": "18:00", "after_hours": "message|voicemail|handoff"},
  "handoff": {"phone": "+91...", "queue": "sales"}
}
```

**agent_changes** — `tenant_id`, `agent_id`, `version_id FK`, `user_id null` (null = system/testing agent), `source text req check in (ui,copilot,testing_agent,api,import)`, `reason text req`, `patch jsonb req` (RFC 6902 JSON Patch), `before jsonb`, `after jsonb`. Index `(agent_id, created_at desc)`.

**agent_lifecycle_events** — `tenant_id`, `agent_id`, `version_id`, `from_status`, `to_status`, `user_id`, `note`, `test_run_id null`.

### Knowledge

**kb_sources** — `tenant_id`, `kind text req check in (pdf,docx,txt,csv,url,sitemap,faq,manual)`, `name req`, `uri text null` (URL or storage key), `language text null` (ISO 639-1, detected or set), `size_bytes bigint`, `status text req default 'queued' check in (queued,extracting,cleaning,chunking,embedding,indexing,available,failed,disabled,blocked)`, `status_reason text`, `enabled bool req default true`, `sync_schedule text null` (cron for URLs), `last_synced_at`, `checksum text`, `created_by`. Index `(tenant_id, status)`.

**kb_documents** — `tenant_id`, `source_id FK cascade`, `title`, `uri`, `language`, `content_hash`, `char_count int`, `metadata jsonb`.

**kb_chunks** — `tenant_id`, `document_id FK cascade`, `source_id FK cascade`, `ordinal int req`, `content text req`, `language text`, `token_count int`, `embedding vector(768) req` (multilingual model required — current default `BAAI/bge-small-en-v1.5`, 384-d, is English-only and cannot serve Telugu/Hindi queries over English docs; target `gemini-embedding-001` at 768-d or `multilingual-e5-base`), `tsv tsvector GENERATED` (BM25-ish keyword search), `metadata jsonb`. Index: HNSW on `embedding` (cosine), GIN on `tsv`, btree `(tenant_id, source_id)`.

**kb_ingest_jobs** — `tenant_id`, `source_id`, `stage text`, `status text`, `attempt int default 0`, `error text`, `started_at`, `finished_at`.

**agent_knowledge** — `tenant_id`, `agent_id`, `source_id`. PK `(agent_id, source_id)`. (Version config lists `source_ids` for reproducibility; this table serves queries "which agents use this source".)

### Workflows

**workflows** — `tenant_id`, `agent_id null FK` (null for tenant-level automation), `kind text req check in (conversation,automation)`, `name req`, `trigger text req` (automation: `lead.created`, `lead.updated`, `call.completed`, `call.missed`, `appointment.booked`, `webhook.received`, `schedule`; conversation: `conversation.started`), `trigger_config jsonb default '{}'`, `graph jsonb req` (`{nodes:[{id,type,position,data}], edges:[{id,source,sourceHandle,target,label}]}`), `graph_version int req default 1`, `is_active bool req default false`, `created_by`. Index `(tenant_id, kind, trigger) WHERE is_active`.
Node `type` enum (shared TS/Python schema): `trigger, message, condition, action, delay, ai_agent, knowledge, handoff, end, filter, loop` with `action.data.action ∈ {ai_call, send_whatsapp, send_email, update_lead, assign_lead, create_reminder, book_appointment, http_request}`.

**workflow_runs** — `tenant_id`, `workflow_id`, `workflow_graph_version int`, `agent_version_id null`, `trigger_event_id null FK domain_events`, `conversation_id null`, `lead_id null`, `mode text check in (live,test,dry_run)`, `status text check in (running,waiting,success,failed,cancelled)`, `started_at`, `finished_at`, `error text`. Index `(tenant_id, workflow_id, started_at desc)`.

**workflow_run_steps** — `tenant_id`, `run_id FK cascade`, `node_id text req`, `node_type text req`, `seq int req`, `status text check in (idle,running,success,failed,skipped)`, `input jsonb`, `output jsonb`, `error text`, `started_at`, `duration_ms int`. Index `(run_id, seq)`.

**scheduled_jobs** — `tenant_id`, `kind text` (workflow_resume, kb_sync, webhook_retry, campaign_dial, retention_purge), `payload jsonb`, `run_at timestamptz req`, `status text default 'pending'`, `attempts int default 0`, `locked_by`, `locked_at`, `last_error`. Index `(status, run_at)`.

### Conversations & calls

**conversations** — `tenant_id`, `agent_id`, `agent_version_id req`, `channel text req check in (phone,web_chat,web_voice,avatar,api,test)`, `deployment_id null`, `external_session_id text` (API `sessionId`), `lead_id null`, `language_detected text`, `status text check in (active,completed,handed_off,failed)`, `started_at`, `ended_at`, `summary text`, `sentiment text`, `call_log_id null FK` (phone). Unique `(tenant_id, agent_id, external_session_id)`. Index `(tenant_id, started_at desc)`.

**messages** — `tenant_id`, `conversation_id FK cascade`, `role text check in (user,assistant,system,tool)`, `content text`, `language text`, `tool_name text null`, `tool_payload jsonb null`, `latency_ms int null`, `tokens_in int`, `tokens_out int`, `kb_chunk_ids uuid[] null`, `workflow_node_id text null`. Index `(conversation_id, created_at)`.

**call_logs** (keep, adjust) — add `conversation_id FK`, `agent_version_id`, `recording_key` (storage key, not public URL); `call_date/hour/day_of_week` become derived from `started_at timestamptz`; `agent_id` → FK uuid.

**call_turn_metrics** (keep) — add FK `conversation_id`.

**phone_numbers** — `tenant_id`, `e164 text req unique`, `provider text` (vobiz), `agent_id null FK`, `direction text check in (inbound,outbound,both)`, `livekit_trunk_id`, `dispatch_rule_id`, `status`.

### CRM

**leads** — `tenant_id`, `name req`, `phone text req (E.164)`, `email citext`, `company`, `status text req default 'new'` (tenant-configurable pipeline later), `score text check in (hot,warm,cold)`, `score_explanation`, `owner_user_id null FK users`, `source text check in (phone,website,api,import,manual,campaign)`, `source_agent_id null`, `custom jsonb req default '{}'`, `follow_up_at timestamptz null`, `consent jsonb` (channel consents + timestamp), `deleted_at`. Unique `(tenant_id, phone) WHERE deleted_at IS NULL`. GIN on `custom`.
Migrate: `budget, state, neet_score, rank, parent_involved, country_preference, objection, session_booked` → `custom` + `lead_field_definitions` for the existing tenant.

**lead_field_definitions** — `tenant_id`, `key text req`, `label req`, `type check in (text,number,boolean,date,select)`, `options jsonb`, `required bool`, `capture_in_widget bool`, `ord int`. Unique `(tenant_id, key)`.

**lead_activities** (keep) — `metadata_json text` → `metadata jsonb`; add `actor_type (user,agent,system,workflow)`, `actor_id`.

**appointments** (keep, fix types) — `scheduled_start/end timestamptz`, add `lead_id FK`, `agent_id`, `conversation_id`, `external_calendar_event_id`.

**campaigns / campaign_leads** — port from Supabase v9: campaign(`agent_id`, `name`, `status`, `schedule jsonb`, `concurrency int`, `retry_policy jsonb`), campaign_leads(`campaign_id`, `lead_id`, `status`, `attempts`, `last_call_log_id`, `outcome`).

### Quality

**training_examples** — `tenant_id`, `agent_id`, `category text check in (instruction,example,good_response,bad_response,expected_response,scenario,objection,qualification,language)`, `input text req`, `expected_output text`, `bad_output text null`, `language text req`, `tags text[]`, `status text check in (draft,active,archived)`, `source text check in (manual,import,testing_agent,copilot,conversation)`, `source_conversation_id null`. Index `(agent_id, status)`; trigram index on `input` for search.

**test_cases** — `tenant_id`, `agent_id`, `suite text check in (text,voice,avatar,workflow,knowledge,multilingual,regression)`, `name req`, `input jsonb req` (text, audio storage key, or multi-turn script), `language text`, `expected jsonb req` (`{type: exact|contains|regex|llm_judge|workflow_path|kb_source, value, rubric}`), `critical bool default false`, `enabled bool default true`, `training_example_id null`.

**test_runs** — `tenant_id`, `agent_id`, `agent_version_id req`, `trigger text check in (manual,activation,schedule,testing_agent)`, `suites text[]`, `status check in (queued,running,passed,failed,error)`, `totals jsonb` (`passed, failed, changed, p50_ms, p95_ms`), `started_at`, `finished_at`, `triggered_by`.

**test_results** — `tenant_id`, `run_id FK cascade`, `test_case_id`, `status check in (pass,fail,error,skipped)`, `actual jsonb`, `score numeric`, `judge_reason text`, `latency_ms int`, `conversation_id null`, `changed_vs_production bool`.

### Deploy & integrate

**deployments** — `tenant_id`, `agent_id`, `channel text check in (website,chat_api,voice,avatar,api)`, `public_id text req unique` (e.g. `dep_7fK2...`, safe to expose), `allowed_origins text[]`, `config jsonb` (widget: position, size, theme, branding, welcome, avatar/voice/chat toggles, languages, business hours, lead fields), `status check in (active,paused)`, `verified_at` (snippet detected on domain).

**webhooks** — `tenant_id`, `url text req (https)`, `events text[] req` (`conversation.started, conversation.completed, lead.created, lead.updated, call.started, call.completed, workflow.started, workflow.completed, workflow.failed, agent.handoff`), `secret_enc bytea req`, `agent_id null`, `status check in (active,disabled)`, `failure_count int default 0`.

**webhook_deliveries** — `tenant_id`, `webhook_id`, `event_id FK domain_events`, `attempt int`, `status check in (pending,success,failed,giving_up)`, `request_body jsonb`, `response_status int`, `response_body text (truncated 4 KB)`, `duration_ms`, `next_attempt_at`. Index `(webhook_id, created_at desc)`.

**domain_events** (outbox) — `tenant_id`, `type text req`, `payload jsonb req`, `occurred_at req`, `processed_at null`. Index `(processed_at) WHERE processed_at IS NULL`.

**analytics_events** — `tenant_id`, `agent_id`, `agent_version_id`, `conversation_id`, `channel`, `type` (session_started, session_ended, lead_captured, conversion, handoff, workflow_completed, …), `language`, `value numeric`, `props jsonb`, `occurred_at`. Partition monthly by `occurred_at`; index `(tenant_id, occurred_at)`. Materialised daily rollups for dashboards.

### Copilot, billing, audit

**copilot_threads** (`tenant_id, user_id, agent_id, title`), **copilot_messages** (`thread_id, role, content, context jsonb, tool_calls jsonb, status`), **change_proposals** (`tenant_id, agent_id, version_id, thread_id, patch jsonb, before jsonb, after jsonb, status check in (pending,applied,rejected,expired), decided_by, decided_at`).

**subscriptions** (`tenant_id unique, plan, provider, external_id, status, current_period_end`), **usage_records** (`tenant_id, metric check in (voice_minutes,chat_messages,avatar_minutes,kb_pages,tests), quantity, period date`; unique `(tenant_id, metric, period)`).

**audit_logs** (keep) — add `ip`, `user_agent`, `before jsonb`, `after jsonb`; written by a service-layer helper on every mutating admin action.

## 3. Relationships

- tenants 1—N everything tenant-owned; users N—M tenants via memberships.
- agents 1—N agent_versions; agents → production_version_id / draft_version_id (1—1 pointers).
- agent_versions 1—N agent_changes; 1—N conversations; 1—N test_runs.
- agents N—M kb_sources via agent_knowledge; kb_sources 1—N kb_documents 1—N kb_chunks.
- agents 1—N workflows (conversation); tenant 1—N workflows (automation); workflows 1—N workflow_runs 1—N workflow_run_steps.
- conversations 1—N messages; conversations 0..1—1 call_logs; conversations N—1 leads.
- leads 1—N lead_activities, appointments, campaign_leads.
- agents 1—N training_examples, test_cases, deployments, phone_numbers.
- test_runs 1—N test_results N—1 test_cases.
- webhooks 1—N webhook_deliveries N—1 domain_events.

## 4. User ownership

All data belongs to a **tenant**, not to individual users. `created_by`/`owner_user_id` record authorship and assignment only. A user's personal data: profile, theme, auth sessions, copilot threads (private to the user, visible to tenant Owner for audit).

## 5. Authentication flow

1. **Sign up**: `POST /api/auth/signup {email, password, name, company}` → create tenant + user + membership(owner) in one transaction → send verification email → return 201 (no tokens until verified, or allow limited session — decision: allow session, block deploy/activation until verified).
2. **Sign in**: `POST /api/auth/login` → verify bcrypt → create `auth_sessions` row → access JWT (15 min, claims `sub`, `tid`, `role`, `sid`) in response body + refresh token in httpOnly cookie. Rate limit 5/min/IP+email; lockout 15 min after 10 failures.
3. **Refresh**: `POST /api/auth/refresh` (cookie) → rotate refresh token; reuse of a rotated token revokes the whole session family.
4. **Switch tenant**: `POST /api/auth/switch {tenant_id}` → new access token for that membership.
5. **Reset**: request (always 202) → email token (1 h) → set password → revoke all sessions.
6. **Invite**: Admin creates → email → accept sets password (new user) or links membership (existing user).
7. **Logout**: revoke session; clear cookie.
8. **API key**: `Authorization: Bearer avn_live_...` → lookup by prefix, constant-time hash compare, scope check.
9. **Widget**: `POST /api/v1/deployments/{public_id}/sessions` with `Origin` → validated against `allowed_origins` → returns 30-min session token scoped to that deployment.

## 6. Authorization rules

Roles: **Owner** ⊃ **Admin** ⊃ **Builder** ⊃ **Agent** ⊃ **Viewer**.

| Resource | Viewer | Agent (human) | Builder | Admin | Owner |
|---|---|---|---|---|---|
| Agents, versions (read) | R | R | R | R | R |
| Draft edit, training, tests, workflows | — | — | CRUD | CRUD | CRUD |
| Submit for testing / run regression | — | — | ✓ | ✓ | ✓ |
| Approve / Activate / Rollback / Disable | — | — | — | ✓ | ✓ |
| KB sources | R | R | CRUD | CRUD | CRUD |
| Deployments, API keys, webhooks | — | — | R | CRUD | CRUD |
| Integrations (secrets) | — | — | — | CRUD | CRUD |
| Leads, activities, appointments | R | CRUD (assigned or all per tenant setting) | CRUD | CRUD | CRUD |
| Delete leads / export data | — | — | — | ✓ | ✓ |
| Conversations, recordings | R (no recordings) | R | R | R | R |
| Team & invitations | — | — | — | CRUD (not owner) | CRUD |
| Billing, delete tenant, transfer ownership | — | — | — | R | CRUD |
| Audit log | — | — | — | R | R |

Public (API key / widget session): only `chat`, `sessions`, `leads:create` (widget lead capture), scoped to the key/deployment's agent.

## 7. Data validation

| Field | Rule |
|---|---|
| email | RFC 5322 basic, ≤ 254, lower-cased (citext) |
| password | ≥ 10 chars, not in breached list (k-anonymity check P1), ≤ 128 |
| phone | E.164 via `phonenumbers`; default region from tenant |
| agent name | 2–60, unique per tenant (case-insensitive) |
| greeting | ≤ 500 chars per language |
| instructions | ≤ 20,000 chars |
| language codes | ISO 639-1 from supported list (en, te, hi, ta, kn, ml, ar, es, fr, de, pt, ja, ko, zh) |
| KB upload | pdf/docx/txt/csv by magic bytes; ≤ 25 MB; ≤ 500 sources/tenant (plan-based) |
| URL sources | https/http public hosts only (existing SSRF validator), ≤ 2,000 pages per sitemap |
| workflow graph | exactly one trigger; ≤ 200 nodes; every node reachable; no cycles except via `loop`; condition nodes have ≥ 2 outgoing edges; required node config present |
| webhook URL | https only in production; no private IPs |
| allowed origins | scheme + host (+ port), no wildcards except `*.domain.tld` |
| version transitions | only along lifecycle graph; activation requires approved + no critical failures in latest run for that version |
| training example | input 1–4,000 chars; expected ≤ 4,000 |

## 8. Retention and deletion

| Data | Default retention | On deletion |
|---|---|---|
| Recordings | 90 days (tenant-configurable 0–730) | Storage object deleted by nightly job |
| Transcripts / messages | 180 days (configurable) | Hard delete; analytics keep aggregates without content |
| Leads | Until deleted; soft delete 30 days then purge | Cascades activities; conversations unlinked |
| KB files | Until source removed | Files, documents, chunks deleted |
| Webhook deliveries | 30 days | Purged |
| Workflow runs/steps | 90 days | Purged (aggregates kept) |
| Test runs | Keep last 50 per agent + all runs tied to activations | Older purged |
| Audit logs | 2 years | Immutable until expiry |
| Tenant deletion | 30-day grace (status `deleted`), then full purge incl. storage and vectors | Export offered before |
| DPDP data-principal request | Export all data for a phone/email as JSON; erase on request within 30 days | Logged in audit |

## 9. Migration and seed data

**Process:** Alembic; every schema change is a migration reviewed in PR; expand → backfill → contract across releases; CI runs `alembic upgrade head` on empty DB and on a staging snapshot.

**Migration from today's stores (one-time scripts, idempotent):**
1. `app/` SQLite/Postgres tables → new schema (UUID conversion, timestamp parsing, `tenant_id` backfill; the seeded admin with `tenant_id NULL` gets a real tenant).
2. `data/agents_store.json` → `agents` + `agent_versions` v1 (status production for the currently deployed agent, draft for others).
3. `data/config.json` → tenant `integrations` + defaults.
4. `data/crm_*.json` and Supabase `crm_*` → leads/activities/workflows/campaigns (workflows: linear actions → graph; vocabulary mapped: `lead_created→lead.created`, `crm_update→update_lead`, `whatsapp→send_whatsapp`, `reminder→create_reminder`).
5. KB SQLite + FAISS → `kb_*` with re-embedding into pgvector (don't copy hashed-fallback vectors).
6. `data/recordings` → object storage, `recording_key` set.

**Seed data (dev/staging only):** one tenant "Demo Co", users per role with known passwords from env, one agent with En+Te config and a starter conversation workflow, 3 KB sources (small PDF, FAQ, manual text), 20 training examples, 30 test cases across suites, 50 leads, templates catalogue. **Production seed:** templates catalogue and voice catalogue only; no default admin password (first Owner created via signup or CLI `python -m app.cli create-owner`).
