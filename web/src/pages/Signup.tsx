import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Mail, User, Lock, Building2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import { startSession } from '../lib/session'
import AuthLayout, { AuthField, AuthSubmit } from '../components/auth/AuthLayout'
import { authLinkStyle } from '../components/auth/styles'

export default function Signup() {
  const navigate = useNavigate()
  const [companyName, setCompanyName] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 10) {
      toast.error('Password must be at least 10 characters')
      return
    }
    setLoading(true)
    try {
      // The signup response is the same whether or not the email already has an account,
      // so the login below is what tells us a new workspace was created.
      await api.post('/api/auth/signup', { email, password, name, company_name: companyName })
      let accessToken: string
      try {
        accessToken = (await api.post<{ access_token: string }>('/api/auth/login', { email, password })).access_token
      } catch {
        toast.error('We could not sign you in. If you already have an account, log in or reset your password. We also sent a note to your inbox.', { duration: 8000 })
        navigate('/login', { replace: true })
        return
      }
      await startSession(accessToken)
      toast.success('Workspace created. Check your email to verify your address.')
      navigate('/', { replace: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Create your workspace"
      subtitle="Set up aVn for your team"
      footer={<>Already have an account? <Link to="/login" style={authLinkStyle}>Log in</Link></>}
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <AuthField id="company" label="Company name" icon={Building2} required autoComplete="organization"
          value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="Acme Inc." />
        <AuthField id="name" label="Your name" icon={User} required autoComplete="name"
          value={name} onChange={e => setName(e.target.value)} placeholder="Jane Doe" />
        <AuthField id="email" label="Work email" icon={Mail} type="email" required autoComplete="email"
          value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" />
        <AuthField id="password" label="Password (10+ characters)" icon={Lock} type="password" required minLength={10}
          autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••••" />
        <AuthSubmit loading={loading} label="Create workspace" loadingLabel="Creating…" />
      </form>
    </AuthLayout>
  )
}
