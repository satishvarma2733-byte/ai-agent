import { useEffect, useState, useCallback, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  Phone,
  Users,
  Bot,
  Percent,
  Clock,
  Wifi,
  WifiOff,
  RefreshCw,
  ArrowRight,
  AlertTriangle,
  PhoneOff,
  Activity,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'

import { LoadingState, ErrorState } from '../components/ui/States'
import { statsApi } from '../api/stats'
import { logsApi } from '../api/logs'
import { kbApi } from '../api/kb'
import { crmApi } from '../api/crm'
import { analyticsApi, type Overview as OverviewData } from '../api/analytics'
import { callsApi, type LiveCalls } from '../api/calls'
import type { CallLog, KbStatus, Lead } from '../types'

// ── Helpers ─────────────────────────────────────────────────────────

function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.max(0, sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function pctChange(now: number, before: number): number | null {
  if (!before) return null
  return Math.round(((now - before) / before) * 100)
}

function timeAgo(iso: string, now: number): string {
  const sec = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (sec < 60) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

const ACTIVITY_COLORS: Record<string, string> = { call: '#6D5DFE', lead: '#3B82F6', appointment: '#22C55E' }

const label = { fontSize: 11, fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em' } as const

// ── Sub-components ───────────────────────────────────────────────────

function KpiCard({ title, value, accent, children, aside }: {
  title: string; value: ReactNode; accent: string; children?: ReactNode; aside?: ReactNode
}) {
  return (
    <div className="avn-card" style={{ padding: '16px 20px', borderTop: `2px solid ${accent}`, borderRadius: '0 0 12px 12px', minHeight: 108, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{ ...label, marginBottom: 8 }}>{title}</div>
          <div style={{ fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.04em', color: 'var(--color-text-primary)', lineHeight: 1 }}>{value}</div>
        </div>
        {aside}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 'auto', fontSize: 11, color: 'var(--color-text-muted)' }}>{children}</div>
    </div>
  )
}

function Trend({ change, suffix = 'vs previous 7 days' }: { change: number | null; suffix?: string }) {
  if (change === null) return <span>No calls in the previous 7 days</span>
  const up = change >= 0
  return (
    <>
      {up ? <TrendingUp size={10} color="#4ADE80" /> : <TrendingDown size={10} color="#F87171" />}
      <span style={{ color: up ? '#4ADE80' : '#F87171', fontWeight: 500 }}>{Math.abs(change)}%</span>
      <span>{suffix}</span>
    </>
  )
}

function Sparkline({ data, color, width = 80, height = 28 }: { data: number[]; color: string; width?: number; height?: number }) {
  if (data.length < 2 || !data.some(Boolean)) return null
  const max = Math.max(...data, 1)
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - (v / max) * height}`).join(' ')
  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CardHeader({ children, link }: { children: ReactNode; link?: { to: string; text: string } }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{children}</div>
      {link && (
        <Link to={link.to} style={{ fontSize: 12, color: 'var(--color-link)', textDecoration: 'none', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4 }}>
          {link.text} <ArrowRight size={11} />
        </Link>
      )}
    </div>
  )
}

function Muted({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', textAlign: 'center', padding: '20px 16px' }}>{children}</div>
}

function fetchDashboard() {
  return Promise.allSettled([
    analyticsApi.overview(14),
    callsApi.live(),
    logsApi.list(),
    kbApi.status(),
    statsApi.health(),
    crmApi.listLeads(),
  ])
}

// ══════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ══════════════════════════════════════════════════════════════════════

export default function Overview() {
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [live, setLive] = useState<LiveCalls | null>(null)
  const [logs, setLogs] = useState<CallLog[]>([])
  const [kbStatus, setKbStatus] = useState<KbStatus | null>(null)
  const [health, setHealth] = useState<'ok' | 'error' | 'loading'>('loading')
  const [leads, setLeads] = useState<Lead[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [ending, setEnding] = useState<string | null>(null)

  const apply = useCallback((results: Awaited<ReturnType<typeof fetchDashboard>>) => {
    const [o, lc, l, kb, h, crmLeads] = results
    if (o.status === 'fulfilled') { setOverview(o.value); setError(null) }
    else setError(o.reason instanceof Error ? o.reason.message : 'Failed to load overview')
    setLive(lc.status === 'fulfilled' ? lc.value : null)
    if (l.status === 'fulfilled') setLogs(Array.isArray(l.value) ? l.value.slice(0, 5) : [])
    if (kb.status === 'fulfilled') setKbStatus(kb.value)
    if (crmLeads.status === 'fulfilled') setLeads(crmLeads.value)
    setHealth(h.status === 'fulfilled' ? 'ok' : 'error')
    setLoaded(true)
  }, [])

  const load = useCallback(async () => apply(await fetchDashboard()), [apply])

  useEffect(() => {
    let cancelled = false
    fetchDashboard().then(results => { if (!cancelled) apply(results) })
    // Live calls change quickly; the rest refreshes on demand.
    const poll = setInterval(() => {
      callsApi.live().then(setLive).catch(() => setLive(null))
    }, 15000)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => { cancelled = true; clearInterval(poll); clearInterval(tick) }
  }, [apply])

  const handleRefresh = async () => {
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  const endCall = async (id: string) => {
    if (!confirm('End this call for everyone on it?')) return
    setEnding(id)
    try {
      await callsApi.end(id)
      toast.success('Call ended')
      setLive(await callsApi.live())
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not end the call')
    } finally {
      setEnding(null)
    }
  }

  if (!loaded) return <div style={{ padding: 48 }}><LoadingState /></div>
  if (error || !overview) return <div style={{ padding: 48 }}><ErrorState message={error ?? 'No data'} onRetry={handleRefresh} /></div>

  const { totals, trend, daily, agents, activity } = overview
  const liveCalls = live?.calls ?? []
  const activeAgents = agents.filter(a => a.status !== 'disabled').length
  const totalLeads = leads.length
  const convertedLeads = leads.filter(l => l.status === 'Converted').length
  const conversionRate = totalLeads ? Math.round((convertedLeads / totalLeads) * 100) : 0
  const yesterday = daily.length > 1 ? daily[daily.length - 2].calls : 0

  return (
    <div className="page-wrapper">

      {/* ── Top Bar ── */}
      <div style={{ padding: '20px 28px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)', letterSpacing: '-0.02em', marginBottom: 2 }}>Overview</div>
          <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>Your workspace's calls, agents and leads</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '6px 12px', background: 'var(--color-bg-surface)', border: `1px solid ${health === 'ok' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`, borderRadius: 8 }}>
            {health === 'ok' ? <Wifi size={13} color="#22C55E" /> : <WifiOff size={13} color="#EF4444" />}
            <span style={{ fontSize: 12, fontWeight: 500, color: health === 'ok' ? '#4ADE80' : '#F87171' }}>
              {health === 'ok' ? 'API reachable' : 'API unreachable'}
            </span>
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            aria-label="Refresh"
            style={{ width: 34, height: 34, borderRadius: 8, background: 'var(--color-bg-surface)', border: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: refreshing ? 'wait' : 'pointer', color: 'var(--color-text-secondary)' }}
          >
            <RefreshCw size={14} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>
      </div>

      <div style={{ padding: '0 28px' }}>

        {live && !live.configured && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', marginBottom: 24, background: 'var(--color-bg-surface)', border: '1px solid rgba(255,255,255,0.07)', borderLeft: '3px solid #F59E0B', borderRadius: '0 8px 8px 0' }}>
            <AlertTriangle size={14} color="#F59E0B" style={{ flexShrink: 0 }} />
            <div style={{ flex: 1, fontSize: 13, color: 'var(--color-text-primary)' }}>
              LiveKit is not configured <span style={{ color: 'var(--color-text-secondary)' }}>· live calls can't be shown or controlled until it is.</span>
            </div>
            <Link to="/configuration" style={{ padding: '4px 12px', fontSize: 12, fontWeight: 500, color: 'var(--color-text-primary)', border: '1px solid rgba(245,158,11,0.4)', borderRadius: 6, textDecoration: 'none' }}>
              Configure
            </Link>
          </div>
        )}

        {/* ── KPI Row ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
          <KpiCard title="Total calls" value={totals.calls.toLocaleString()} accent="#6D5DFE" aside={<Sparkline data={daily.map(d => d.calls)} color="#6D5DFE" />}>
            <Trend change={pctChange(trend.calls_7d, trend.calls_prev_7d)} />
          </KpiCard>
          <KpiCard title="Booking rate" value={`${totals.booking_rate}%`} accent="#22C55E" aside={<Sparkline data={daily.map(d => d.bookings)} color="#22C55E" />}>
            <span>{totals.bookings.toLocaleString()} calls ended in a booking</span>
          </KpiCard>
          <KpiCard title="Avg call duration" value={fmtDuration(totals.avg_duration)} accent="#F59E0B">
            <span>{totals.minutes.toLocaleString()} minutes in total</span>
          </KpiCard>
          <KpiCard title="Agents" value={agents.length} accent="#3B82F6" aside={<Bot size={20} color="#3B82F6" style={{ opacity: 0.6 }} />}>
            <span>{live?.configured ? `${liveCalls.length} live call${liveCalls.length === 1 ? '' : 's'} now` : `${activeAgents} not disabled`}</span>
          </KpiCard>
        </div>

        {/* ── Live Calls + Agents ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16, marginBottom: 16, alignItems: 'start' }}>

          <div className="avn-card" style={{ overflow: 'hidden' }}>
            <CardHeader link={{ to: '/live-calls', text: 'View all' }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: liveCalls.length ? '#EF4444' : '#3F3F46', animation: liveCalls.length ? 'pulse-dot 1.5s ease-in-out infinite' : 'none' }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Live Calls</span>
              <span style={{ padding: '1px 7px', borderRadius: 4, background: 'rgba(239,68,68,0.12)', fontSize: 11.5, fontWeight: 600, color: '#F87171' }}>{liveCalls.length}</span>
            </CardHeader>
            {!live ? <Muted>Live calls could not be loaded.</Muted>
              : !live.configured ? <Muted>Connect LiveKit in Configuration to see calls as they happen.</Muted>
              : !liveCalls.length ? <Muted>No calls in progress.</Muted>
              : liveCalls.map(call => (
                <div key={call.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto', alignItems: 'center', gap: 16, padding: '11px 20px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 1 }}>{call.caller_name || call.phone_number}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>{call.phone_number}</div>
                  </div>
                  <div style={{ padding: '2px 8px', borderRadius: 4, background: 'rgba(109,93,254,0.12)', color: '#9B8EFF', fontSize: 11.5, fontWeight: 500, textTransform: 'capitalize' }}>{call.direction}</div>
                  <div style={{ fontFamily: 'JetBrains Mono, Fira Code, monospace', fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', minWidth: 44, textAlign: 'right' }}>
                    {fmtDuration(Math.round((now - new Date(call.started_at).getTime()) / 1000))}
                  </div>
                  <button
                    title="End call"
                    disabled={ending === call.id}
                    onClick={() => endCall(call.id)}
                    style={{ width: 28, height: 28, borderRadius: 6, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#EF4444' }}
                  >
                    <PhoneOff size={13} />
                  </button>
                </div>
              ))}
          </div>

          <div className="avn-card" style={{ overflow: 'hidden' }}>
            <CardHeader link={{ to: '/agents', text: 'All agents' }}>
              <Bot size={14} color="#6D5DFE" />
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Agents</span>
              <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>calls, last 14 days</span>
            </CardHeader>
            {!agents.length ? <Muted>No agents yet.</Muted> : agents.slice(0, 5).map((agent, i) => (
              <div key={agent.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ width: 32, height: 32, borderRadius: 8, background: `hsl(${240 + i * 30}, 60%, 25%)`, border: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, color: '#FFFFFF', flexShrink: 0 }}>
                  {agent.name[0]?.toUpperCase() ?? '?'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{agent.name}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', textTransform: 'capitalize' }}>{agent.status}</div>
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#A1A1AA' }}>{agent.calls}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Calls chart, Recent calls, Activity ── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 280px', gap: 16, marginBottom: 32 }}>

          <div className="avn-card" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 2 }}>Calls per day</div>
            <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginBottom: 16 }}>Last 14 days · bookings in green</div>
            {!daily.some(d => d.calls) ? <Muted>No calls in the last 14 days.</Muted> : (
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 120 }}>
                {daily.map(d => {
                  const max = Math.max(...daily.map(x => x.calls), 1)
                  return (
                    <div key={d.date} title={`${d.date}: ${d.calls} calls, ${d.bookings} booked`} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                      <div style={{ height: `${(d.calls / max) * 100}%`, minHeight: d.calls ? 3 : 1, background: 'rgba(109,93,254,0.55)', borderRadius: '3px 3px 0 0', position: 'relative' }}>
                        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: d.calls ? `${(d.bookings / d.calls) * 100}%` : 0, background: '#22C55E', borderRadius: d.bookings === d.calls ? '3px 3px 0 0' : 0 }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            {overview.latency.avg_total_ms != null && (
              <div style={{ marginTop: 14, fontSize: 11.5, color: 'var(--color-text-secondary)' }}>
                Average agent response: <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{Math.round(overview.latency.avg_total_ms)} ms</span> over {overview.latency.turns} turns
              </div>
            )}
          </div>

          <div className="avn-card" style={{ padding: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={label}>Recent calls</span>
              <Link to="/call-logs" style={{ fontSize: 11.5, color: 'var(--color-link)', textDecoration: 'none', fontWeight: 500 }}>View all</Link>
            </div>
            {logs.length === 0 ? <Muted>No calls yet.</Muted> : logs.map((log, i) => (
              <div key={log.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderBottom: i < logs.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                <div style={{ width: 28, height: 28, borderRadius: 6, background: `hsl(${200 + i * 40}, 40%, 20%)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: '#FFFFFF', flexShrink: 0 }}>
                  {(log.caller_name || log.phone_number)?.[0] || '#'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.caller_name || log.phone_number}</div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{timeAgo(log.created_at, now)} · {fmtDuration(log.duration_seconds)}</div>
                </div>
                <div style={{ padding: '2px 7px', borderRadius: 4, background: log.was_booked ? 'rgba(34,197,94,0.10)' : 'rgba(255,255,255,0.05)', fontSize: 11, fontWeight: 500, color: log.was_booked ? '#4ADE80' : '#71717A' }}>
                  {log.was_booked ? 'Booked' : 'Ended'}
                </div>
              </div>
            ))}
          </div>

          <div className="avn-card" style={{ overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '14px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <Activity size={13} color="#71717A" />
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Activity</span>
            </div>
            <div style={{ padding: '4px 0' }}>
              {!activity.length ? <Muted>Nothing has happened yet.</Muted> : activity.slice(0, 6).map((item, i) => (
                <div key={`${item.kind}-${item.at}-${i}`} style={{ display: 'flex', gap: 10, padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: ACTIVITY_COLORS[item.kind] ?? '#71717A', marginTop: 5, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--color-text-primary)', marginBottom: 2, lineHeight: 1.3 }}>{item.title}</div>
                    <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>{timeAgo(item.at, now)}</div>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ padding: '10px 16px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 10px', background: 'var(--color-bg-surface)', border: '1px solid rgba(255,255,255,0.06)', borderLeft: `3px solid ${kbStatus?.kb_enabled ? '#22C55E' : '#F59E0B'}`, borderRadius: '0 8px 8px 0' }}>
                <div>
                  <div style={{ fontSize: 11.5, fontWeight: 500, color: '#A1A1AA' }}>Knowledge Base</div>
                  <div style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>
                    {!kbStatus ? 'Status unavailable' : kbStatus.kb_enabled ? `${kbStatus.counts?.chunks || 0} chunks indexed` : 'Turned off in Configuration'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Leads ── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32 }}>
          {[
            { label: 'Total Leads', value: totalLeads, icon: <Users size={14} color="#71717A" />, desc: 'In CRM pipeline' },
            { label: 'Lead conversion', value: `${conversionRate}%`, icon: <Percent size={14} color="#71717A" />, desc: `${convertedLeads} converted` },
            { label: 'Calls Today', value: totals.calls_today, icon: <Phone size={14} color="#71717A" />, desc: `${yesterday} yesterday` },
            { label: 'Overdue follow-ups', value: overview.follow_ups.overdue, icon: <Clock size={14} color="#71717A" />, desc: `${overview.follow_ups.today} due today`, to: '/crm?follow_up=overdue' },
          ].map((item: { label: string; value: ReactNode; icon: ReactNode; desc: string; to?: string }) => (
            <Link key={item.label} to={item.to ?? '/crm'} className="avn-card" style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {item.icon}
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 2 }}>{item.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: 2 }}>{item.value}</div>
                <div style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{item.desc}</div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse-dot { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        @media (max-width: 1280px) {
          .page-wrapper [style*="grid-template-columns: repeat(4"] { grid-template-columns: repeat(2, 1fr) !important; }
          .page-wrapper [style*="1fr 320px"] { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 960px) {
          .page-wrapper [style*="1fr 1fr 280px"] { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  )
}
