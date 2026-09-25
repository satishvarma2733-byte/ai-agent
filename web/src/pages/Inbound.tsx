import { useEffect, useState } from 'react'
import { PhoneIncoming, Radio, Users, Clock, ArrowRight, PhoneForwarded, Voicemail, CheckCircle2, Activity, PhoneOff, Play } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import NeuralPulse from '../components/ui/NeuralPulse'
import WaveformVisualizer from '../components/ui/WaveformVisualizer'
import Badge from '../components/ui/Badge'
import { LoadingState, EmptyState } from '../components/ui/States'
import { inboundApi } from '../api/inbound'
import { apiUrl } from '../api/client'
import { logsApi } from '../api/logs'
import type { InboundCall } from '../types'
import { formatDistanceToNow } from 'date-fns'

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

        {/* Avatar / Call Logo */}
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
            <PhoneIncoming size={16} />
          ) : (
            (call.caller_name || call.phone_number).charAt(0).toUpperCase()
          )}
        </div>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
            {call.caller_name || 'Unknown Caller'}
            {call.status === 'completed' && <span style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 400 }}>· Inbound</span>}
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

      {/* Expand details sub-panel for completed calls */}
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

export default function Inbound() {
  const [calls, setCalls] = useState<InboundCall[]>([])
  const [loading, setLoading] = useState(true)
  const [health, setHealth] = useState<'ok' | 'error' | 'loading'>('loading')

  // Playback/details state
  const [expandedCallId, setExpandedCallId] = useState<string | null>(null)
  const [transcripts, setTranscripts] = useState<Record<string, string>>({})
  const [loadingTranscripts, setLoadingTranscripts] = useState<Record<string, boolean>>({})

  const load = async () => {
    setLoading(true)
    const [c, h] = await Promise.allSettled([inboundApi.list(), inboundApi.health()])
    if (c.status === 'fulfilled') setCalls(c.value)
    setHealth(h.status === 'fulfilled' ? 'ok' : 'error')
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const live = calls.filter(c => c.status === 'live')
  const queued = calls.filter(c => c.status === 'queued')
  const completed = calls.filter(c => c.status === 'completed')

  const handleAction = async (action: string, id: string) => {
    try {
      if (action === 'end') {
        const res = await inboundApi.end(id)
        if (res.status === 'ok') toast.success('Call ended successfully')
        else toast.error('Failed to end call')
        load()
      } else if (action === 'voicemail') {
        const res = await inboundApi.voicemail(id)
        if (res.status === 'ok') toast.success('Call routed to voicemail')
        else toast.error('Failed to route call to voicemail')
        load()
      } else if (action === 'transfer') {
        const destination = prompt('Enter the phone number or SIP address to transfer the call to:')
        if (destination && destination.trim()) {
          const res = await inboundApi.transfer(id, destination.trim())
          if (res.status === 'ok') toast.success(`Call transferring to ${destination.trim()}`)
          else toast.error('Failed to transfer call')
          load()
        }
      } else if (action === 'expand') {
        if (expandedCallId === id) {
          setExpandedCallId(null)
        } else {
          setExpandedCallId(id)
          if (!transcripts[id]) {
            setLoadingTranscripts(prev => ({ ...prev, [id]: true }))
            try {
              const text = await logsApi.transcript(id)
              setTranscripts(prev => ({ ...prev, [id]: text }))
            } catch {
              setTranscripts(prev => ({ ...prev, [id]: 'No transcript generated.' }))
            } finally {
              setLoadingTranscripts(prev => ({ ...prev, [id]: false }))
            }
          }
        }
      }
    } catch (e) {
      console.error('Error executing call action:', e)
      toast.error('An error occurred executing this action')
    }
  }

  return (
    <div className="page-wrapper">
      {/* Header */}
      <div style={{ padding: '32px 32px 0', marginBottom: 28 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(34,211,165,0.06), rgba(123,97,255,0.04))',
          border: '1px solid rgba(34,211,165,0.12)',
          borderRadius: 18,
          padding: '24px 28px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{
              fontFamily: 'Satoshi, Inter, sans-serif',
              fontSize: 26,
              fontWeight: 700,
              letterSpacing: '-0.03em',
              background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #22D3A5)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              marginBottom: 6,
            }}>
              Inbound Calls
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
              Live call handling · SIP routing · AI receptionist
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <NeuralPulse color={health === 'ok' ? '#22D3A5' : '#FF4D6A'} size={10} active />
            <span style={{ fontSize: 13.5, fontWeight: 600, color: health === 'ok' ? '#22D3A5' : '#FF4D6A' }}>
              SIP {health === 'ok' ? 'Online' : 'Offline'}
            </span>
          </div>
        </div>
      </div>

      <div style={{ padding: '0 32px' }}>
        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
          <GradientStatCard label="Live Now" value={live.length} icon={<Radio size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={0} />
          <GradientStatCard label="In Queue" value={queued.length} icon={<Users size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={80} />
          <GradientStatCard label="Completed" value={completed.length} icon={<CheckCircle2 size={20} color="#fff" />} gradient="linear-gradient(135deg,#5EE6FF,#0EA5E9)" delay={160} />
          <GradientStatCard label="Total Today" value={calls.length} icon={<PhoneIncoming size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={240} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16, alignItems: 'start' }}>
          {/* Call Feed */}
          <Card padding={0}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <PhoneIncoming size={15} color="#22D3A5" />
              <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Call Feed</span>
              {live.length > 0 && (
                <span className="avn-chip avn-chip-green" style={{ fontSize: 10, marginLeft: 4 }}>
                  {live.length} LIVE
                </span>
              )}
            </div>

            {loading ? (
              <LoadingState />
            ) : calls.length === 0 ? (
              <EmptyState
                icon={<PhoneIncoming size={22} />}
                title="No inbound calls"
                description="Inbound calls will appear here in real-time when the SIP gateway receives them."
              />
            ) : (
              calls.map((call) => (
                <CallRow
                  key={call.id}
                  call={call}
                  onAction={handleAction}
                  isExpanded={expandedCallId === call.id}
                  transcript={transcripts[call.id] || null}
                  loadingTranscript={!!loadingTranscripts[call.id]}
                />
              ))
            )}
          </Card>

          {/* Right: System status */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Activity size={14} color="#7B61FF" />
                System Status
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { label: 'SIP Gateway', value: health === 'ok' ? 'Connected' : 'Offline', ok: health === 'ok' },
                  { label: 'LiveKit', value: health === 'ok' ? 'Active' : 'Unavailable', ok: health === 'ok' },
                  { label: 'Gemini Runtime', value: 'Online', ok: true },
                  { label: 'KB Retrieval', value: 'Active', ok: true },
                  { label: 'Human Handoff', value: 'Available', ok: true },
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
                <Clock size={14} color="#F5A623" />
                Queue Config
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { label: 'Max Queue Size', value: '10 calls' },
                  { label: 'Wait Timeout', value: '120s' },
                  { label: 'Business Hours', value: '9am–6pm IST' },
                  { label: 'Voicemail', value: 'Enabled' },
                ].map(({ label, value }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>{label}</span>
                    <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{value}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
