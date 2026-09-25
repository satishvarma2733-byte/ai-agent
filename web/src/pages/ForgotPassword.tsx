import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import AuthLayout, { AuthField, AuthSubmit } from '../components/auth/AuthLayout'
import { authLinkStyle } from '../components/auth/styles'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await api.post('/api/auth/password/forgot', { email })
      setSent(true)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle={sent ? undefined : 'We will email you a link to choose a new password'}
      footer={<Link to="/login" style={authLinkStyle}>Back to log in</Link>}
    >
      {sent ? (
        <p role="status" style={{ fontSize: 14, color: 'var(--color-text-primary)', lineHeight: 1.6, textAlign: 'center' }}>
          If an account exists for <strong>{email}</strong>, a reset link is on its way. The link expires in 1 hour.
        </p>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <AuthField id="email" label="Email address" icon={Mail} type="email" required autoComplete="email"
            value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" />
          <AuthSubmit loading={loading} label="Send reset link" loadingLabel="Sending…" />
        </form>
      )}
    </AuthLayout>
  )
}
