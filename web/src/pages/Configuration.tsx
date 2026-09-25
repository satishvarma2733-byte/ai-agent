import { useEffect, useState, useCallback, type ReactNode } from 'react'
import {
  Save, Settings2, Zap, Globe2, MessageSquare, Database, Bell, Brain, Shield,
  WifiOff,
} from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/layout/PageHeader'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Textarea from '../components/ui/Textarea'
import Select from '../components/ui/Select'
import Toggle from '../components/ui/Toggle'
import { LoadingState } from '../components/ui/States'
import { configApi } from '../api/config'
import type { AgentConfig } from '../types'

const SECRET_FIELDS: (keyof AgentConfig)[] = [
  'livekit_api_secret', 'google_api_key', 'telegram_bot_token', 'supabase_key',
]

function SectionHeader({ icon, title, subtitle }: { icon: ReactNode; title: string; subtitle?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
      <div style={{
        width: 34, height: 34, borderRadius: 10,
        background: 'rgba(123,97,255,0.1)',
        border: '1px solid rgba(123,97,255,0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>{title}</div>
        {subtitle && <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 1 }}>{subtitle}</div>}
      </div>
    </div>
  )
}

function FormRow({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 14, marginBottom: 14 }}>
      {children}
    </div>
  )
}

export default function Configuration() {
  const [cfg, setCfg] = useState<AgentConfig | null>(null)
  const [dirty, setDirty] = useState<Partial<AgentConfig>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [offline, setOffline] = useState<string | null>(null)
  const [denied, setDenied] = useState(false)
  const [activeSection, setActiveSection] = useState<string>('greeting')

  const load = useCallback(async () => {
    setLoading(true)
    setOffline(null)
    try {
      const data = await configApi.get()
      setCfg(data)
      setDirty({})
    } catch (e) {
      const status = (e as { status?: number }).status
      if (status === 403) setDenied(true)
      else setOffline(status ? (e instanceof Error ? e.message : `HTTP ${status}`) : 'The API could not be reached.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const merged = { ...cfg, ...dirty } as AgentConfig

  function set<K extends keyof AgentConfig>(key: K, value: AgentConfig[K]) {
    setDirty(prev => ({ ...prev, [key]: value }))
  }

  function str(key: keyof AgentConfig): string {
    const v = merged[key]
    if (v === null || v === undefined) return ''
    return String(v)
  }

  function num(key: keyof AgentConfig): number {
    return Number(merged[key]) || 0
  }

  function bool(key: keyof AgentConfig): boolean {
    return Boolean(merged[key])
  }

  async function handleSave() {
    if (!cfg) return
    setSaving(true)
    try {
      const res = await configApi.save(dirty)
      if (res.config) setCfg(res.config)
      setDirty({})
      toast.success('Configuration saved successfully')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: '48px 32px' }}><LoadingState /></div>
  if (denied) return (
    <div style={{ padding: '48px 32px' }}>
      <div className="glass-card" style={{ padding: '28px', maxWidth: 560 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: 8 }}>Admins only</div>
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
          Voice configuration and provider keys can be viewed and changed by Admins and the workspace Owner.
          Ask one of them if something needs to change.
        </div>
      </div>
    </div>
  )

  const hasDirty = Object.keys(dirty).length > 0

  const navSections = [
    { id: 'greeting', label: 'Greeting & Prompt', icon: MessageSquare },
    { id: 'gemini', label: 'Gemini Runtime', icon: Zap },
    { id: 'session', label: 'Session & Timeout', icon: Settings2 },
    { id: 'livekit', label: 'LiveKit & SIP', icon: Globe2 },
    { id: 'google', label: 'Google API', icon: Shield },
    { id: 'supabase', label: 'Supabase', icon: Database },
    { id: 'telegram', label: 'Telegram', icon: Bell },
    { id: 'kb', label: 'Knowledge Base', icon: Brain },
  ]

  return (
    <div className="page-wrapper">
      <PageHeader
        title="Configuration"
        subtitle="Manage agent settings, integrations, and system configuration"
        accent="#7B61FF"
        actions={
          <Button
            variant="primary"
            loading={saving}
            disabled={!hasDirty}
            icon={<Save size={14} />}
            onClick={handleSave}
            id="save-config-btn"
          >
            {hasDirty ? 'Save Changes' : 'Up to Date'}
          </Button>
        }
      />

      {hasDirty && (
        <div style={{
          margin: '0 32px 16px',
          padding: '10px 16px',
          background: 'rgba(123,97,255,0.08)',
          border: '1px solid rgba(123,97,255,0.25)',
          borderRadius: 10,
          fontSize: 12.5,
          color: '#9580FF',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#7B61FF', boxShadow: '0 0 8px rgba(123,97,255,0.8)', flexShrink: 0 }} />
          {Object.keys(dirty).length} unsaved change{Object.keys(dirty).length !== 1 ? 's' : ''} — click Save Changes to apply
        </div>
      )}

      {offline && (
        <div style={{
          margin: '0 32px 16px',
          padding: '10px 16px',
          background: 'rgba(245,166,35,0.08)',
          border: '1px solid rgba(245,166,35,0.25)',
          borderRadius: 10,
          fontSize: 12.5,
          color: '#F5A623',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <WifiOff size={14} />
          Could not load the saved configuration ({offline}). The form shows defaults; saving would overwrite your settings.
        </div>
      )}

      <div style={{ padding: '0 32px', display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Section Nav */}
        <div className="glass-card" style={{ padding: '8px', position: 'sticky', top: 72 }}>
          {navSections.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => {
                setActiveSection(id)
                document.getElementById(`section-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 10px',
                borderRadius: 9,
                border: 'none',
                background: activeSection === id ? 'rgba(123,97,255,0.15)' : 'transparent',
                color: activeSection === id ? '#9580FF' : 'var(--color-text-muted)',
                fontSize: 12.5,
                fontWeight: activeSection === id ? 600 : 400,
                cursor: 'pointer',
                transition: 'all 0.15s',
                textAlign: 'left',
                marginBottom: 2,
              }}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {/* Sections */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingBottom: 48 }}>

          {/* Greeting & Prompt */}
          <div id="section-greeting">
            <Card>
              <SectionHeader
                icon={<MessageSquare size={16} color="#7B61FF" />}
                title="Greeting & Agent Instructions"
                subtitle="Configure what the AI says and how it behaves"
              />
              <div style={{ marginBottom: 14 }}>
                <Textarea
                  label="First Line (Greeting)"
                  id="first_line"
                  value={str('first_line')}
                  rows={3}
                  onChange={e => set('first_line', e.target.value)}
                  hint="The very first thing the AI says when a call connects"
                />
              </div>
              <Textarea
                label="Agent Instructions (System Prompt)"
                id="agent_instructions"
                value={str('agent_instructions')}
                rows={8}
                hint="Detailed instructions guiding the agent's behavior throughout the call"
                onChange={e => set('agent_instructions', e.target.value)}
              />
            </Card>
          </div>

          {/* Gemini Runtime */}
          <div id="section-gemini">
            <Card>
              <SectionHeader
                icon={<Zap size={16} color="#7B61FF" />}
                title="Gemini Live Runtime"
                subtitle="Model, voice, and performance configuration"
              />
              <FormRow>
                <Input
                  label="Live Model"
                  id="gemini_live_model"
                  value={str('gemini_live_model')}
                  placeholder="gemini-2.0-flash-live-001"
                  onChange={e => set('gemini_live_model', e.target.value)}
                />
                <Select
                  label="Voice"
                  id="gemini_live_voice"
                  value={str('gemini_live_voice')}
                  onChange={e => set('gemini_live_voice', e.target.value)}
                  options={[
                    { value: 'Puck', label: 'Puck' },
                    { value: 'Charon', label: 'Charon' },
                    { value: 'Kore', label: 'Kore' },
                    { value: 'Fenrir', label: 'Fenrir' },
                    { value: 'Aoede', label: 'Aoede' },
                  ]}
                />
              </FormRow>
              <FormRow>
                <Input
                  label="Temperature"
                  id="gemini_live_temperature"
                  type="number"
                  min={0} max={2} step={0.1}
                  value={num('gemini_live_temperature')}
                  onChange={e => set('gemini_live_temperature', parseFloat(e.target.value))}
                />
                <Input
                  label="Language"
                  id="gemini_live_language"
                  value={str('gemini_live_language')}
                  placeholder="Leave empty for multilingual"
                  onChange={e => set('gemini_live_language', e.target.value)}
                />
                <Select
                  label="Language Preset"
                  id="lang_preset"
                  value={str('lang_preset')}
                  onChange={e => set('lang_preset', e.target.value)}
                  options={[
                    { value: 'multilingual', label: 'Multilingual' },
                    { value: 'english', label: 'English' },
                    { value: 'hindi', label: 'Hindi' },
                  ]}
                />
              </FormRow>
              <FormRow>
                <Input label="TTS Model" id="gemini_tts_model" value={str('gemini_tts_model')} onChange={e => set('gemini_tts_model', e.target.value)} />
                <Input label="Connect Timeout (s)" id="gemini_live_connect_timeout" type="number" value={num('gemini_live_connect_timeout')} onChange={e => set('gemini_live_connect_timeout', parseFloat(e.target.value))} />
                <Input label="Connect Retries" id="gemini_live_connect_retries" type="number" value={num('gemini_live_connect_retries')} onChange={e => set('gemini_live_connect_retries', parseInt(e.target.value))} />
              </FormRow>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 6 }}>
                <Toggle
                  id="gemini_live_preflight_enabled"
                  checked={bool('gemini_live_preflight_enabled')}
                  onChange={v => set('gemini_live_preflight_enabled', v)}
                  label="Preflight Enabled"
                  hint="Test connection before accepting calls"
                />
              </div>
              {bool('gemini_live_preflight_enabled') && (
                <div style={{ marginTop: 16, maxWidth: 280 }}>
                  <Input
                    label="Preflight Timeout (s)"
                    id="gemini_live_preflight_timeout"
                    type="number"
                    value={num('gemini_live_preflight_timeout')}
                    onChange={e => set('gemini_live_preflight_timeout', parseFloat(e.target.value))}
                  />
                </div>
              )}
            </Card>
          </div>

          {/* Session */}
          <div id="section-session">
            <Card>
              <SectionHeader
                icon={<Settings2 size={16} color="#7B61FF" />}
                title="Session & Timeout"
                subtitle="Call duration and session management"
              />
              <FormRow>
                <Input label="Max Turns" id="max_turns" type="number" value={num('max_turns')} onChange={e => set('max_turns', parseInt(e.target.value))} />
                <Input label="User Away Timeout (s)" id="user_away_timeout" type="number" value={num('user_away_timeout')} onChange={e => set('user_away_timeout', parseFloat(e.target.value))} />
                <Input label="Close Transcript Timeout (s)" id="session_close_transcript_timeout" type="number" value={num('session_close_transcript_timeout')} onChange={e => set('session_close_transcript_timeout', parseFloat(e.target.value))} />
              </FormRow>
            </Card>
          </div>

          {/* LiveKit */}
          <div id="section-livekit">
            <Card>
              <SectionHeader
                icon={<Globe2 size={16} color="#7B61FF" />}
                title="LiveKit & SIP"
                subtitle="Real-time voice infrastructure configuration"
              />
              <FormRow>
                <Input label="LiveKit URL" id="livekit_url" value={str('livekit_url')} placeholder="wss://your-project.livekit.cloud" onChange={e => set('livekit_url', e.target.value)} />
                <Input label="LiveKit API Key" id="livekit_api_key" value={str('livekit_api_key')} onChange={e => set('livekit_api_key', e.target.value)} />
                <Input
                  label="LiveKit API Secret"
                  id="livekit_api_secret"
                  type="password"
                  value={SECRET_FIELDS.includes('livekit_api_secret') && !dirty['livekit_api_secret'] ? (cfg?.livekit_api_secret ? '••••••••' : '') : str('livekit_api_secret')}
                  placeholder={cfg?.livekit_api_secret ? 'Leave blank to keep current' : 'Enter secret'}
                  onChange={e => set('livekit_api_secret', e.target.value)}
                  hint="Leave blank to keep the existing value"
                />
              </FormRow>
              <FormRow>
                <Input label="SIP Trunk ID" id="sip_trunk_id" value={str('sip_trunk_id')} onChange={e => set('sip_trunk_id', e.target.value)} />
              </FormRow>
            </Card>
          </div>

          {/* Google API */}
          <div id="section-google">
            <Card>
              <SectionHeader
                icon={<Shield size={16} color="#7B61FF" />}
                title="Google API"
                subtitle="Required for Gemini and embedding access"
              />
              <div style={{ maxWidth: 420 }}>
                <Input
                  label="Google API Key"
                  id="google_api_key"
                  type="password"
                  placeholder={cfg?.google_api_key ? 'Leave blank to keep current' : 'Enter key'}
                  onChange={e => set('google_api_key', e.target.value)}
                  hint="Used for Gemini embeddings and live API access."
                />
              </div>
            </Card>
          </div>

          {/* Supabase */}
          <div id="section-supabase">
            <Card>
              <SectionHeader
                icon={<Database size={16} color="#7B61FF" />}
                title="Supabase"
                subtitle="PostgreSQL database and vector store backend"
              />
              <FormRow>
                <Input label="Supabase URL" id="supabase_url" value={str('supabase_url')} placeholder="https://xxx.supabase.co" onChange={e => set('supabase_url', e.target.value)} />
                <Input
                  label="Supabase Key"
                  id="supabase_key"
                  type="password"
                  placeholder={cfg?.supabase_key ? 'Leave blank to keep current' : 'Enter key'}
                  onChange={e => set('supabase_key', e.target.value)}
                  hint="Service role key for backend Supabase access."
                />
              </FormRow>
            </Card>
          </div>

          {/* Telegram */}
          <div id="section-telegram">
            <Card>
              <SectionHeader
                icon={<Bell size={16} color="#7B61FF" />}
                title="Telegram Notifications"
                subtitle="Get notified of bookings and call events"
              />
              <FormRow>
                <Input
                  label="Bot Token"
                  id="telegram_bot_token"
                  type="password"
                  placeholder={cfg?.telegram_bot_token ? 'Leave blank to keep current' : 'Enter token'}
                  onChange={e => set('telegram_bot_token', e.target.value)}
                />
                <Input
                  label="Chat ID"
                  id="telegram_chat_id"
                  value={str('telegram_chat_id')}
                  onChange={e => set('telegram_chat_id', e.target.value)}
                />
              </FormRow>
            </Card>
          </div>

          {/* Knowledge Base */}
          <div id="section-kb">
            <Card>
              <SectionHeader
                icon={<Brain size={16} color="#7B61FF" />}
                title="Knowledge Base"
                subtitle="Vector retrieval, embeddings, and chunking configuration"
              />
              <div style={{ display: 'flex', gap: 24, marginBottom: 18, flexWrap: 'wrap' }}>
                <Toggle id="kb_enabled" checked={bool('kb_enabled')} onChange={v => set('kb_enabled', v)} label="KB Enabled" hint="Enable knowledge base retrieval for all calls" />
                <Toggle id="kb_rerank_enabled" checked={bool('kb_rerank_enabled')} onChange={v => set('kb_rerank_enabled', v)} label="Rerank Enabled" hint="Cross-encoder reranking of retrieved chunks" />
              </div>
              <FormRow>
                <Input label="Backend" id="kb_backend" value={str('kb_backend')} hint="e.g. local_faiss or supabase" onChange={e => set('kb_backend', e.target.value)} />
                <Input label="Data Directory" id="kb_data_dir" value={str('kb_data_dir')} onChange={e => set('kb_data_dir', e.target.value)} />
                <Input label="Top K" id="kb_top_k" type="number" value={num('kb_top_k')} onChange={e => set('kb_top_k', parseInt(e.target.value))} />
              </FormRow>
              <FormRow>
                <Input label="Similarity Threshold" id="kb_similarity_threshold" type="number" step={0.01} value={num('kb_similarity_threshold')} onChange={e => set('kb_similarity_threshold', parseFloat(e.target.value))} />
                <Input label="Context Char Budget" id="kb_context_char_budget" type="number" value={num('kb_context_char_budget')} onChange={e => set('kb_context_char_budget', parseInt(e.target.value))} />
                <Input label="Live Timeout (ms)" id="kb_live_timeout_ms" type="number" value={num('kb_live_timeout_ms')} onChange={e => set('kb_live_timeout_ms', parseInt(e.target.value))} />
              </FormRow>
              <FormRow>
                <Input label="Chunk Size" id="kb_chunk_size" type="number" value={num('kb_chunk_size')} onChange={e => set('kb_chunk_size', parseInt(e.target.value))} />
                <Input label="Chunk Overlap" id="kb_chunk_overlap" type="number" value={num('kb_chunk_overlap')} onChange={e => set('kb_chunk_overlap', parseInt(e.target.value))} />
                <Input label="Worker Poll (s)" id="kb_worker_poll_seconds" type="number" value={num('kb_worker_poll_seconds')} onChange={e => set('kb_worker_poll_seconds', parseInt(e.target.value))} />
              </FormRow>
              <FormRow>
                <Input label="Embedding Provider" id="kb_embedding_provider" value={str('kb_embedding_provider')} onChange={e => set('kb_embedding_provider', e.target.value)} />
                <Input label="Embedding Model" id="kb_embedding_model" value={str('kb_embedding_model')} onChange={e => set('kb_embedding_model', e.target.value)} />
                <Input label="Index Kind" id="kb_index_kind" value={str('kb_index_kind')} onChange={e => set('kb_index_kind', e.target.value)} />
              </FormRow>
              <FormRow>
                <Input label="Fallback Provider" id="kb_embedding_fallback_provider" value={str('kb_embedding_fallback_provider')} onChange={e => set('kb_embedding_fallback_provider', e.target.value)} />
                <Input label="Fallback Model" id="kb_embedding_fallback_model" value={str('kb_embedding_fallback_model')} onChange={e => set('kb_embedding_fallback_model', e.target.value)} />
              </FormRow>
            </Card>
          </div>

          {/* Save footer */}
          {hasDirty && (
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              padding: '16px 0',
              gap: 10,
            }}>
              <Button variant="secondary" onClick={() => { setDirty({}); toast('Changes discarded', { icon: '↩' }) }}>
                Discard
              </Button>
              <Button variant="primary" loading={saving} icon={<Save size={14} />} onClick={handleSave}>
                Save Changes
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
