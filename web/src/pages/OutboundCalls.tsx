import { useEffect, useState, useRef, type ReactNode } from 'react'
import {
  PhoneOutgoing, Phone, Users, CheckCircle2, XCircle, Upload,
  Activity, Globe2, Zap, ArrowRight, FileSpreadsheet, Trash2,
  Radio, Clock, PhoneForwarded, Voicemail, PhoneOff, Play,
  BarChart3, Pause, PlayCircle, Download, MapPin
} from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import NeuralPulse from '../components/ui/NeuralPulse'
import Badge from '../components/ui/Badge'
import Input from '../components/ui/Input'
import Textarea from '../components/ui/Textarea'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import { LoadingState, EmptyState } from '../components/ui/States'
import type { SingleCallResult, BulkCallEntry, InboundCall, Campaign, ColumnMapping } from '../types'
import { campaignsApi } from '../api/campaigns'
import { callsApi } from '../api/calls'
import { apiUrl } from '../api/client'
import { logsApi } from '../api/logs'
import { useSearchParams } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import WaveformVisualizer from '../components/ui/WaveformVisualizer'

type Tab = 'single' | 'bulk' | 'campaigns'

// ── Parse CSV/Excel-like text ───────────────────────────────────
function parseFileToNumbers(text: string): string[] {
  return text
    .split(/[\n,;\t]/)
    .map(s => s.replace(/[^+0-9]/g, '').trim())
    .filter(s => s.length >= 7)
}

// ── Result row ──────────────────────────────────────────────────
function ResultRow({ r, index }: { r: BulkCallEntry; index: number }) {
  const ok = r.status === 'ok'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '11px 20px',
      borderBottom: '1px solid rgba(255,255,255,0.03)',
      animation: `fadeInUp 0.2s cubic-bezier(0.22,1,0.36,1) ${index * 20}ms both`,
    }}>
      {ok
        ? <CheckCircle2 size={14} color="#22D3A5" style={{ flexShrink: 0 }} />
        : <XCircle size={14} color="#FF4D6A" style={{ flexShrink: 0 }} />}
      <span style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--color-text-primary)', flex: 1 }}>{r.phone}</span>
      {ok
        ? <span style={{ fontSize: 11, color: 'var(--color-text-muted)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.dispatch_id}</span>
        : <span style={{ fontSize: 11.5, color: '#FF4D6A' }}>{r.message}</span>
      }
      <Badge variant={ok ? 'success' : 'danger'} dot>{ok ? 'Sent' : 'Failed'}</Badge>
    </div>
  )
}

const STATUS_CONFIG: Record<string, { label: string; color: string; badge: 'success' | 'violet' | 'warning' | 'info' | 'default' }> = {
  live:        { label: 'LIVE', color: '#22D3A5', badge: 'success' },
  queued:      { label: 'QUEUED', color: '#7B61FF', badge: 'violet' },
  completed:   { label: 'COMPLETED', color: 'var(--color-text-muted)', badge: 'default' },
  transferred: { label: 'TRANSFERRED', color: '#5EE6FF', badge: 'info' },
  voicemail:   { label: 'VOICEMAIL', color: '#F5A623', badge: 'warning' },
}

interface CallRowProps {
  call: InboundCall
  onAction: (action: string, id: string) => void
  isExpanded: boolean
  transcript: string | null
  loadingTranscript: boolean
}

function CallRow({ call, onAction, isExpanded, transcript, loadingTranscript }: CallRowProps) {
  const cfg = STATUS_CONFIG[call.status] ?? STATUS_CONFIG.completed
  const isLive = call.status === 'live'
  const isQueued = call.status === 'queued'

  return (
    <div style={{
      borderBottom: '1px solid rgba(255,255,255,0.03)',
      background: isLive ? 'rgba(34,211,165,0.03)' : isQueued ? 'rgba(123,97,255,0.03)' : 'transparent',
      transition: 'background 0.15s',
      position: 'relative',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '14px 20px',
      }}>
        {isLive && (
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: '#22D3A5', borderRadius: '0 3px 3px 0', boxShadow: '0 0 10px rgba(34,211,165,0.5)' }} />
        )}

        {/* Status indicator */}
        <NeuralPulse color={cfg.color} size={9} active={isLive || isQueued} />

        {/* Avatar / Direction Logo */}
        <div style={{
          width: 38, height: 38,
          borderRadius: 10,
          background: `linear-gradient(135deg, ${cfg.color}22, ${cfg.color}08)`,
          border: `1px solid ${cfg.color}30`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          fontSize: 13.5, fontWeight: 700, color: cfg.color,
        }}>
          {call.status === 'completed' ? (
            <PhoneOutgoing size={16} />
          ) : (
            (call.caller_name || call.phone_number).charAt(0).toUpperCase()
          )}
        </div>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
            {call.caller_name || 'Unknown Contact'}
            {call.status === 'completed' && <span style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 400 }}>· Outbound</span>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{call.phone_number}</div>
        </div>

        {/* Waveform for live */}
        {isLive && (
          <div style={{ flexShrink: 0 }}>
            <WaveformVisualizer bars={12} color="#22D3A5" height={28} active />
          </div>
        )}

        {/* Duration */}
        <div style={{ flexShrink: 0, textAlign: 'right' }}>
          <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginBottom: 3 }}>
            {Math.floor(call.duration_seconds / 60)}m {call.duration_seconds % 60}s
          </div>
          <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
            {formatDistanceToNow(new Date(call.started_at), { addSuffix: true })}
          </div>
        </div>

        {/* Status badge */}
        <Badge variant={cfg.badge} dot={!isLive} glow={isLive}>{cfg.label}</Badge>

        {/* Actions */}
        {(isLive || isQueued) ? (
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            <button
              onClick={() => onAction('transfer', call.id)}
              title="Transfer"
              style={{
                width: 30, height: 30, borderRadius: 7,
                background: 'rgba(94,230,255,0.1)',
                border: '1px solid rgba(94,230,255,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', color: '#5EE6FF',
              }}
            >
              <PhoneForwarded size={13} />
            </button>
            <button
              onClick={() => onAction('voicemail', call.id)}
              title="Voicemail"
              style={{
                width: 30, height: 30, borderRadius: 7,
                background: 'rgba(245,166,35,0.1)',
                border: '1px solid rgba(245,166,35,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', color: '#F5A623',
              }}
            >
              <Voicemail size={13} />
            </button>
            <button
              onClick={() => onAction('end', call.id)}
              title="End Call"
              style={{
                width: 30, height: 30, borderRadius: 7,
                background: 'rgba(255,77,106,0.1)',
                border: '1px solid rgba(255,77,106,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', color: '#FF4D6A',
              }}
            >
              <PhoneOff size={13} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => onAction('expand', call.id)}
            style={{
              padding: '4px 10px',
              borderRadius: 7,
              background: isExpanded ? 'rgba(123,97,255,0.18)' : 'rgba(255,255,255,0.04)',
              border: `1px solid ${isExpanded ? 'rgba(123,97,255,0.3)' : 'rgba(255,255,255,0.08)'}`,
              color: isExpanded ? '#9580FF' : '#94A3B8',
              fontSize: 12,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              transition: 'all 0.15s'
            }}
          >
            <Play size={10} fill={isExpanded ? '#9580FF' : 'none'} />
            Playback
          </button>
        )}
      </div>

      {/* Expand sub-panel details */}
      {isExpanded && (
        <div style={{ padding: '0 20px 16px 20px', borderTop: '1px solid rgba(255,255,255,0.03)', display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
          {call.summary && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>AI Summary</div>
              <div style={{ fontSize: 12.5, color: 'var(--color-text-primary)', lineHeight: 1.5 }}>{call.summary}</div>
            </div>
          )}
          {call.recording_url && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Call Playback</div>
              <audio controls src={apiUrl(call.recording_url)} style={{ width: '100%', height: 36, outline: 'none' }} />
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Transcript</div>
            {loadingTranscript ? (
              <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Loading transcript...</span>
            ) : (
              <pre style={{
                background: 'rgba(0,0,0,0.2)',
                border: '1px solid rgba(255,255,255,0.04)',
                borderRadius: 8,
                padding: 10,
                fontSize: 12,
                color: '#8891a8',
                whiteSpace: 'pre-wrap',
                maxHeight: 160,
                overflowY: 'auto',
                margin: 0,
                lineHeight: 1.5
              }}>
                {transcript || 'No transcript available.'}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function OutboundCalls() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('single')
  const [health, setHealth] = useState<'ok' | 'error' | 'loading'>('loading')
  const fileRef = useRef<HTMLInputElement>(null)

  // Single
  const [phone, setPhone] = useState(searchParams.get('phone') ?? '')
  const [callerName, setCallerName] = useState(searchParams.get('name') ?? '')
  const [phoneErr, setPhoneErr] = useState('')
  const [singleLoading, setSingleLoading] = useState(false)
  const [singleResult, setSingleResult] = useState<SingleCallResult | null>(null)

  // Bulk
  const [bulkText, setBulkText] = useState('')
  const [bulkLoading, setBulkLoading] = useState(false)
  const [bulkResults, setBulkResults] = useState<BulkCallEntry[]>([])
  const [bulkTotal, setBulkTotal] = useState<number | null>(null)
  const [bulkErr, setBulkErr] = useState('')
  const [uploadedFile, setUploadedFile] = useState<{ name: string; count: number } | null>(null)
  const [dragging, setDragging] = useState(false)

  // Stats
  const [stats] = useState({ today: 0, success: 0, failed: 0 })

  // Campaigns
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [campaignsLoading, setCampaignsLoading] = useState(false)
  const [confirmStart, setConfirmStart] = useState<Campaign | null>(null)
  const [starting, setStarting] = useState(false)

  const runCampaignAction = async (action: 'start' | 'pause', c: Campaign) => {
    try {
      await (action === 'start' ? campaignsApi.start(c.id) : campaignsApi.pause(c.id))
      toast.success(action === 'start' ? 'Campaign started' : 'Campaign paused')
      loadCampaigns()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Could not ${action} the campaign`)
    }
  }
  const [showMapper, setShowMapper] = useState(false)
  const [parsedRows, setParsedRows] = useState<Record<string, string>[]>([])
  const [detectedColumns, setDetectedColumns] = useState<string[]>([])
  const [columnMapping, setColumnMapping] = useState<ColumnMapping>({ phone: '', name: '', custom_fields: [] })
  const [campaignName, setCampaignName] = useState('')

  // Call Feed
  const [feedCalls, setFeedCalls] = useState<InboundCall[]>([])
  const [feedLoading, setFeedLoading] = useState(true)

  // Playback/details state
  const [expandedCallId, setExpandedCallId] = useState<string | null>(null)
  const [activeTranscript, setActiveTranscript] = useState<string | null>(null)
  const [loadingTranscript, setLoadingTranscript] = useState(false)

  async function loadFeed() {
    try {
      const list = await callsApi.list()
      setFeedCalls(list)
    } catch (e) {
      console.error(e)
    } finally {
      setFeedLoading(false)
    }
  }

  async function loadCampaigns() {
    setCampaignsLoading(true)
    try {
      const list = await campaignsApi.list()
      setCampaigns(Array.isArray(list) ? list : [])
    } catch { setCampaigns([]) }
    finally { setCampaignsLoading(false) }
  }

  async function handleFileForCampaign(file: File) {
    const text = await file.text()
    const lines = text.split('\n').filter(l => l.trim())
    if (lines.length < 2) { toast.error('File must have a header row and at least one data row'); return }
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
    const rows = lines.slice(1).map(line => {
      const vals = line.split(',').map(v => v.trim().replace(/^"|"$/g, ''))
      const obj: Record<string, string> = {}
      headers.forEach((h, i) => { obj[h] = vals[i] || '' })
      return obj
    }).filter(r => Object.values(r).some(v => v))
    setDetectedColumns(headers)
    setParsedRows(rows)
    const phoneLike = headers.find(h => /phone|mobile|number|tel/i.test(h))
    const nameLike = headers.find(h => /name|contact|person/i.test(h))
    setColumnMapping({ phone: phoneLike || '', name: nameLike || '', custom_fields: [] })
    setShowMapper(true)
  }

  async function handleCreateCampaign() {
    if (!columnMapping.phone) { toast.error('Please map the Phone column'); return }
    if (!campaignName.trim()) { toast.error('Please enter a campaign name'); return }
    const leads = parsedRows.map(row => {
      const custom: Record<string, string> = {}
      columnMapping.custom_fields.forEach(f => { custom[f] = row[f] || '' })
      return { phone: row[columnMapping.phone] || '', name: row[columnMapping.name] || '', custom_fields: custom }
    }).filter(l => l.phone)
    try {
      await campaignsApi.create({ name: campaignName.trim(), leads })
      toast.success(`Campaign "${campaignName}" created with ${leads.length} leads`)
      setShowMapper(false); setCampaignName(''); setParsedRows([])
      loadCampaigns()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Failed to create campaign') }
  }

  const handleAction = async (action: string, id: string) => {
    try {
      if (action === 'end') {
        const res = await callsApi.end(id)
        if (res.status === 'ok') toast.success('Call ended successfully')
        else toast.error('Failed to end call')
      } else if (action === 'voicemail') {
        const res = await callsApi.voicemail(id)
        if (res.status === 'ok') toast.success('Call routed to voicemail')
        else toast.error('Failed to route call to voicemail')
      } else if (action === 'transfer') {
        const destination = prompt('Enter the phone number or SIP address to transfer the call to:')
        if (destination && destination.trim()) {
          const res = await callsApi.transfer(id, destination.trim())
          if (res.status === 'ok') toast.success(`Call transferring to ${destination.trim()}`)
          else toast.error('Failed to transfer call')
        }
      } else if (action === 'expand') {
        if (expandedCallId === id) {
          setExpandedCallId(null)
          setActiveTranscript(null)
        } else {
          setExpandedCallId(id)
          setLoadingTranscript(true)
          setActiveTranscript(null)
          try {
            const text = await logsApi.transcript(id)
            setActiveTranscript(text)
          } catch {
            setActiveTranscript('No transcript generated.')
          } finally {
            setLoadingTranscript(false)
          }
        }
      }
    } catch (e) {
      console.error('Error executing call action:', e)
      toast.error('An error occurred executing this action')
    }
    loadFeed()
  }

  useEffect(() => {
    const p = searchParams.get('phone'); const n = searchParams.get('name')
    if (p) setPhone(p); if (n) setCallerName(n)
    // /health returns { status: 'ok', ... }
    fetch('/health')
      .then(r => r.json())
      .then((h: { status?: string }) => setHealth(h?.status === 'ok' ? 'ok' : 'error'))
      .catch(() => setHealth('error'))
    loadFeed()
    loadCampaigns()
    const timer = setInterval(() => {
      callsApi.list().then(setFeedCalls).catch(() => {})
    }, 5000)
    return () => clearInterval(timer)
  }, [searchParams])

  // ── Single dispatch ─────────────────────────────────────────
  async function handleSingle() {
    setPhoneErr(''); setSingleResult(null)
    const raw = phone.trim()
    if (!raw) { setPhoneErr('Phone number is required'); return }
    const normalized = (raw.startsWith('+') ? '+' : '') + raw.replace(/\D/g, '')
    const digits = normalized.replace('+', '')
    if (digits.length < 7) { setPhoneErr('Too short — include country code'); return }
    if (digits.length > 15) { setPhoneErr('Too long — max 15 digits'); return }
    setSingleLoading(true)
    try {
      const res = await callsApi.single(normalized, callerName.trim() || undefined)
      setSingleResult(res)
      if (res.status === 'ok') {
        toast.success(`Dispatched to ${normalized}`)
        setPhone(normalized)
        loadFeed()
      }
      else toast.error(res.message ?? 'Dispatch failed')
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed'
      toast.error(msg); setSingleResult({ status: 'error', message: msg })
    } finally { setSingleLoading(false) }
  }

  // ── File upload (CSV / Excel) ───────────────────────────────
  async function handleFile(file: File) {
    const allowed = ['.csv', '.xlsx', '.xls', '.txt']
    if (!allowed.some(ext => file.name.toLowerCase().endsWith(ext))) {
      toast.error('Only CSV, Excel (.xlsx/.xls), or .txt files are supported'); return
    }
    const text = await file.text()
    const numbers = parseFileToNumbers(text)
    if (numbers.length === 0) { toast.error('No valid phone numbers found in file'); return }
    setBulkText(numbers.join('\n'))
    setUploadedFile({ name: file.name, count: numbers.length })
    toast.success(`Loaded ${numbers.length} numbers from ${file.name}`)
  }

  // ── Bulk dispatch ───────────────────────────────────────────
  async function handleBulk() {
    setBulkErr(''); setBulkResults([]); setBulkTotal(null)
    const lines = bulkText.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length === 0) { setBulkErr('Enter at least one phone number'); return }
    if (lines.length > 100) { setBulkErr('Maximum 100 numbers per dispatch'); return }
    setBulkLoading(true)
    try {
      const res = await callsApi.bulkText(bulkText)
      setBulkResults(res.results ?? [])
      setBulkTotal(res.total ?? lines.length)
      const ok = res.results?.filter(r => r.status === 'ok').length ?? 0
      const fail = res.results?.filter(r => r.status === 'error').length ?? 0
      toast.success(`Dispatched ${ok} call${ok !== 1 ? 's' : ''}${fail > 0 ? `, ${fail} failed` : ''}`)
      loadFeed()
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Bulk dispatch failed'
      setBulkErr(msg); toast.error(msg)
    } finally { setBulkLoading(false) }
  }

  const lineCount = bulkText.split('\n').filter(l => l.trim()).length
  const bulkOk = bulkResults.filter(r => r.status === 'ok').length
  const bulkFail = bulkResults.filter(r => r.status === 'error').length

  const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: 'single', label: 'Single Call', icon: <Phone size={14} /> },
    { id: 'bulk', label: 'Bulk Calls', icon: <Users size={14} /> },
    { id: 'campaigns', label: 'Campaigns', icon: <BarChart3 size={14} /> },
  ]

  return (
    <div className="page-wrapper">
      {/* ── Hero Header (matches Inbound style) ── */}
      <div style={{ padding: '32px 32px 0', marginBottom: 28 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,97,255,0.07), rgba(94,230,255,0.03))',
          border: '1px solid rgba(123,97,255,0.14)',
          borderRadius: 18,
          padding: '24px 28px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'relative', overflow: 'hidden',
        }}>
          <div style={{ position: 'absolute', top: -60, right: -60, width: 200, height: 200, borderRadius: '50%', background: 'rgba(123,97,255,0.12)', filter: 'blur(60px)', pointerEvents: 'none' }} />
          <div>
            <div style={{
              fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700,
              letterSpacing: '-0.03em', marginBottom: 6,
              background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #7B61FF)',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
            }}>
              Outbound Calls
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>AI-powered voice dispatch · LiveKit SIP · Bulk upload</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <NeuralPulse color={health === 'ok' ? '#7B61FF' : '#FF4D6A'} size={10} active />
            <span style={{ fontSize: 13.5, fontWeight: 600, color: health === 'ok' ? '#7B61FF' : '#FF4D6A' }}>
              SIP {health === 'ok' ? 'Ready' : 'Offline'}
            </span>
          </div>
        </div>
      </div>

      <div style={{ padding: '0 32px' }}>
        {/* ── Stat Cards ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
          <GradientStatCard label="Dispatched Today" value={stats.today} icon={<PhoneOutgoing size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={0} />
          <GradientStatCard label="Successful" value={bulkOk || stats.success} icon={<CheckCircle2 size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={80} />
          <GradientStatCard label="Failed" value={bulkFail || stats.failed} icon={<XCircle size={20} color="#fff" />} gradient="linear-gradient(135deg,#FF4D6A,#CC1F38)" delay={160} />
          <GradientStatCard label="Queue Size" value={lineCount} icon={<Users size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={240} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, alignItems: 'start' }}>
          {/* ── Main Panel ── */}
          <div>
            {/* Tab switcher */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 14, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, padding: 4, width: 'fit-content' }}>
              {TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    padding: '8px 18px', borderRadius: 9, border: 'none', cursor: 'pointer',
                    fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
                    background: tab === t.id ? 'rgba(123,97,255,0.18)' : 'transparent',
                    color: tab === t.id ? '#9580FF' : 'var(--color-text-muted)',
                    transition: 'all 0.15s',
                    boxShadow: tab === t.id ? '0 0 12px rgba(123,97,255,0.2)' : 'none',
                  }}
                >
                  {t.icon}{t.label}
                </button>
              ))}
            </div>

            {/* ── Single Call Tab ── */}
            {tab === 'single' && (
              <Card style={{ animation: 'scaleIn 0.18s cubic-bezier(0.22,1,0.36,1) both' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#7B61FF,#5851CC)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 18px rgba(123,97,255,0.35)', flexShrink: 0 }}>
                    <Phone size={17} color="#fff" />
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>Single Call</div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Dispatch one outbound call immediately via SIP</div>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <Input label="Phone Number" id="single-phone" value={phone}
                    onChange={e => { setPhone(e.target.value); setPhoneErr('') }}
                    placeholder="+919999999999" error={phoneErr} hint="E.164 format with country code" />
                  <Input label="Caller Name (optional)" id="single-name" value={callerName}
                    onChange={e => setCallerName(e.target.value)} placeholder="e.g. Asha" />

                  <Button variant="primary" loading={singleLoading}
                    icon={<PhoneOutgoing size={15} />} onClick={handleSingle}
                    id="dispatch-single-btn" style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}>
                    {singleLoading ? 'Connecting…' : 'Dispatch Call'}
                  </Button>
                </div>

                {/* Result */}
                {singleLoading && <div style={{ marginTop: 20 }}><LoadingState message="Connecting via SIP trunk…" /></div>}
                {singleResult && !singleLoading && (
                  <div style={{
                    marginTop: 20, padding: '16px 18px', borderRadius: 12,
                    background: singleResult.status === 'ok' ? 'rgba(34,211,165,0.06)' : 'rgba(255,77,106,0.06)',
                    border: `1px solid ${singleResult.status === 'ok' ? 'rgba(34,211,165,0.2)' : 'rgba(255,77,106,0.2)'}`,
                    animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      {singleResult.status === 'ok'
                        ? <CheckCircle2 size={18} color="#22D3A5" />
                        : <XCircle size={18} color="#FF4D6A" />}
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>
                        {singleResult.status === 'ok' ? 'Call Dispatched Successfully' : 'Dispatch Failed'}
                      </span>
                    </div>
                    {singleResult.status === 'ok' ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {[['Phone', singleResult.phone], ['ID', singleResult.dispatch_id], ['Room', singleResult.room], ['Trunk', singleResult.sip_trunk_id]]
                          .filter(([, v]) => v).map(([k, v]) => (
                            <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{k}</span>
                              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)', fontFamily: 'monospace', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
                            </div>
                          ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: 13, color: '#FF4D6A' }}>{singleResult.message}</div>
                    )}
                  </div>
                )}
              </Card>
            )}

            {/* ── Bulk Call Tab ── */}
            {tab === 'bulk' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, animation: 'scaleIn 0.18s cubic-bezier(0.22,1,0.36,1) both' }}>
                <Card>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#5EE6FF,#0EA5E9)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 18px rgba(94,230,255,0.3)', flexShrink: 0 }}>
                      <Users size={17} color="#fff" />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>Bulk Dispatch</div>
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Upload CSV/Excel or paste numbers — up to 100 per batch</div>
                    </div>
                    {lineCount > 0 && (
                      <span className="avn-chip avn-chip-cyan">{lineCount} numbers</span>
                    )}
                  </div>

                  {/* File Drop Zone */}
                  <div
                    onDragOver={e => { e.preventDefault(); setDragging(true) }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={async e => {
                      e.preventDefault(); setDragging(false)
                      const f = e.dataTransfer.files[0]
                      if (f) await handleFile(f)
                    }}
                    onClick={() => fileRef.current?.click()}
                    style={{
                      border: `2px dashed ${dragging ? 'rgba(94,230,255,0.6)' : 'rgba(255,255,255,0.1)'}`,
                      borderRadius: 12,
                      padding: '22px 20px',
                      textAlign: 'center',
                      background: dragging ? 'rgba(94,230,255,0.04)' : 'rgba(255,255,255,0.02)',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      marginBottom: 14,
                    }}
                  >
                    <input
                      ref={fileRef} type="file"
                      accept=".csv,.xlsx,.xls,.txt"
                      style={{ display: 'none' }}
                      onChange={async e => {
                        const f = e.target.files?.[0]
                        if (f) await handleFile(f)
                        e.target.value = ''
                      }}
                    />
                    <Upload size={22} color="#4B5675" style={{ margin: '0 auto 8px' }} />
                    <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--color-text-secondary)' }}>
                      Drop a file here or <span style={{ color: '#7B61FF' }}>browse</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                      Supports CSV, Excel (.xlsx/.xls), or plain TXT — one number per row
                    </div>
                    {uploadedFile && (
                      <div style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', background: 'rgba(94,230,255,0.08)', border: '1px solid rgba(94,230,255,0.2)', borderRadius: 8 }}>
                        <FileSpreadsheet size={13} color="#5EE6FF" />
                        <span style={{ fontSize: 12, color: '#5EE6FF', fontWeight: 500 }}>{uploadedFile.name}</span>
                        <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>· {uploadedFile.count} numbers</span>
                        <button aria-label="Remove file" onClick={e => { e.stopPropagation(); setUploadedFile(null); setBulkText('') }}
                          style={{ background: 'none', border: 'none', color: '#FF4D6A', cursor: 'pointer', padding: 0, marginLeft: 4 }}>
                          <Trash2 size={11} />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Textarea */}
                  <Textarea
                    label="Or Paste Numbers Manually"
                    id="bulk-numbers"
                    value={bulkText}
                    onChange={e => { setBulkText(e.target.value); setBulkErr(''); setUploadedFile(null) }}
                    rows={8}
                    placeholder={`+919999999999\n+918888888888\n+917777777777`}
                    error={bulkErr}
                    hint="One phone number per line, E.164 format"
                  />

                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
                    <Button variant="primary" loading={bulkLoading}
                      icon={<PhoneOutgoing size={15} />} onClick={handleBulk}
                      style={{ flex: 1, justifyContent: 'center' }}>
                      {bulkLoading ? `Dispatching ${lineCount} calls…` : `Dispatch ${lineCount > 0 ? lineCount : ''} Calls`}
                    </Button>
                    {bulkText && (
                      <Button variant="ghost" onClick={() => { setBulkText(''); setBulkResults([]); setUploadedFile(null) }}>
                        Clear
                      </Button>
                    )}
                  </div>
                </Card>

                {/* Results */}
                {bulkResults.length > 0 && (
                  <Card padding={0} style={{ animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both' }}>
                    <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <PhoneOutgoing size={14} color="#7B61FF" />
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Results ({bulkTotal})</span>
                      {bulkOk > 0 && <span className="avn-chip avn-chip-green">{bulkOk} dispatched</span>}
                      {bulkFail > 0 && <span className="avn-chip avn-chip-red">{bulkFail} failed</span>}
                    </div>
                    <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                      {bulkResults.map((r, i) => <ResultRow key={i} r={r} index={i} />)}
                    </div>
                  </Card>
                )}
              </div>
            )}

            {/* ── Campaigns Tab ── */}
            {tab === 'campaigns' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, animation: 'scaleIn 0.18s cubic-bezier(0.22,1,0.36,1) both' }}>
                <Card>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#F5A623,#D97706)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 18px rgba(245,166,35,0.3)', flexShrink: 0 }}>
                      <BarChart3 size={17} color="#fff" />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>Campaign Manager</div>
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Upload leads, map columns, and run automated outbound campaigns</div>
                    </div>
                  </div>

                  {/* Upload zone for campaigns */}
                  <div
                    onClick={() => {
                      const inp = document.createElement('input')
                      inp.type = 'file'; inp.accept = '.csv,.xlsx,.xls,.txt'
                      inp.onchange = async (e) => {
                        const f = (e.target as HTMLInputElement).files?.[0]
                        if (f) await handleFileForCampaign(f)
                      }
                      inp.click()
                    }}
                    style={{
                      border: '2px dashed rgba(245,166,35,0.3)',
                      borderRadius: 12, padding: '22px 20px', textAlign: 'center',
                      background: 'rgba(245,166,35,0.03)', cursor: 'pointer',
                      transition: 'all 0.2s', marginBottom: 14,
                    }}
                  >
                    <Upload size={22} color="#F5A623" style={{ margin: '0 auto 8px' }} />
                    <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--color-text-secondary)' }}>
                      Upload a CSV with lead data to create a campaign
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                      Headers will be auto-detected for column mapping
                    </div>
                  </div>
                </Card>

                {/* Campaign List */}
                <Card padding={0}>
                  <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <BarChart3 size={14} color="#F5A623" />
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Campaigns ({campaigns.length})</span>
                  </div>
                  {campaignsLoading ? (
                    <div style={{ padding: 20 }}><LoadingState /></div>
                  ) : campaigns.length === 0 ? (
                    <EmptyState icon={<BarChart3 size={22} />} title="No campaigns" description="Create your first campaign by uploading a CSV file above." />
                  ) : (
                    campaigns.map((c) => (
                      <div key={c.id} style={{
                        display: 'flex', alignItems: 'center', gap: 14, padding: '14px 20px',
                        borderBottom: '1px solid rgba(255,255,255,0.03)',
                        transition: 'background 0.15s',
                      }}>
                        <NeuralPulse color={c.status === 'running' ? '#22D3A5' : c.status === 'paused' ? '#F5A623' : 'var(--color-text-muted)'} size={9} active={c.status === 'running'} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 2 }}>{c.name}</div>
                          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                            {c.completed_leads}/{c.total_leads} leads · {c.qualified_leads} qualified · {c.scheduled_leads} scheduled
                          </div>
                        </div>
                        {/* Progress bar */}
                        <div style={{ width: 80, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.06)', overflow: 'hidden', flexShrink: 0 }}>
                          <div style={{
                            height: '100%', borderRadius: 3,
                            width: `${c.total_leads > 0 ? (c.completed_leads / c.total_leads) * 100 : 0}%`,
                            background: 'linear-gradient(90deg, #7B61FF, #22D3A5)',
                            transition: 'width 0.3s',
                          }} />
                        </div>
                        <Badge variant={c.status === 'running' ? 'success' : c.status === 'paused' ? 'warning' : c.status === 'completed' ? 'default' : 'info'} dot>
                          {c.status.toUpperCase()}
                        </Badge>
                        <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                          {(c.status === 'queued' || c.status === 'paused') && (
                            <button
                              onClick={() => setConfirmStart(c)}
                              title="Start"
                              style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(34,211,165,0.1)', border: '1px solid rgba(34,211,165,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#22D3A5' }}
                            >
                              <PlayCircle size={13} />
                            </button>
                          )}
                          {c.status === 'running' && (
                            <button
                              onClick={() => runCampaignAction('pause', c)}
                              title="Pause"
                              style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(245,166,35,0.1)', border: '1px solid rgba(245,166,35,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#F5A623' }}
                            >
                              <Pause size={13} />
                            </button>
                          )}
                          <button
                            onClick={() => window.open(`/api/crm/campaigns/${c.id}/export`, '_blank')}
                            title="Export CSV"
                            style={{ width: 28, height: 28, borderRadius: 7, background: 'rgba(94,230,255,0.1)', border: '1px solid rgba(94,230,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#5EE6FF' }}
                          >
                            <Download size={13} />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </Card>
              </div>
            )}

            {/* ── Outbound Call Feed Card ── */}
            <Card padding={0} style={{ marginTop: 20 }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <PhoneOutgoing size={15} color="#7B61FF" />
                <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Outbound Call Feed</span>
                {feedCalls.filter(c => c.status === 'live').length > 0 && (
                  <span className="avn-chip avn-chip-green" style={{ fontSize: 10, marginLeft: 4 }}>
                    {feedCalls.filter(c => c.status === 'live').length} LIVE
                  </span>
                )}
              </div>

              {feedLoading ? (
                <div style={{ padding: 20 }}><LoadingState /></div>
              ) : feedCalls.length === 0 ? (
                <EmptyState
                  icon={<PhoneOutgoing size={22} />}
                  title="No outbound calls"
                  description="Outbound calls will appear here in real-time when they are dispatched."
                />
              ) : (
                feedCalls.map((call) => (
                  <CallRow
                    key={call.id}
                    call={call}
                    onAction={handleAction}
                    isExpanded={expandedCallId === call.id}
                    transcript={activeTranscript}
                    loadingTranscript={loadingTranscript}
                  />
                ))
              )}
            </Card>
          </div>

          {/* ── Right Panel (System Status — matches Inbound) ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Activity size={14} color="#7B61FF" /> System Status
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { label: 'SIP Trunk', value: health === 'ok' ? 'Connected' : 'Offline', ok: health === 'ok' },
                  { label: 'LiveKit', value: health === 'ok' ? 'Active' : 'Unavailable', ok: health === 'ok' },
                  { label: 'Gemini Runtime', value: 'Online', ok: true },
                  { label: 'Rate Limit', value: '100/batch', ok: true },
                  { label: 'Dispatch Mode', value: 'Async Queue', ok: true },
                ].map(({ label, value, ok }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>{label}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className={`status-dot ${ok ? 'ok' : 'error'}`} style={{ width: 6, height: 6 }} />
                      <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{value}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Globe2 size={14} color="#5EE6FF" /> Dispatch Config
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { label: 'Max Batch', value: '100 calls' },
                  { label: 'AI Model', value: 'Gemini Live' },
                  { label: 'File Formats', value: 'CSV, XLSX, TXT' },
                  { label: 'Retry Policy', value: '2 attempts' },
                ].map(({ label, value }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>{label}</span>
                    <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{value}</span>
                  </div>
                ))}
              </div>
              <button
                onClick={() => setTab('bulk')}
                style={{
                  marginTop: 14, width: '100%', padding: '8px',
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: 8, color: 'var(--color-text-muted)', fontSize: 12, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                  transition: 'all 0.15s',
                }}
              >
                <Zap size={11} /> Start Bulk Dispatch <ArrowRight size={11} />
              </button>
            </Card>
          </div>
        </div>
      </div>

      {/* Campaign start confirmation: starting dials real people */}
      <Modal open={!!confirmStart} onClose={() => setConfirmStart(null)} title="Start campaign?" width={460}>
        {confirmStart && (
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ fontSize: 13.5, color: 'var(--color-text-primary)', lineHeight: 1.6 }}>
              <strong>{confirmStart.name}</strong> will call{' '}
              <strong>{confirmStart.total_leads - confirmStart.completed_leads}</strong> of {confirmStart.total_leads} numbers,
              up to {confirmStart.concurrency_limit} at a time, retrying failed calls up to {confirmStart.retry_limit} times.
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>These are real phone calls to real people and each one is billed. You can pause the campaign at any time.</div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="ghost" onClick={() => setConfirmStart(null)}>Cancel</Button>
              <Button variant="primary" loading={starting} onClick={async () => {
                setStarting(true)
                await runCampaignAction('start', confirmStart)
                setStarting(false)
                setConfirmStart(null)
              }}>Start calling</Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Column Mapper Modal */}
      {showMapper && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000, animation: 'fadeIn 0.2s both',
        }}>
          <div style={{
            background: 'var(--color-bg-card)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 16, padding: 28, width: '100%', maxWidth: 520,
            maxHeight: '80vh', overflowY: 'auto',
            boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
            animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#7B61FF,#5851CC)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <MapPin size={17} color="#fff" />
              </div>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)' }}>Map Columns</div>
                <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Detected {detectedColumns.length} columns · {parsedRows.length} rows</div>
              </div>
              <button onClick={() => setShowMapper(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 18 }}>×</button>
            </div>

            <Input label="Campaign Name" id="campaign-name" value={campaignName}
              onChange={e => setCampaignName(e.target.value)} placeholder="e.g. Q3 Outreach" />

            <div style={{ marginTop: 16, marginBottom: 8, fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Required Mappings</div>

            {/* Phone mapping */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Phone Number Column *</label>
              <select aria-label="Phone number column"
                value={columnMapping.phone}
                onChange={e => setColumnMapping(prev => ({ ...prev, phone: e.target.value }))}
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
                  color: 'var(--color-text-primary)', fontSize: 13, outline: 'none',
                }}
              >
                <option value="">Select column...</option>
                {detectedColumns.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {/* Name mapping */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 4, display: 'block' }}>Name Column</label>
              <select aria-label="Name column"
                value={columnMapping.name}
                onChange={e => setColumnMapping(prev => ({ ...prev, name: e.target.value }))}
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
                  color: 'var(--color-text-primary)', fontSize: 13, outline: 'none',
                }}
              >
                <option value="">Select column...</option>
                {detectedColumns.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {/* Custom fields */}
            <div style={{ marginTop: 16, marginBottom: 8, fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Custom Variables (optional)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {detectedColumns.filter(c => c !== columnMapping.phone && c !== columnMapping.name).map(col => (
                <label key={col} style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
                  borderRadius: 8, background: 'rgba(255,255,255,0.02)',
                  border: `1px solid ${columnMapping.custom_fields.includes(col) ? 'rgba(123,97,255,0.3)' : 'rgba(255,255,255,0.05)'}`,
                  cursor: 'pointer', transition: 'all 0.15s',
                }}>
                  <input
                    type="checkbox"
                    checked={columnMapping.custom_fields.includes(col)}
                    onChange={() => setColumnMapping(prev => ({
                      ...prev,
                      custom_fields: prev.custom_fields.includes(col)
                        ? prev.custom_fields.filter(f => f !== col)
                        : [...prev.custom_fields, col]
                    }))}
                    style={{ accentColor: '#7B61FF' }}
                  />
                  <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{col}</span>
                </label>
              ))}
            </div>

            {/* Preview */}
            <div style={{ marginTop: 16, marginBottom: 8, fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Preview (first 3 rows)</div>
            <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: 8, padding: 10, overflowX: 'auto', fontSize: 12, color: '#8891a8' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {columnMapping.phone && <th style={{ textAlign: 'left', padding: '4px 8px', color: '#7B61FF', fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>Phone</th>}
                    {columnMapping.name && <th style={{ textAlign: 'left', padding: '4px 8px', color: '#7B61FF', fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>Name</th>}
                    {columnMapping.custom_fields.map(f => (
                      <th key={f} style={{ textAlign: 'left', padding: '4px 8px', color: '#5EE6FF', fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>{f}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsedRows.slice(0, 3).map((row, i) => (
                    <tr key={i}>
                      {columnMapping.phone && <td style={{ padding: '4px 8px' }}>{row[columnMapping.phone] || '—'}</td>}
                      {columnMapping.name && <td style={{ padding: '4px 8px' }}>{row[columnMapping.name] || '—'}</td>}
                      {columnMapping.custom_fields.map(f => (
                        <td key={f} style={{ padding: '4px 8px' }}>{row[f] || '—'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <Button variant="ghost" onClick={() => setShowMapper(false)} style={{ flex: 1, justifyContent: 'center' }}>Cancel</Button>
              <Button variant="primary" onClick={handleCreateCampaign} icon={<PlayCircle size={15} />} style={{ flex: 2, justifyContent: 'center' }}>Create Campaign</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
