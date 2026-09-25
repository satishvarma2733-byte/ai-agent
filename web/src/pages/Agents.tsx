import { useEffect, useState, useRef } from 'react'
import {
  Bot, Zap, PhoneCall, Clock, TrendingUp, Settings2, Circle, Activity,
  Plus, Trash2, ChevronRight, ChevronLeft, Check, Mic, Brain,
  Globe, Calendar, Phone, Shield, Volume2, Sliders, BookOpen,
  AlertCircle, X, Copy, ExternalLink, Radio, ArrowUpRight, ServerCog,
} from 'lucide-react'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import NeuralPulse from '../components/ui/NeuralPulse'
import WaveformVisualizer from '../components/ui/WaveformVisualizer'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Textarea from '../components/ui/Textarea'
import Modal from '../components/ui/Modal'
import { LoadingState } from '../components/ui/States'
import { agentsApi } from '../api/agents'
import { configApi } from '../api/config'
import VersionsModal from '../components/agents/VersionsModal'
import NumbersModal from '../components/agents/NumbersModal'
import type { Agent } from '../api/agents'
import toast from 'react-hot-toast'

const STATUS_COLORS: Record<string, string> = {
  active: '#22D3A5',
  processing: '#7B61FF',
  idle: '#F5A623',
  offline: 'var(--color-text-muted)',
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Active',
  processing: 'Processing',
  idle: 'Idle',
  offline: 'Offline',
}

const WIZARD_STEPS = [
  { id: 'identity', label: 'Identity', icon: Bot, desc: 'Name & personality' },
  { id: 'voice', label: 'Voice & LLM', icon: Mic, desc: 'Voice type & model' },
  { id: 'behavior', label: 'Behavior', icon: Brain, desc: 'Instructions & rules' },
  { id: 'deploy', label: 'Deploy', icon: Zap, desc: 'Working hours & routing' },
]

const VOICE_OPTIONS = [
  { value: 'Puck', label: 'Puck', desc: 'Male · Deep & Professional', sample: '🎙️' },
  { value: 'Charon', label: 'Charon', desc: 'Male · Warm & Friendly', sample: '🎙️' },
  { value: 'Kore', label: 'Kore', desc: 'Female · Bright & Energetic', sample: '🎙️' },
  { value: 'Fenrir', label: 'Fenrir', desc: 'Male · Playful & Casual', sample: '🎙️' },
  { value: 'Aoede', label: 'Aoede', desc: 'Female · Soft & Calming', sample: '🎙️' },
  { value: 'Leda', label: 'Leda', desc: 'Female · Clear & Authoritative', sample: '🎙️' },
]

const MODEL_OPTIONS = [
  { value: 'gemini-2.0-flash-live-001', label: 'Gemini 2.0 Flash Live', desc: 'Best for real-time voice — sub-400ms', badge: 'RECOMMENDED' },
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', desc: 'Higher reasoning, standard latency', badge: '' },
  { value: 'gemini-2.0-flash-exp', label: 'Gemini 2.0 Flash Exp', desc: 'Experimental features enabled', badge: 'BETA' },
]

const LANGUAGE_OPTIONS = [
  { value: 'en', label: '🇺🇸 English' },
  { value: 'hi', label: '🇮🇳 Hindi' },
  { value: 'es', label: '🇪🇸 Spanish' },
  { value: 'fr', label: '🇫🇷 French' },
  { value: 'de', label: '🇩🇪 German' },
  { value: 'ar', label: '🇸🇦 Arabic' },
  { value: 'pt', label: '🇧🇷 Portuguese' },
]

const PERSONA_PRESETS = [
  { label: 'Receptionist', icon: Phone, prompt: 'You are a professional receptionist for {company}. Greet callers warmly, answer questions about our services, and schedule appointments. Keep responses concise and helpful. Always maintain a professional tone.' },
  { label: 'Sales Agent', icon: TrendingUp, prompt: 'You are an expert sales agent for {company}. Your goal is to qualify leads, understand their needs, and guide them toward our solutions. Be consultative, not pushy. Handle objections gracefully.' },
  { label: 'Support Agent', icon: Shield, prompt: 'You are a customer support specialist for {company}. Help customers resolve their issues efficiently. Be empathetic, patient, and solution-focused. Escalate complex issues to human agents when needed.' },
  { label: 'Appointment Booker', icon: Calendar, prompt: 'You are an appointment scheduling assistant. Your main role is to check availability and book meetings for customers. Collect name, contact number, and preferred time. Confirm all bookings before finalizing.' },
]

interface AgentFormData {
  name: string
  description: string
  voice: string
  model: string
  status: string
  temperature: number
  tags: string
  instructions: string
  language: string
  greeting: string
  max_call_duration: number
  fallback_phone: string
  working_hours_start: string
  working_hours_end: string
  working_days: string[]
}

// ── Pre-configured Aryan Agent (from backend .env) ───────────────
const ARYAN_PRESET: AgentFormData = {
  name: 'Aryan — AVN AI Inbound Receptionist',
  description: 'AI voice agent for AVN AI. Handles inbound calls, qualifies leads, explains AI automation services, and books consultations. Powered by Gemini 2.0 Flash Live with multilingual support.',
  voice: 'Puck',
  model: 'gemini-2.0-flash-live-001',
  status: 'active',
  temperature: 0.8,
  tags: 'inbound, avn-ai, sales, multilingual, kb-enabled',
  language: 'hi',
  greeting: 'Namaste! This is Aryan from AVN AI - we help businesses automate with AI. Hmm, may I ask what kind of business you run?',
  instructions: `You are Aryan, a friendly and professional AI receptionist for AVN AI — a company that helps businesses automate operations using AI voice agents, CRM automation, and workflow intelligence.

Your primary goals:
1. Warmly greet the caller and understand their business type
2. Qualify their interest in AI automation (size of team, current pain points, budget awareness)
3. Explain AVN AI's key offerings: AI inbound/outbound calling, Voice CRM, Workflow automation
4. Invite them to book a free 30-minute consultation session
5. Collect their name, phone, and preferred time slot
6. If they have technical questions, refer to the Knowledge Base

Tone: Conversational, warm, consultative. Mix Hindi and English naturally (Hinglish) for Indian callers.
Never be pushy. Always listen first, then suggest.
If the caller seems confused, simplify. If they seem technical, go deeper.
Max call duration: 5 minutes. Always aim to end with a next step (booking or callback).`,
  max_call_duration: 300,
  fallback_phone: '',
  working_hours_start: '09:00',
  working_hours_end: '21:00',
  working_days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// ── Agent Card ────────────────────────────────────────────────────
interface AgentCardProps {
  agent: Agent
  onConfigure: (agent: Agent) => void
  onDelete: (id: string) => void
  onDeploy?: (agent: Agent) => void
  onNumbers?: (agent: Agent) => void
  onVersions?: (agent: Agent) => void
  isDeployed?: boolean
}

function AgentCard({ agent, onConfigure, onDelete, onDeploy, onVersions, onNumbers, isDeployed }: AgentCardProps) {
  const color = STATUS_COLORS[agent.status] ?? 'var(--color-text-muted)'
  const isActive = agent.status === 'active' || agent.status === 'processing'
  const [copied, setCopied] = useState(false)

  const copyId = () => {
    navigator.clipboard.writeText(agent.id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div
      className="glass-card"
      style={{
        padding: '20px 22px',
        position: 'relative',
        overflow: 'hidden',
        transition: 'border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease',
        borderColor: isDeployed ? 'rgba(94,230,255,0.4)' : isActive ? 'rgba(123,97,255,0.25)' : undefined,
        boxShadow: isDeployed ? '0 0 0 1px rgba(94,230,255,0.2), 0 8px 40px rgba(0,0,0,0.5)' : isActive ? '0 0 0 1px rgba(123,97,255,0.1), 0 8px 40px rgba(0,0,0,0.5)' : undefined,
      }}
      onMouseOver={e => (e.currentTarget.style.transform = 'translateY(-2px)')}
      onMouseOut={e => (e.currentTarget.style.transform = '')}
    >
      {/* Deployed badge */}
      {isDeployed && (
        <div style={{ position: 'absolute', top: 10, left: 10, display: 'flex', alignItems: 'center', gap: 5, fontSize: 9, fontWeight: 800, color: '#5EE6FF', background: 'rgba(94,230,255,0.1)', padding: '3px 8px', borderRadius: 100, border: '1px solid rgba(94,230,255,0.25)', letterSpacing: '0.06em', animation: 'neural-pulse 2s ease-in-out infinite' }}>
          <Radio size={8} /> RUNTIME ACTIVE
        </div>
      )}
      {/* Glow bg */}
      {isActive && (
        <div style={{
          position: 'absolute', top: -40, right: -40,
          width: 160, height: 160,
          borderRadius: '50%',
          background: color,
          opacity: 0.07,
          filter: 'blur(40px)',
          pointerEvents: 'none',
        }} />
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 13,
            background: `linear-gradient(135deg, ${color}28, ${color}08)`,
            border: `1px solid ${color}35`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <Bot size={19} color={color} />
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {agent.name}
            </div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 1 }}>{agent.voice} · {agent.model.replace('gemini-', 'G').replace('-live-001', ' Live').replace('-flash', ' Flash')}</div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>
              <span style={{ textTransform: 'capitalize', color: agent.lifecycle === 'production' ? '#22D3A5' : agent.lifecycle === 'disabled' ? '#FF8A9B' : '#F5C26B' }}>
                {agent.lifecycle}
              </span>
              {agent.production_version != null && <> · live v{agent.production_version}</>}
              {agent.draft_version != null && <> · draft v{agent.draft_version} (unpublished)</>}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <NeuralPulse color={color} size={9} active={isActive} />
          <Badge
            variant={agent.status === 'active' ? 'success' : agent.status === 'processing' ? 'violet' : agent.status === 'idle' ? 'warning' : 'default'}
            dot={!isActive}
          >
            {STATUS_LABELS[agent.status]}
          </Badge>
        </div>
      </div>

      {/* Waveform if active */}
      {isActive && (
        <div style={{ marginBottom: 14, background: 'rgba(123,97,255,0.05)', borderRadius: 8, padding: '6px 10px' }}>
          <WaveformVisualizer bars={24} color={color} height={28} active />
        </div>
      )}

      {/* Description */}
      {agent.description && (
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 12, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {agent.description}
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
        {[
          { label: 'Today', value: agent.calls_today, icon: PhoneCall },
          { label: 'Total', value: agent.calls_total, icon: Activity },
          { label: 'Success', value: `${agent.success_rate}%`, icon: TrendingUp },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} style={{
            background: 'rgba(255,255,255,0.03)',
            borderRadius: 8, padding: '8px 10px', textAlign: 'center',
          }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>{value}</div>
            <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', marginTop: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
              <Icon size={9} color="#4B5675" />
              {label}
            </div>
          </div>
        ))}
      </div>

      {/* Tags */}
      {agent.tags && agent.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 12 }}>
          {agent.tags.map((tag) => (
            <span key={tag} className="avn-chip avn-chip-gray" style={{ fontSize: 10 }}>{tag}</span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.04)',
      }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={copyId}
              title="Copy Agent ID"
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '3px 8px',
                background: 'transparent', border: 'none',
                color: copied ? '#22D3A5' : 'var(--color-text-muted)',
                fontSize: 10.5, fontFamily: 'monospace', cursor: 'pointer',
                transition: 'color 0.15s',
              }}
            >
              {copied ? <Check size={10} /> : <Copy size={10} />}
              {agent.id.slice(0, 8)}…
            </button>
            {onVersions && (
              <button
                onClick={() => onVersions(agent)}
                title="Versions and approvals"
                style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 9px', background: 'rgba(123,97,255,0.08)', border: '1px solid rgba(123,97,255,0.18)', borderRadius: 6, color: '#9580FF', fontSize: 10.5, fontWeight: 600, cursor: 'pointer' }}
              >
                Versions
              </button>
            )}
            {onNumbers && (
              <button
                onClick={() => onNumbers(agent)}
                title="Business numbers this agent answers"
                style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 9px', background: 'rgba(34,211,165,0.08)', border: '1px solid rgba(34,211,165,0.18)', borderRadius: 6, color: '#22D3A5', fontSize: 10.5, fontWeight: 600, cursor: 'pointer' }}
              >
                Numbers
              </button>
            )}
            {onDeploy && (
              <button
                onClick={() => onDeploy(agent)}
                title="Answer calls to numbers that aren't connected to any agent"
                style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 9px', background: 'rgba(94,230,255,0.08)', border: '1px solid rgba(94,230,255,0.15)', borderRadius: 6, color: '#5EE6FF', fontSize: 10.5, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s' }}
              >
                <Radio size={9} /> Set as default
              </button>
            )}
          </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button aria-label={`Delete ${agent.name}`}
            onClick={() => onDelete(agent.id)}
            style={{ width: 28, height: 28, borderRadius: 7, background: 'transparent', border: '1px solid rgba(255,77,106,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--color-text-muted)', transition: 'all 0.15s' }}
            onMouseOver={e => { e.currentTarget.style.background = 'rgba(255,77,106,0.1)'; e.currentTarget.style.color = '#FF4D6A' }}
            onMouseOut={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--color-text-muted)' }}
          >
            <Trash2 size={12} />
          </button>
          <button
            onClick={() => onConfigure(agent)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 12px', background: 'rgba(123,97,255,0.1)',
              border: '1px solid rgba(123,97,255,0.2)', borderRadius: 7,
              color: '#9580FF', fontSize: 11.5, fontWeight: 600,
              cursor: 'pointer', transition: 'all 0.15s',
            }}
            onMouseOver={e => { e.currentTarget.style.background = 'rgba(123,97,255,0.2)'; e.currentTarget.style.borderColor = 'rgba(123,97,255,0.4)' }}
            onMouseOut={e => { e.currentTarget.style.background = 'rgba(123,97,255,0.1)'; e.currentTarget.style.borderColor = 'rgba(123,97,255,0.2)' }}
          >
            <Settings2 size={12} /> Configure
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Wizard Step Indicator ─────────────────────────────────────────
function WizardSteps({ step, setStep, maxReached }: { step: number; setStep: (s: number) => void; maxReached: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', padding: '20px 24px 0', gap: 0 }}>
      {WIZARD_STEPS.map((s, i) => {
        const done = i < step
        const active = i === step
        const reachable = i <= maxReached
        const Icon = s.icon
        return (
          <div key={s.id} style={{ display: 'flex', alignItems: 'center', flex: i < WIZARD_STEPS.length - 1 ? 1 : 0 }}>
            <button
              onClick={() => reachable && setStep(i)}
              disabled={!reachable}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                background: 'transparent', border: 'none', cursor: reachable ? 'pointer' : 'default',
                padding: '0 4px', minWidth: 60,
              }}
            >
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: done ? 'linear-gradient(135deg, #22D3A5, #15997A)' : active ? 'linear-gradient(135deg, #7B61FF, #5EE6FF)' : 'rgba(255,255,255,0.04)',
                border: done ? '1px solid rgba(34,211,165,0.4)' : active ? '1px solid rgba(123,97,255,0.4)' : '1px solid rgba(255,255,255,0.07)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: active ? '0 0 16px rgba(123,97,255,0.3)' : 'none',
                transition: 'all 0.2s',
              }}>
                {done ? <Check size={15} color="#fff" /> : <Icon size={15} color={active ? '#fff' : 'var(--color-text-muted)'} />}
              </div>
              <span style={{ fontSize: 10.5, fontWeight: active ? 700 : 500, color: active ? 'var(--color-text-primary)' : done ? '#22D3A5' : 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                {s.label}
              </span>
            </button>
            {i < WIZARD_STEPS.length - 1 && (
              <div style={{ flex: 1, height: 1, background: done ? 'rgba(34,211,165,0.3)' : 'rgba(255,255,255,0.06)', margin: '0 4px', marginBottom: 20, transition: 'background 0.3s' }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Step 1: Identity ──────────────────────────────────────────────
function StepIdentity({ form, setForm }: { form: AgentFormData; setForm: React.Dispatch<React.SetStateAction<AgentFormData>> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ background: 'rgba(123,97,255,0.06)', border: '1px solid rgba(123,97,255,0.12)', borderRadius: 12, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg, #7B61FF, #5EE6FF)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 0 16px rgba(123,97,255,0.3)' }}>
          <Bot size={18} color="#fff" />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Agent Identity</div>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Define who your AI voice agent is</div>
        </div>
      </div>

      <Input
        label="Agent Name *"
        id="agent-name"
        value={form.name}
        placeholder="e.g. Aria — NMC Inbound Receptionist"
        onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
      />

      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>Persona Preset (optional)</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {PERSONA_PRESETS.map(p => {
            const Icon = p.icon
            const isSelected = form.instructions === p.prompt
            return (
              <button
                key={p.label}
                onClick={() => setForm(f => ({ ...f, instructions: p.prompt }))}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
                  background: isSelected ? 'rgba(123,97,255,0.12)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${isSelected ? 'rgba(123,97,255,0.4)' : 'rgba(255,255,255,0.07)'}`,
                  borderRadius: 10, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                }}
              >
                <div style={{ width: 28, height: 28, borderRadius: 8, background: isSelected ? 'rgba(123,97,255,0.2)' : 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon size={14} color={isSelected ? '#9580FF' : 'var(--color-text-muted)'} />
                </div>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: isSelected ? '#9580FF' : 'var(--color-text-secondary)' }}>{p.label}</span>
                {isSelected && <Check size={12} color="#9580FF" style={{ marginLeft: 'auto' }} />}
              </button>
            )
          })}
        </div>
      </div>

      <Input
        label="Brief Description"
        id="agent-desc"
        value={form.description}
        placeholder="e.g. Handles inbound calls for NMC consulting, books appointments"
        onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Select
          label="Primary Language"
          id="agent-lang"
          value={form.language}
          options={LANGUAGE_OPTIONS}
          onChange={e => setForm(f => ({ ...f, language: e.target.value }))}
        />
        <Input
          label="Tags (comma separated)"
          id="agent-tags"
          value={form.tags}
          placeholder="inbound, sales, support"
          onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
        />
      </div>
    </div>
  )
}

// ── Step 2: Voice & LLM ───────────────────────────────────────────
function StepVoice({ form, setForm }: { form: AgentFormData; setForm: React.Dispatch<React.SetStateAction<AgentFormData>> }) {
  const [playing, setPlaying] = useState<string | null>(null)

  const previewVoice = (voiceName: string) => {
    setPlaying(voiceName)
    setTimeout(() => setPlaying(null), 2000)
    toast(`🎙️ ${voiceName} voice preview (sample TTS)`, { icon: '🔊' })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 10 }}>Select Voice</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {VOICE_OPTIONS.map(v => {
            const isSelected = form.voice === v.value
            const isPlaying = playing === v.value
            return (
              <div
                key={v.value}
                onClick={() => setForm(f => ({ ...f, voice: v.value }))}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px',
                  background: isSelected ? 'rgba(123,97,255,0.1)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${isSelected ? 'rgba(123,97,255,0.35)' : 'rgba(255,255,255,0.06)'}`,
                  borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                <div style={{
                  width: 36, height: 36, borderRadius: 9,
                  background: isSelected ? 'linear-gradient(135deg, #7B61FF, #5EE6FF)' : 'rgba(255,255,255,0.06)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  boxShadow: isSelected ? '0 0 12px rgba(123,97,255,0.3)' : 'none',
                }}>
                  {isPlaying
                    ? <WaveformVisualizer bars={8} color="#fff" height={18} active />
                    : <Mic size={15} color={isSelected ? '#fff' : 'var(--color-text-muted)'} />
                  }
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: isSelected ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>{v.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{v.desc}</div>
                </div>
                {isSelected && (
                  <button
                    onClick={e => { e.stopPropagation(); previewVoice(v.value) }}
                    style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px', background: 'rgba(123,97,255,0.15)', border: '1px solid rgba(123,97,255,0.25)', borderRadius: 7, color: '#9580FF', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}
                  >
                    <Volume2 size={10} /> Preview
                  </button>
                )}
                {isSelected && !isPlaying && <Check size={14} color="#9580FF" />}
              </div>
            )
          })}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 10 }}>LLM Model</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {MODEL_OPTIONS.map(m => {
            const isSelected = form.model === m.value
            return (
              <div
                key={m.value}
                onClick={() => setForm(f => ({ ...f, model: m.value }))}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px',
                  background: isSelected ? 'rgba(123,97,255,0.1)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${isSelected ? 'rgba(123,97,255,0.35)' : 'rgba(255,255,255,0.06)'}`,
                  borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                <div style={{ width: 36, height: 36, borderRadius: 9, background: isSelected ? 'rgba(123,97,255,0.2)' : 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Zap size={15} color={isSelected ? '#9580FF' : 'var(--color-text-muted)'} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: isSelected ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>{m.label}</span>
                    {m.badge && <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: m.badge === 'RECOMMENDED' ? 'rgba(34,211,165,0.15)' : 'rgba(245,166,35,0.15)', color: m.badge === 'RECOMMENDED' ? '#22D3A5' : '#F5A623', letterSpacing: '0.05em' }}>{m.badge}</span>}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{m.desc}</div>
                </div>
                {isSelected && <Check size={14} color="#9580FF" />}
              </div>
            )
          })}
        </div>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)' }}>Temperature — Creativity</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: '#9580FF' }}>{form.temperature.toFixed(1)}</span>
        </div>
        <input
          type="range" min="0" max="1" step="0.1"
          value={form.temperature}
          onChange={e => setForm(f => ({ ...f, temperature: parseFloat(e.target.value) }))}
          style={{ width: '100%', accentColor: '#7B61FF' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>Precise & factual</span>
          <span style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>Creative & varied</span>
        </div>
      </div>
    </div>
  )
}

// ── Step 3: Behavior ──────────────────────────────────────────────
function StepBehavior({ form, setForm }: { form: AgentFormData; setForm: React.Dispatch<React.SetStateAction<AgentFormData>> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Textarea
        label="Greeting Message (first thing agent says)"
        id="agent-greeting"
        value={form.greeting}
        rows={3}
        placeholder="Hello, thank you for calling {company}! I'm Aria, your AI assistant. How can I help you today?"
        onChange={e => setForm(f => ({ ...f, greeting: e.target.value }))}
      />

      <Textarea
        label="System Instructions / Persona Prompt"
        id="agent-instructions"
        value={form.instructions}
        rows={6}
        placeholder="You are a professional AI receptionist for {company}. Your role is to:&#10;1. Greet callers warmly and professionally&#10;2. Answer questions about services&#10;3. Schedule appointments&#10;4. Handle objections gracefully..."
        onChange={e => setForm(f => ({ ...f, instructions: e.target.value }))}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Select
          label="Runtime Status"
          id="agent-status"
          value={form.status}
          options={[
            { value: 'active', label: 'Active (Live feed)' },
            { value: 'processing', label: 'Processing' },
            { value: 'idle', label: 'Idle / Standby' },
            { value: 'offline', label: 'Offline / Sleep' },
          ]}
          onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
        />
        <Input
          label="Max Call Duration (seconds)"
          id="agent-maxdur"
          type="number"
          value={String(form.max_call_duration)}
          placeholder="300"
          onChange={e => setForm(f => ({ ...f, max_call_duration: parseInt(e.target.value) || 300 }))}
        />
      </div>

      <div style={{ background: 'rgba(245,166,35,0.06)', border: '1px solid rgba(245,166,35,0.15)', borderRadius: 10, padding: '12px 14px', display: 'flex', gap: 10 }}>
        <AlertCircle size={14} color="#F5A623" style={{ flexShrink: 0, marginTop: 1 }} />
        <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
          Use <code style={{ color: '#F5A623', background: 'rgba(245,166,35,0.1)', padding: '1px 5px', borderRadius: 4 }}>{'{company}'}</code> and <code style={{ color: '#F5A623', background: 'rgba(245,166,35,0.1)', padding: '1px 5px', borderRadius: 4 }}>{'{agent_name}'}</code> placeholders in your instructions — they'll be replaced at runtime.
        </div>
      </div>
    </div>
  )
}

// ── Step 4: Deploy ────────────────────────────────────────────────
function StepDeploy({ form, setForm, isEdit }: { form: AgentFormData; setForm: React.Dispatch<React.SetStateAction<AgentFormData>>; isEdit: boolean }) {
  const toggleDay = (day: string) => {
    setForm(f => ({
      ...f,
      working_days: f.working_days.includes(day)
        ? f.working_days.filter(d => d !== day)
        : [...f.working_days, day]
    }))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Working Hours */}
      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, padding: '14px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Calendar size={14} color="#5EE6FF" />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Working Hours</span>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {DAYS.map(day => {
            const active = form.working_days.includes(day)
            return (
              <button
                key={day}
                onClick={() => toggleDay(day)}
                style={{
                  flex: 1, padding: '6px 2px', borderRadius: 8, fontSize: 11, fontWeight: 600,
                  background: active ? 'rgba(94,230,255,0.12)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${active ? 'rgba(94,230,255,0.3)' : 'rgba(255,255,255,0.07)'}`,
                  color: active ? '#5EE6FF' : 'var(--color-text-muted)', cursor: 'pointer', transition: 'all 0.15s',
                }}
              >{day}</button>
            )
          })}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Input
            label="Start Time"
            id="agent-start"
            type="time"
            value={form.working_hours_start}
            onChange={e => setForm(f => ({ ...f, working_hours_start: e.target.value }))}
          />
          <Input
            label="End Time"
            id="agent-end"
            type="time"
            value={form.working_hours_end}
            onChange={e => setForm(f => ({ ...f, working_hours_end: e.target.value }))}
          />
        </div>
      </div>

      {/* Fallback */}
      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, padding: '14px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Phone size={14} color="#7B61FF" />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Fallback Routing</span>
        </div>
        <Input
          label="Fallback Phone Number (when agent is offline)"
          id="agent-fallback"
          value={form.fallback_phone}
          placeholder="+91 98765 43210"
          onChange={e => setForm(f => ({ ...f, fallback_phone: e.target.value }))}
        />
      </div>

      {/* Summary */}
      <div style={{ background: 'rgba(34,211,165,0.06)', border: '1px solid rgba(34,211,165,0.15)', borderRadius: 12, padding: '14px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Check size={14} color="#22D3A5" />
          <span style={{ fontSize: 13, fontWeight: 600, color: '#22D3A5' }}>Configuration Summary</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {[
            { label: 'Name', value: form.name || '—' },
            { label: 'Voice', value: form.voice },
            { label: 'Model', value: form.model.replace('gemini-', 'Gemini ') },
            { label: 'Language', value: form.language.toUpperCase() },
            { label: 'Status', value: form.status },
            { label: 'Working Days', value: form.working_days.join(', ') || 'None' },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--color-text-muted)' }}>{label}</span>
              <span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────
export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isEdit, setIsEdit] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [wizardStep, setWizardStep] = useState(0)
  const [maxReached, setMaxReached] = useState(0)
  const [form, setForm] = useState<AgentFormData>(ARYAN_PRESET)
  const [deployedAgentId, setDeployedAgentId] = useState<string | null>(null)
  const [deploying, setDeploying] = useState(false)
  const [showDeployConfirm, setShowDeployConfirm] = useState<Agent | null>(null)
  const [versionsFor, setVersionsFor] = useState<Agent | null>(null)
  const [numbersFor, setNumbersFor] = useState<Agent | null>(null)

  const loadAgents = async () => {
    setLoading(true)
    try {
      const data = await agentsApi.list()
      setAgents(data)
      // Mark first active agent as deployed by default
      const activeAgent = data.find((a: Agent) => a.status === 'active')
      if (activeAgent && !deployedAgentId) setDeployedAgentId(activeAgent.id)
    } catch {
      toast.error('Failed to load agents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAgents() }, [])

  // Deploy agent to live runtime
  // Pushes the agent's *production* version into the (single, shared) voice runtime config.
  // Drafts are never deployed; per-agent runtime dispatch replaces this in Milestone 3 (task 3.4).
  const deployToRuntime = async (agent: Agent) => {
    setDeploying(true)
    try {
      const production = (await agentsApi.versions(agent.id)).find(v => v.status === 'production')
      if (!production) {
        toast.error(`"${agent.name}" has no production version yet. Open Versions to test, approve, and activate one.`)
        return
      }
      const config = production.config as {
        instructions: string
        greetings: Record<string, string>
        languages: { supported: string[]; default: string }
        llm: { temperature: number }
        voice: { voice: string; live_model: string }
        limits: { max_call_seconds: number }
      }
      const lang = config.languages.default
      const configPatch = {
        gemini_live_voice: config.voice.voice,
        gemini_live_model: config.voice.live_model,
        gemini_live_temperature: config.llm.temperature,
        gemini_live_language: lang,
        first_line: config.greetings[lang] || config.instructions.split('\n')[0] || '',
        agent_instructions: config.instructions,
        max_turns: Math.max(5, Math.floor(config.limits.max_call_seconds / 20)),
        lang_preset: config.languages.supported.length > 1 || lang !== 'en' ? 'multilingual' : 'en',
      }
      await configApi.save(configPatch)
      setDeployedAgentId(agent.id)
      setAgents(prev => prev.map(a => ({
        ...a,
        status: a.id === agent.id ? 'active' : (a.status === 'active' ? 'idle' : a.status)
      })))
      toast.success(`"${agent.name}" v${production.number} deployed to the live runtime`, { duration: 4000 })
    } catch (err) {
      toast.error(`Deploy failed: ${err instanceof Error ? err.message : 'Backend unreachable'}`)
    } finally {
      setDeploying(false)
      setShowDeployConfirm(null)
    }
  }

  const openCreate = () => {
    setForm(ARYAN_PRESET)  // Pre-fill with Aryan config
    setIsEdit(false)
    setEditId(null)
    setWizardStep(0)
    setMaxReached(0)
    setIsModalOpen(true)
  }

  const openEdit = (agent: Agent) => {
    const a = agent as any
    setForm({
      name: agent.name || '',
      description: agent.description || '',
      voice: agent.voice || 'Puck',
      model: agent.model || 'gemini-2.0-flash-live-001',
      status: agent.status || 'idle',
      temperature: a.temperature ?? 0.7,
      tags: (agent.tags || []).join(', '),
      instructions: a.instructions || '',
      language: a.language || 'en',
      greeting: a.greeting || '',
      max_call_duration: a.max_call_duration ?? 300,
      fallback_phone: a.fallback_phone || '',
      working_hours_start: a.working_hours_start || '09:00',
      working_hours_end: a.working_hours_end || '18:00',
      working_days: a.working_days || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
    })
    setIsEdit(true)
    setEditId(agent.id)
    setWizardStep(0)
    setMaxReached(3)
    setIsModalOpen(true)
  }

  const goNext = () => {
    if (!form.name && wizardStep === 0) {
      toast.error('Agent Name is required')
      return
    }
    const next = Math.min(wizardStep + 1, WIZARD_STEPS.length - 1)
    setWizardStep(next)
    setMaxReached(prev => Math.max(prev, next))
  }

  const handleSave = async () => {
    if (!form.name) { toast.error('Agent Name is required'); return }
    const payload = {
      name: form.name,
      description: form.description,
      voice: form.voice,
      model: form.model,
      status: form.status as any,
      temperature: form.temperature,
      tags: form.tags.split(',').map(s => s.trim()).filter(Boolean),
      instructions: form.instructions,
      language: form.language,
      greeting: form.greeting,
      max_call_duration: form.max_call_duration,
      fallback_phone: form.fallback_phone,
      working_hours_start: form.working_hours_start,
      working_hours_end: form.working_hours_end,
      working_days: form.working_days,
    }
    try {
      if (isEdit && editId) {
        const updated = await agentsApi.update(editId, payload)
        toast.success(updated.draft_version
          ? `Saved to draft v${updated.draft_version}. Production is unchanged until it's activated.`
          : 'Agent updated')
        setAgents(prev => prev.map(a => a.id === editId ? updated : a))
      } else {
        const created = await agentsApi.create(payload)
        toast.success('Agent created as draft v1')
        setAgents(prev => [...prev, created])
      }
      setIsModalOpen(false)
    } catch (err: any) {
      toast.error(err.message || 'Failed to save agent')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this agent?')) return
    try {
      const res = await agentsApi.delete(id)
      if (res.success) {
        toast.success('Agent deleted')
        setAgents(prev => prev.filter(a => a.id !== id))
      }
    } catch {
      toast.error('Failed to delete agent')
    }
  }

  const active = agents.filter(a => a.status === 'active' || a.status === 'processing')
  const idle = agents.filter(a => a.status === 'idle')
  const offline = agents.filter(a => a.status === 'offline')

  const renderStep = () => {
    switch (wizardStep) {
      case 0: return <StepIdentity form={form} setForm={setForm} />
      case 1: return <StepVoice form={form} setForm={setForm} />
      case 2: return <StepBehavior form={form} setForm={setForm} />
      case 3: return <StepDeploy form={form} setForm={setForm} isEdit={isEdit} />
      default: return null
    }
  }

  return (
    <div className="page-wrapper">
      {versionsFor && (
        <VersionsModal agent={versionsFor} onClose={() => setVersionsFor(null)} onChanged={() => { void loadAgents() }} />
      )}
      <NumbersModal agent={numbersFor} onClose={() => setNumbersFor(null)} />
      {/* Header */}
      <div style={{ padding: '32px 32px 0', marginBottom: 28 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(94,230,255,0.04))',
          border: '1px solid rgba(123,97,255,0.12)',
          borderRadius: 18, padding: '24px 28px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{ position: 'absolute', top: -60, right: -60, width: 200, height: 200, borderRadius: '50%', background: 'rgba(123,97,255,0.08)', filter: 'blur(60px)', pointerEvents: 'none' }} />
          <div>
            <div style={{
              fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em',
              background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #9580FF)',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 6,
            }}>AI Agents</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Autonomous voice agents powered by Gemini Live Runtime</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button variant="primary" icon={<Plus size={15} />} onClick={openCreate}>Create Agent</Button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(123,97,255,0.08)', padding: '6px 12px', borderRadius: 10, border: '1px solid rgba(123,97,255,0.15)' }}>
              <Zap size={14} color="#7B61FF" />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#7B61FF' }}>{active.length} Active</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ padding: '0 32px' }}>
        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
          <GradientStatCard label="Total Agents" value={agents.length} icon={<Bot size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={0} />
          <GradientStatCard label="Active Now" value={active.length} icon={<Circle size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={80} />
          <GradientStatCard label="Idle / Standby" value={idle.length} icon={<Clock size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={160} />
          <GradientStatCard label="Offline" value={offline.length} icon={<PhoneCall size={20} color="#fff" />} gradient="linear-gradient(135deg,#4B5675,#374151)" delay={240} />
        </div>

        {loading ? (
          <LoadingState />
        ) : agents.length === 0 ? (
          <Card style={{ textAlign: 'center', padding: 48 }}>
            <div style={{ width: 64, height: 64, borderRadius: 18, background: 'linear-gradient(135deg, rgba(123,97,255,0.15), rgba(94,230,255,0.05))', border: '1px solid rgba(123,97,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
              <Bot size={28} color="#7B61FF" />
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 8 }}>No Voice Agents configured</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 24, maxWidth: 320, margin: '0 auto 24px' }}>Create your first Gemini Live voice agent to handle inbound or outbound calls automatically</div>
            <Button variant="primary" icon={<Plus size={14} />} onClick={openCreate}>Create your first agent</Button>
          </Card>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Runtime Status Banner */}
            {deployedAgentId && (() => {
              const deployed = agents.find(a => a.id === deployedAgentId)
              return deployed ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 20px', background: 'rgba(94,230,255,0.06)', border: '1px solid rgba(94,230,255,0.2)', borderRadius: 14, animation: 'fadeInUp 0.3s ease both' }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(94,230,255,0.1)', border: '1px solid rgba(94,230,255,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Radio size={16} color="#5EE6FF" />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#5EE6FF' }}>Live Runtime: <span style={{ color: 'var(--color-text-primary)' }}>{deployed.name}</span></div>
                    <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 2 }}>Default agent: answers numbers not connected to another agent · Voice: {deployed.voice} · Model: {deployed.model.replace('gemini-', 'Gemini ')}</div>
                  </div>
                  <Badge variant="info" dot>RUNTIME ACTIVE</Badge>
                </div>
              ) : null
            })()}

            {/* Agent Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
              {agents.map((agent, i) => (
                <div key={agent.id} style={{ animation: `fadeInUp 0.4s cubic-bezier(0.22,1,0.36,1) ${i * 60}ms both` }}>
                  <AgentCard
                    agent={agent}
                    onConfigure={openEdit}
                    onDelete={handleDelete}
                    onDeploy={a => setShowDeployConfirm(a)}
                    onVersions={a => setVersionsFor(a)}
                    onNumbers={a => setNumbersFor(a)}
                    isDeployed={agent.id === deployedAgentId}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        {!loading && (
          <Card style={{ marginTop: 24, background: 'rgba(123,97,255,0.04)', borderColor: 'rgba(123,97,255,0.1)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: 'linear-gradient(135deg, #7B61FF, #5EE6FF)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 20px rgba(123,97,255,0.4)' }}>
                <Zap size={18} color="#fff" />
              </div>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Gemini Live Runtime</div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Agents run on Google Gemini Live with real-time audio streaming</div>
              </div>
              <a
                href="https://ai.google.dev/gemini-api/docs/live"
                target="_blank"
                rel="noopener noreferrer"
                style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#7B61FF', textDecoration: 'none', fontWeight: 500, flexShrink: 0 }}
              >
                Docs <ExternalLink size={11} />
              </a>
            </div>
          </Card>
        )}
      </div>

      {/* ── Deploy Confirm Modal ── */}
      <Modal
        open={!!showDeployConfirm}
        onClose={() => setShowDeployConfirm(null)}
        title="Deploy Agent to Runtime"
        width={480}
      >
        {showDeployConfirm && (
          <div style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', background: 'rgba(94,230,255,0.06)', border: '1px solid rgba(94,230,255,0.15)', borderRadius: 12, marginBottom: 20 }}>
              <div style={{ width: 40, height: 40, borderRadius: 11, background: 'rgba(94,230,255,0.1)', border: '1px solid rgba(94,230,255,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Radio size={18} color="#5EE6FF" />
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>{showDeployConfirm.name}</div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2 }}>Voice: {showDeployConfirm.voice} · Model: {showDeployConfirm.model.replace('gemini-', 'Gemini ')}</div>
              </div>
            </div>

            <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.6, marginBottom: 14 }}>
              Deploying this agent will update the <strong style={{ color: '#5EE6FF' }}>live runtime config</strong> and apply:
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '12px 14px', marginBottom: 20 }}>
              {[
                { k: 'Voice', v: showDeployConfirm.voice },
                { k: 'Model', v: showDeployConfirm.model.replace('gemini-', 'Gemini ') },
                { k: 'Greeting', v: ((showDeployConfirm as any).greeting || '').slice(0, 60) + '…' || 'Default greeting' },
                { k: 'Instructions', v: ((showDeployConfirm as any).instructions || '').slice(0, 80) + '…' },
                { k: 'Temperature', v: String((showDeployConfirm as any).temperature ?? 0.8) },
                { k: 'Working Hours', v: `${(showDeployConfirm as any).working_hours_start ?? '09:00'} – ${(showDeployConfirm as any).working_hours_end ?? '18:00'}` },
              ].map(({ k, v }) => v && v !== '…' && (
                <div key={k} style={{ display: 'flex', gap: 10, fontSize: 12, marginBottom: 6 }}>
                  <span style={{ color: 'var(--color-text-muted)', width: 100, flexShrink: 0 }}>{k}</span>
                  <span style={{ color: 'var(--color-text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
                </div>
              ))}
            </div>

            <div style={{ background: 'rgba(245,166,35,0.07)', border: '1px solid rgba(245,166,35,0.15)', borderRadius: 10, padding: '10px 12px', marginBottom: 20, fontSize: 12, color: '#F5A623' }}>
              ⚠️ This will immediately affect live calls. Any active calls will continue with the previous config.
            </div>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Button variant="ghost" onClick={() => setShowDeployConfirm(null)}>Cancel</Button>
              <Button
                variant="primary"
                icon={<Radio size={13} />}
                onClick={() => deployToRuntime(showDeployConfirm)}
                disabled={deploying}
              >
                {deploying ? 'Deploying…' : 'Deploy to Runtime'}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* ── Agent Wizard Modal ── */}
      <Modal
        open={isModalOpen}
        onClose={() => { setIsModalOpen(false) }}
        title={isEdit ? `Edit Agent — ${form.name || '…'}` : 'Create New AI Agent'}
        width={600}
      >
        <div>
          <WizardSteps step={wizardStep} setStep={setWizardStep} maxReached={maxReached} />

          <div style={{ padding: '20px 24px', minHeight: 360 }}>
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: 3 }}>
                {WIZARD_STEPS[wizardStep].label}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{WIZARD_STEPS[wizardStep].desc}</div>
            </div>
            <div style={{ marginTop: 16 }}>
              {renderStep()}
            </div>
          </div>

          {/* Footer actions */}
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 24px', borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(0,0,0,0.2)' }}>
            <div>
              {isEdit && editId && (
                <Button variant="danger" icon={<Trash2 size={13} />} onClick={() => { handleDelete(editId); setIsModalOpen(false) }}>
                  Delete
                </Button>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {wizardStep > 0 && (
                <Button variant="ghost" icon={<ChevronLeft size={14} />} onClick={() => setWizardStep(w => w - 1)}>Back</Button>
              )}
              <Button variant="ghost" onClick={() => setIsModalOpen(false)}>Cancel</Button>
              {wizardStep < WIZARD_STEPS.length - 1 ? (
                <Button variant="primary" onClick={goNext}>
                  Next <ChevronRight size={14} />
                </Button>
              ) : (
                <Button variant="primary" icon={<Check size={14} />} onClick={handleSave}>
                  {isEdit ? 'Save Changes' : 'Deploy Agent'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
