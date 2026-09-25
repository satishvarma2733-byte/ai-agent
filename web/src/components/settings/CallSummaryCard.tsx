import { useEffect, useState } from 'react'
import { Mail, Send } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import Toggle from '../ui/Toggle'
import { workspaceApi, type CallSummarySettings } from '../../api/workspace'

const TIMEZONES = ['Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Europe/London', 'America/New_York', 'America/Los_Angeles', 'Australia/Sydney', 'UTC']

// After each call, email a summary (who, outcome, mood, what was said) to the team. Admins only.
export default function CallSummaryCard() {
  const [saved, setSaved] = useState<CallSummarySettings | null>(null)
  const [draft, setDraft] = useState<CallSummarySettings | null>(null)
  const [emails, setEmails] = useState('')
  const [busy, setBusy] = useState<'save' | 'test' | null>(null)

  useEffect(() => {
    workspaceApi.callSummaries().then(s => { setSaved(s); setDraft(s); setEmails((s.emails ?? []).join('\n')) }).catch(() => setSaved(null))
  }, [])

  if (!draft || !saved) return null
  const set = <K extends keyof CallSummarySettings>(key: K, value: CallSummarySettings[K]) => setDraft(d => d && { ...d, [key]: value })
  const extra = emails.split(/[\n,]/).map(e => e.trim()).filter(Boolean)
  const nobody = !draft.to_managers && !draft.to_assignee && extra.length === 0

  const save = async () => {
    setBusy('save')
    try {
      const next = await workspaceApi.saveCallSummaries({
        enabled: draft.enabled, to_managers: draft.to_managers, to_assignee: draft.to_assignee, emails: extra,
        min_seconds: draft.min_seconds, include_transcript: draft.include_transcript, timezone: draft.timezone,
      })
      setSaved(next); setDraft(next); setEmails((next.emails ?? []).join('\n'))
      toast.success(next.enabled ? 'Call summaries are on' : 'Call summaries are off')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    setBusy('test')
    try {
      const res = await workspaceApi.testCallSummary()
      toast.success(res.status === 'sent' || res.status === 'logged'
        ? `Latest call's summary sent to ${res.recipients.join(', ')}`
        : `Email failed (${res.status}). Check the email provider settings.`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not send the test')
    } finally {
      setBusy(null)
    }
  }

  const label = { fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6, display: 'block' } as const

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <Mail size={16} color="#9580FF" />
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>Call summaries</div>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 14, maxWidth: 640 }}>
        After each call, email who called, whether they booked, how they sounded and the AI summary. Only calls that end after
        you turn this on are sent.
      </div>
      {!saved.email_ready && (
        <div style={{ fontSize: 12.5, color: 'var(--color-danger)', marginBottom: 14 }}>
          Email isn't set up on this server yet (RESEND_API_KEY and EMAIL_FROM), so summaries can't be delivered.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 520 }}>
        <Toggle id="cs-enabled" checked={draft.enabled} onChange={v => set('enabled', v)} label="Send call summaries" />
        <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <legend style={label}>Send to</legend>
          <Toggle id="cs-managers" checked={draft.to_managers} onChange={v => set('to_managers', v)} label="Managers, Admins and the Owner" />
          <Toggle id="cs-assignee" checked={draft.to_assignee} onChange={v => set('to_assignee', v)} label="The teammate the lead is assigned to" />
        </fieldset>
        <div>
          <label htmlFor="cs-emails" style={label}>Other addresses (one per line, up to 10)</label>
          <textarea id="cs-emails" className="avn-input" rows={3} value={emails} onChange={e => setEmails(e.target.value)}
            placeholder="frontdesk@yourbusiness.com" style={{ width: '100%', padding: '8px 10px', fontSize: 12.5, resize: 'vertical' }} />
        </div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
          <div>
            <label htmlFor="cs-min" style={label}>Skip calls shorter than (seconds)</label>
            <input id="cs-min" className="avn-input" type="number" min={0} max={600} value={draft.min_seconds}
              onChange={e => set('min_seconds', Number(e.target.value))} style={{ width: 120, height: 34 }} />
          </div>
          <div>
            <label htmlFor="cs-tz" style={label}>Times shown in</label>
            <select id="cs-tz" className="avn-input" value={draft.timezone} onChange={e => set('timezone', e.target.value)} style={{ height: 34 }}>
              {[...new Set([draft.timezone, ...TIMEZONES])].map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
          </div>
        </div>
        <Toggle id="cs-transcript" checked={draft.include_transcript} onChange={v => set('include_transcript', v)}
          label="Include the transcript" hint="Up to 3,000 characters; the full transcript stays in Call Logs." />
        {draft.enabled && nobody && <div style={{ fontSize: 12, color: 'var(--color-danger)' }}>Choose at least one recipient.</div>}
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="primary" onClick={save} loading={busy === 'save'} disabled={draft.enabled && nobody}>Save</Button>
          <Button variant="secondary" icon={<Send size={12} />} onClick={test} loading={busy === 'test'} disabled={!saved.email_ready}>
            Send latest call as a test
          </Button>
        </div>
      </div>
    </Card>
  )
}
