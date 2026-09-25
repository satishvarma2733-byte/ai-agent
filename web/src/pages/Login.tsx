import { useState, useEffect } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { Mail, Lock } from 'lucide-react'
import toast from 'react-hot-toast'
import { api, getAccessToken } from '../api/client'
import { restoreSession, startSession } from '../lib/session'
import AuthLayout, { AuthField, AuthSubmit } from '../components/auth/AuthLayout'
import { authLinkStyle } from '../components/auth/styles'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const returnTo = (location.state as { from?: string } | null)?.from || '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  // Already signed in (valid refresh cookie)? Skip the form.
  useEffect(() => {
    let cancelled = false
    ;(getAccessToken() ? Promise.resolve(true) : restoreSession().then(Boolean))
      .then(signedIn => { if (signedIn && !cancelled) navigate(returnTo, { replace: true }) })
    return () => { cancelled = true }
  }, [navigate, returnTo])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { access_token } = await api.post<{ access_token: string }>('/api/auth/login', { email, password })
      await startSession(access_token)
      navigate(returnTo, { replace: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Log in to your aVn workspace"
      footer={<>Don't have an account? <Link to="/signup" style={authLinkStyle}>Sign up</Link></>}
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <AuthField id="email" label="Email address" icon={Mail} type="email" required autoComplete="email"
          value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" />
        <AuthField id="password" label="Password" icon={Lock} type="password" required autoComplete="current-password"
          value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••••" />
        <div style={{ textAlign: 'right', marginTop: -8 }}>
          <Link to="/forgot-password" style={{ ...authLinkStyle, fontSize: 12 }}>Forgot password?</Link>
        </div>
        <AuthSubmit loading={loading} label="Sign in" loadingLabel="Signing in…" />
      </form>
    </AuthLayout>
  )
}
