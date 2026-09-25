import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { getAccessToken } from './api/client'
import { restoreSession } from './lib/session'
import { Toaster } from 'react-hot-toast'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
const Signup = lazy(() => import('./pages/Signup'))
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const AcceptInvite = lazy(() => import('./pages/AcceptInvite'))
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'))
const Overview = lazy(() => import('./pages/Overview'))
const Configuration = lazy(() => import('./pages/Configuration'))
const CallLogs = lazy(() => import('./pages/CallLogs'))
const CRM = lazy(() => import('./pages/CRM'))
const Contacts = lazy(() => import('./pages/Contacts'))
const Appointments = lazy(() => import('./pages/Appointments'))
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase'))
const OutboundCalls = lazy(() => import('./pages/OutboundCalls'))
const Agents = lazy(() => import('./pages/Agents'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Inbound = lazy(() => import('./pages/Inbound'))
const CMS = lazy(() => import('./pages/CMS'))
const Workflows = lazy(() => import('./pages/Workflows'))
const LiveCalls = lazy(() => import('./pages/LiveCalls'))
const Team = lazy(() => import('./pages/Team'))
const Billing = lazy(() => import('./pages/Billing'))
const Settings = lazy(() => import('./pages/Settings'))

// Each page is its own chunk, loaded on first visit, so sign-in doesn't download the whole app.
function PageLoading() {
  return <div role="status" style={{ padding: 32, color: 'var(--color-text-muted)' }}>Loading…</div>
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [state, setState] = useState<'checking' | 'signed-in' | 'signed-out'>(() => (getAccessToken() ? 'signed-in' : 'checking'))

  useEffect(() => {
    if (state !== 'checking') return
    let cancelled = false
    restoreSession().then(user => { if (!cancelled) setState(user ? 'signed-in' : 'signed-out') })
    return () => { cancelled = true }
  }, [state])

  if (state === 'checking') {
    return <div role="status" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-muted)' }}>Loading…</div>
  }
  if (state === 'signed-out') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Layout><Suspense fallback={<PageLoading />}>{children}</Suspense></Layout>
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#0E1420',
            color: 'var(--color-text-primary)',
            border: '1px solid rgba(123,97,255,0.25)',
            borderRadius: '12px',
            fontSize: '13px',
            fontFamily: "'General Sans', 'Inter', sans-serif",
            boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(123,97,255,0.1)',
          },
          success: { iconTheme: { primary: '#22D3A5', secondary: '#0E1420' } },
          error:   { iconTheme: { primary: '#FF4D6A', secondary: '#0E1420' } },
          duration: 3500,
        }}
      />
      <Suspense fallback={<PageLoading />}>
        <Routes>
          <Route path="/login"  element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password"  element={<ResetPassword />} />
          <Route path="/accept-invite"   element={<AcceptInvite />} />
          <Route path="/verify-email"    element={<VerifyEmail />} />

          <Route path="/"               element={<ProtectedRoute><Overview /></ProtectedRoute>} />
          <Route path="/agents"         element={<ProtectedRoute><Agents /></ProtectedRoute>} />
          <Route path="/analytics"      element={<ProtectedRoute><Analytics /></ProtectedRoute>} />
          <Route path="/call-logs"      element={<ProtectedRoute><CallLogs /></ProtectedRoute>} />
          <Route path="/live-calls"     element={<ProtectedRoute><LiveCalls /></ProtectedRoute>} />
          <Route path="/inbound"        element={<ProtectedRoute><Inbound /></ProtectedRoute>} />
          <Route path="/outbound"       element={<ProtectedRoute><OutboundCalls /></ProtectedRoute>} />
          <Route path="/contacts"       element={<ProtectedRoute><Contacts /></ProtectedRoute>} />
          <Route path="/crm"            element={<ProtectedRoute><CRM /></ProtectedRoute>} />
          <Route path="/appointments"   element={<ProtectedRoute><Appointments /></ProtectedRoute>} />
          <Route path="/workflows"      element={<ProtectedRoute><Workflows /></ProtectedRoute>} />
          <Route path="/knowledge-base" element={<ProtectedRoute><KnowledgeBase /></ProtectedRoute>} />
          <Route path="/cms"            element={<ProtectedRoute><CMS /></ProtectedRoute>} />
          <Route path="/team"           element={<ProtectedRoute><Team /></ProtectedRoute>} />
          <Route path="/billing"        element={<ProtectedRoute><Billing /></ProtectedRoute>} />
          <Route path="/settings"       element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          <Route path="/configuration"  element={<ProtectedRoute><Configuration /></ProtectedRoute>} />
          
          {/* Wildcard fallback to login */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
