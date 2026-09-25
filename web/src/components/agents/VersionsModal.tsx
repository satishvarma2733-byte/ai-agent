import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import { agentsApi } from '../../api/agents'
import type { Agent, AgentChange, AgentVersion, VersionAction } from '../../api/agents'

const STATUS_COLOR: Record<string, string> = {
  draft: '#F5C26B', testing: '#5EE6FF', evaluation: '#5EE6FF', approved: '#9580FF',
  production: '#22D3A5', superseded: 'var(--color-text-muted)', rejected: '#FF8A9B',
}

// Mirrors app/services/agents.py TRANSITIONS.
const ACTIONS: Record<string, { action: VersionAction; label: string; admin: boolean; variant: 'primary' | 'ghost' | 'danger' }[]> = {
  draft:      [{ action: 'submit', label: 'Submit for testing', admin: false, variant: 'primary' }],
  testing:    [{ action: 'evaluate', label: 'Mark tested', admin: false, variant: 'primary' },
               { action: 'reject', label: 'Reject', admin: false, variant: 'ghost' }],
  evaluation: [{ action: 'approve', label: 'Approve', admin: true, variant: 'primary' },
               { action: 'reject', label: 'Reject', admin: false, variant: 'ghost' }],
  approved:   [{ action: 'activate', label: 'Activate in production', admin: true, variant: 'primary' },
               { action: 'reject', label: 'Reject', admin: false, variant: 'ghost' }],
  superseded: [{ action: 'rollback', label: 'Roll back to this version', admin: true, variant: 'danger' }],
}

const ROLE_RANK: Record<string, number> = { Viewer: 0, Agent: 1, Manager: 2, Admin: 3, Owner: 4 }

function formatValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '—'
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 140 ? `${text.slice(0, 140)}…` : text
}

function ChangeList({ changes }: { changes: { path: string; before?: unknown; after?: unknown }[] }) {
  if (changes.length === 0) return <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>No differences.</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {changes.map(c => (
        <div key={c.path} style={{ fontSize: 12, lineHeight: 1.5 }}>
          <code style={{ color: '#9580FF' }}>{c.path}</code>
          <div style={{ color: '#FF8A9B' }}>− {formatValue(c.before)}</div>
          <div style={{ color: '#22D3A5' }}>+ {formatValue(c.after)}</div>
        </div>
      ))}
    </div>
  )
}

export default function VersionsModal({ agent, onClose, onChanged }: {
  agent: Agent
  onClose: () => void
  onChanged: () => void
}) {
  const role = localStorage.getItem('userRole') || ''
  const canBuild = (ROLE_RANK[role] ?? -1) >= ROLE_RANK.Manager
  const isAdmin = (ROLE_RANK[role] ?? -1) >= ROLE_RANK.Admin
  const [tab, setTab] = useState<'versions' | 'changes'>('versions')
  const [versions, setVersions] = useState<AgentVersion[] | null>(null)
  const [changes, setChanges] = useState<AgentChange[] | null>(null)
  const [diff, setDiff] = useState<{ title: string; changes: { path: string; before?: unknown; after?: unknown }[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([agentsApi.versions(agent.id), agentsApi.changes(agent.id)])
      .then(([v, c]) => { if (!cancelled) { setVersions(v); setChanges(c) } })
      .catch(e => toast.error(e instanceof Error ? e.message : 'Could not load versions'))
    return () => { cancelled = true }
  }, [agent.id, reloadKey])

  const production = versions?.find(v => v.status === 'production')

  const run = async (version: AgentVersion, action: VersionAction, label: string) => {
    if (action === 'activate' || action === 'rollback') {
      if (!confirm(`${label}: v${version.number} will handle live calls for "${agent.name}". Continue?`)) return
    }
    setBusy(true)
    try {
      await agentsApi.versionAction(agent.id, version.number, action)
      toast.success(`v${version.number}: ${label}`)
      setReloadKey(k => k + 1)
      onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const discard = async () => {
    if (!confirm('Discard the unpublished draft? Its changes will be kept in history but not used.')) return
    setBusy(true)
    try {
      await agentsApi.discardDraft(agent.id)
      toast.success('Draft discarded')
      setReloadKey(k => k + 1)
      onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not discard')
    } finally {
      setBusy(false)
    }
  }

  const showDiff = async (version: AgentVersion) => {
    if (!production) return
    try {
      const res = await agentsApi.compare(agent.id, production.number, version.number)
      setDiff({ title: `Production v${production.number} → v${version.number}`, changes: res.changes })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not compare')
    }
  }

  return (
    <Modal open onClose={onClose} title={`${agent.name} — versions`} width={640}>
      <div style={{ padding: '16px 24px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div role="tablist" style={{ display: 'flex', gap: 4 }}>
          {(['versions', 'changes'] as const).map(t => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} style={{
              padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
              background: tab === t ? 'rgba(123,97,255,0.18)' : 'transparent', color: tab === t ? '#9580FF' : 'var(--color-text-muted)',
            }}>{t === 'versions' ? 'Versions' : 'Change log'}</button>
          ))}
        </div>

        {tab === 'versions' ? (
          versions === null ? <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Loading…</div> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {versions.map(v => {
                const actions = (ACTIONS[v.status] ?? [])
                  .filter(a => (a.admin ? isAdmin : canBuild))
                  .filter(a => a.action !== 'rollback' || v.activated_at)
                return (
                  <div key={v.id} style={{ padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.07)', background: 'rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <strong style={{ fontSize: 13, color: 'var(--color-text-primary)' }}>v{v.number}</strong>
                      <span style={{ fontSize: 11.5, fontWeight: 700, color: STATUS_COLOR[v.status], textTransform: 'capitalize' }}>{v.status}</span>
                      <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                        {v.activated_at ? `activated ${new Date(v.activated_at).toLocaleString()}` : `updated ${new Date(v.updated_at).toLocaleString()}`}
                      </span>
                      <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {production && v.id !== production.id && (
                          <Button variant="ghost" size="sm" onClick={() => showDiff(v)}>Compare</Button>
                        )}
                        {v.status === 'draft' && canBuild && (v.number > 1 || production) && (
                          <Button variant="ghost" size="sm" disabled={busy} onClick={discard}>Discard</Button>
                        )}
                        {actions.map(a => (
                          <Button key={a.action} variant={a.variant} size="sm" disabled={busy} onClick={() => run(v, a.action, a.label)}>{a.label}</Button>
                        ))}
                      </div>
                    </div>
                  </div>
                )
              })}
              {!canBuild && <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Managers and admins can move versions through testing and approval.</div>}
              {diff && (
                <div style={{ padding: 12, borderRadius: 10, border: '1px solid rgba(123,97,255,0.2)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <strong style={{ fontSize: 12.5, color: 'var(--color-text-primary)' }}>{diff.title}</strong>
                    <button onClick={() => setDiff(null)} aria-label="Close comparison" style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer' }}>✕</button>
                  </div>
                  <ChangeList changes={diff.changes} />
                </div>
              )}
            </div>
          )
        ) : (
          changes === null ? <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Loading…</div> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 420, overflowY: 'auto' }}>
              {changes.map(c => (
                <div key={c.id} style={{ padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.07)' }}>
                  <div style={{ fontSize: 12.5, color: 'var(--color-text-primary)', marginBottom: 4 }}>
                    <strong>v{c.version_number}</strong> · {c.reason}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginBottom: 6 }}>
                    {c.user_name ?? 'System'} · {c.source} · {new Date(c.created_at).toLocaleString()}
                  </div>
                  <ChangeList changes={c.changes} />
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </Modal>
  )
}
