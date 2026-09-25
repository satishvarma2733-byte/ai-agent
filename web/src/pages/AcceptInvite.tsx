import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Lock, User } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import { clearSession, startSession } from '../lib/session'
import AuthLayout, { AuthField, AuthSubmit } from '../components/auth/AuthLayout'
import { authLinkStyle } from '../components/auth/styles'

interface InvitationPreview { email: string; role: string; tenant_name: string; expires_at: string }

export default function AcceptInvite() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [invite, setInvite] = useState<InvitationPreview | null>(null)
  const [error, setError] = useState<string | null>(token ? null : 'This invitation link is incomplete.')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) return
    api.get<InvitationPreview>(`/api/auth/invitations/${encodeURIComponent(token)}`)
      .then(setInvite)
      .catch(err => setError(err instanceof Error ? err.message : 'Invitation not found'))
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      clearSession()
      const { access_token } = await api.post<{ access_token: string }>('/api/auth/invitations/accept', { token, name, password })
      await startSession(access_token)
      toast.success(`Welcome to ${invite?.tenant_name ?? 'aVn'}!`)
      navigate('/', { replace: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not accept the invitation')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title={invite ? `Join ${invite.tenant_name}` : 'Accept invitation'}
      subtitle={invite ? <>You are invited as <strong>{invite.role}</strong> · {invite.email}</> : undefined}
      footer={<Link to="/login" style={authLinkStyle}>Already have an account? Log in</Link>}
    >
      {error ? (
        <p role="alert" style={{ fontSize: 14, color: '#FF8A9B', textAlign: 'center' }}>{error}</p>
      ) : !invite ? (
        <p style={{ fontSize: 14, color: 'var(--color-text-muted)', textAlign: 'center' }}>Checking invitation…</p>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <AuthField id="name" label="Your name" icon={User} required autoComplete="name"
            value={name} onChange={e => setName(e.target.value)} />
          <AuthField id="password" label="Choose a password (10+ characters)" icon={Lock} type="password" required minLength={10}
            autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
          <AuthSubmit loading={loading} label="Join workspace" loadingLabel="Joining…" />
        </form>
      )}
    </AuthLayout>
  )
}
