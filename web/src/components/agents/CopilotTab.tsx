import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'
import Button from '../ui/Button'
import { agentsApi, type Agent } from '../../api/agents'
import type { Schema } from '../../api/types'

type Proposal = Schema<'CopilotProposalOut'>

const EXAMPLES = [
  'Greet callers in Telugu and make Telugu the default language',
  'Be more formal and keep answers under two sentences',
  'We are open on Saturdays from 10:00 to 14:00 too',
]

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'string' ? value : JSON.stringify(value)
}

// Copilot: describe a change in plain words, check the exact diff, then save it to the draft.
export default function CopilotTab({ agent, canBuild, onApplied }: { agent: Agent; canBuild: boolean; onApplied: () => void }) {
  const [request, setRequest] = useState('')
  const [asked, setAsked] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [thinking, setThinking] = useState(false)
  const [applying, setApplying] = useState(false)

  if (!canBuild) {
    return <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Managers and admins can change agents with the copilot.</div>
  }

  const ask = async () => {
    setThinking(true)
    setProposal(null)
    try {
      setProposal(await agentsApi.copilot(agent.id, request.trim()))
      setAsked(request.trim())
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'The copilot could not answer')
    } finally {
      setThinking(false)
    }
  }

  const apply = async () => {
    if (!proposal) return
    setApplying(true)
    try {
      await agentsApi.copilotApply(agent.id, asked, proposal.patch)
      toast.success('Saved to the draft. Test it, then submit it for review.')
      setProposal(null)
      setRequest('')
      onApplied()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not apply')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>
        Say what you want changed. You'll see exactly what changes before anything is saved, and changes go to the draft, not to live calls.
      </div>
      <label htmlFor="copilot-request" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)' }}>What should change?</label>
      <textarea id="copilot-request" className="avn-input" rows={3} maxLength={1000} value={request} onChange={e => setRequest(e.target.value)}
        placeholder={EXAMPLES[0]} style={{ width: '100%', padding: '8px 10px', fontSize: 13 }} />
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {EXAMPLES.map(x => (
          <button key={x} type="button" onClick={() => setRequest(x)} style={{ fontSize: 11.5, padding: '4px 9px', borderRadius: 99, cursor: 'pointer',
            border: '1px solid rgba(123,97,255,0.25)', background: 'transparent', color: 'var(--color-text-secondary)' }}>{x}</button>
        ))}
      </div>
      <div>
        <Button variant="primary" size="sm" icon={<Sparkles size={13} />} loading={thinking} disabled={request.trim().length < 3} onClick={ask}>Suggest change</Button>
      </div>

      {proposal && (
        <div style={{ border: '1px solid rgba(123,97,255,0.2)', borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {proposal.summary && <div style={{ fontSize: 13, color: 'var(--color-text-primary)' }}>{proposal.summary}</div>}
          {proposal.changes.length === 0 ? (
            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>No changes to make.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {proposal.changes.map(c => (
                <div key={c.path} style={{ fontSize: 12 }}>
                  <div style={{ fontWeight: 700, color: 'var(--color-text-secondary)', marginBottom: 2 }}>{c.path}</div>
                  <div style={{ whiteSpace: 'pre-wrap', color: 'var(--color-danger)', maxHeight: 120, overflow: 'auto' }}>− {show(c.before)}</div>
                  <div style={{ whiteSpace: 'pre-wrap', color: '#22D3A5', maxHeight: 160, overflow: 'auto' }}>+ {show(c.after)}</div>
                </div>
              ))}
            </div>
          )}
          {proposal.ignored.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--color-warning, #F5A524)' }}>
              Left out (the copilot can't change these): {proposal.ignored.join(', ')}
            </div>
          )}
          {proposal.changes.length > 0 && (
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="primary" size="sm" loading={applying} onClick={apply}>Apply to draft</Button>
              <Button variant="secondary" size="sm" onClick={() => setProposal(null)}>Discard</Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
