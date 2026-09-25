import { useEffect, useState } from 'react'
import { Copy, MessageCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import Input from '../ui/Input'
import Select from '../ui/Select'
import { whatsappApi, type WhatsAppConnect, type WhatsAppStatus } from '../../api/whatsapp'

type Provider = 'meta' | 'twilio'

const FIELDS: Record<Provider, { key: keyof WhatsAppConnect; label: string; hint?: string; secret?: boolean }[]> = {
  meta: [
    { key: 'phone_number_id', label: 'Phone number ID', hint: 'WhatsApp Manager → API setup' },
    { key: 'access_token', label: 'Access token', hint: 'A permanent system-user token with whatsapp_business_messaging', secret: true },
    { key: 'app_secret', label: 'App secret', hint: 'App settings → Basic; used to check webhook signatures', secret: true },
  ],
  twilio: [
    { key: 'account_sid', label: 'Account SID' },
    { key: 'auth_token', label: 'Auth token', secret: true },
    { key: 'from_number', label: 'WhatsApp sender number', hint: 'With country code, e.g. +14155550100' },
  ],
}

// A workspace's WhatsApp sender: Meta Cloud API or Twilio. Credentials are checked with the provider before saving.
export default function WhatsAppCard() {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null)
  const [editing, setEditing] = useState(false)
  const [provider, setProvider] = useState<Provider>('meta')
  const [values, setValues] = useState<Partial<WhatsAppConnect>>({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    whatsappApi.status().then(setStatus).catch(() => setStatus({ connected: false }))
  }, [])

  if (!status) return null

  const save = async () => {
    setBusy(true)
    try {
      const next = await whatsappApi.connect({ ...values, provider } as WhatsAppConnect)
      setStatus(next)
      setEditing(false)
      setValues({})
      toast.success(`WhatsApp connected: ${next.sender}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not connect WhatsApp')
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    if (!confirm('Disconnect WhatsApp? Workflows that send WhatsApp messages will fail until it is connected again.')) return
    setBusy(true)
    try {
      await whatsappApi.disconnect()
      setStatus({ connected: false })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not disconnect')
    } finally {
      setBusy(false)
    }
  }

  const copy = (text: string) => navigator.clipboard.writeText(text).then(() => toast.success('Copied'), () => toast.error('Copy failed'))
  const showForm = editing || !status.connected

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <MessageCircle size={16} color="#22D3A5" />
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>WhatsApp</div>
        <span className="avn-chip avn-chip-gray" style={{ marginLeft: 'auto' }}>
          {status.connected ? `${status.provider === 'meta' ? 'Meta' : 'Twilio'} · ${status.sender}` : 'Not connected'}
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        Send messages from the CRM and from workflows ("Send WhatsApp" step). Free text only reaches customers who
        messaged you in the last 24 hours; otherwise use an approved template. Replies appear on the lead's timeline.
      </div>

      {status.connected && status.webhook_url && !editing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
            {status.provider === 'meta'
              ? 'In your Meta app, set the WhatsApp webhook to this URL with this verify token, and subscribe to "messages".'
              : 'In Twilio, set this as the sender\'s "A message comes in" webhook. Delivery updates use it automatically.'}
          </div>
          {[['Webhook URL', status.webhook_url], ...(status.verify_token ? [['Verify token', status.verify_token]] : [])].map(([label, value]) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>{label}</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="avn-input" readOnly value={value ?? ''} aria-label={label} style={{ flex: 1, height: 34, fontFamily: 'monospace', fontSize: 12 }} />
                <Button variant="secondary" size="sm" icon={<Copy size={12} />} onClick={() => copy(value ?? '')}>Copy</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 14, maxWidth: 520 }}>
          <Select label="Provider" id="wa-provider" value={provider} onChange={e => { setProvider(e.target.value as Provider); setValues({}) }}
            options={[{ value: 'meta', label: 'Meta WhatsApp Cloud API' }, { value: 'twilio', label: 'Twilio' }]} />
          {FIELDS[provider].map(f => (
            <Input key={f.key} id={`wa-${f.key}`} label={f.label} hint={f.hint} type={f.secret ? 'password' : 'text'} autoComplete="off"
              value={(values[f.key] as string | undefined) ?? ''} onChange={e => setValues(v => ({ ...v, [f.key]: e.target.value }))} />
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        {showForm ? (
          <>
            <Button variant="primary" onClick={save} loading={busy}>Check and connect</Button>
            {status.connected && <Button variant="ghost" onClick={() => setEditing(false)} disabled={busy}>Cancel</Button>}
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => { setProvider((status.provider as Provider) ?? 'meta'); setEditing(true) }}>Change</Button>
            <Button variant="danger" onClick={disconnect} disabled={busy}>Disconnect</Button>
          </>
        )}
      </div>
    </Card>
  )
}
