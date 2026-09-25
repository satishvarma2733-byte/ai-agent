import { useEffect, useState } from 'react'
import { Copy, Webhook } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import { LoadingState, ErrorState } from '../ui/States'
import { api } from '../../api/client'
import type { Schema } from '../../api/types'

type Status = Schema<'WebhookStatusOut'>
type Created = Schema<'WebhookCreatedOut'>

// Lead-capture webhook: website forms and tools POST leads to a secret URL.
export default function IntegrationsTab({ canEdit }: { canEdit: boolean }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [created, setCreated] = useState<Created | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!canEdit) return
    let cancelled = false
    api.get<Status>('/api/integrations/webhook')
      .then(s => { if (!cancelled) setStatus(s) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load integrations') })
    return () => { cancelled = true }
  }, [canEdit])

  if (!canEdit) return <Card><div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Only Admins and the Owner can manage integrations.</div></Card>
  if (error) return <ErrorState message={error} />
  if (!status) return <LoadingState />

  const rotate = async () => {
    if (status.configured && !confirm('Create a new URL and secret? The current URL stops working immediately.')) return
    setBusy(true)
    try {
      const result = await api.post<Created>('/api/integrations/webhook/rotate')
      setCreated(result)
      setStatus({ configured: true, created_at: new Date().toISOString(), last_used_at: null })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not create the webhook')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!confirm('Turn off the lead webhook? Forms posting to it will get "not found".')) return
    setBusy(true)
    try {
      await api.delete('/api/integrations/webhook')
      setCreated(null)
      setStatus({ configured: false })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not turn off the webhook')
    } finally {
      setBusy(false)
    }
  }

  const copy = (text: string) => navigator.clipboard.writeText(text).then(() => toast.success('Copied'), () => toast.error('Copy failed'))
  const example = created ? `curl -X POST ${created.url} \\\n  -H "Content-Type: application/json" \\\n  -d '{"name": "Asha Rao", "phone": "+919876543210", "email": "asha@example.com"}'` : ''

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <Webhook size={16} color="#9580FF" />
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>Lead capture webhook</div>
        <span className="avn-chip avn-chip-gray" style={{ marginLeft: 'auto' }}>{status.configured ? 'On' : 'Off'}</span>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        POST JSON with <code>name</code> and <code>phone</code> (plus optional <code>email</code>, <code>company</code>, <code>notes</code>,
        {' '}<code>custom_fields</code>) to create a lead, or add to an existing one with the same phone. It fires the
        {' '}"Webhook received" workflow trigger. The signing secret signs your outgoing "Call webhook" workflow steps
        (header <code>X-AVN-Signature: sha256=…</code>).
        {status.configured && status.last_used_at && <> Last used {new Date(status.last_used_at).toLocaleString()}.</>}
      </div>
      {created && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14, padding: 12, border: '1px solid rgba(245,166,35,0.3)', borderRadius: 10 }}>
          <div style={{ fontSize: 12, color: '#F5A623', fontWeight: 600 }}>Copy these now; they won't be shown again.</div>
          {[['URL', created.url], ['Signing secret', created.signing_secret]].map(([label, value]) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{label}</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="avn-input" readOnly value={value} style={{ flex: 1, height: 34, fontFamily: 'monospace', fontSize: 12 }} aria-label={label} />
                <Button variant="secondary" size="sm" icon={<Copy size={12} />} onClick={() => copy(value)}>Copy</Button>
              </div>
            </div>
          ))}
          <pre style={{ margin: 0, fontSize: 11.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: 'var(--color-text-secondary)' }}>{example}</pre>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <Button variant="primary" onClick={rotate} loading={busy}>{status.configured ? 'Create new URL and secret' : 'Turn on'}</Button>
        {status.configured && <Button variant="danger" onClick={remove} disabled={busy}>Turn off</Button>}
      </div>
    </Card>
  )
}
