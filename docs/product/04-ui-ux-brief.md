# 4. UI and UX Design Brief

## 1. Audience and tone

- **Audience:** non-engineer operators and builders at SMB / mid-market companies, often working in English with customers speaking Telugu, Hindi, or code-mixed speech; plus developers on the Deploy/API screens.
- **Three adjectives:** **Confident** (serious ops tool, not a toy), **Transparent** (always shows what the agent did and why), **Calm** (dense data without noise).
- **Voice of UI copy:** plain, specific, action-first ("Activate v13", not "Proceed"). Never claim a feature worked when it didn't; not-configured states say exactly what's missing.

## 2. Reference products

| Product | Borrow | Avoid |
|---|---|---|
| Linear | Keyboard-first, crisp dark theme, command palette, fast transitions | Hiding critical actions behind shortcuts only |
| Vercel dashboard | Deploy flow, environment/version clarity, logs | — |
| Retell / Vapi | Voice test console, latency breakdown | Developer-only jargon on builder screens |
| Voiceflow / n8n | Canvas node design, run inspection per node | Overcrowded node palettes |
| Intercom Fin | Widget polish, handoff UX | Upsell interruptions |
| Stripe | Webhook delivery logs, API key UX (show once) | — |

## 3. Colour palette

**Current state 🟡:** tokens in `src/index.css` (`@theme`) and a light override exist, but pages use inline hex colours from a *different* palette (`#7B61FF` ×117, `#22D3A5` ×99, `#4B5675` ×279 …). Light mode therefore only restyles the shell. **Rule going forward: components use CSS variables only; no hex in `.tsx`.** Enforced by an ESLint rule (`no-restricted-syntax` for hex literals in style props) after migration.

Unified tokens (dark / light). Brand violet is kept; semantic colours standardised.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg-base` | `#0A0B0F` | `#F6F6F8` | app background |
| `--bg-surface` | `#111318` | `#FFFFFF` | sidebar, topbar |
| `--bg-card` | `#151922` | `#FFFFFF` | cards, panels |
| `--bg-elevated` | `#1C2030` | `#F1F1F4` | popovers, inputs, canvas nodes |
| `--bg-hover` | `#1E2333` | `#EDEDF1` | row/item hover |
| `--border` | `rgba(255,255,255,.08)` | `rgba(0,0,0,.08)` | default borders |
| `--border-strong` | `rgba(255,255,255,.14)` | `rgba(0,0,0,.16)` | inputs, focus-adjacent |
| `--text-primary` | `#F5F7FB` | `#0B0B10` | headings, body |
| `--text-secondary` | `#A1A8BA` | `#4B5060` | secondary text (≥ 4.5:1) |
| `--text-muted` | `#7C849A` | `#6B7080` | captions, meta (≥ 4.5:1 on card) |
| `--text-disabled` | `#4B5263` | `#B4B7C0` | disabled only |
| `--primary` | `#7B6CFF` | `#5B4BEF` | primary actions, focus, selection |
| `--primary-muted` | `rgba(123,108,255,.14)` | `rgba(91,75,239,.10)` | selected backgrounds |
| `--success` | `#22C58B` | `#0E9F6E` | SUCCESS, active, live |
| `--warning` | `#F5A623` | `#B86E00` | paused, degraded |
| `--danger` | `#FF5470` | `#D92D4A` | FAILED, destructive |
| `--info` | `#5EB8FF` | `#1D72D8` | informational |
| `--skipped` | `#8A90A2` | `#8A90A2` | SKIPPED / IDLE |

Node-category accents (canvas): Trigger = `--primary`, Message = `--info`, Condition = `--warning`, Action = `--success`, AI Agent = violet-pink `#C06CFF`/`#9B3FE0`, Knowledge = cyan `#3CCFE0`/`#0891A5`, Delay = `--skipped`, Handoff = orange `#FF8A3D`/`#C2570C`, End = `--text-muted`.

**Accessibility finding ❌:** current secondary text `#4B5675` on `#0A0B0F` is ~2.7:1 and on cards ~2.4:1, failing WCAG AA (4.5:1). `#3B4560` (palette descriptions) is worse. The new `--text-muted` fixes this.

**Theme modes:** `data-theme="dark" | "light"` on `<html>`; **System** removes the attribute and uses `@media (prefers-color-scheme)`. Preference stored per user (server) with localStorage cache to avoid flash; inline script in `index.html` applies before first paint.

## 4. Typography

| Role | Font | Size / line-height / weight |
|---|---|---|
| Display (page title) | Satoshi | 26/32, 700, −0.02em |
| H2 section | Satoshi | 18/24, 600 |
| H3 card title | General Sans | 14/20, 600 |
| Body | Inter | 14/20, 400 |
| Small / meta | Inter | 12/16, 400–500 |
| Micro label (uppercase) | Inter | 11/14, 700, +0.08em |
| Code, IDs, JSON | JetBrains Mono | 12.5/18 |
| Indic scripts | **Noto Sans Telugu / Devanagari / Tamil / Kannada / Malayalam, Noto Sans Arabic, Noto Sans JP/KR/SC** as fallbacks in the font stack | same scale; line-height +2 px for Indic |

Current state 🟡: fonts load from Fontshare + Google Fonts; ~600 inline `fontSize` values across pages with no scale. Replace with Tailwind text utilities mapped to the scale. Add Noto fallbacks (❌ missing — Telugu currently renders in OS fallback fonts).

Minimum text size 12 px (current UI uses 10–10.5 px in many places → raise).

## 5. Components

Existing in `src/components/ui`: Button, Card, GlassCard, Badge, Input, Select, Textarea, Toggle, Modal, ConfirmDialog, Table, AnimatedTable, States, GradientStatCard, WaveformVisualizer, NeuralPulse, theme-toggle. **All to be tokenised.**

To add:

| Component | Notes |
|---|---|
| Tabs (URL-synced) | replaces per-page tab bars |
| Drawer / Sheet | Copilot on mobile, Execution Timeline |
| Tooltip, Popover, DropdownMenu | Radix primitives for a11y |
| Toast | keep react-hot-toast, themed |
| StatusPill | IDLE / RUNNING / SUCCESS / FAILED / SKIPPED; DRAFT / TESTING / EVALUATION / APPROVED / PRODUCTION / DISABLED |
| DiffView | before/after for Copilot previews and version compare (side-by-side + inline) |
| StepTimeline | execution steps with expandable input/output JSON, duration bar |
| ChatThread | streaming bubbles, timestamps, copy, retry, stop, tool-call chips |
| VoiceConsole | mic level, status chain (Listening → … → Completed), transcript, language badge |
| AvatarStage | video element, status overlay, fullscreen, not-configured state |
| PipelineStepper | Extract → Clean → Chunk → Embed → Index → Available |
| DataTable | sorting, filtering, pagination, row selection, column visibility, empty/loading/error |
| CodeBlock | copy button, language label (embed snippet, API examples) |
| EmptyState, NotConfiguredState, ErrorState, Skeleton | standardised |
| Canvas nodes | React Flow custom nodes: icon, title, subtitle, category accent, status ring, input/output handles, error badge |
| LanguageBadge | ISO code + native name (తెలుగు, हिन्दी) |

## 6. Layout rules

- **Grid:** 4 px base; spacing scale 4, 8, 12, 16, 20, 24, 32, 40, 48.
- **Radius:** 6 (inputs, chips), 10 (buttons, nodes), 14 (cards), 18 (hero/modals).
- **App shell:** sidebar 248 px (collapsed 64), topbar 56 px, content max-width none for Studio, 1280 px for list pages, page padding 24 px (16 px < 768).
- **Studio:** left nav 220 px · center flex · Copilot 380 px (resizable 320–560, collapsible) · bottom timeline 240 px (resizable, collapsible).
- **Breakpoints:** `sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536. < 1024: Copilot becomes overlay sheet. < 768: bottom tabs, single column.
- **Density:** tables 44 px rows (36 px compact option).
- **RTL:** `dir="rtl"` for Arabic in chat/widget content areas; use logical CSS properties (`margin-inline-start`).

## 7. Screen notes (hierarchy)

| Screen | Primary | Secondary | Tertiary |
|---|---|---|---|
| Studio Overview | Agent name, lifecycle pill, production vs draft version, primary action (Test / Activate / Deploy) | Channel status cards, setup checklist | Recent sessions, KPIs |
| Workflow editor | Canvas | Node palette (search at top), node config panel | Minimap, zoom controls, validation list |
| Live Tester / Test Center | Conversation / input | Step timeline with per-node I/O and ms | Logs, raw events |
| Voice Test | Big status chain + mic control | Transcript with language tags, agent response | Latency breakdown (STT/LLM/TTS), audio playback |
| Avatar Dashboard | Video stage | Agent name/status/version/voice/language | Transcript, node, KB source, execution status |
| Knowledge | Table of sources with status | Pipeline stepper for processing items | Preview drawer, retrieval test |
| Versions | Version list with lifecycle + who/when/why | Diff view | Test results per version |
| Deploy › Website | Snippet + allowed domains | Widget configurator with live preview | Install verification |
| Copilot | Thread | Context chips (agent, version, node) | Step list during execution, change previews |

## 8. Accessibility (WCAG 2.1 AA)

- Contrast ≥ 4.5:1 text, ≥ 3:1 UI components and focus indicators (both themes; automated check in CI via axe + token contrast script).
- Full keyboard access: all controls tabbable; canvas supports keyboard node selection (Tab), move (arrows, Shift = 10 px), connect (Enter on handle → choose target), delete (Del).
- Visible focus ring (`--primary`, 2 px, offset 2) — exists globally, keep.
- Labels: every input has a `<label>`; icon-only buttons have `aria-label` (many current icon buttons use `title` only).
- Live regions: streaming chat and execution status use `aria-live="polite"`; errors `assertive`.
- Touch targets ≥ 40×40 px on touch devices (current icon buttons are 28 px).
- Reduced motion: respect `prefers-reduced-motion` (disable pulse/glow animations, framer-motion transitions).
- Language: set `lang` attribute on transcript/message elements per detected language for screen readers.
- Captions: voice and avatar tests show live transcript by default.

## 9. Interaction states

| State | Treatment |
|---|---|
| Hover | `--bg-hover` background; cursor pointer; no layout shift |
| Focus | 2 px `--primary` ring, offset 2 |
| Active/pressed | 1 px translate-y or 0.98 scale (disabled under reduced motion) |
| Selected | `--primary-muted` background + `--primary` border |
| Disabled | 50% opacity, `not-allowed`, tooltip explaining why (role, gate, not configured) |
| Loading | Skeletons for first load; inline spinners on buttons; never block whole page for partial loads |
| Streaming | Blinking caret at end of text; Stop button replaces Send |
| Running (node/test) | `--primary` animated ring; elapsed ms counter |
| Success | `--success` icon + short toast; state persists in UI (not only toast) |
| Error | `--danger` inline message with cause and next step; Retry where safe |
| Skipped | `--skipped` dashed ring |
| Dirty / unsaved | Dot on tab + "Unsaved" label; leave-guard |
| Not configured | Neutral card, provider logo, required fields, Connect button |

## 10. Assets needed

| Asset | Status |
|---|---|
| aVn logo (SVG, light/dark, mark-only, favicon, 512 px app icon, OG image) | 🟡 favicon only |
| Icon set | ✅ lucide-react; add node-type icon mapping |
| Empty-state illustrations (agents, knowledge, tests, workflows, analytics) — single line style, theme-aware | ❌ |
| Default avatar thumbnails (from provider) | ❌ depends on D2 |
| Voice sample clips per voice × language (generated via real TTS, cached) | ❌ |
| Widget launcher icons + default brand theme | ❌ |
| Product screenshots for docs/marketing | ❌ after M3 |
| Template agent cover images | ❌ |
