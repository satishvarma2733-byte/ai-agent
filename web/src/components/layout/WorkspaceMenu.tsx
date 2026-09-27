import { useEffect, useState } from 'react'
import { Check, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../../api/client'
import type { Schema } from '../../api/types'
import { startSession } from '../../lib/session'

type Workspace = Schema<'AccountWorkspaceOut'>

const itemStyle = {
  width: '100%', textAlign: 'left', padding: '8px 14px', background: 'transparent', border: 'none',
  color: 'var(--color-text-primary)', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
} as const

// The account's workspaces inside the account menu. Switching moves this device only; the page reloads so
// every screen loads the new workspace's data.
export default function WorkspaceMenu() {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get<Workspace[]>('/api/auth/workspaces').then(setWorkspaces).catch(() => setWorkspaces([]))
  }, [])

  const enter = async (request: Promise<{ access_token: string }>) => {
    setBusy(true)
    try {
      await startSession((await request).access_token)
      window.location.assign('/')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not switch workspace')
      setBusy(false)
    }
  }

  const create = () => {
    const name = prompt('Name of the new workspace')?.trim()
    if (name) void enter(api.post<{ access_token: string }>('/api/auth/workspaces', { name }))
  }

  if (workspaces === null) return null
  return (
    <div style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '6px 0' }}>
      <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--color-text-muted)', padding: '4px 14px' }}>WORKSPACES</div>
      {workspaces.map(w => (
        <button key={w.id} role="menuitemradio" aria-checked={w.current} disabled={busy || w.current}
          onClick={() => void enter(api.post<{ access_token: string }>('/api/auth/workspaces/switch', { tenant_id: w.id }))}
          style={{ ...itemStyle, cursor: w.current ? 'default' : 'pointer' }}>
          <span style={{ width: 14, display: 'inline-flex' }}>{w.current && <Check size={13} color="#9580FF" />}</span>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.name}</span>
          <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{w.role}</span>
        </button>
      ))}
      <button role="menuitem" disabled={busy} onClick={create} style={{ ...itemStyle, color: 'var(--color-link)' }}>
        <Plus size={13} /> New workspace
      </button>
    </div>
  )
}
