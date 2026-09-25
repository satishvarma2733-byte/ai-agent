import { useEffect, useState } from 'react'
import { Shield, Monitor, Building2, Check, Minus, LogOut, ListPlus, Plug } from 'lucide-react'
import IntegrationsTab from '../components/settings/IntegrationsTab'
import WhatsAppCard from '../components/settings/WhatsAppCard'
import CallSummaryCard from '../components/settings/CallSummaryCard'
import LeadFieldsTab from '../components/settings/LeadFieldsTab'
import toast from 'react-hot-toast'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { LoadingState, ErrorState } from '../components/ui/States'
import { workspaceApi, type SignedInSession, type Workspace } from '../api/workspace'

type TabId = 'workspace' | 'fields' | 'integrations' | 'sessions' | 'roles'

const TABS: { id: TabId; label: string; icon: typeof Shield }[] = [
  { id: 'workspace', label: 'Workspace', icon: Building2 },
  { id: 'fields', label: 'CRM fields', icon: ListPlus },
  { id: 'integrations', label: 'Integrations', icon: Plug },
  { id: 'sessions', label: 'Signed-in devices', icon: Monitor },
  { id: 'roles', label: 'Roles', icon: Shield },
]

const ROLES = ['Owner', 'Admin', 'Manager', 'Agent', 'Viewer'] as const
type Role = typeof ROLES[number]

// Mirrors the server's checks (each capability needs this role or higher). Roles are fixed; they can't be edited.
const CAPABILITIES: { label: string; minimum: Role }[] = [
  { label: 'View calls, leads, analytics and agents', minimum: 'Viewer' },
  { label: 'Add and edit leads, appointments, CMS and knowledge base', minimum: 'Agent' },
  { label: 'Place single outbound calls (30 per hour)', minimum: 'Agent' },
  { label: 'Bulk calls, campaigns and workflows', minimum: 'Manager' },
  { label: 'Build agent drafts and submit them for review', minimum: 'Manager' },
  { label: 'Approve and activate agent versions; disable agents', minimum: 'Admin' },
  { label: 'Delete leads', minimum: 'Admin' },
  { label: 'Invite and manage team members', minimum: 'Admin' },
  { label: 'Voice configuration and provider keys', minimum: 'Admin' },
  { label: 'Rename the workspace', minimum: 'Admin' },
  { label: 'Define CRM fields, business phone numbers and webhooks', minimum: 'Admin' },
]

const rank = (role: string) => ROLES.length - ROLES.indexOf(role as Role)

function describeDevice(userAgent?: string | null): string {
  if (!userAgent) return 'Unknown device'
  const browser = /Edg\//.test(userAgent) ? 'Edge' : /Chrome\//.test(userAgent) ? 'Chrome' : /Firefox\//.test(userAgent) ? 'Firefox' : /Safari\//.test(userAgent) ? 'Safari' : 'Browser'
  const os = /Windows/.test(userAgent) ? 'Windows' : /Mac OS X/.test(userAgent) ? 'macOS' : /Android/.test(userAgent) ? 'Android' : /iPhone|iPad/.test(userAgent) ? 'iOS' : /Linux/.test(userAgent) ? 'Linux' : ''
  return os ? `${browser} · ${os}` : browser
}

function WorkspaceTab({ canEdit }: { canEdit: boolean }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    workspaceApi.get()
      .then(w => { if (!cancelled) { setWorkspace(w); setName(w.name) } })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the workspace') })
    return () => { cancelled = true }
  }, [])

  const save = async () => {
    if (!name.trim()) { toast.error('Workspace name is required'); return }
    setSaving(true)
    try {
      const updated = await workspaceApi.rename(name.trim())
      setWorkspace(updated)
      setName(updated.name)
      toast.success('Workspace renamed')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not rename the workspace')
    } finally {
      setSaving(false)
    }
  }

  if (error) return <ErrorState message={error} />
  if (!workspace) return <LoadingState />
  return (
    <Card>
      <label htmlFor="ws-name" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6 }}>Workspace name</label>
      <div style={{ display: 'flex', gap: 10, marginBottom: 18, maxWidth: 520 }}>
        <input id="ws-name" className="avn-input" value={name} maxLength={150} disabled={!canEdit}
          onChange={e => setName(e.target.value)} style={{ flex: 1 }} />
        {canEdit && <Button onClick={save} loading={saving} disabled={name.trim() === workspace.name}>Save</Button>}
      </div>
      {!canEdit && <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 18 }}>Only Admins and the Owner can rename the workspace.</div>}
      <table className="avn-table" style={{ maxWidth: 520 }}>
        <tbody>
          <tr><td>Plan</td><td style={{ textAlign: 'right' }}>{workspace.plan}</td></tr>
          <tr><td>Status</td><td style={{ textAlign: 'right', textTransform: 'capitalize' }}>{workspace.status}</td></tr>
          <tr><td>Workspace ID</td><td style={{ textAlign: 'right', fontFamily: 'monospace', fontSize: 12 }}>{workspace.id}</td></tr>
        </tbody>
      </table>
    </Card>
  )
}

function SessionsTab() {
  const [sessions, setSessions] = useState<SignedInSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ending, setEnding] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    workspaceApi.sessions()
      .then(s => { if (!cancelled) setSessions(s) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load sessions') })
    return () => { cancelled = true }
  }, [])

  const end = async (id: string) => {
    setEnding(id)
    try {
      await workspaceApi.endSession(id)
      setSessions(prev => prev?.filter(s => s.id !== id) ?? null)
      toast.success('Device signed out')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not sign the device out')
    } finally {
      setEnding(null)
    }
  }

  if (error) return <ErrorState message={error} />
  if (!sessions) return <LoadingState />
  return (
    <Card padding={0}>
      <table className="avn-table">
        <thead>
          <tr><th>Device</th><th>IP address</th><th>Signed in</th><th>Last active</th><th /></tr>
        </thead>
        <tbody>
          {sessions.map(s => (
            <tr key={s.id}>
              <td style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>
                {describeDevice(s.user_agent)}
                {s.current && <span className="avn-chip avn-chip-cyan" style={{ marginLeft: 8, fontSize: 10.5 }}>This device</span>}
              </td>
              <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{s.ip ?? '—'}</td>
              <td>{new Date(s.created_at).toLocaleString()}</td>
              <td>{new Date(s.last_used_at).toLocaleString()}</td>
              <td style={{ textAlign: 'right' }}>
                {!s.current && (
                  <Button size="sm" variant="danger" loading={ending === s.id} onClick={() => end(s.id)}>
                    <LogOut size={12} /> Sign out
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function RolesTab({ myRole }: { myRole: string }) {
  return (
    <Card padding={0}>
      <div style={{ padding: '14px 20px', fontSize: 12.5, color: 'var(--color-text-muted)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        What each role can do. Roles are fixed; change someone's role under Team. Your role: <strong style={{ color: 'var(--color-text-primary)' }}>{myRole || 'unknown'}</strong>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="avn-table">
          <thead>
            <tr>
              <th style={{ minWidth: 260 }}>Capability</th>
              {ROLES.map(r => <th key={r} style={{ textAlign: 'center' }}>{r}</th>)}
            </tr>
          </thead>
          <tbody>
            {CAPABILITIES.map(c => (
              <tr key={c.label}>
                <td>{c.label}</td>
                {ROLES.map(r => (
                  <td key={r} style={{ textAlign: 'center' }}>
                    {rank(r) >= rank(c.minimum) ? <Check size={14} color="#22D3A5" /> : <Minus size={14} color="#4B5675" />}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState<TabId>('workspace')
  const myRole = localStorage.getItem('userRole') || ''
  const canEditWorkspace = rank(myRole) >= rank('Admin')

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 24 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(94,230,255,0.04))',
          border: '1px solid rgba(123,97,255,0.14)', borderRadius: 18, padding: '24px 28px',
        }}>
          <div style={{ fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--color-text-primary)', marginBottom: 6 }}>Settings</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Workspace details, your signed-in devices, and what each role can do</div>
        </div>
      </div>

      <div style={{ padding: '0 32px', marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 12, border: '1px solid rgba(255,255,255,0.06)', width: 'fit-content' }}>
          {TABS.map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
                display: 'flex', alignItems: 'center', gap: 7, padding: '8px 18px', borderRadius: 9, border: 'none',
                background: isActive ? 'rgba(123,97,255,0.18)' : 'transparent',
                color: isActive ? '#9580FF' : 'var(--color-text-muted)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
              }}>
                <Icon size={13} /> {tab.label}
              </button>
            )
          })}
        </div>
      </div>

      <div style={{ padding: '0 32px 32px' }}>
        {activeTab === 'workspace' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <WorkspaceTab canEdit={canEditWorkspace} />
            {canEditWorkspace && <CallSummaryCard />}
          </div>
        )}
        {activeTab === 'fields' && <LeadFieldsTab canEdit={canEditWorkspace} />}
        {activeTab === 'integrations' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <IntegrationsTab canEdit={canEditWorkspace} />
            {canEditWorkspace && <WhatsAppCard />}
          </div>
        )}
        {activeTab === 'sessions' && <SessionsTab />}
        {activeTab === 'roles' && <RolesTab myRole={myRole} />}
      </div>
    </div>
  )
}
