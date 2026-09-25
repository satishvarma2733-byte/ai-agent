import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  BarChart3, TrendingUp, Clock, PhoneCall, Zap, Brain, CalendarCheck,
  Download, RefreshCw, ArrowUpRight, ArrowDownRight, Smile,
} from 'lucide-react'
import GradientStatCard from '../components/ui/GradientStatCard'
import Card from '../components/ui/Card'
import { LoadingState } from '../components/ui/States'
import { analyticsApi, PERIOD_DAYS, type DayPoint, type Overview, type Period } from '../api/analytics'
import { downloadCsv } from '../lib/csv'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const SENTIMENT_COLORS: Record<string, string> = { positive: '#22D3A5', neutral: '#5EE6FF', negative: '#FF4D6A', unknown: '#4B5675' }

function fmtDuration(sec: number) {
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

function pctChange(now: number, before: number): number | undefined {
  if (!before) return undefined
  return Math.round(((now - before) / before) * 100)
}

function sectionTitle(icon: ReactNode, title: string, note?: string) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
      {icon}
      <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>{title}</span>
      {note && <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginLeft: 4 }}>{note}</span>}
    </div>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', padding: '18px 0', textAlign: 'center' }}>{children}</div>
}

// ── Bar chart ─────────────────────────────────────────────────────
function MiniBarChart({ data, valueKey, color = '#7B61FF', height = 80 }: {
  data: DayPoint[]; valueKey: 'calls' | 'bookings'; color?: string; height?: number
}) {
  const vals = data.map(d => d[valueKey])
  const max = Math.max(...vals, 1)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height, paddingTop: 8 }}>
      {vals.map((v, i) => (
        <div key={data[i].date} title={`${data[i].date}: ${v}`} style={{
          flex: 1, borderRadius: '3px 3px 0 0',
          background: v ? `linear-gradient(180deg, ${color}, ${color}60)` : 'rgba(255,255,255,0.05)',
          height: `${Math.max((v / max) * 100, 3)}%`,
          opacity: 0.85, minWidth: 3,
        }} />
      ))}
    </div>
  )
}

function MetricCard({ label, value, icon, color, sub, data, valueKey, trend }: {
  label: string; value: string; icon: ReactNode; color: string; sub?: string;
  data: DayPoint[]; valueKey: 'calls' | 'bookings'; trend?: number
}) {
  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--color-text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 8 }}>{label}</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--color-text-primary)', letterSpacing: '-0.04em', lineHeight: 1 }}>{value}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
            {trend !== undefined && (
              <span title="Last 7 days compared with the 7 days before" style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, fontWeight: 700, color: trend >= 0 ? '#22D3A5' : '#FF4D6A' }}>
                {trend >= 0 ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
                {Math.abs(trend)}%
              </span>
            )}
            {sub && <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>{sub}</span>}
          </div>
        </div>
        <div style={{ width: 38, height: 38, borderRadius: 10, background: `linear-gradient(135deg, ${color}22, ${color}08)`, border: `1px solid ${color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {icon}
        </div>
      </div>
      <MiniBarChart data={data} valueKey={valueKey} color={color} height={60} />
    </Card>
  )
}

// ── Latency breakdown ─────────────────────────────────────────────
function LatencyCard({ latency }: { latency: Overview['latency'] }) {
  const parts: [string, number | null | undefined, string][] = [
    ['Speech-to-text', latency.avg_stt_ms, '#5EE6FF'],
    ['Knowledge base', latency.avg_kb_ms, '#9580FF'],
    ['LLM first token', latency.avg_llm_ms, '#7B61FF'],
    ['Text-to-speech', latency.avg_tts_ms, '#22D3A5'],
  ]
  const max = Math.max(...parts.map(p => p[1] ?? 0), 1)
  return (
    <Card>
      {sectionTitle(<Zap size={14} color="#7B61FF" />, 'Response latency', latency.turns ? `average of ${latency.turns} agent turns` : undefined)}
      {!latency.turns ? <Empty>No turn metrics recorded in this period yet. They appear after the voice agent handles calls.</Empty> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {parts.map(([label, ms, color]) => (
            <div key={label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{label}</span>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--color-text-primary)' }}>{ms == null ? '—' : `${Math.round(ms)} ms`}</span>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${((ms ?? 0) / max) * 100}%`, background: color, borderRadius: 6 }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ── Sentiment ─────────────────────────────────────────────────────
function SentimentCard({ sentiment }: { sentiment: Overview['sentiment'] }) {
  const entries = Object.entries(sentiment).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, n]) => sum + n, 0)
  return (
    <Card>
      {sectionTitle(<Smile size={14} color="#22D3A5" />, 'Caller sentiment')}
      {!total ? <Empty>No calls in this period.</Empty> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {entries.map(([name, count]) => (
            <div key={name}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', textTransform: 'capitalize' }}>{name}</span>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--color-text-primary)' }}>{count} · {Math.round((count / total) * 100)}%</span>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(count / total) * 100}%`, background: SENTIMENT_COLORS[name] ?? '#7B61FF', borderRadius: 6 }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ── Heatmap ───────────────────────────────────────────────────────
function CallHeatmap({ cells, timezone }: { cells: Overview['heatmap']; timezone: string }) {
  const counts = new Map(cells.map(c => [`${c.day}-${c.hour}`, c.calls]))
  const max = Math.max(...cells.map(c => c.calls), 1)
  const hours = Array.from({ length: 24 }, (_, h) => h)
  return (
    <Card>
      {sectionTitle(<BarChart3 size={14} color="#5EE6FF" />, 'Call volume heatmap', `calls by hour and day (${timezone})`)}
      {!cells.length ? <Empty>No calls in this period.</Empty> : (
        <div style={{ overflowX: 'auto' }}>
          <div style={{ minWidth: 620 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '40px repeat(24, 1fr)', gap: 2, marginBottom: 4 }}>
              <div />
              {hours.map(h => (
                <div key={h} style={{ fontSize: 9, color: 'var(--color-text-muted)', textAlign: 'center', fontWeight: 600 }}>{h % 3 === 0 ? h : ''}</div>
              ))}
            </div>
            {DAY_NAMES.map((day, di) => (
              <div key={day} style={{ display: 'grid', gridTemplateColumns: '40px repeat(24, 1fr)', gap: 2, marginBottom: 2 }}>
                <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', fontWeight: 600 }}>{day}</div>
                {hours.map(h => {
                  const n = counts.get(`${di}-${h}`) ?? 0
                  const intensity = n / max
                  return (
                    <div key={h} title={`${day} ${h}:00 — ${n} call${n === 1 ? '' : 's'}`} style={{
                      height: 20, borderRadius: 4,
                      background: n ? `rgba(94,230,255,${0.2 + intensity * 0.8})` : 'rgba(255,255,255,0.04)',
                    }} />
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

// ── Agents ────────────────────────────────────────────────────────
function AgentTable({ agents }: { agents: Overview['agents'] }) {
  return (
    <Card padding={0}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        {sectionTitle(<Zap size={14} color="#7B61FF" />, 'Agents', 'calls handled in this period')}
      </div>
      {!agents.length ? <div style={{ padding: '0 20px 12px' }}><Empty>No agents yet. Create one under Agents.</Empty></div> : (
        <div style={{ overflowX: 'auto' }}>
          <table className="avn-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Calls</th>
                <th style={{ textAlign: 'right' }}>Bookings</th>
                <th style={{ textAlign: 'right' }}>Booking rate</th>
              </tr>
            </thead>
            <tbody>
              {agents.map(a => (
                <tr key={a.id}>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{a.name}</td>
                  <td style={{ textTransform: 'capitalize' }}>{a.status}</td>
                  <td style={{ textAlign: 'right', color: '#9580FF', fontWeight: 700 }}>{a.calls}</td>
                  <td style={{ textAlign: 'right', color: '#22D3A5' }}>{a.bookings}</td>
                  <td style={{ textAlign: 'right' }}>{a.calls ? `${Math.round((a.bookings / a.calls) * 100)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ── Main ──────────────────────────────────────────────────────────
export default function Analytics() {
  const [period, setPeriod] = useState<Period>('7d')
  const [reloads, setReloads] = useState(0)
  // The result remembers which request it answers, so loading is derived instead of set in the effect.
  const [result, setResult] = useState<{ key: string; data?: Overview; error?: string } | null>(null)
  const requestKey = `${period}:${reloads}`

  useEffect(() => {
    let cancelled = false
    analyticsApi.overview(PERIOD_DAYS[period])
      .then(data => { if (!cancelled) setResult({ key: requestKey, data }) })
      .catch(e => { if (!cancelled) setResult({ key: requestKey, error: e instanceof Error ? e.message : 'Failed to load' }) })
    return () => { cancelled = true }
  }, [period, requestKey])

  const loading = result?.key !== requestKey
  const data = loading ? null : result?.data ?? null
  const error = loading ? null : result?.error ?? null
  const reload = useCallback(() => setReloads(n => n + 1), [])

  const calls = data?.daily.reduce((sum, d) => sum + d.calls, 0) ?? 0
  const bookings = data?.daily.reduce((sum, d) => sum + d.bookings, 0) ?? 0
  const seconds = data?.daily.reduce((sum, d) => sum + d.avg_duration * d.calls, 0) ?? 0
  const avgDuration = calls ? Math.round(seconds / calls) : 0
  const bookingRate = calls ? Math.round((bookings / calls) * 100) : 0
  const weekly = period === '7d' && data

  function exportCsv() {
    if (!data) return
    downloadCsv(`avn_analytics_${period}_${new Date().toISOString().slice(0, 10)}.csv`, [
      ['Date', 'Calls', 'Bookings', 'Booking rate %', 'Avg duration (s)'],
      ...data.daily.map(d => [d.date, d.calls, d.bookings, d.calls ? Math.round((d.bookings / d.calls) * 100) : 0, d.avg_duration]),
    ])
  }

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 24 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(94,230,255,0.04))',
          border: '1px solid rgba(123,97,255,0.12)',
          borderRadius: 18, padding: '22px 28px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12,
        }}>
          <div>
            <div style={{
              fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em',
              background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #9580FF)',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 6,
            }}>Analytics</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Calls, bookings, latency and sentiment from your workspace's own records</div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.04)', padding: 4, borderRadius: 10, border: '1px solid rgba(255,255,255,0.07)' }}>
              {(['7d', '30d', '90d'] as Period[]).map(p => (
                <button key={p} onClick={() => setPeriod(p)} style={{
                  padding: '5px 14px', borderRadius: 7, border: 'none',
                  background: period === p ? 'rgba(123,97,255,0.2)' : 'transparent',
                  color: period === p ? '#9580FF' : 'var(--color-text-muted)',
                  fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                }}>{p}</button>
              ))}
            </div>
            <button
              onClick={reload}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 9, color: 'var(--color-text-secondary)', fontSize: 12.5, fontWeight: 500, cursor: 'pointer' }}
            >
              <RefreshCw size={13} /> Refresh
            </button>
            <button
              onClick={exportCsv}
              disabled={!data}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: 'rgba(34,211,165,0.08)', border: '1px solid rgba(34,211,165,0.15)', borderRadius: 9, color: '#22D3A5', fontSize: 12.5, fontWeight: 600, cursor: data ? 'pointer' : 'not-allowed' }}
            >
              <Download size={13} /> Export CSV
            </button>
          </div>
        </div>
      </div>

      <div style={{ padding: '0 32px' }}>
        {loading ? <LoadingState /> : error || !data ? (
          <div style={{ textAlign: 'center', padding: '60px 0' }}>
            <BarChart3 size={32} color="#4B5675" style={{ margin: '0 auto 14px' }} />
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 8 }}>Unable to Load Analytics</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginBottom: 20 }}>{error ?? 'No data'}</div>
            <button onClick={reload} style={{ padding: '9px 20px', background: 'rgba(123,97,255,0.15)', border: '1px solid rgba(123,97,255,0.3)', borderRadius: 10, color: '#9580FF', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Try Again</button>
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px,1fr))', gap: 14, marginBottom: 24 }}>
              <GradientStatCard label="Calls" value={calls} icon={<PhoneCall size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={0} />
              <GradientStatCard label="Bookings" value={bookings} icon={<CalendarCheck size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={60} />
              <GradientStatCard label="Booking rate" value={`${bookingRate}%`} icon={<TrendingUp size={20} color="#fff" />} gradient="linear-gradient(135deg,#5EE6FF,#0EA5E9)" delay={120} />
              <GradientStatCard label="Avg duration" value={`${avgDuration}s`} icon={<Clock size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={180} />
              <GradientStatCard label="Turn latency" value={data.latency.avg_total_ms == null ? '—' : `${Math.round(data.latency.avg_total_ms)}ms`} icon={<Zap size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#9580FF)" delay={240} />
              <GradientStatCard label="Turns using KB" value={data.latency.kb_usage_rate == null ? '—' : `${data.latency.kb_usage_rate}%`} icon={<Brain size={20} color="#fff" />} gradient="linear-gradient(135deg,#5EE6FF,#7B61FF)" delay={300} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 18 }}>
              <MetricCard label="Calls per day" value={String(calls)} icon={<PhoneCall size={16} color="#7B61FF" />} color="#7B61FF" sub={`${period} total`} data={data.daily} valueKey="calls"
                trend={weekly ? pctChange(data.trend.calls_7d, data.trend.calls_prev_7d) : undefined} />
              <MetricCard label="Bookings per day" value={String(bookings)} icon={<CalendarCheck size={16} color="#22D3A5" />} color="#22D3A5" sub={`average call ${fmtDuration(avgDuration)}`} data={data.daily} valueKey="bookings"
                trend={weekly ? pctChange(data.trend.bookings_7d, data.trend.bookings_prev_7d) : undefined} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 18 }}>
              <LatencyCard latency={data.latency} />
              <SentimentCard sentiment={data.sentiment} />
            </div>

            <div style={{ marginBottom: 18 }}>
              <CallHeatmap cells={data.heatmap} timezone={data.timezone} />
            </div>

            <div style={{ marginBottom: 18 }}>
              <AgentTable agents={data.agents} />
            </div>

            <Card padding={0}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                {sectionTitle(<BarChart3 size={14} color="#7B61FF" />, 'Daily breakdown', 'newest first')}
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="avn-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th style={{ textAlign: 'right' }}>Calls</th>
                      <th style={{ textAlign: 'right' }}>Bookings</th>
                      <th style={{ textAlign: 'right' }}>Booking rate</th>
                      <th style={{ textAlign: 'right' }}>Avg duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.daily].reverse().map(row => (
                      <tr key={row.date}>
                        <td style={{ color: 'var(--color-text-primary)' }}>{row.date}</td>
                        <td style={{ textAlign: 'right', color: '#9580FF', fontWeight: 600 }}>{row.calls}</td>
                        <td style={{ textAlign: 'right', color: '#22D3A5' }}>{row.bookings}</td>
                        <td style={{ textAlign: 'right' }}>{row.calls ? `${Math.round((row.bookings / row.calls) * 100)}%` : '—'}</td>
                        <td style={{ textAlign: 'right', color: '#F5A623' }}>{row.calls ? fmtDuration(row.avg_duration) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
