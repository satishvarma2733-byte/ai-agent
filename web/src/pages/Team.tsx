import { useEffect, useState } from 'react'
import {
  UserCheck, Plus, Mail, Shield, Settings2, CheckCircle2, Search, Crown, Eye, Copy, X, Clock,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import toast from 'react-hot-toast'
import { teamApi, ASSIGNABLE_ROLES } from '../api/team'
import { restoreSession } from '../lib/session'
import type { AssignableRole, Invitation, Member, Role } from '../api/team'

const ROLE_CONFIG: Record<Role, { color: string; bg: string; icon: LucideIcon }> = {
  Owner:   { color: '#F5A623', bg: 'rgba(245,166,35,0.12)', icon: Crown },
  Admin:   { color: '#9580FF', bg: 'rgba(123,97,255,0.12)', icon: Shield },
  Manager: { color: '#5EE6FF', bg: 'rgba(94,230,255,0.1)',  icon: Settings2 },
  Agent:   { color: '#22D3A5', bg: 'rgba(34,211,165,0.1)',  icon: UserCheck },
  Viewer:  { color: 'var(--color-text-secondary)', bg: 'rgba(148,163,184,0.1)', icon: Eye },
}

// Mirrors what the API enforces (app/core/permissions.py, RoleChecker usage, Viewer rule).
const ROLE_PERMISSIONS: Record<Role, string[]> = {
  Owner:   ['Everything an Admin can do', 'Cannot be removed or demoted'],
  Admin:   ['Invite members and change roles (up to Admin)', 'Deactivate members', 'Voice runtime configuration', 'Delete leads'],
  Manager: ['Create and edit workflows', 'Create, start, pause, and delete campaigns', 'Calendar sync'],
  Agent:   ['Work with leads, calls, appointments, knowledge base, and content'],
  Viewer:  ['Read-only access to the workspace'],
}

const ROLE_ORDER: Role[] = ['Owner', 'Admin', 'Manager', 'Agent', 'Viewer']
const rank = (r: string) => ROLE_ORDER.length - ROLE_ORDER.indexOf(r as Role)

const EMAIL_STATUS_TEXT: Record<string, string> = {
  sent: 'Invitation email sent.',
  logged: 'Email is not configured locally; the email was written to the API log. Share the link below.',
  not_configured: 'Email is not configured on this server. Share the link below with the person you invited.',
  failed: 'The invitation email could not be sent. Share the link below instead.',
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
}

function RolePill({ role }: { role: Role }) {
  const cfg = ROLE_CONFIG[role] ?? ROLE_CONFIG.Agent
  const Icon = cfg.icon
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 100, background: cfg.bg, border: `1px solid ${cfg.color}25` }}>
      <Icon size={10} color={cfg.color} aria-hidden />
      <span style={{ fontSize: 11, fontWeight: 700, color: cfg.color }}>{role}</span>
    </span>
  )
}

function MemberCard({ member, canEdit, onEdit }: { member: Member; canEdit: boolean; onEdit: () => void }) {
  const cfg = ROLE_CONFIG[member.role] ?? ROLE_CONFIG.Agent
  const initials = member.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
  return (
    <div className="glass-card" style={{ padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
        <div aria-hidden style={{
          width: 44, height: 44, borderRadius: 13, background: `linear-gradient(135deg, ${cfg.color}28, ${cfg.color}10)`,
          border: `1px solid ${cfg.color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 15, fontWeight: 700, color: cfg.color, flexShrink: 0,
        }}>{initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{member.name}</div>
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{member.email}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <RolePill role={member.role} />
          <Badge variant={member.status === 'active' ? 'success' : 'default'} dot>{member.status}</Badge>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.04)', gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
          {member.email_verified ? 'Email verified' : 'Email not verified'} · Last active {formatDate(member.last_seen)}
        </span>
        {canEdit && (
          <Button variant="ghost" size="sm" icon={<Settings2 size={11} />} onClick={onEdit}>Edit</Button>
        )}
      </div>
    </div>
  )
}

export default function Team() {
  const myRole = (localStorage.getItem('userRole') || '') as Role
  const myEmail = localStorage.getItem('userEmail') || ''
  const isAdmin = rank(myRole) >= rank('Admin')

  const [members, setMembers] = useState<Member[]>([])
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<'All' | Role>('All')
  const [activeTab, setActiveTab] = useState<'members' | 'permissions'>('members')

  const [showInvite, setShowInvite] = useState(false)
  const [inviteForm, setInviteForm] = useState<{ email: string; role: AssignableRole }>({ email: '', role: 'Agent' })
  const [inviting, setInviting] = useState(false)
  const [inviteResult, setInviteResult] = useState<{ url: string; status: string } | null>(null)

  const [editMember, setEditMember] = useState<Member | null>(null)
  const [editForm, setEditForm] = useState<{ role: AssignableRole; status: 'active' | 'inactive' }>({ role: 'Agent', status: 'active' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([teamApi.members(), isAdmin ? teamApi.invitations() : Promise.resolve([] as Invitation[])])
      .then(([m, inv]) => {
        if (cancelled) return
        setMembers(m)
        setInvitations(inv)
        setLoadError(null)
      })
      .catch(e => { if (!cancelled) setLoadError(e instanceof Error ? e.message : 'Could not load the team') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [isAdmin])

  const filtered = members.filter(m => {
    const q = search.toLowerCase()
    return (m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q)) && (roleFilter === 'All' || m.role === roleFilter)
  })
  const assignable = ASSIGNABLE_ROLES.filter(r => rank(r) <= rank(myRole))
  const canEdit = (m: Member) => isAdmin && m.role !== 'Owner' && m.email !== myEmail && rank(m.role) <= rank(myRole)

  const closeInvite = () => {
    setShowInvite(false)
    setInviteResult(null)
    setInviteForm({ email: '', role: 'Agent' })
  }

  const handleInvite = async () => {
    setInviting(true)
    try {
      const res = await teamApi.invite(inviteForm.email.trim(), inviteForm.role)
      setInviteResult({ url: res.accept_url, status: res.email_status })
      setInvitations(prev => [res.invitation, ...prev.filter(i => i.email !== res.invitation.email)])
      if (res.email_status === 'sent') toast.success(`Invitation sent to ${res.invitation.email}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not create the invitation')
    } finally {
      setInviting(false)
    }
  }

  const handleRevoke = async (inv: Invitation) => {
    if (!confirm(`Revoke the invitation for ${inv.email}?`)) return
    try {
      await teamApi.revokeInvitation(inv.id)
      setInvitations(prev => prev.filter(i => i.id !== inv.id))
      toast.success('Invitation revoked')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not revoke')
    }
  }

  const openEdit = (m: Member) => {
    setEditMember(m)
    if (m.role === 'Owner') return  // the Owner is never editable (canEdit hides the button)
    setEditForm({ role: m.role, status: m.status })
  }

  const handleRemove = async () => {
    if (!editMember) return
    if (!confirm(`Remove ${editMember.name} from the workspace? They are signed out now, and their leads become unassigned.`)) return
    setSaving(true)
    try {
      await teamApi.removeMember(editMember.id)
      setMembers(prev => prev.filter(m => m.id !== editMember.id))
      toast.success(`${editMember.name} was removed`)
      setEditMember(null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not remove the member')
    } finally {
      setSaving(false)
    }
  }

  const handleTransfer = async () => {
    if (!editMember) return
    if (!confirm(`Make ${editMember.name} the owner? You will become an Admin, and this can only be undone by the new owner.`)) return
    setSaving(true)
    try {
      await teamApi.transferOwnership(editMember.id)
      await restoreSession()  // picks up your new role
      toast.success(`${editMember.name} is now the owner`)
      setEditMember(null)
      setMembers(await teamApi.members())
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not transfer ownership')
    } finally {
      setSaving(false)
    }
  }

  const handleSave = async () => {
    if (!editMember) return
    const patch: { role?: AssignableRole; status?: 'active' | 'inactive' } = {}
    if (editForm.role !== editMember.role) patch.role = editForm.role
    if (editForm.status !== editMember.status) patch.status = editForm.status
    if (!patch.role && !patch.status) { setEditMember(null); return }
    setSaving(true)
    try {
      const updated = await teamApi.updateMember(editMember.id, patch)
      setMembers(prev => prev.map(m => (m.id === updated.id ? updated : m)))
      toast.success(`${updated.name} updated. They'll need to sign in again.`)
      setEditMember(null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update the member')
    } finally {
      setSaving(false)
    }
  }

  const copyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast.success('Invitation link copied')
    } catch {
      toast.error('Copy failed; select the link and copy it manually')
    }
  }

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 24 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(94,230,255,0.07), rgba(123,97,255,0.04))', border: '1px solid rgba(94,230,255,0.12)',
          borderRadius: 18, padding: '22px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap',
        }}>
          <div>
            <h1 style={{
              fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em',
              background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #5EE6FF)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
              backgroundClip: 'text', marginBottom: 6,
            }}>Team Management</h1>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
              Members, roles, and invitations · {members.filter(m => m.status === 'active').length} active
            </div>
          </div>
          {isAdmin && <Button variant="primary" icon={<Plus size={14} />} onClick={() => setShowInvite(true)}>Invite member</Button>}
        </div>
      </div>

      <div style={{ padding: '0 32px 32px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14, marginBottom: 24 }}>
          <GradientStatCard label="Members" value={members.length} icon={<UserCheck size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" delay={0} />
          <GradientStatCard label="Active" value={members.filter(m => m.status === 'active').length} icon={<CheckCircle2 size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={80} />
          <GradientStatCard label="Owners & admins" value={members.filter(m => m.role === 'Owner' || m.role === 'Admin').length} icon={<Crown size={20} color="#fff" />} gradient="linear-gradient(135deg,#9580FF,#7B61FF)" delay={160} />
          {isAdmin && <GradientStatCard label="Pending invitations" value={invitations.length} icon={<Mail size={20} color="#fff" />} gradient="linear-gradient(135deg,#5EE6FF,#0EA5E9)" delay={240} />}
        </div>

        <div role="tablist" style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 11, border: '1px solid rgba(255,255,255,0.06)', marginBottom: 20, width: 'fit-content' }}>
          {(['members', 'permissions'] as const).map(t => (
            <button key={t} role="tab" aria-selected={activeTab === t} onClick={() => setActiveTab(t)} style={{
              padding: '6px 18px', borderRadius: 8, border: 'none', background: activeTab === t ? 'rgba(123,97,255,0.18)' : 'transparent',
              color: activeTab === t ? '#9580FF' : 'var(--color-text-muted)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', textTransform: 'capitalize',
            }}>{t}</button>
          ))}
        </div>

        {activeTab === 'members' ? (
          <>
            <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
              <div style={{ position: 'relative', flex: 1, minWidth: 200, maxWidth: 280 }}>
                <Search size={13} color="var(--color-text-muted)" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} aria-hidden />
                <input aria-label="Search members" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search members…" className="avn-input"
                  style={{ width: '100%', paddingLeft: 32, height: 36, fontSize: 13 }} />
              </div>
              {(['All', ...ROLE_ORDER] as const).map(r => (
                <button key={r} onClick={() => setRoleFilter(r)} aria-pressed={roleFilter === r} style={{
                  padding: '6px 14px', borderRadius: 9, border: `1px solid ${roleFilter === r ? 'rgba(123,97,255,0.3)' : 'rgba(255,255,255,0.07)'}`,
                  background: roleFilter === r ? 'rgba(123,97,255,0.12)' : 'rgba(255,255,255,0.03)',
                  color: roleFilter === r ? '#9580FF' : 'var(--color-text-muted)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                }}>{r}</button>
              ))}
            </div>

            {loading ? (
              <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Loading team…</div>
            ) : loadError ? (
              <Card><div role="alert" style={{ fontSize: 13, color: '#FF8A9B' }}>{loadError}</div></Card>
            ) : filtered.length === 0 ? (
              <Card><div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>No members match these filters.</div></Card>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                {filtered.map(m => <MemberCard key={m.id} member={m} canEdit={canEdit(m)} onEdit={() => openEdit(m)} />)}
              </div>
            )}

            {isAdmin && invitations.length > 0 && (
              <Card style={{ marginTop: 24 }} padding={0}>
                <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Clock size={14} color="#7B61FF" aria-hidden />
                  <h2 style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>Pending invitations</h2>
                </div>
                {invitations.map(inv => (
                  <div key={inv.id} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,0.03)', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 180 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{inv.email}</div>
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Expires {formatDate(inv.expires_at)}</div>
                    </div>
                    <RolePill role={inv.role} />
                    <Button variant="ghost" size="sm" icon={<X size={11} />} onClick={() => handleRevoke(inv)}>Revoke</Button>
                  </div>
                ))}
              </Card>
            )}
          </>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
            {ROLE_ORDER.map(role => {
              const cfg = ROLE_CONFIG[role]
              const Icon = cfg.icon
              return (
                <Card key={role} style={{ borderColor: `${cfg.color}20` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                    <div style={{ width: 38, height: 38, borderRadius: 10, background: cfg.bg, border: `1px solid ${cfg.color}25`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Icon size={17} color={cfg.color} aria-hidden />
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>{role}</div>
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{members.filter(m => m.role === role).length} members</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {role !== 'Viewer' && role !== 'Agent' && (
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Everything below, plus:</div>
                    )}
                    {ROLE_PERMISSIONS[role].map(perm => (
                      <div key={perm} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                        <CheckCircle2 size={12} color={cfg.color} style={{ marginTop: 3, flexShrink: 0 }} aria-hidden />
                        <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{perm}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      </div>

      <Modal open={showInvite} onClose={closeInvite} title="Invite team member" width={480}>
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {inviteResult ? (
            <>
              <div role="status" style={{ fontSize: 13, color: 'var(--color-text-primary)', lineHeight: 1.5 }}>{EMAIL_STATUS_TEXT[inviteResult.status] ?? ''}</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input readOnly aria-label="Invitation link" value={inviteResult.url} className="avn-input" style={{ flex: 1, height: 36, fontSize: 12 }}
                  onFocus={e => e.currentTarget.select()} />
                <Button variant="secondary" size="sm" icon={<Copy size={12} />} onClick={() => copyLink(inviteResult.url)}>Copy</Button>
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>The link works once and expires in 7 days.</div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button variant="primary" onClick={closeInvite}>Done</Button>
              </div>
            </>
          ) : (
            <>
              <Input label="Email address" id="inv-email" type="email" value={inviteForm.email}
                onChange={e => setInviteForm(f => ({ ...f, email: e.target.value }))} placeholder="name@company.com" />
              <Select label="Role" id="inv-role" value={inviteForm.role}
                options={assignable.map(r => ({ value: r, label: r }))}
                onChange={e => setInviteForm(f => ({ ...f, role: e.target.value as AssignableRole }))} />
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
                <Button variant="ghost" onClick={closeInvite}>Cancel</Button>
                <Button variant="primary" icon={<Mail size={13} />} onClick={handleInvite} disabled={inviting || !inviteForm.email.trim()}>
                  {inviting ? 'Creating…' : 'Create invitation'}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      <Modal open={editMember !== null} onClose={() => setEditMember(null)} title={editMember ? `Edit ${editMember.name}` : 'Edit member'} width={440}>
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Select label="Role" id="edit-role" value={editForm.role}
            options={assignable.map(r => ({ value: r, label: r }))}
            onChange={e => setEditForm(f => ({ ...f, role: e.target.value as AssignableRole }))} />
          <Select label="Status" id="edit-status" value={editForm.status}
            options={[{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive (cannot sign in)' }]}
            onChange={e => setEditForm(f => ({ ...f, status: e.target.value as 'active' | 'inactive' }))} />
          <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Changing role or status signs this person out of all devices.</div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <Button variant="danger" onClick={handleRemove} disabled={saving} style={{ marginRight: 'auto' }}>Remove</Button>
            {myRole === 'Owner' && editMember?.status === 'active' && (
              <Button variant="secondary" onClick={handleTransfer} disabled={saving}>Make owner</Button>
            )}
            <Button variant="ghost" onClick={() => setEditMember(null)}>Cancel</Button>
            <Button variant="primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
