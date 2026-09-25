import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Lock } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import AuthLayout, { AuthField, AuthSubmit } from '../components/auth/AuthLayout'
import { authLinkStyle } from '../components/auth/styles'

export default function ResetPassword() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password !== confirm) {
      toast.error('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      await api.post('/api/auth/password/reset', { token, password })
      toast.success('Password updated. Log in with your new password.')
      navigate('/login', { replace: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Reset failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout title="Choose a new password" footer={<Link to="/login" style={authLinkStyle}>Back to log in</Link>}>
      {!token ? (
        <p style={{ fontSize: 14, color: 'var(--color-text-primary)', textAlign: 'center' }}>
          This reset link is incomplete. <Link to="/forgot-password" style={authLinkStyle}>Request a new one</Link>.
        </p>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <AuthField id="password" label="New password (10+ characters)" icon={Lock} type="password" required minLength={10}
            autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
          <AuthField id="confirm" label="Confirm new password" icon={Lock} type="password" required minLength={10}
            autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} />
          <AuthSubmit loading={loading} label="Update password" loadingLabel="Updating…" />
        </form>
      )}
    </AuthLayout>
  )
}
