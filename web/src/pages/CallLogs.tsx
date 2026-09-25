import { useEffect, useState, useMemo } from 'react'
import { Download, Copy, Search, Phone, ChevronDown, ChevronUp, Gauge, PhoneIncoming, PhoneOutgoing } from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/layout/PageHeader'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States'
import { logsApi } from '../api/logs'
import type { CallLog, LatencySummary } from '../types'
import { format } from 'date-fns'

function fmtDuration(sec: number) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

function fmtMs(val: number | undefined): string {
  if (val === undefined || val === null) return '—'
  return `${val.toFixed(0)} ms`
}

type SortField = 'created_at' | 'duration_seconds' | 'caller_name'

// ─── Latency mini-panel shown inside transcript modal ─────
function LatencyPanel({ l }: { l: LatencySummary }) {
  const rows: [string, string][] = [
    ['Turns', String(l.turns)],
    ['KB turns', String(l.kb_used_turns)],
    ['KB avg', fmtMs(l.kb_ms)],
    ['LLM first token', fmtMs(l.llm_first_token_ms)],
    ['TTS first audio', fmtMs(l.tts_first_audio_ms)],
    ['Tool avg', fmtMs(l.tool_ms)],
    ['Total turn avg', fmtMs(l.total_turn_ms)],
  ].filter(([, v]) => v !== '—') as [string, string][]

  return (
    <div style={{
      background: 'var(--color-bg-card)',
      border: '1px solid #1e2236',
      borderRadius: 8,
      padding: '12px 14px',
      marginBottom: 12,
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(140px,1fr))',
      gap: '8px 16px',
    }}>
      {rows.map(([label, val]) => (
        <div key={label}>
          <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-primary)', fontWeight: 500, marginTop: 2 }}>{val}</div>
        </div>
      ))}
    </div>
  )
}

export default function CallLogs() {
  const [logs, setLogs] = useState<CallLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortAsc, setSortAsc] = useState(false)

  // Transcript modal state
  const [activeLog, setActiveLog] = useState<CallLog | null>(null)
  const [transcript, setTranscript] = useState<string | null>(null)
  const [transcriptLoading, setTranscriptLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await logsApi.list()
      setLogs(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load logs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return logs
      .filter(l =>
        !q ||
        l.caller_name?.toLowerCase().includes(q) ||
        String(l.phone_number)?.includes(q) ||
        l.summary?.toLowerCase().includes(q)
      )
      .sort((a, b) => {
        let v = 0
        if (sortField === 'created_at') v = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        else if (sortField === 'duration_seconds') v = a.duration_seconds - b.duration_seconds
        else if (sortField === 'caller_name') v = (a.caller_name ?? '').localeCompare(b.caller_name ?? '')
        return sortAsc ? v : -v
      })
  }, [logs, search, sortField, sortAsc])

  function toggleSort(f: SortField) {
    if (sortField === f) setSortAsc(a => !a)
    else { setSortField(f); setSortAsc(false) }
  }

  function SortIcon({ field }: { field: SortField }) {
    if (sortField !== field) return null
    return sortAsc ? <ChevronUp size={12} /> : <ChevronDown size={12} />
  }

  async function openTranscript(log: CallLog) {
    setActiveLog(log)
    setTranscript(null)
    setTranscriptLoading(true)
    try {
      // Backend returns plain text — already includes latency block + transcript body
      const text = await logsApi.transcript(log.id)
      setTranscript(typeof text === 'string' ? text : JSON.stringify(text, null, 2))
    } catch (e) {
      setTranscript('Failed to load transcript: ' + (e instanceof Error ? e.message : 'Unknown error'))
    } finally {
      setTranscriptLoading(false)
    }
  }

  function closeModal() {
    setActiveLog(null)
    setTranscript(null)
    setTranscriptLoading(false)
  }

  function copyTranscript() {
    if (!transcript) return
    navigator.clipboard.writeText(transcript)
    toast.success('Transcript copied')
  }

  function downloadTranscript() {
    if (!transcript || !activeLog) return
    const blob = new Blob([transcript], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const safeName = (activeLog.caller_name || String(activeLog.phone_number)).replace(/[^a-z0-9]/gi, '-')
    a.download = `transcript-${safeName}-${String(activeLog.id)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const Th = ({ label, field }: { label: string; field?: SortField }) => (
    <th
      onClick={field ? () => toggleSort(field) : undefined}
      style={{
        textAlign: 'left',
        padding: '10px 14px',
        fontSize: 11.5,
        fontWeight: 600,
        color: 'var(--color-text-muted)',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        cursor: field ? 'pointer' : undefined,
        userSelect: 'none',
        background: 'var(--color-bg-card)',
      }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {label}
        {field && <SortIcon field={field} />}
      </span>
    </th>
  )

  const modalTitle = activeLog
    ? `${activeLog.caller_name || String(activeLog.phone_number)} — ${format(new Date(activeLog.created_at), 'MMM d, h:mm a')}`
    : ''

  return (
    <div className="animate-fade-in" style={{ padding: '0 0 40px' }}>
      <PageHeader
        title="Call Logs"
        subtitle={`${logs.length} total call${logs.length !== 1 ? 's' : ''} (last 50)`}
      />

      <div style={{ padding: '24px 32px' }}>
        <Card padding={0}>
          {/* Toolbar */}
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #1e2236', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '0 0 280px' }}>
              <Search size={14} color="#555e78" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search caller, phone, summary…"
                style={{
                  width: '100%',
                  padding: '7px 12px 7px 32px',
                  background: 'var(--color-bg-card)',
                  border: '1px solid #2a2f47',
                  borderRadius: 8,
                  color: '#e8ecf0',
                  fontSize: 13,
                  outline: 'none',
                }}
              />
            </div>
            <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginLeft: 'auto' }}>
              {filtered.length} result{filtered.length !== 1 ? 's' : ''}
            </span>
          </div>

          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState message={error} onRetry={load} />
          ) : filtered.length === 0 ? (
            <EmptyState icon={<Phone size={36} />} title="No call logs" description="Calls will appear here once they occur." />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    <Th label="Type" />
                    <Th label="Caller" field="caller_name" />
                    <Th label="Phone" />
                    <Th label="Date" field="created_at" />
                    <Th label="Duration" field="duration_seconds" />
                    <Th label="Booked" />
                    <Th label="Latency" />
                    <Th label="Summary" />
                    <Th label="" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(log => (
                    <tr
                      key={String(log.id)}
                      style={{ borderBottom: '1px solid #131625', transition: 'background 0.1s' }}
                      onMouseOver={e => (e.currentTarget.style.background = '#181c2e')}
                      onMouseOut={e => (e.currentTarget.style.background = '')}
                    >
                      <td style={{ padding: '11px 14px' }}>
                        {log.direction === 'inbound' ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#22D3A5', fontSize: 12, fontWeight: 500 }}>
                            <PhoneIncoming size={13} /> Inbound
                          </span>
                        ) : (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#7B61FF', fontSize: 12, fontWeight: 500 }}>
                            <PhoneOutgoing size={13} /> Outbound
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#e8ecf0', fontWeight: 500 }}>
                        {log.caller_name || '—'}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12.5 }}>
                        {log.phone_number}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12.5, whiteSpace: 'nowrap' }}>
                        {format(new Date(log.created_at), 'MMM d, h:mm a')}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12.5 }}>
                        {fmtDuration(log.duration_seconds)}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <Badge variant={log.was_booked ? 'success' : 'default'} dot>
                          {log.was_booked ? 'Booked' : 'No booking'}
                        </Badge>
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        {log.latency_summary ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#7c6fcd' }}>
                            <Gauge size={13} />
                            {fmtMs(log.latency_summary.total_turn_ms)}
                          </span>
                        ) : (
                          <span style={{ color: '#3b4260', fontSize: 12 }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: '11px 14px', color: '#8891a8', fontSize: 12.5, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {log.summary || '—'}
                      </td>
                      <td style={{ padding: '11px 14px' }}>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openTranscript(log)}
                        >
                          Transcript
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Transcript Modal */}
      <Modal
        open={activeLog !== null}
        onClose={closeModal}
        title={`Transcript — ${modalTitle}`}
        width={720}
      >
        <div style={{ padding: '16px 20px' }}>
          {/* Latency summary from the log row (pre-computed by backend) */}
          {activeLog?.latency_summary && (
            <LatencyPanel l={activeLog.latency_summary} />
          )}

          {transcriptLoading ? (
            <LoadingState message="Loading transcript…" />
          ) : (
            <>
              <div style={{ display: 'flex', gap: 8, marginBottom: 12, justifyContent: 'flex-end' }}>
                <Button variant="ghost" size="sm" icon={<Copy size={13} />} onClick={copyTranscript}>Copy</Button>
                <Button variant="ghost" size="sm" icon={<Download size={13} />} onClick={downloadTranscript}>Download .txt</Button>
              </div>
              <pre
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid #1e2236',
                  borderRadius: 8,
                  padding: '14px 16px',
                  fontSize: 12.5,
                  color: 'var(--color-text-primary)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  lineHeight: 1.75,
                  maxHeight: 480,
                  overflowY: 'auto',
                  margin: 0,
                }}
              >
                {transcript ?? ''}
              </pre>
            </>
          )}
        </div>
      </Modal>
    </div>
  )
}
