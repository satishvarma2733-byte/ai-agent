import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getAccessToken } from '../api/client'
import AuthLayout from '../components/auth/AuthLayout'
import { authLinkStyle } from '../components/auth/styles'

export default function VerifyEmail() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [state, setState] = useState<'working' | 'done' | 'error'>(token ? 'working' : 'error')
  const [message, setMessage] = useState(token ? '' : 'This verification link is incomplete.')
  const started = useRef(false)

  useEffect(() => {
    // Tokens are single-use; StrictMode would otherwise submit twice in development.
    if (!token || started.current) return
    started.current = true
    api.post('/api/auth/verify-email', { token })
      .then(() => {
        localStorage.setItem('emailVerified', '1')
        setState('done')
      })
      .catch(err => {
        setState('error')
        setMessage(err instanceof Error ? err.message : 'Verification failed')
      })
  }, [token])

  const signedIn = Boolean(getAccessToken())
  return (
    <AuthLayout
      title="Email verification"
      footer={<Link to={signedIn ? '/' : '/login'} style={authLinkStyle}>{signedIn ? 'Go to dashboard' : 'Log in'}</Link>}
    >
      <p role="status" style={{ fontSize: 14, textAlign: 'center', color: state === 'error' ? '#FF8A9B' : '#C8D0E0' }}>
        {state === 'working' ? 'Verifying…' : state === 'done' ? 'Your email address is verified.' : message}
      </p>
    </AuthLayout>
  )
}
