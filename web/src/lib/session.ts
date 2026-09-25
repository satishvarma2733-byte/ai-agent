import { api, clearSession, refreshAccessToken, setAccessToken } from '../api/client'
import type { Schema } from '../api/types'

export { clearSession }

export type SessionUser = Schema<'UserOut'>

/** Store a fresh access token and cache the profile used by the shell (role, name). */
export async function startSession(accessToken: string): Promise<SessionUser> {
  setAccessToken(accessToken)
  const me = await api.get<SessionUser>('/api/auth/me')
  localStorage.setItem('userEmail', me.email)
  localStorage.setItem('userName', me.name)
  localStorage.setItem('userRole', me.role)
  localStorage.setItem('tenantId', me.tenant_id ?? '')
  localStorage.setItem('emailVerified', me.email_verified_at ? '1' : '')
  window.dispatchEvent(new Event('roleChanged'))
  return me
}

export async function logout() {
  try {
    await api.post('/api/auth/logout')
  } catch {
    // Session may already be gone; clearing locally is what matters.
  }
  clearSession()
  window.location.href = '/login'
}

/** On page load: exchange the httpOnly refresh cookie for an access token. Null if not signed in. */
export async function restoreSession(): Promise<SessionUser | null> {
  const token = await refreshAccessToken()
  if (!token) return null
  try {
    return await startSession(token)
  } catch {
    clearSession()
    return null
  }
}
