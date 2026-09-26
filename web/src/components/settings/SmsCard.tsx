import { useEffect, useState } from 'react'
import { MessageSquare } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import Input from '../ui/Input'
import { smsApi, type SmsStatus } from '../../api/sms'

// The workspace's SMS sender (Twilio), used by the "Send SMS" workflow step.
export default function SmsCard() {
  const [status, setStatus] = useState<SmsStatus | null>(null)
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState({ account_sid: '', auth_token: '', from_number: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => { smsApi.status().then(setStatus).catch(() => setStatus({ connected: false })) }, [])
  if (!status) return null

  const save = async () => {
    setBusy(true)
    try {
      const next = await smsApi.connect(values)
      setStatus(next); setEditing(false); setValues({ account_sid: '', auth_token: '', from_number: '' })
      toast.success(`SMS connected: ${next.sender}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not connect SMS')
    } finally {
      setBusy(false)
    }
  }
  const disconnect = async () => {
    if (!confirm('Disconnect SMS? Workflows that send SMS will fail until it is connected again.')) return
    setBusy(true)
    try { await smsApi.disconnect(); setStatus({ connected: false }) } catch (e) { toast.error(e instanceof Error ? e.message : 'Could not disconnect') } finally { setBusy(false) }
  }
  const showForm = editing || !status.connected

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <MessageSquare size={16} color="#5EE6FF" />
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>SMS</div>
        <span className="avn-chip avn-chip-gray" style={{ marginLeft: 'auto' }}>{status.connected ? `Twilio · ${status.sender}` : 'Not connected'}</span>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        Text reminders and follow-ups from workflows ("Send SMS" step) through your Twilio account. In India, the sender and
        message templates also need DLT registration with the operator.
      </div>
      {showForm && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 14, maxWidth: 520 }}>
          <Input id="sms-sid" label="Account SID" autoComplete="off" value={values.account_sid} onChange={e => setValues(v => ({ ...v, account_sid: e.target.value }))} />
          <Input id="sms-token" label="Auth token" type="password" autoComplete="off" value={values.auth_token} onChange={e => setValues(v => ({ ...v, auth_token: e.target.value }))} />
          <Input id="sms-from" label="SMS number" hint="With country code, e.g. +14155550100" value={values.from_number} onChange={e => setValues(v => ({ ...v, from_number: e.target.value }))} />
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
            <Button variant="secondary" onClick={() => setEditing(true)}>Change</Button>
            <Button variant="danger" onClick={disconnect} disabled={busy}>Disconnect</Button>
          </>
        )}
      </div>
    </Card>
  )
}
