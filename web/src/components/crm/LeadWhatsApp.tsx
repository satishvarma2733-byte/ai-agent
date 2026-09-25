import { useCallback, useEffect, useState } from 'react'
import { MessageCircle, Send } from 'lucide-react'
import toast from 'react-hot-toast'
import Button from '../ui/Button'
import { whatsappApi, type WhatsAppMessage, type WhatsAppStatus } from '../../api/whatsapp'

const STATUS_LABEL: Record<string, string> = { sent: 'Sent', delivered: 'Delivered', read: 'Read', failed: 'Failed', received: '' }

// WhatsApp conversation with one lead: recent messages both ways, and free text or an approved template to send.
export default function LeadWhatsApp({ leadId, onSent }: { leadId: string; onSent?: () => void }) {
  const [status, setStatus] = useState<WhatsAppStatus | null>(null)
  const [messages, setMessages] = useState<WhatsAppMessage[]>([])
  const [mode, setMode] = useState<'text' | 'template'>('text')
  const [text, setText] = useState('')
  const [template, setTemplate] = useState({ name: '', language: 'en', params: '' })
  const [sending, setSending] = useState(false)

  const load = useCallback(() => {
    whatsappApi.messages(leadId).then(setMessages).catch(() => setMessages([]))
  }, [leadId])

  useEffect(() => {
    whatsappApi.status().then(setStatus).catch(() => setStatus({ connected: false }))
  }, [])
  useEffect(load, [load])

  if (!status) return null

  const send = async () => {
    setSending(true)
    try {
      await whatsappApi.send(mode === 'text'
        ? { lead_id: leadId, text }
        : { lead_id: leadId, template: { name: template.name.trim(), language: template.language.trim() || 'en',
            params: template.params.split('\n').map(p => p.trim()).filter(Boolean) } })
      toast.success('WhatsApp sent')
      setText('')
      onSent?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'WhatsApp not sent')
    } finally {
      setSending(false)
      load()
    }
  }

  const canSend = mode === 'text' ? text.trim().length > 0 : template.name.trim().length > 0
  const field = { width: '100%', padding: '8px 10px', fontSize: 12.5 } as const

  return (
    <div style={{ background: 'var(--color-bg-card)', border: '1px solid rgba(34,211,165,0.2)', borderRadius: 14, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <MessageCircle size={15} color="#22D3A5" />
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>WhatsApp</span>
      </div>
      {!status.connected ? (
        <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Not connected. An admin can connect it in Settings → Integrations.</div>
      ) : (
        <>
          {messages.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 220, overflowY: 'auto' }}>
              {[...messages].reverse().map(m => (
                <div key={m.id} style={{ alignSelf: m.direction === 'in' ? 'flex-start' : 'flex-end', maxWidth: '85%',
                  background: m.direction === 'in' ? 'rgba(255,255,255,0.05)' : 'rgba(34,211,165,0.1)', borderRadius: 10, padding: '6px 10px' }}>
                  <div style={{ fontSize: 12.5, color: 'var(--color-text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{m.body}</div>
                  <div style={{ fontSize: 10.5, color: m.status === 'failed' ? 'var(--color-danger)' : 'var(--color-text-muted)', marginTop: 2 }}>
                    {new Date(m.created_at).toLocaleString()}{STATUS_LABEL[m.status] ? ` · ${STATUS_LABEL[m.status]}` : ''}
                    {m.status === 'failed' && m.error ? ` · ${m.error}` : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div role="radiogroup" aria-label="Message type" style={{ display: 'flex', gap: 6 }}>
            {(['text', 'template'] as const).map(m => (
              <button key={m} role="radio" aria-checked={mode === m} onClick={() => setMode(m)} style={{
                padding: '4px 10px', borderRadius: 7, fontSize: 11.5, cursor: 'pointer', border: '1px solid rgba(255,255,255,0.1)',
                background: mode === m ? 'rgba(34,211,165,0.15)' : 'transparent', color: mode === m ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
              }}>{m === 'text' ? 'Message' : 'Template'}</button>
            ))}
          </div>
          {mode === 'text' ? (
            <textarea className="avn-input" aria-label="WhatsApp message" rows={3} value={text} onChange={e => setText(e.target.value)}
              placeholder="Only reaches the customer within 24 hours of their last message" style={{ ...field, resize: 'vertical' }} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input className="avn-input" aria-label="Template" value={template.name} onChange={e => setTemplate(t => ({ ...t, name: e.target.value }))}
                placeholder={status.provider === 'twilio' ? 'Content SID, e.g. HX…' : 'Template name, e.g. appointment_reminder'} style={field} />
              {status.provider === 'meta' && (
                <input className="avn-input" aria-label="Template language" value={template.language} onChange={e => setTemplate(t => ({ ...t, language: e.target.value }))}
                  placeholder="Language code, e.g. en or en_US" style={field} />
              )}
              <textarea className="avn-input" aria-label="Template values" rows={2} value={template.params} onChange={e => setTemplate(t => ({ ...t, params: e.target.value }))}
                placeholder="Values for {{1}}, {{2}}… one per line" style={{ ...field, resize: 'vertical' }} />
            </div>
          )}
          <Button size="sm" variant="primary" icon={<Send size={12} />} loading={sending} disabled={!canSend} onClick={send} style={{ alignSelf: 'flex-end' }}>
            Send
          </Button>
        </>
      )}
    </div>
  )
}
