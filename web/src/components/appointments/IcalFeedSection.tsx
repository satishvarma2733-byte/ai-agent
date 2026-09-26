import { useEffect, useState } from 'react'
import { Copy } from 'lucide-react'
import toast from 'react-hot-toast'
import Button from '../ui/Button'
import { calendarApi, type IcalFeed } from '../../api/calendar'

// A secret calendar-feed URL for Apple Calendar, Outlook and other apps that subscribe to a calendar. Admins only.
export default function IcalFeedSection() {
  const [feed, setFeed] = useState<IcalFeed | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { calendarApi.icalFeed().then(setFeed).catch(() => setFeed(null)) }, [])
  if (!feed) return null

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    try { await fn() } catch (e) { toast.error(e instanceof Error ? e.message : 'Something went wrong') } finally { setBusy(false) }
  }
  const rotate = () => act(async () => {
    if (feed.enabled && !confirm('Create a new link? Calendars subscribed to the current link stop updating.')) return
    setFeed(await calendarApi.rotateIcalFeed())
  })
  const off = () => act(async () => {
    if (!confirm('Turn off the calendar feed? Subscribed calendars stop updating.')) return
    await calendarApi.deleteIcalFeed()
    setFeed({ enabled: false })
  })
  const copy = (text: string) => navigator.clipboard.writeText(text).then(() => toast.success('Copied'), () => toast.error('Copy failed'))

  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10, padding: 14, marginTop: 12,
      display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Calendar feed (Apple, Outlook)</span>
      <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
        Subscribe to appointments from any calendar app. Anyone with the link can see them, so share it carefully.
      </div>
      {feed.enabled && feed.url && (
        <div style={{ display: 'flex', gap: 6 }}>
          <input className="avn-input" readOnly aria-label="Calendar feed link" value={feed.url} style={{ flex: 1, height: 30, fontSize: 11, fontFamily: 'monospace' }} />
          <Button size="sm" variant="secondary" icon={<Copy size={12} />} onClick={() => copy(feed.url!)}>Copy</Button>
        </div>
      )}
      {feed.enabled && feed.webcal_url && (
        <a href={feed.webcal_url} style={{ fontSize: 12, color: 'var(--color-link)' }}>Open in my calendar app</a>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <Button size="sm" variant={feed.enabled ? 'secondary' : 'primary'} loading={busy} onClick={rotate} style={{ flex: 1 }}>
          {feed.enabled ? 'New link' : 'Turn on'}
        </Button>
        {feed.enabled && <Button size="sm" variant="ghost" disabled={busy} onClick={off}>Turn off</Button>}
      </div>
    </div>
  )
}
