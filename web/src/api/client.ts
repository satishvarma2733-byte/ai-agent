// In dev, use empty string so requests go through Vite's proxy (no CORS).
// In production, use VITE_API_BASE_URL env var or default to same-origin.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

/** Absolute URL for an API path the browser loads directly (e.g. an <audio> src); other URLs pass through. */
export function apiUrl(url: string): string {
  return url.startsWith('/') ? `${BASE}${url}` : url
}

export type ApiClientError = Error & { status: number; body?: unknown }

function makeApiClientError(status: number, message: string, body?: unknown): ApiClientError {
  const err = new Error(message) as ApiClientError
  err.name = 'ApiClientError'
  err.status = status
  err.body = body
  return err
}

async function parseResponse(res: Response): Promise<unknown> {
  const ct = res.headers.get('content-type') ?? ''
  if (ct.includes('text/plain') || ct.includes('text/')) {
    return res.text()
  }
  // try JSON, fallback to text
  const text = await res.text()
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

// The access token lives only in memory, so an injected script can't read it from storage.
// A page load gets a fresh one from the httpOnly refresh cookie (restoreSession in lib/session.ts).
let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null) {
  accessToken = token
}

// Profile details kept for display only (not secrets); older builds also stored tokens here.
const AUTH_STORAGE_KEYS = ['accessToken', 'refreshToken', 'userEmail', 'userName', 'userRole', 'tenantId', 'emailVerified']
for (const legacy of ['accessToken', 'refreshToken']) localStorage.removeItem(legacy)

export function clearSession() {
  accessToken = null
  for (const key of AUTH_STORAGE_KEYS) localStorage.removeItem(key)
}

// One refresh at a time: parallel requests that hit 401 share the same rotation.
let refreshing: Promise<string | null> | null = null

export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${BASE}/api/auth/refresh`, { method: 'POST', credentials: 'include' })
      if (!res.ok) return null
      const { access_token } = await res.json() as { access_token: string }
      accessToken = access_token
      return access_token
    } catch {
      return null
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  isFormData = false
): Promise<T> {
  const url = `${BASE}${path}`
  const headers: Record<string, string> = {}
  let fetchBody: BodyInit | undefined

  const token = accessToken
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  if (body !== undefined) {
    if (isFormData && body instanceof FormData) {
      fetchBody = body
    } else {
      headers['Content-Type'] = 'application/json'
      fetchBody = JSON.stringify(body)
    }
  }

  // credentials: 'include' so the httpOnly refresh cookie reaches /api/auth/* (also cross-origin in production)
  let res = await fetch(url, { method, headers, body: fetchBody, credentials: 'include' })

  // Expired access token: rotate via the refresh cookie once, then retry.
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    const fresh = await refreshAccessToken()
    if (fresh) {
      headers['Authorization'] = `Bearer ${fresh}`
      res = await fetch(url, { method, headers, body: fetchBody, credentials: 'include' })
    } else {
      clearSession()
      window.location.href = '/login'
    }
  }

  const data = await parseResponse(res)

  if (!res.ok) {
    throw makeApiClientError(res.status, errorMessage(data, res.status), data)
  }

  return data as T
}

// FastAPI returns `detail` (string, or a list of validation errors); legacy routes used `message`.
function errorMessage(data: unknown, status: number): string {
  if (typeof data === 'object' && data !== null) {
    const body = data as { detail?: unknown; message?: unknown }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: string; loc?: unknown[] }
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined
      return field ? `${String(field)}: ${first.msg ?? 'invalid'}` : String(first.msg ?? 'Invalid request')
    }
    if (typeof body.message === 'string') return body.message
  }
  return `HTTP ${status}`
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, form: FormData) => request<T>('POST', path, form, true),
  getBaseUrl: () => BASE,
}
