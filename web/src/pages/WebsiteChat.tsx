import { useCallback, useEffect, useState } from 'react'
import { Copy, KeyRound, MessageSquare, Plus, RefreshCw, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { LoadingState } from '../components/ui/States'
import { agentsApi, type Agent } from '../api/agents'
import { widgetsApi, type ApiKey, type ChatConversation, type Widget } from '../api/widgets'

const ROLE_RANK: Record<string, number> = { Viewer: 0, Agent: 1, Manager: 2, Admin: 3, Owner: 4 }
const label = { fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 } as const
const field = { width: '100%', height: 34 } as const
const copy = (text: string) => navigator.clipboard.writeText(text).then(() => toast.success('Copied'), () => toast.error('Copy failed'))
const errorText = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback)

function SectionTitle({ icon, title, hint }: { icon: React.ReactNode; title: string; hint: string }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)' }}>{icon}{title}</div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginTop: 3 }}>{hint}</div>
    </div>
  )
}

function Toggle({ id, checked, onChange, children }: { id: string; checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label htmlFor={id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
      <input id={id} type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />{children}
    </label>
  )
}

function NewWidget({ agents, onCreated }: { agents: Agent[]; onCreated: () => void }) {
  const [form, setForm] = useState({ name: 'Website chat', agent_id: '', origins: '', greeting: '', color: '#7B61FF', voice_enabled: false, lead_capture: true })
  const [saving, setSaving] = useState(false)
  const agentId = form.agent_id || agents[0]?.id || ''
  const create = async () => {
    setSaving(true)
    try {
      await widgetsApi.create({ name: form.name.trim(), agent_id: agentId, allowed_origins: form.origins.split(/[\s,]+/).filter(Boolean),
        greeting: form.greeting.trim() || null, color: form.color, voice_enabled: form.voice_enabled, lead_capture: form.lead_capture })
      toast.success('Widget created. Copy the embed code into your site.')
      setForm(f => ({ ...f, origins: '', greeting: '' }))
      onCreated()
    } catch (e) {
      toast.error(errorText(e, 'Could not create the widget'))
    } finally {
      setSaving(false)
    }
  }
  if (!agents.length) return <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>Create an agent first; the widget answers with one of your agents.</div>
  return (
    <details>
      <summary style={{ fontSize: 13, cursor: 'pointer', color: 'var(--color-link)' }}>Add a widget</summary>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10, marginTop: 10 }}>
        <div>
          <label htmlFor="w-name" style={label}>Name</label>
          <input id="w-name" className="avn-input" value={form.name} maxLength={100} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={field} />
        </div>
        <div>
          <label htmlFor="w-agent" style={label}>Agent</label>
          <select id="w-agent" className="avn-input" value={agentId} onChange={e => setForm(f => ({ ...f, agent_id: e.target.value }))} style={field}>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}{a.production_version ? '' : ' (not live yet)'}</option>)}
          </select>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="w-origins" style={label}>Websites it runs on (one per line), e.g. https://www.example.com</label>
          <textarea id="w-origins" className="avn-input" rows={2} value={form.origins} onChange={e => setForm(f => ({ ...f, origins: e.target.value }))}
            style={{ width: '100%', padding: '7px 10px', fontSize: 12.5 }} placeholder="https://www.example.com" />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <label htmlFor="w-greeting" style={label}>First message (leave empty to use the agent's greeting)</label>
          <input id="w-greeting" className="avn-input" value={form.greeting} maxLength={500} onChange={e => setForm(f => ({ ...f, greeting: e.target.value }))} style={field} />
        </div>
        <div>
          <label htmlFor="w-color" style={label}>Colour</label>
          <input id="w-color" type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 60, height: 34, border: 'none', background: 'none' }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, justifyContent: 'flex-end' }}>
          <Toggle id="w-voice" checked={form.voice_enabled} onChange={v => setForm(f => ({ ...f, voice_enabled: v }))}>Let visitors talk by voice (uses call minutes)</Toggle>
          <Toggle id="w-lead" checked={form.lead_capture} onChange={v => setForm(f => ({ ...f, lead_capture: v }))}>Ask for contact details and add them to the CRM</Toggle>
        </div>
      </div>
      <Button variant="primary" size="sm" icon={<Plus size={13} />} style={{ marginTop: 10 }} loading={saving}
        disabled={!form.name.trim() || !agentId || !form.origins.trim()} onClick={create}>Create widget</Button>
    </details>
  )
}

function WidgetCard({ w, onChanged }: { w: Widget; onChanged: () => void }) {
  const update = async (patch: Parameters<typeof widgetsApi.update>[1]) => {
    try { await widgetsApi.update(w.id, patch); onChanged() } catch (e) { toast.error(errorText(e, 'Could not save')) }
  }
  const rotate = async () => {
    if (!confirm('Make a new key? The embed code on your site stops working until you replace it.')) return
    try { await widgetsApi.rotateKey(w.id); toast.success('New key made. Update the embed code on your site.'); onChanged() } catch (e) { toast.error(errorText(e, 'Could not rotate')) }
  }
  const remove = async () => {
    if (!confirm(`Delete "${w.name}"? The chat disappears from your site.`)) return
    try { await widgetsApi.remove(w.id); onChanged() } catch (e) { toast.error(errorText(e, 'Could not delete')) }
  }
  const editOrigins = async () => {
    const next = prompt('Websites it runs on, separated by commas', w.allowed_origins.join(', '))
    if (next !== null) await update({ allowed_origins: next.split(/[\s,]+/).filter(Boolean) })
  }
  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.07)', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span aria-hidden style={{ width: 12, height: 12, borderRadius: 99, background: w.color }} />
        <strong style={{ fontSize: 14, color: 'var(--color-text-primary)' }}>{w.name}</strong>
        <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>answers as {w.agent_name}</span>
        {!w.agent_live && <span style={{ fontSize: 11.5, color: 'var(--color-warning, #F5A524)' }}>Agent isn't live yet: the chat won't open until a version is activated.</span>}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          <button onClick={rotate} className="avn-btn avn-btn-secondary" style={{ height: 30, fontSize: 12 }} aria-label={`New key for ${w.name}`}><RefreshCw size={12} /> New key</button>
          <button onClick={remove} className="avn-btn avn-btn-secondary" style={{ height: 30, color: 'var(--color-danger)' }} aria-label={`Delete ${w.name}`}><Trash2 size={13} /></button>
        </div>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>
        Runs on: {w.allowed_origins.join(', ')} <button onClick={editOrigins} style={{ background: 'none', border: 'none', color: 'var(--color-link)', cursor: 'pointer', fontSize: 12.5 }}>Edit</button>
      </div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <Toggle id={`on-${w.id}`} checked={w.enabled} onChange={v => update({ enabled: v })}>On</Toggle>
        <Toggle id={`voice-${w.id}`} checked={w.voice_enabled} onChange={v => update({ voice_enabled: v })}>Voice</Toggle>
        <Toggle id={`lead-${w.id}`} checked={w.lead_capture} onChange={v => update({ lead_capture: v })}>Capture leads</Toggle>
      </div>
      <div>
        <div style={label}>Embed code: paste it before &lt;/body&gt; on your site</div>
        <div style={{ display: 'flex', gap: 6 }}>
          <code style={{ flex: 1, fontSize: 11.5, padding: '8px 10px', borderRadius: 8, background: 'rgba(0,0,0,0.25)', overflowX: 'auto', whiteSpace: 'nowrap' }}>{w.embed_code}</code>
          <button onClick={() => copy(w.embed_code)} className="avn-btn avn-btn-secondary" style={{ height: 34 }} aria-label="Copy embed code"><Copy size={13} /></button>
        </div>
      </div>
    </div>
  )
}

function ApiKeys() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null)
  const [name, setName] = useState('')
  const [created, setCreated] = useState<string | null>(null)
  const load = useCallback(() => { widgetsApi.apiKeys().then(setKeys).catch(() => setKeys([])) }, [])
  useEffect(load, [load])
  const create = async () => {
    try { const res = await widgetsApi.createApiKey(name.trim()); setCreated(res.key); setName(''); load() } catch (e) { toast.error(errorText(e, 'Could not create the key')) }
  }
  const revoke = async (k: ApiKey) => {
    if (!confirm(`Revoke "${k.name}"? Anything using it stops working.`)) return
    try { await widgetsApi.revokeApiKey(k.id); load() } catch (e) { toast.error(errorText(e, 'Could not revoke')) }
  }
  return (
    <Card>
      <SectionTitle icon={<KeyRound size={16} color="#9580FF" />} title="Chat API keys"
        hint="For your own server or app: POST /api/public/chat with Authorization: Bearer <key> and {message, agent_id, session}. Keep keys secret; never put them in a web page." />
      {created && (
        <div role="status" style={{ border: '1px solid rgba(34,211,165,0.3)', borderRadius: 10, padding: 10, marginBottom: 12, fontSize: 12.5 }}>
          <div style={{ marginBottom: 6, color: 'var(--color-text-primary)' }}>Copy this key now. It won't be shown again.</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <code style={{ flex: 1, padding: '7px 10px', borderRadius: 8, background: 'rgba(0,0,0,0.25)', overflowX: 'auto', whiteSpace: 'nowrap' }}>{created}</code>
            <button onClick={() => copy(created)} className="avn-btn avn-btn-secondary" style={{ height: 32 }} aria-label="Copy API key"><Copy size={13} /></button>
            <button onClick={() => setCreated(null)} className="avn-btn avn-btn-secondary" style={{ height: 32, fontSize: 12 }}>Done</button>
          </div>
        </div>
      )}
      {keys === null ? <LoadingState /> : keys.map(k => (
        <div key={k.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: 12.5 }}>
          <strong style={{ color: k.revoked_at ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}>{k.name}</strong>
          <code style={{ color: 'var(--color-text-muted)' }}>{k.prefix}…</code>
          <span style={{ color: 'var(--color-text-muted)', marginLeft: 'auto' }}>
            {k.revoked_at ? 'Revoked' : k.last_used_at ? `Used ${formatDistanceToNow(new Date(k.last_used_at), { addSuffix: true })}` : 'Never used'}
          </span>
          {!k.revoked_at && <button onClick={() => revoke(k)} className="avn-btn avn-btn-secondary" style={{ height: 28, fontSize: 12 }}>Revoke</button>}
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
        <input className="avn-input" aria-label="Key name" placeholder="Key name, e.g. Mobile app" value={name} maxLength={100} onChange={e => setName(e.target.value)} style={{ flex: 1, height: 32 }} />
        <Button variant="secondary" size="sm" disabled={!name.trim()} onClick={create}>Create key</Button>
      </div>
    </Card>
  )
}

function Conversations() {
  const [items, setItems] = useState<ChatConversation[] | null>(null)
  useEffect(() => { widgetsApi.conversations().then(setItems).catch(() => setItems([])) }, [])
  return (
    <Card>
      <SectionTitle icon={<MessageSquare size={16} color="#22D3A5" />} title="Recent conversations" hint="The latest chats from your website and the API." />
      {items === null ? <LoadingState /> : items.length === 0 ? (
        <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>No conversations yet.</div>
      ) : items.map(c => (
        <details key={c.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', padding: '8px 0' }}>
          <summary style={{ cursor: 'pointer', fontSize: 12.5, color: 'var(--color-text-secondary)' }}>
            <strong style={{ color: 'var(--color-text-primary)' }}>{c.lead_name || 'Visitor'}</strong> · {c.source} · {c.messages} message{c.messages === 1 ? '' : 's'} · {formatDistanceToNow(new Date(c.updated_at), { addSuffix: true })}
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
            {c.turns.map((t, i) => (
              <div key={i} style={{ fontSize: 12.5, whiteSpace: 'pre-wrap', color: t.role === 'caller' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>
                <strong>{t.role === 'caller' ? 'Visitor' : c.agent_name}:</strong> {t.text}
              </div>
            ))}
          </div>
        </details>
      ))}
    </Card>
  )
}

// Website chat: the widget for the workspace's site, API keys for its own apps, and the conversations they bring in.
export default function WebsiteChat() {
  const role = localStorage.getItem('userRole') || ''
  const isAdmin = (ROLE_RANK[role] ?? -1) >= ROLE_RANK.Admin
  const [widgets, setWidgets] = useState<Widget[] | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const load = useCallback(() => {
    if (!isAdmin) return
    widgetsApi.list().then(setWidgets).catch(e => { setWidgets([]); toast.error(errorText(e, 'Could not load widgets')) })
  }, [isAdmin])
  useEffect(load, [load])
  useEffect(() => { if (isAdmin) agentsApi.list().then(setAgents).catch(() => setAgents([])) }, [isAdmin])

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 20 }}>
        <div style={{ background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(34,211,165,0.04))', border: '1px solid rgba(123,97,255,0.14)', borderRadius: 18, padding: '22px 28px' }}>
          <div style={{ fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--color-text-primary)', marginBottom: 6 }}>Website chat</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Put your agent on your website as a chat (and voice) bubble. Visitors who leave their details land in the CRM.</div>
        </div>
      </div>
      <div style={{ padding: '0 32px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {isAdmin && (
          <Card>
            <SectionTitle icon={<MessageSquare size={16} color="#9580FF" />} title="Widgets" hint="Each widget works only on the websites you list for it." />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {widgets === null ? <LoadingState /> : widgets.map(w => <WidgetCard key={w.id} w={w} onChanged={load} />)}
              <NewWidget agents={agents} onCreated={load} />
            </div>
          </Card>
        )}
        {isAdmin && <ApiKeys />}
        <Conversations />
      </div>
    </div>
  )
}
