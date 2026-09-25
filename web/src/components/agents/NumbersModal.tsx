import { useEffect, useState } from 'react'
import { Phone, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import { agentsApi, type Agent, type AgentNumber } from '../../api/agents'

// Business numbers routed to one agent. Calls to other numbers use the default agent.
export default function NumbersModal({ agent, onClose }: { agent: Agent | null; onClose: () => void }) {
  const [numbers, setNumbers] = useState<AgentNumber[] | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const role = localStorage.getItem('userRole') || ''
  const canEdit = role === 'Owner' || role === 'Admin'

  useEffect(() => {
    if (!agent) return
    let cancelled = false
    agentsApi.numbers(agent.id)
      .then(n => { if (!cancelled) setNumbers(n) })
      .catch(e => { if (!cancelled) toast.error(e instanceof Error ? e.message : 'Could not load numbers') })
    return () => { cancelled = true; setNumbers(null) }
  }, [agent])

  if (!agent) return null

  const add = async () => {
    if (!draft.trim()) return
    setBusy(true)
    try {
      const created = await agentsApi.addNumber(agent.id, draft.trim())
      setNumbers(prev => [...(prev ?? []), created])
      setDraft('')
      toast.success(`${created.phone_number} now reaches ${agent.name}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not add the number')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (n: AgentNumber) => {
    if (!confirm(`Stop routing ${n.phone_number} to ${agent.name}? Calls to it will use the default agent.`)) return
    try {
      await agentsApi.removeNumber(agent.id, n.id)
      setNumbers(prev => prev?.filter(x => x.id !== n.id) ?? null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not remove the number')
    }
  }

  return (
    <Modal open onClose={onClose} title={`Phone numbers · ${agent.name}`} width={480}>
      <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
          Calls to these numbers are answered by this agent's production version. The number must also be connected
          to your LiveKit SIP trunk. Numbers not listed on any agent use the default agent.
        </div>
        {numbers === null ? (
          <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>Loading…</div>
        ) : numbers.length === 0 ? (
          <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>No numbers yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {numbers.map(n => (
              <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: '1px solid var(--color-border)', borderRadius: 8 }}>
                <Phone size={13} color="#9580FF" />
                <span style={{ flex: 1, fontFamily: 'monospace', fontSize: 13, color: 'var(--color-text-primary)' }}>{n.phone_number}</span>
                {canEdit && (
                  <button onClick={() => remove(n)} title="Remove" aria-label={`Remove ${n.phone_number}`}
                    style={{ background: 'transparent', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer' }}>
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        {canEdit ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="avn-input" value={draft} placeholder="+91 40 1234 5678" onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void add() }} style={{ flex: 1, height: 36 }} aria-label="Phone number" />
            <Button variant="primary" onClick={add} loading={busy} disabled={!draft.trim()}>Add</Button>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Only Admins and the Owner can change numbers.</div>
        )}
      </div>
    </Modal>
  )
}
