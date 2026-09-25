import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Radio, PhoneOff, Users, Clock, AlertTriangle, RefreshCw, PhoneIncoming, PhoneOutgoing } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import { LoadingState } from '../components/ui/States'
import { callsApi, type LiveCalls as LiveCallsData } from '../api/calls'

const POLL_MS = 5000

function formatDuration(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.max(0, sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function LiveCalls() {
  const [data, setData] = useState<LiveCallsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [ending, setEnding] = useState<string | null>(null)

  const apply = useCallback((result: PromiseSettledResult<LiveCallsData>) => {
    if (result.status === 'fulfilled') { setData(result.value); setError(null) }
    else setError(result.reason instanceof Error ? result.reason.message : 'Could not load live calls')
  }, [])

  const refresh = useCallback(async () => {
    const [result] = await Promise.allSettled([callsApi.live()])
    apply(result)
  }, [apply])

  useEffect(() => {
    let cancelled = false
    const fetchOnce = () => Promise.allSettled([callsApi.live()]).then(([r]) => { if (!cancelled) apply(r) })
    void fetchOnce()
    const poll = setInterval(fetchOnce, POLL_MS)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => { cancelled = true; clearInterval(poll); clearInterval(tick) }
  }, [apply])

  const endCall = async (id: string) => {
    if (!confirm('End this call for everyone on it?')) return
    setEnding(id)
    try {
      await callsApi.end(id)
      toast.success('Call ended')
      await refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not end the call')
    } finally {
      setEnding(null)
    }
  }

  const calls = data?.calls ?? []
  const inbound = calls.filter(c => c.direction === 'inbound').length
  const longest = calls.reduce((max, c) => Math.max(max, Math.round((now - new Date(c.started_at).getTime()) / 1000)), 0)

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 24 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(255,77,106,0.08), rgba(123,97,255,0.04))',
          border: '1px solid rgba(255,77,106,0.14)', borderRadius: 18, padding: '22px 28px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--color-text-primary)', marginBottom: 6 }}>Live Calls</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Calls in progress right now, read from LiveKit every {POLL_MS / 1000} seconds</div>
          </div>
          <button onClick={refresh} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 9, color: 'var(--color-text-secondary)', fontSize: 12.5, cursor: 'pointer' }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <div style={{ padding: '0 32px 32px' }}>
        {!data && !error ? <LoadingState /> : (
          <>
            {error && (
              <Card style={{ marginBottom: 18, borderLeft: '3px solid #FF4D6A' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--color-text-primary)' }}>
                  <AlertTriangle size={15} color="#FF4D6A" /> {error}
                </div>
              </Card>
            )}
            {data && !data.configured && (
              <Card style={{ marginBottom: 18, borderLeft: '3px solid #F5A623' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--color-text-primary)' }}>
                  <AlertTriangle size={15} color="#F5A623" />
                  LiveKit is not configured, so live calls can't be shown.
                  <Link to="/configuration" style={{ color: '#9580FF', marginLeft: 'auto', fontWeight: 600 }}>Open Configuration</Link>
                </div>
              </Card>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px,1fr))', gap: 14, marginBottom: 24 }}>
              <GradientStatCard label="Live now" value={calls.length} icon={<Radio size={20} color="#fff" />} gradient="linear-gradient(135deg,#FF4D6A,#C0304A)" />
              <GradientStatCard label="Inbound" value={inbound} icon={<PhoneIncoming size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={60} />
              <GradientStatCard label="Outbound" value={calls.length - inbound} icon={<PhoneOutgoing size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={120} />
              <GradientStatCard label="Longest (s)" value={longest} icon={<Clock size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={180} />
            </div>

            <Card padding={0}>
              {!calls.length ? (
                <div style={{ textAlign: 'center', padding: '48px 16px', color: 'var(--color-text-muted)', fontSize: 13 }}>
                  <Radio size={28} color="#4B5675" style={{ margin: '0 auto 12px', display: 'block' }} />
                  {data?.configured ? 'No calls in progress.' : 'Nothing to show until LiveKit is configured.'}
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="avn-table">
                    <thead>
                      <tr>
                        <th>Caller</th>
                        <th>Direction</th>
                        <th style={{ textAlign: 'right' }}>Participants</th>
                        <th style={{ textAlign: 'right' }}>Duration</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {calls.map(call => (
                        <tr key={call.id}>
                          <td>
                            <div style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{call.caller_name || call.phone_number}</div>
                            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>{call.phone_number}</div>
                          </td>
                          <td style={{ textTransform: 'capitalize' }}>{call.direction}</td>
                          <td style={{ textAlign: 'right' }}><Users size={12} style={{ verticalAlign: -1, marginRight: 4 }} />{call.participants}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{formatDuration(Math.round((now - new Date(call.started_at).getTime()) / 1000))}</td>
                          <td style={{ textAlign: 'right' }}>
                            <button
                              onClick={() => endCall(call.id)}
                              disabled={ending === call.id}
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', background: 'rgba(255,77,106,0.1)', border: '1px solid rgba(255,77,106,0.25)', borderRadius: 8, color: '#FF4D6A', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                            >
                              <PhoneOff size={12} /> {ending === call.id ? 'Ending…' : 'End call'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 12 }}>
              Transfers happen inside the voice agent when its transfer tool is configured; they can't be started from this page yet.
            </div>
          </>
        )}
      </div>
    </div>
  )
}
