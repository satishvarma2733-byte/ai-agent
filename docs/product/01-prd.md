# 1. Product Requirements Document (PRD)

## 1. Product name and idea

**aVn — Agentic Voice Network.** A platform where a business creates one AI agent, trains and tests it in its customers' languages, and deploys it to phone, website chat, voice, AI avatar, and API, with a built-in CRM and workflow automation.

## 2. Target users

| Persona | Who | Needs |
|---|---|---|
| **Owner / Admin** | Founder or ops head of an SMB or mid-market company (education consultancies, clinics, real estate, D2C support) in India and multilingual markets | Launch an agent without engineers, control cost, trust it won't embarrass the brand |
| **Agent Builder** | Ops or CX manager who configures the agent | Edit instructions, knowledge, workflows; test in Telugu/Hindi/English; ship safely |
| **Sales / Support Agent (human)** | Team member working leads | See AI-qualified leads, transcripts, handoffs; follow up |
| **Developer** | Customer's engineer | Embed widget, call API, receive webhooks, without seeing provider keys |
| **Platform Operator** | aVn staff | Manage tenants, plans, incidents |

## 3. Problem and current workaround

- **Problem:** Businesses in multilingual markets miss calls and chats outside hours, lose leads because follow-up is slow, and can't staff agents fluent in Telugu, Hindi, and code-mixed speech.
- **Current workaround:** Human call centres, IVR menus, English-only chatbots, WhatsApp handled manually, leads tracked in spreadsheets. Existing AI builders (Vapi, Retell, Voiceflow) are voice- *or* chat-first, weak in Indian languages, and have no built-in CRM.

## 4. Goals and success measures

| Goal | Metric | Target (6 months after GA) |
|---|---|---|
| Fast time to value | Median time from signup to first successful test conversation | ≤ 15 min |
| Agents reach production | % of created agents promoted to PRODUCTION | ≥ 40% |
| Quality | Regression pass rate at activation | ≥ 95%, zero critical failures |
| Multilingual quality | Human-rated correct-language, correct-answer rate (Te/Hi/En/mixed) | ≥ 90% |
| Voice responsiveness | Voice turn latency p50 / p95 | ≤ 800 ms / ≤ 1.5 s |
| Business outcome | Leads captured per active agent per week | Tracked; baseline in first month |
| Automation | Conversations resolved without human handoff | ≥ 60% |
| Reliability | Platform uptime (API + voice) | ≥ 99.5% |

## 5. Core features

Priority: **P0** = required for v1 GA, **P1** = v1.x, **P2** = later. Status against the current codebase.

| # | Feature | User benefit | Priority | Status |
|---|---|---|---|---|
| F1 | Accounts, tenants, roles, invitations | Team works safely in one workspace | P0 | 🟡 JWT + roles in `app/`; no invites, no password reset, UI bypasses auth |
| F2 | Agent Studio workspace (13 sections) | One place to build an agent | P0 | ❌ Agents page is a create/edit wizard |
| F3 | Agent config: instructions, greeting, languages, voice, tools | Define behaviour without code | P0 | 🟡 Wizard fields exist; stored in JSON file / partially in DB |
| F4 | Versioning + lifecycle (Draft → … → Production → Disabled) | Never break production | P0 | ❌ |
| F5 | Per-agent runtime (each agent answers its own number/channel) | Multiple agents per tenant | P0 | ❌ one global config |
| F6 | Knowledge base: PDF, DOCX, TXT, CSV, URL, sitemap, FAQ, manual | Agent answers from company facts | P0 | 🟡 PDF/URL/sitemap only; no per-agent assignment |
| F7 | Cross-lingual retrieval (14 languages, auto-detect) | Telugu question over English docs | P0 | 🟡 multilingual prompts; retrieval not cross-lingual-verified |
| F8 | Conversation workflows (Trigger, Message, Condition, AI Agent, Knowledge, Action, Delay, Handoff, End) | Deterministic business logic | P0 | ❌ |
| F9 | Automation workflows (lead/call/appointment/webhook triggers) | Follow up automatically | P0 | 🟡 linear engine, broken builder |
| F10 | Visual workflow editor (drag, connect, zoom, minimap, undo/redo) | Build flows visually | P0 | 🟡 static SVG |
| F11 | Test Center: text, workflow, knowledge, multilingual | Prove it works before launch | P0 | ❌ |
| F12 | Voice Test in browser with barge-in | Hear the agent before customers do | P0 | ❌ (phone only) |
| F13 | Training dataset (examples, expected outputs) | Improve answers in a controlled way | P0 | ❌ |
| F14 | Regression suite gating activation | Safe updates | P0 | ❌ |
| F15 | Agent Copilot with change preview (Apply/Reject) | Configure by talking | P1 | ❌ |
| F16 | Website widget (chat + voice + lead capture) | Deploy to site with one snippet | P0 | ❌ |
| F17 | Public chat API (JSON + streaming) + API keys | Developers integrate | P0 | ❌ |
| F18 | Webhooks with delivery logs | Connect to other systems | P1 | ❌ |
| F19 | Phone channel (inbound, outbound, campaigns, transfer) | Voice at scale | P0 | ✅ core / 🟡 campaigns only in legacy backend |
| F20 | CRM: leads, timeline, custom fields, assignment, scoring | Leads land in one place | P0 | 🟡 fields hardcoded to one vertical |
| F21 | Appointments + calendar sync | Agent books meetings | P0 | 🟡 internal calendar only; Google/Zoho sync not built |
| F22 | Analytics across channels | See outcomes | P1 | 🟡 calls only, some numbers fake |
| F23 | AI Avatar channel + Avatar Test | Video presence | P1 | ❌ (needs provider) |
| F24 | Testing Agent (autonomous) | Find failures, propose fixes | P2 | ❌ |
| F25 | Billing & plans, usage metering | Monetise | P1 | 🟡 static page |
| F26 | Light / Dark / System theme | Comfort, accessibility | P0 | 🟡 |
| F27 | WhatsApp & email actions | Multichannel follow-up | P1 | 🟡 only log a timeline entry, no real send |
| F28 | Audit log | Accountability | P0 | 🟡 table exists, not written to |

## 6. Out of scope for v1

- Native mobile apps (responsive web only).
- Marketplace of third-party agent templates.
- Custom LLM fine-tuning (training = prompt examples + retrieval, not weight updates).
- Self-hosted / on-prem edition.
- Languages beyond the 14 listed; voice quality guarantees beyond English, Telugu, Hindi and their mixes.
- Outbound SMS; social channels other than WhatsApp.
- Avatar custom likeness cloning.

## 7. User stories

**Onboarding & team**
- US1. As an Owner, I want to sign up with my company name and invite teammates by email, so I can work together in one workspace.
- US2. As an Admin, I want to assign Admin, Manager, or Agent roles, so people only change what they're allowed to.

**Build**
- US3. As a Builder, I want to create an agent from a template, so I start with sensible defaults.
- US4. As a Builder, I want to add English and Telugu and pick a voice, so the agent speaks my customers' languages.
- US5. As a Builder, I want to upload PDFs and a website URL and assign them to an agent, so it answers from my facts.
- US6. As a Builder, I want to draw a conversation workflow with conditions and handoff, so important paths are deterministic.
- US7. As a Builder, I want to tell the Copilot "add a condition for interested leads" and see a preview before it changes anything.

**Test & ship**
- US8. As a Builder, I want to chat with my draft agent and see each workflow step with inputs, outputs, and timing.
- US9. As a Builder, I want to speak to my agent in Telugu from my browser and interrupt it, so I know how it sounds.
- US10. As a Builder, I want to add expected answers as test cases and run them on every new version, so updates don't regress.
- US11. As an Admin, I want activation blocked when critical tests fail, so production stays safe.
- US12. As an Admin, I want to roll back to the previous version in one click.

**Deploy & operate**
- US13. As a Builder, I want an embed snippet restricted to my domains, so only my site can use the widget.
- US14. As a Developer, I want an API key and a `/chat` endpoint with streaming, so I can use the agent in my app.
- US15. As a Developer, I want webhooks for lead.created and conversation.completed with retries, so my systems stay in sync.
- US16. As a Sales Agent, I want captured leads to appear in the CRM with the transcript, so I can follow up.
- US17. As an Owner, I want analytics by channel and language, so I know what's working.

## 8. Acceptance criteria (P0 selection)

| Story | Given | When | Then |
|---|---|---|---|
| US1 | A new visitor | they submit signup with a unique email, password ≥ 10 chars, company name | a tenant and Admin user are created, they land in onboarding, and a verification email is sent |
| US2 | An Agent-role user | they call any agent-config write endpoint | the API returns 403 and the UI hides the control |
| US4 | A draft agent | the Builder enables Telugu and saves | a new draft version records the change, user, time, and reason; production is unchanged |
| US5 | A PDF uploaded | ingest completes | source status goes Extract → Clean → Chunk → Embed → Index → Available; a search for a phrase in the PDF returns it; failures show a reason |
| US5b | Embedding provider not configured | a source is uploaded | status is "Blocked: embedding provider not configured" (no hashed fallback) |
| US6 | A workflow with a Condition node | the builder connects only one branch | save is allowed but validation shows "Condition has no 'else' path" |
| US8 | A draft agent with workflow | the Builder sends "I need help with billing" | the timeline shows each executed node with status, input, output, and ms; the reply streams |
| US9 | Microphone permission granted | the Builder speaks Telugu, then talks over the agent | transcript shows Telugu, detected language = te, agent audio stops within 300 ms of user speech, and it answers the new question |
| US11 | A draft with 1 failing critical test | Admin clicks Activate | activation is refused and the failing test is linked |
| US12 | v13 in production, v12 previous | Admin clicks Rollback | v12 is production within 5 s for new sessions; audit log entry created |
| US13 | Allowed domains = `example.com` | the widget loads on `evil.com` | the session request is rejected (403) and no agent data is returned |
| US14 | A valid API key | client POSTs `/api/v1/agents/{id}/chat` with `stream=true` | server sends SSE `token` events then a `done` event with `sessionId`; no provider keys in any response |
| US15 | A webhook endpoint returning 500 | lead.created fires | delivery retried with exponential backoff up to 6 times; each attempt visible in delivery log |
| US16 | Widget visitor gives name + phone | conversation ends | a lead exists in CRM with source=website, agent id, transcript link, and `lead.created` fired |
| F-all | Any integration not configured | the user opens its feature | the UI shows a "not configured" state with a link to settings; no simulated output |

## 9. Non-functional requirements (summary; detail in TRD)

- Tenant isolation on every query and file path.
- PII (phone, email, transcripts, recordings) encrypted at rest; retention configurable.
- Compliance: India DPDP Act 2023 (consent, deletion on request); call-recording consent prompt configurable.
- WCAG 2.1 AA.

## 10. Open questions

| # | Question | Blocks | Proposed default |
|---|---|---|---|
| D1 | Single backend: `app/` (FastAPI + SQLAlchemy) or legacy `backend_api.py`? | Everything | `app/` |
| D2 | Avatar provider (Tavus, HeyGen Interactive, Simli, D-ID) and account | F23 | Decide by M4 |
| D3 | WhatsApp provider (Meta Cloud API, Gupshup, Twilio) | F27 | Meta Cloud API |
| D4 | Email provider (Resend, SES, SMTP) | F1 verification, F27 | Resend |
| D5 | Production domain for app, API, `widget.js` | F16 | `app.<domain>`, `api.<domain>`, `cdn.<domain>` |
| D6 | Data residency (India region required?) | TRD hosting | Mumbai region |
| D7 | LLM providers: Gemini only, or abstraction for others now? | F2, F15 | Gemini now, interface ready |
| D8 | Keep Supabase at all, or Postgres only? | Schema | Postgres only (Supabase optional as managed Postgres) |
| D9 | Pricing plans and usage units (minutes, messages, agents) | F25 | Free / Growth / Enterprise by minutes + messages |
| D10 | What happens to the eWings-specific lead fields? | Schema | Move to tenant custom fields; migrate existing data |
| D11 | Is STT for browser voice test the same Gemini Live path as phone? | F12 | Yes, via LiveKit room |
