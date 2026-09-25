import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Calendar } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import { calendarApi, type CalendarProvider, type CalendarStatus } from '../../api/calendar'

const ROLE_RANK: Record<string, number> = { Viewer: 0, Agent: 1, Manager: 2, Admin: 3, Owner: 4 }

/** Connect Google / Zoho Calendar: appointments are copied there, busy time there blocks bookings,
 *  and moves or deletions made there come back. Admins connect; Managers can force a sync. */
export default function CalendarIntegrations({ onChanged }: { onChanged?: () => void }) {
  const role = localStorage.getItem('userRole') || ''
  const isAdmin = (ROLE_RANK[role] ?? -1) >= ROLE_RANK.Admin
  const canSync = (ROLE_RANK[role] ?? -1) >= ROLE_RANK.Manager
  const [items, setItems] = useState<CalendarStatus[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()

  const load = useCallback(() => {
    calendarApi.status().then(setItems).catch(() => setItems([]))
  }, [])

  useEffect(load, [load])

  // Back from the provider's sign-in page.
  useEffect(() => {
    const provider = params.get('calendar')
    const result = params.get('result')
    if (!provider || !result) return
    const label = provider === 'zoho' ? 'Zoho Calendar' : 'Google Calendar'
    if (result === 'connected') toast.success(`${label} connected. Upcoming appointments are being added.`)
    else toast.error(params.get('message') || `Couldn't connect ${label}.`)
    const next = new URLSearchParams(params)
    ;['calendar', 'result', 'message'].forEach(k => next.delete(k))
    setParams(next, { replace: true })
  }, [params, setParams])

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key)
    try {
      await action()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setBusy(null)
    }
  }

  const connect = (p: CalendarProvider) => run(`connect-${p}`, async () => {
    const { url } = await calendarApi.connect(p)
    window.location.assign(url)
  })
  const sync = (p: CalendarProvider) => run(`sync-${p}`, async () => {
    const res = await calendarApi.sync(p)
    toast.success(res.changed ? `Synced. ${res.changed} appointment${res.changed === 1 ? '' : 's'} changed in the calendar.` : 'Calendar is up to date.')
    load()
    if (res.changed) onChanged?.()
  })
  const disconnect = (p: CalendarProvider, label: string) => run(`disconnect-${p}`, async () => {
    if (!window.confirm(`Disconnect ${label}? Events already in the calendar stay there.`)) return
    await calendarApi.disconnect(p)
    toast.success(`${label} disconnected`)
    load()
  })

  return (
    <Card>
      <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Calendar size={15} color="#7B61FF" />
        Calendar Integrations
      </div>
      <p style={{ fontSize: 12, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 16 }}>
        Appointments appear in your calendar, and time you're busy there isn't offered to callers.
      </p>
      {items.map((c, i) => {
        const provider = c.provider as CalendarProvider
        const needsReconnect = c.status === 'error' && (c.last_error ?? '').includes('Connect the calendar again')
        return (
          <div key={c.provider} style={{
            background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10,
            padding: 14, marginBottom: i < items.length - 1 ? 12 : 0, display: 'flex', flexDirection: 'column', gap: 8,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{c.label}</span>
              <Badge variant={!c.connected ? 'default' : c.status === 'error' ? 'danger' : 'success'}>
                {!c.connected ? 'Not connected' : needsReconnect ? 'Reconnect needed' : c.status === 'error' ? 'Sync problem' : 'Connected'}
              </Badge>
            </div>
            {c.connected && (
              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
                {c.account_email && <div>{c.account_email}</div>}
                <div>{c.last_synced_at ? `Last synced ${new Date(c.last_synced_at).toLocaleString()}` : 'Not synced yet'}</div>
                {(c.pending > 0 || c.failed > 0) && (
                  <div>{c.pending > 0 && `${c.pending} waiting`}{c.pending > 0 && c.failed > 0 && ' · '}{c.failed > 0 && `${c.failed} failed`}</div>
                )}
                {c.last_error && <div style={{ color: 'var(--color-danger)' }}>{c.last_error}</div>}
              </div>
            )}
            {!c.available && !c.connected && (
              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>Not set up on this server yet.</div>
            )}
            <div style={{ display: 'flex', gap: 8 }}>
              {(!c.connected || needsReconnect) && isAdmin && c.available && (
                <Button size="sm" variant="primary" loading={busy === `connect-${provider}`} onClick={() => connect(provider)} style={{ flex: 1, height: 32 }}>
                  {needsReconnect ? 'Reconnect' : 'Connect'}
                </Button>
              )}
              {c.connected && !needsReconnect && canSync && (
                <Button size="sm" variant="secondary" loading={busy === `sync-${provider}`} onClick={() => sync(provider)} style={{ flex: 1, height: 32 }}>
                  Sync now
                </Button>
              )}
              {c.connected && isAdmin && (
                <Button size="sm" variant="ghost" loading={busy === `disconnect-${provider}`} onClick={() => disconnect(provider, c.label)} style={{ height: 32 }}>
                  Disconnect
                </Button>
              )}
            </div>
            {!c.connected && c.available && !isAdmin && (
              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>An admin can connect this calendar.</div>
            )}
          </div>
        )
      })}
    </Card>
  )
}
