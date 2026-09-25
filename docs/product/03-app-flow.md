# 3. App Flow

## 1. Entry points

| Entry | Lands on | Status |
|---|---|---|
| Marketing site → "Start free" | `/signup` | 🟡 page exists; no marketing site |
| Invite email link | `/invite/:token` → set password → `/` | ❌ |
| Password reset link | `/reset/:token` | ❌ |
| Direct URL / bookmark | requested route, via login if no session | 🟡 auto dev-login bypasses this |
| Deep link from notification / webhook log / alert | e.g. `/agents/:id/tests/runs/:runId` | ❌ |
| Customer website | widget bubble (not the dashboard) | ❌ |
| Phone call | voice agent (no UI) | ✅ |

## 2. Screen inventory

### Existing screens (keep, fix)

| Route | Screen | Purpose | Data required | Status |
|---|---|---|---|---|
| `/login` | Login | Sign in | — | 🟡 bypassed by dev token |
| `/signup` | Signup | Create tenant + Admin | — | 🟡 insecure API (see TRD §4) |
| `/` | Dashboard | Tenant-wide KPIs | stats, calls, leads, appointments | 🟡 mix of real and hardcoded |
| `/agents` | AI Agents | List agents | agents | 🟡 becomes Agent list → opens Studio |
| `/analytics` | Analytics | Cross-channel analytics | analytics events | 🟡 call data only, some fake |
| `/live-calls` | Live Calls | Active sessions | live sessions | 🟡 static, no API |
| `/inbound`, `/outbound` | Calling | Inbound history; single/bulk outbound, campaigns | calls, campaigns | ✅ / 🟡 campaigns legacy-only |
| `/call-logs` | Call Logs | Transcripts, recordings | call logs | ✅ |
| `/contacts` | Contacts | Unified contacts | contacts | ✅ |
| `/crm` | Voice CRM | Leads pipeline, timeline, scoring | leads, activities | 🟡 vertical-specific fields |
| `/appointments` | Appointments | Calendar + bookings | appointments | ✅ |
| `/workflows` | Workflows | Automation list, builder, templates, history | workflows, runs | 🟡 see earlier review |
| `/knowledge-base` | Knowledge Base | Tenant KB library | kb sources, jobs | 🟡 |
| `/cms` | Content Manager | Pages, prompts, FAQs, media | cms | ✅ (prompts/FAQs to merge into Studio/KB) |
| `/team` | Team | Members, roles, invites | users, invites | 🟡 static |
| `/billing` | Billing | Plan, usage, invoices | subscription, usage | 🟡 static |
| `/settings` | Settings | Profile, org, security, integrations | tenant, user, integrations | 🟡 static |
| `/configuration` | Configuration | Global runtime config | config | 🟡 replaced by per-agent Studio settings; keep as platform/tenant defaults |

### New screens

| Route | Screen | Purpose | Data required |
|---|---|---|---|
| `/onboarding` | First-use wizard | Company, use case, languages, first agent from template | tenant, templates |
| `/agents/:id` | Studio → Overview | Status, version, channels, health, recent sessions | agent, versions, metrics |
| `/agents/:id/instructions` | Instructions | Persona, goals, greeting per language, guardrails | draft version |
| `/agents/:id/knowledge` | Knowledge | Assign/unassign KB sources, test retrieval | kb sources, assignments |
| `/agents/:id/tools` | Tools | Enable calendar, CRM, transfer, webhooks, custom HTTP tools | tools, integrations |
| `/agents/:id/workflows` | Workflows | Conversation flow editor + Live Tester | workflow graph, runs |
| `/agents/:id/languages` | Languages | Supported languages, auto-detect, fallback | draft version |
| `/agents/:id/voice` | Voice | Voice, speed, preview (real TTS), interruption sensitivity | voices catalogue |
| `/agents/:id/avatar` | Avatar | Provider state, avatar, background, style, Avatar Dashboard | avatar provider config |
| `/agents/:id/training` | Training | Dataset table, import/export | training examples |
| `/agents/:id/tests` | Test Center | Tabs: Text, Voice, Avatar, Workflow, Knowledge, Multilingual, Regression | test cases, runs |
| `/agents/:id/versions` | Versions | List, diff, activate, rollback, change log | versions, changes |
| `/agents/:id/deploy` | Deploy | Channels: Website, Chat API, Voice numbers, Avatar, API keys, Webhooks | deployments, numbers, keys |
| `/agents/:id/analytics` | Agent Analytics | Per-agent metrics | analytics events |
| `/settings/integrations` | Integrations | Connect WhatsApp, email, calendar, avatar, BYO LLM key | integrations |
| `/settings/api-keys` | API Keys | Create/revoke keys | api keys |
| `/settings/webhooks` | Webhooks | Endpoints + delivery logs | webhooks, deliveries |
| `/settings/audit` | Audit Log | Who changed what | audit logs |
| `/invite/:token`, `/reset/:token`, `/verify/:token` | Auth flows | — | token |

Persistent in Studio: right **Copilot** panel (collapsible), bottom **Execution Timeline** drawer (collapsible).

## 3. Primary journey — create to production

```
/signup → verify email → /onboarding (company, languages En+Te, template "Lead Qualifier")
  → /agents/:id (Overview, status DRAFT, v1 draft)
  → Instructions: edit greeting (En, Te) → autosave to draft
  → Knowledge: upload PDF + website URL → wait until Available → assign to agent
  → Workflows: Trigger → Greeting → Triage (AI) → Condition(billing?) → Action / Handoff → End → Save
  → Test Center › Text: "I need help with billing" → timeline all SUCCESS
  → Test Center › Voice: speak Telugu, interrupt once → Completed
  → Training: add 5 expected Q&A → mark 2 as critical tests
  → Versions: "Submit for testing" → status TESTING → regression runs → EVALUATION → Approve → APPROVED
  → Activate → PRODUCTION (v1)
  → Deploy › Website: add allowed domain → copy snippet → "Verify install" turns green
  → Widget on site: chat → voice → lead form → lead appears in /crm with transcript
  → Analytics shows the session
```

**Success state:** agent badge = PRODUCTION v1, website channel "Live", first lead visible in CRM.

## 4. Alternate journeys

| Journey | Flow |
|---|---|
| Edit production agent | Any edit on a PRODUCTION agent creates draft v(n+1); banner "Editing draft v13 — production is v12"; production untouched until activation |
| Cancel draft | Versions → Discard draft → confirm → draft deleted, change log keeps record |
| Rollback | Versions → select previous version → Rollback → confirm (reason required) → production pointer flips; audit entry |
| Regression fails | Activate disabled; failing critical tests listed with diff; "Fix with Copilot" opens Copilot with failure context |
| Copilot proposes change | Preview card Before/After → Apply (writes draft, logs reason = prompt) / Reject (nothing changes) / Edit (open field) |
| Skip onboarding | "Skip for now" → blank Studio with checklist on Overview |
| Integration missing | Feature shows "Not configured" + "Connect" → `/settings/integrations#provider` → returns to origin after connect |
| Disable agent | Overview → Disable → all channels stop accepting sessions; widget shows offline message; phone routes to fallback number |
| Human handoff | Handoff node → phone: SIP transfer; chat: conversation assigned to human queue, CRM notification |

## 5. Action specifications (key actions)

Each row: trigger · validation · loading · success · error · next.

| Action | Trigger | Validation | Loading | Success | Error | Next |
|---|---|---|---|---|---|---|
| Sign up | Submit form | email format, unique; password ≥ 10 incl. letter+number; company 2–100 chars | button spinner, form disabled | toast "Check your email" | inline field errors; 409 → "Email already registered" | `/verify-pending` |
| Log in | Submit | required fields | spinner | redirect to `returnTo` or `/` | "Incorrect email or password" (generic); 429 → "Too many attempts, try in N min" | — |
| Create agent | "New agent" → template → name | name 2–60, unique per tenant | modal spinner | toast; open Studio | inline | `/agents/:id` |
| Save instructions | Autosave 1 s after typing, or Ctrl+S | greeting ≤ 500 chars; instructions ≤ 20k | "Saving…" indicator | "Saved to draft v13" | "Couldn't save — retry" with retry, local draft kept | stay |
| Upload KB file | Drop / pick file | type in {pdf, docx, txt, csv}; ≤ 25 MB; tenant quota | per-file progress bar then pipeline stepper | status Available | status Failed + reason + Retry | stay |
| Add URL source | Paste URL | https, public host (SSRF guard), not duplicate | pipeline stepper | Available | "Couldn't fetch (HTTP 403)" | stay |
| Add workflow node | Drag from palette / Copilot apply | node type allowed in flow kind; max 200 nodes | none | node selected, config panel open | toast on limit | stay |
| Connect nodes | Drag handle → handle | no self-loop; no cycles except via Loop node; one outgoing per non-branch node | none | edge drawn | edge snaps back + tooltip reason | stay |
| Save workflow | Ctrl+S / Save | graph validation (one trigger, all paths reach End, configs complete) | spinner on Save | "Saved" + dirty flag cleared | list of validation issues, click to focus node | stay |
| Run text test | Send in Live Tester | non-empty ≤ 4k chars | streaming; timeline steps animate RUNNING | final SUCCESS, latency | step FAILED with error; message "Agent error — see step N" | stay |
| Start voice test | "Start" | mic permission; LiveKit configured | "Connecting…" | status ● Listening | permission denied → instructions; not configured → config state | stay |
| Run regression | "Run suite" / auto on submit | ≥ 1 test case | progress n/N | summary Passed/Failed/Changed | run error → retry | results view |
| Activate version | "Activate" | status APPROVED; no critical failures; role ≥ Admin | confirm modal → spinner | "v13 is live" | 409 gate failure with links | Overview |
| Rollback | "Rollback" | target version previously production; reason required | spinner | "Rolled back to v12" | error toast | Overview |
| Create API key | "New key" | name; scopes ≥ 1 | spinner | key shown once with copy + warning | error | list |
| Add webhook | "Add endpoint" | https URL; events ≥ 1 | "Sending test event…" | secret shown once; test delivery status | "Endpoint returned 500" (saved as disabled) | list |
| Copilot command | Enter in Copilot | non-empty | streaming with step list | answer or change preview | error bubble with Retry | stay |
| Invite member | "Invite" | email; role | spinner | row "Pending" | 409 already member | list |

## 6. Navigation rules

- **Global sidebar** (existing groups: Core, Calling, CRM, Intelligence, System). "AI Agents" opens the list; selecting an agent enters **Studio**, which replaces the main area with its own left nav plus a breadcrumb `Agents / <name> / <section>`.
- **Back**: browser back works everywhere (every tab, modal-with-state, and test run has a URL). Leaving a dirty editor prompts "Discard unsaved changes?".
- **Deep links**: `/agents/:id/workflows?node=<nodeId>`, `/agents/:id/tests/runs/:runId`, `/agents/:id/versions/:v/compare/:w`, `/crm?lead=<id>`.
- **Keyboard**: `⌘K` global search (exists); Studio `g` then letter to jump sections; editor shortcuts in UI brief.
- **Mobile (< 768 px)**: bottom tab bar (exists); Studio sections become a select; canvas read-only with pan/zoom; Copilot becomes full-screen sheet.

## 7. Empty and blocked states

| State | Where | Content |
|---|---|---|
| No agents | `/agents` | Illustration, "Create your first agent", templates |
| No KB sources | Knowledge | "Add a PDF, website, or FAQ", drop zone |
| No test cases | Test Center | "Generate from training data" / "Add test" |
| No runs yet | Workflows history, analytics | "No executions yet — run a test" (never fake rows) |
| Permission denied | Any write control | Control disabled with tooltip "Admins only"; direct URL → 403 page |
| Integration not configured | Voice/Avatar/WhatsApp/Email/Calendar | Provider name, what's needed, "Connect" (Admin) or "Ask an admin" |
| Backend unreachable | Global | Top banner "Can't reach aVn — retrying", sidebar status (exists); writes disabled |
| Offline (browser) | Global | Banner; queued autosaves retried on reconnect |
| Agent disabled | Studio | Red banner; channels show "Offline" |
| Quota exceeded | Test/Deploy | "Monthly minutes used — upgrade" link to Billing |

## 8. First-use journey

1. Signup → email verification.
2. `/onboarding` step 1: company name, industry, team size.
3. Step 2: primary use (inbound support, lead qualification, appointment booking, outbound follow-up).
4. Step 3: languages (pre-select English + detected browser locale; Telugu/Hindi suggested for India).
5. Step 4: template agent created as DRAFT with starter workflow and sample test cases.
6. Land on Studio Overview with **Setup checklist**: Instructions ✓ · Add knowledge · Test in text · Test by voice · Activate · Deploy to website · Invite team. Checklist state stored server-side per agent.
7. Copilot greets with context: "Your agent 'X' is a draft. Want me to add your website as knowledge?"
