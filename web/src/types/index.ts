// ──────────────────────────────────────────────────────────────────
// aVn — Agentic Voice Network · Shared TypeScript Types
// ──────────────────────────────────────────────────────────────────

// ─── Config ───────────────────────────────────────────────────────
export interface AgentConfig {
  first_line: string
  agent_instructions: string
  gemini_live_model: string
  gemini_live_voice: string
  gemini_live_temperature: number
  gemini_live_language: string
  gemini_live_preflight_enabled: boolean
  gemini_live_preflight_timeout: number
  gemini_live_connect_timeout: number
  gemini_live_connect_retries: number
  gemini_tts_model: string
  lang_preset: string
  max_turns: number
  user_away_timeout: number
  session_close_transcript_timeout: number
  livekit_url: string
  livekit_api_key: string
  livekit_api_secret: string
  sip_trunk_id: string
  google_api_key: string
  telegram_bot_token: string
  telegram_chat_id: string
  supabase_url: string
  supabase_key: string
  kb_enabled: boolean
  kb_backend: string
  kb_data_dir: string
  kb_top_k: number
  kb_similarity_threshold: number
  kb_context_char_budget: number
  kb_live_timeout_ms: number
  kb_live_context_char_budget: number
  kb_cache_ttl_seconds: number
  kb_chunk_size: number
  kb_chunk_overlap: number
  kb_worker_poll_seconds: number
  kb_embedding_provider: string
  kb_embedding_model: string
  kb_embedding_fallback_provider: string
  kb_embedding_fallback_model: string
  kb_index_kind: string
  kb_rerank_enabled: boolean
}

// ─── Stats ────────────────────────────────────────────────────────
export interface Stats {
  total_calls: number
  total_bookings: number
  avg_duration: number
  booking_rate: number
}

// ─── Call Logs ────────────────────────────────────────────────────
export interface LatencySummary {
  turns: number
  kb_used_turns: number
  stt_endpoint_ms?: number
  kb_ms?: number
  llm_first_token_ms?: number
  tts_first_audio_ms?: number
  tool_ms?: number
  total_turn_ms?: number
  slowest_turn?: {
    turn_index: number
    total_turn_ms: number | null
    kb_used: boolean
    kb_skipped_reason: string | null
  }
}

export interface CallLog {
  id: string | number
  created_at: string
  phone_number: string
  caller_name: string
  duration_seconds: number
  summary: string
  transcript?: string
  recording_url?: string
  sentiment?: string
  was_booked: boolean
  interrupt_count?: number
  estimated_cost_usd?: number
  call_date?: string
  call_hour?: number
  call_day_of_week?: string
  call_room_id?: string
  direction?: 'inbound' | 'outbound'
  latency_summary?: LatencySummary | null
}

// ─── Contacts ─────────────────────────────────────────────────────
export interface Contact {
  phone_number: string
  caller_name: string
  total_calls: number
  last_seen: string
  is_booked: boolean
  appointment_count: number
}

// ─── Appointments ─────────────────────────────────────────────────
export type AppointmentStatus = 'scheduled' | 'cancelled' | 'completed'

export interface Appointment {
  id: string
  created_at: string
  updated_at: string
  title: string
  contact_name: string
  contact_phone: string
  scheduled_start: string
  scheduled_end: string
  timezone: string
  status: AppointmentStatus
  notes?: string
  source?: string
}

export interface CreateAppointmentPayload {
  title: string
  contact_name: string
  contact_phone: string
  scheduled_start: string
  scheduled_end: string
  timezone: string
  status: AppointmentStatus
  notes?: string
}

export type UpdateAppointmentPayload = Partial<CreateAppointmentPayload>

// ─── Knowledge Base ───────────────────────────────────────────────
export type KbSourceType = 'web_url' | 'pdf_upload'
export type KbSourceStatus = 'ready' | 'pending' | 'error' | 'processing'
export type KbJobStatus = 'completed' | 'pending' | 'running' | 'failed'

export interface KbSource {
  id: number
  created_at: string
  updated_at: string
  source_type: KbSourceType
  title: string
  source_url?: string
  raw_text?: string | null
  storage_bucket?: string | null
  storage_path?: string | null
  mime_type?: string | null
  checksum?: string
  status: KbSourceStatus
  enabled: boolean
  sync_error?: string
  last_synced_at?: string | null
  metadata?: Record<string, unknown>
}

export interface KbJob {
  id: number
  created_at: string
  updated_at: string
  source_id: number
  source_type: string
  job_type: string
  status: KbJobStatus
  payload?: Record<string, unknown>
  last_result?: Record<string, unknown>
}

export interface KbStatus {
  status: string
  kb_enabled: boolean
  backend: string
  runtime: string
  embedding_provider: string
  embedding_model: string
  embedding_ready?: boolean
  embedding_issue?: string | null
  stale_vector_count?: number
  index_kind?: string
  data_dir?: string
  index_status?: {
    vector_count: number
    rebuilt_at: string
  }
  vector_count?: number
  last_rebuild_at?: string
  counts?: {
    sources: number
    jobs: number
    chunks: number
  }
}

export interface KbSearchHit {
  score: number
  title: string
  content: string
  preview: string
  source_type: string
  source_url?: string
}

export interface KbSearchResult {
  status: string
  result?: {
    query: string
    chunk_hits: KbSearchHit[]
  }
  grounding?: {
    query: string
    chunk_hits: KbSearchHit[]
    grounding_text: string
  }
}

// ─── Outbound Calls ───────────────────────────────────────────────
export interface SingleCallResult {
  status: 'ok' | 'error'
  dispatch_id?: string
  room?: string
  phone?: string
  sip_trunk_id?: string
  message?: string
}

export interface BulkCallEntry {
  phone: string
  status: 'ok' | 'error'
  dispatch_id?: string
  room?: string
  message?: string
}

export interface BulkCallResult {
  results: BulkCallEntry[]
  total: number
}

// ─── Agents ───────────────────────────────────────────────────────
export type AgentStatus = 'active' | 'idle' | 'offline' | 'processing'

export interface Agent {
  id: string
  name: string
  status: AgentStatus
  voice: string
  model: string
  calls_today: number
  calls_total: number
  avg_duration: number
  success_rate: number
  last_active: string | null
  description?: string
  tags?: string[]
}

// ─── Analytics ────────────────────────────────────────────────────
export interface DailyMetric {
  date: string
  calls: number
  bookings: number
  avg_duration: number
  conversion_rate: number
}

export interface AnalyticsOverview {
  period: '7d' | '30d' | '90d'
  total_calls: number
  total_bookings: number
  avg_duration: number
  conversion_rate: number
  ai_latency_ms: number
  kb_retrieval_rate: number
  daily: DailyMetric[]
}

// ─── Inbound Calls ────────────────────────────────────────────────
export type InboundCallStatus = 'live' | 'queued' | 'completed' | 'transferred' | 'voicemail'

export interface InboundCall {
  id: string
  phone_number: string
  caller_name: string
  status: InboundCallStatus
  started_at: string
  duration_seconds: number
  sentiment?: string
  room_id?: string
  agent_id?: string
  recording_url?: string
  summary?: string
}

// ─── CMS ──────────────────────────────────────────────────────────
export type CMSPageStatus = 'published' | 'draft' | 'archived'

export interface CMSPage {
  id: string
  created_at: string
  updated_at: string
  title: string
  slug: string
  content: string
  status: CMSPageStatus
  category?: string
  seo_title?: string
  seo_description?: string
}

export interface CMSPrompt {
  id: string
  created_at: string
  updated_at: string
  name: string
  content: string
  active: boolean
  tags?: string[]
}

export interface CMSFaq {
  id: string
  question: string
  answer: string
  category?: string
  order?: number
}

export interface CMSMedia {
  id: string
  created_at: string
  filename: string
  url: string
  mime_type: string
  size_bytes: number
}

// ─── Generic API wrapper ──────────────────────────────────────────
export interface ApiOk<T = unknown> {
  status: 'ok'
  [key: string]: T | string
}

export interface ApiError {
  status: 'error' | 'setup_required' | 'not_configured'
  message: string
}

// ─── Notification ─────────────────────────────────────────────────
export interface AppNotification {
  id: string
  title: string
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
  read: boolean
  created_at: string
}


// ─── CRM ──────────────────────────────────────────────────────────
export type LeadStatus = 'New' | 'Contacted' | 'Follow-up' | 'Interested' | 'Converted' | 'Lost'
export type LeadScore = 'Hot' | 'Warm' | 'Cold'

export interface Lead {
  id: string
  created_at: string
  updated_at: string
  name: string
  phone: string
  email?: string
  company?: string
  status: LeadStatus
  score: LeadScore
  score_explanation?: string
  assigned_agent?: string
  assigned_user_id?: string | null
  custom_fields?: Record<string, string | number | boolean> | null
  state?: string
  neet_score?: number
  rank?: number
  budget?: string
  parent_involved?: boolean
  country_preference?: string
  follow_up_date?: string
  objection?: string
  session_booked?: boolean
  notes?: string
}

export interface LeadActivity {
  id: string | number
  lead_id: string | number
  created_at: string
  activity_type: 'call' | 'note' | 'whatsapp' | 'crm_update' | 'pipeline_change'
  title: string
  description: string
  metadata?: Record<string, any>
}

export interface WorkflowAction {
  type: 'ai_call' | 'whatsapp' | 'reminder' | 'crm_update'
  config: Record<string, any>
}

export interface Workflow {
  id: string
  created_at: string
  name: string
  trigger_event: string
  trigger_config?: Record<string, unknown> | null
  actions: WorkflowAction[]
  is_active: boolean
}

// ─── Campaigns ────────────────────────────────────────────────────
export type CampaignStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed'
export type CampaignLeadOutcome = 'qualified' | 'scheduled' | 'no_answer' | 'failed' | 'pending'

export interface Campaign {
  id: string
  name: string
  status: CampaignStatus
  agent_id?: string
  concurrency_limit: number
  retry_limit: number
  created_at: string
  total_leads: number
  completed_leads: number
  qualified_leads: number
  scheduled_leads: number
  failed_leads: number
}

export interface CampaignLead {
  id: string
  name: string
  phone: string
  status: string
  outcome: CampaignLeadOutcome
  custom_fields?: Record<string, unknown>
}

export interface ColumnMapping {
  phone: string
  name: string
  custom_fields: string[]
}
