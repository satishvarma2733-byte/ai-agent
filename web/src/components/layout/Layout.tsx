import { type ReactNode, useState, useRef, useEffect, useCallback } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Settings2, PhoneCall, Users, CalendarDays, BookOpen,
  PhoneOutgoing, Bot, BarChart3, PhoneIncoming, FileText, Bell, Search,
  ChevronLeft, ChevronRight, Zap, Activity, GitBranch, Radio, UserCheck,
  CreditCard, Sun, Moon, Command, Wifi, WifiOff, Menu, X, Shield,
} from 'lucide-react'
import clsx from 'clsx'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useAppStore } from '@/store/useAppStore'
import toast from 'react-hot-toast'
import { api } from '@/api/client'
import { logout } from '@/lib/session'
import { notificationsApi, type InboxItem } from '@/api/notifications'

const navGroups = [
  {
    label: 'CORE',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
      { to: '/agents', label: 'AI Agents', icon: Bot },
      { to: '/analytics', label: 'Analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'CALLING',
    items: [
      { to: '/live-calls', label: 'Live Calls', icon: Radio },
      { to: '/inbound', label: 'Inbound', icon: PhoneIncoming },
      { to: '/outbound', label: 'Outbound', icon: PhoneOutgoing },
      { to: '/call-logs', label: 'Call Logs', icon: PhoneCall },
    ],
  },
  {
    label: 'CRM',
    items: [
      { to: '/crm', label: 'Voice CRM', icon: Users },
      { to: '/appointments', label: 'Appointments', icon: CalendarDays },
      { to: '/workflows', label: 'Workflows', icon: GitBranch },
    ],
  },
  {
    label: 'INTELLIGENCE',
    items: [
      { to: '/knowledge-base', label: 'Knowledge Base', icon: BookOpen },
      { to: '/cms', label: 'Content Manager', icon: FileText },
    ],
  },
  {
    label: 'SYSTEM',
    items: [
      { to: '/team', label: 'Team', icon: UserCheck },
      { to: '/billing', label: 'Billing', icon: CreditCard },
      { to: '/settings', label: 'Settings', icon: Shield },
      { to: '/configuration', label: 'Configuration', icon: Settings2, minRole: 'Admin' },
    ],
  },
]

const ROLE_RANK: Record<string, number> = { Owner: 5, Admin: 4, Manager: 3, Agent: 2, Viewer: 1 }

// Hides pages the server would refuse (the server still enforces every check).
function navFor(role: string) {
  return navGroups.map(g => ({
    ...g,
    items: g.items.filter(item => {
      const minRole = (item as { minRole?: string }).minRole
      return !minRole || (ROLE_RANK[role] ?? 0) >= ROLE_RANK[minRole]
    }),
  }))
}

const TYPE_COLORS: Record<string, string> = {
  info: '#7B61FF',
  success: '#22D3A5',
  warning: '#F5A623',
  error: '#FF4D6A',
}

const formatNotifTime = (isoString: string) => {
  try {
    const diffMs = Date.now() - new Date(isoString).getTime()
    const diffMins = Math.floor(diffMs / 60000)
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    const diffHrs = Math.floor(diffMins / 60)
    if (diffHrs < 24) return `${diffHrs}h ago`
    return new Date(isoString).toLocaleDateString()
  } catch {
    return 'some time ago'
  }
}

interface LayoutProps { children: ReactNode }

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()
  
  const notifications = useAppStore((s) => s.notifications)
  const unreadCount = useAppStore((s) => s.unreadCount)
  const markAllRead = useAppStore((s) => s.markAllRead)
  const clearNotifications = useAppStore((s) => s.clearNotifications)
  const setNotifications = useAppStore((s) => s.setNotifications)

  const [collapsed, setCollapsed] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('avn-theme')
    return saved ? saved === 'dark' : true
  })
  // ok = calls can work; degraded = API up but LiveKit/model key/database missing; error = API unreachable.
  const [sysStatus, setSysStatus] = useState<'ok' | 'degraded' | 'error' | 'loading'>('loading')
  const [sysMissing, setSysMissing] = useState<string[]>([])
  const [isMobile, setIsMobile] = useState(false)
  const [isTablet, setIsTablet] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const sidebarW = isMobile ? 0 : (collapsed || isTablet) ? 64 : 240

  // Theme persistence & DOM sync
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light')
    localStorage.setItem('avn-theme', darkMode ? 'dark' : 'light')
  }, [darkMode])

  // Responsive breakpoints
  const handleResize = useCallback(() => {
    const w = window.innerWidth
    setIsMobile(w < 768)
    setIsTablet(w >= 768 && w < 1200)
  }, [])

  useEffect(() => {
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [handleResize])

  useEffect(() => {
    if (searchOpen) setTimeout(() => searchRef.current?.focus(), 50)
  }, [searchOpen])

  // keyboard shortcut cmd+k / ctrl+k
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(o => !o)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  // Notifications for the signed-in member — poll every 30s
  useEffect(() => {
    const load = () => notificationsApi.list().then(r => setNotifications(r.items, r.unread)).catch(() => {})
    load()
    const timer = setInterval(load, 30_000)
    return () => clearInterval(timer)
  }, [setNotifications])

  // What calls need (database, LiveKit, model key) — poll every 30s
  useEffect(() => {
    const check = () =>
      api.get<{ ready: boolean; missing: string[] }>('/api/system/status')
        .then(d => {
          setSysMissing(d.missing)
          setSysStatus(d.ready ? 'ok' : 'degraded')
        })
        .catch(() => setSysStatus('error'))
    check()
    const timer = setInterval(check, 30_000)
    return () => clearInterval(timer)
  }, [])

  const allPages = navFor(localStorage.getItem('userRole') || '').flatMap(g => g.items)
  const searchResults = searchQ.length > 1
    ? allPages.filter(p => p.label.toLowerCase().includes(searchQ.toLowerCase()))
    : []

  // Role and identity come from the server session (see lib/session.ts); display only.
  const role = localStorage.getItem('userRole') || ''
  const userName = localStorage.getItem('userName') || ''
  const userEmail = localStorage.getItem('userEmail') || ''
  const [emailVerified, setEmailVerified] = useState(() => localStorage.getItem('emailVerified') === '1')
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const resendVerification = async () => {
    try {
      const res = await api.post<{ email_status: string }>('/api/auth/verify-email/resend')
      if (res.email_status === 'already_verified') {
        localStorage.setItem('emailVerified', '1')
        setEmailVerified(true)
      } else if (res.email_status === 'not_configured') {
        toast.error('Email is not configured on this server yet.')
      } else {
        toast.success('Verification email sent.')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not resend')
    }
  }

  // mobile bottom nav items
  const mobileNavItems = [
    { to: '/', label: 'Home', icon: LayoutDashboard, exact: true },
    { to: '/crm', label: 'CRM', icon: Users },
    { to: '/live-calls', label: 'Live', icon: Radio },
    { to: '/agents', label: 'Agents', icon: Bot },
    { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  ]

  return (
    <div style={{ display: 'flex', height: '100%', minHeight: '100vh', background: darkMode ? '#070B14' : '#F1F5F9' }}>
      {!isMobile && <div className="orb-bg orb-violet" />}
      {!isMobile && <div className="orb-bg orb-cyan" />}

      {/* ── MOBILE OVERLAY ── */}
      {isMobile && mobileMenuOpen && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(7,11,20,0.85)',
            backdropFilter: 'blur(8px)', zIndex: 60,
            animation: 'fadeIn 0.2s ease both',
          }}
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* ── SIDEBAR ── */}
      <aside
        role="navigation"
        aria-label="Main navigation"
        style={{
        width: isMobile ? 280 : sidebarW,
        minWidth: isMobile ? 280 : sidebarW,
        background: darkMode ? 'rgba(11, 16, 28, 0.97)' : 'rgba(255,255,255,0.97)',
        borderRight: `1px solid ${darkMode ? 'rgba(255,255,255,0.06)' : '#E2E8F0'}`,
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: isMobile ? 'fixed' : 'sticky', top: 0, height: '100vh',
        overflow: 'hidden',
        transition: 'transform 0.3s cubic-bezier(0.22,1,0.36,1), width 0.3s cubic-bezier(0.22,1,0.36,1)',
        transform: isMobile ? (mobileMenuOpen ? 'translateX(0)' : 'translateX(-100%)') : 'none',
        zIndex: isMobile ? 70 : 50, backdropFilter: 'blur(20px)',
      }}>
        {/* Logo */}
        <div style={{
          padding: collapsed ? '20px 0' : '20px 16px 16px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', gap: 10,
          justifyContent: collapsed ? 'center' : 'flex-start', flexShrink: 0,
        }}>
          <div style={{
            width: 34, height: 34, borderRadius: 10,
            background: 'linear-gradient(135deg, #7B61FF 0%, #5EE6FF 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0, boxShadow: '0 0 20px rgba(123,97,255,0.5)', position: 'relative',
          }}>
            <Zap size={17} color="#fff" strokeWidth={2.5} />
            <div style={{ position: 'absolute', inset: -2, borderRadius: 12, border: '1.5px solid rgba(123,97,255,0.4)', animation: 'neural-pulse 2.5s ease-in-out infinite' }} />
          </div>
          {!collapsed && (
            <div style={{ minWidth: 0 }}>
              <div style={{
                fontFamily: 'Satoshi, Inter, sans-serif', fontWeight: 700, fontSize: 16,
                letterSpacing: '-0.03em',
                background: 'linear-gradient(135deg, var(--color-text-primary) 40%, #9580FF)',
                WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', lineHeight: 1.2,
              }}>aVn</div>
              <div style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 1, letterSpacing: '0.04em' }}>Agentic Voice Network</div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: collapsed ? '8px 6px' : '8px 8px', overflowY: 'auto', overflowX: 'hidden' }}>
          {navFor(role).map((group) => (
            <div key={group.label} style={{ marginBottom: 2 }}>
              {!collapsed && (
                <div style={{
                  fontSize: 9, fontWeight: 700, color: 'var(--color-text-muted)',
                  letterSpacing: '0.12em', padding: '10px 10px 3px',
                }}>
                  {group.label}
                </div>
              )}
              {collapsed && <div style={{ height: 6 }} />}

              {group.items.map(({ to, label, icon: Icon, exact, badge }: any) => {
                const active = exact ? location.pathname === to : location.pathname.startsWith(to)
                return (
                  <NavLink
                    key={to} to={to} end={exact} title={collapsed ? label : undefined}
                    style={{
                      display: 'flex', alignItems: 'center',
                      gap: collapsed ? 0 : 9,
                      padding: collapsed ? '8px 0' : '7px 10px',
                      justifyContent: collapsed ? 'center' : 'flex-start',
                      borderRadius: 9, marginBottom: 1, fontSize: 12.5,
                      fontWeight: active ? 600 : 400,
                      color: active ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                      background: active ? 'linear-gradient(90deg, rgba(123,97,255,0.14), rgba(94,230,255,0.04))' : 'transparent',
                      textDecoration: 'none',
                      transition: 'all 0.15s ease',
                      border: active ? '1px solid rgba(123,97,255,0.18)' : '1px solid transparent',
                      position: 'relative', overflow: 'hidden',
                    }}
                    className={clsx({ 'nav-active-bar': active && !collapsed })}
                    onMouseOver={e => { if (!active) e.currentTarget.style.color = '#94A3B8' }}
                    onMouseOut={e => { if (!active) e.currentTarget.style.color = 'var(--color-text-muted)' }}
                  >
                    <Icon size={14} color={active ? '#9580FF' : 'currentColor'} style={{ flexShrink: 0, transition: 'color 0.15s' }} />
                    {!collapsed && (
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{label}</span>
                    )}
                    {!collapsed && badge && (
                      <span style={{ fontSize: 8, fontWeight: 800, padding: '2px 5px', borderRadius: 4, background: 'rgba(34,211,165,0.15)', color: '#22D3A5', letterSpacing: '0.06em', animation: 'neural-pulse 2s ease-in-out infinite' }}>{badge}</span>
                    )}
                    {active && !collapsed && (
                      <div style={{ width: 4, height: 4, borderRadius: '50%', background: '#7B61FF', boxShadow: '0 0 6px rgba(123,97,255,0.8)' }} />
                    )}
                  </NavLink>
                )
              })}
            </div>
          ))}
        </nav>

        {/* Bottom */}
        <div style={{
          borderTop: '1px solid rgba(255,255,255,0.05)',
          padding: collapsed ? '10px 6px' : '10px 12px',
          flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          {!collapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px' }}>
              {sysStatus === 'ok'
                ? <><Activity size={12} color="#22D3A5" /><span style={{ fontSize: 10.5, color: '#22D3A5', fontWeight: 500 }}>Ready for calls</span></>
                : sysStatus === 'degraded'
                  ? <><Activity size={12} color="#F59E0B" /><span style={{ fontSize: 10.5, color: '#F59E0B', fontWeight: 500 }}>Missing: {sysMissing.join(', ')}</span></>
                : sysStatus === 'error'
                  ? <><WifiOff size={12} color="#FF4D6A" /><span style={{ fontSize: 10.5, color: '#FF4D6A', fontWeight: 500 }}>API unreachable</span></>
                  : <><div className="loading-dot" /><span style={{ fontSize: 10.5, color: 'var(--color-text-muted)' }}>Checking…</span></>
              }
            </div>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start',
              gap: 8, padding: '6px 8px', borderRadius: 8,
              background: 'transparent', border: '1px solid rgba(255,255,255,0.05)',
              color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: 12,
              transition: 'all 0.15s', width: '100%',
            }}
          >
            {collapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      {/* ── MAIN AREA ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>

        {/* ── TOPBAR ── */}
        <header
          role="banner"
          style={{
          height: 52, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 20px', borderBottom: `1px solid ${darkMode ? 'rgba(255,255,255,0.05)' : '#E2E8F0'}`,
          background: darkMode ? 'rgba(7,11,20,0.85)' : 'rgba(255,255,255,0.85)', backdropFilter: 'blur(16px)',
          position: 'sticky', top: 0, zIndex: 40, flexShrink: 0, gap: 12,
        }}>
          {/* Mobile hamburger */}
          {isMobile && (
            <button
              onClick={() => setMobileMenuOpen(o => !o)}
              aria-label="Toggle navigation menu"
              style={{
                width: 32, height: 32, borderRadius: 8,
                background: 'transparent', border: 'none',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', color: darkMode ? 'var(--color-text-muted)' : '#64748B', flexShrink: 0,
              }}
            >
              {mobileMenuOpen ? <X size={16} /> : <Menu size={16} />}
            </button>
          )}
          {/* Left: search */}
          <div style={{ position: 'relative', flex: 1, maxWidth: 320 }}>
            {searchOpen ? (
              <div style={{ position: 'relative' }}>
                <Search size={13} color="#4B5675" style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                <input
                  ref={searchRef}
                  value={searchQ}
                  onChange={e => setSearchQ(e.target.value)}
                  onBlur={() => { setSearchOpen(false); setSearchQ('') }}
                  placeholder="Search pages…"
                  className="avn-input"
                  style={{ paddingLeft: 32, height: 34, fontSize: 13 }}
                />
                {searchResults.length > 0 && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
                    background: 'var(--color-bg-card)', border: '1px solid rgba(123,97,255,0.2)',
                    borderRadius: 12, overflow: 'hidden', boxShadow: '0 16px 40px rgba(0,0,0,0.5)', zIndex: 100,
                  }}>
                    {searchResults.map(p => (
                      <button
                        key={p.to}
                        onMouseDown={() => { navigate(p.to); setSearchOpen(false); setSearchQ('') }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10,
                          padding: '9px 14px', width: '100%', background: 'transparent',
                          border: 'none', color: 'var(--color-text-secondary)', fontSize: 13, cursor: 'pointer',
                          textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.04)',
                          transition: 'background 0.1s',
                        }}
                        onMouseOver={e => e.currentTarget.style.background = 'rgba(123,97,255,0.08)'}
                        onMouseOut={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <p.icon size={13} color="#7B61FF" />
                        {p.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={() => setSearchOpen(true)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px',
                  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: 9, color: 'var(--color-text-muted)', fontSize: 12, cursor: 'pointer',
                  transition: 'all 0.15s', width: isMobile ? 'auto' : '100%', maxWidth: 220,
                }}
              >
                <Search size={12} />
                {!isMobile && <span>Search…</span>}
                {!isMobile && <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--color-text-muted)', background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 4, display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Command size={8} /> K
                </span>}
              </button>
            )}
          </div>

          {/* Right: actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 6 : 8, flexShrink: 0 }}>
            {/* Role (from the signed-in session) */}
            {role && !isMobile && (
              <span title="Your role in this workspace" style={{
                background: 'rgba(123,97,255,0.08)', border: '1px solid rgba(123,97,255,0.18)',
                borderRadius: 9, color: '#9580FF', fontSize: 11, fontWeight: 600, padding: '4px 9px',
              }}>{role}</span>
            )}

            {/* Status badge */}
            <div title={sysStatus === 'degraded' ? `Calls can't run yet. Missing: ${sysMissing.join(', ')}` : sysStatus === 'ok' ? 'Database, LiveKit and AI model key are configured' : undefined} style={{
              padding: '2px 9px', borderRadius: 100, fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
              background: sysStatus === 'ok' ? 'rgba(34,211,165,0.12)' : sysStatus === 'degraded' ? 'rgba(245,158,11,0.12)' : 'rgba(255,77,106,0.12)',
              color: sysStatus === 'ok' ? '#22D3A5' : sysStatus === 'degraded' ? '#F59E0B' : '#FF4D6A',
              border: `1px solid ${sysStatus === 'ok' ? 'rgba(34,211,165,0.2)' : sysStatus === 'degraded' ? 'rgba(245,158,11,0.25)' : 'rgba(255,77,106,0.2)'}`,
            }}>
              {sysStatus === 'ok' ? 'READY' : sysStatus === 'degraded' ? 'SETUP NEEDED' : sysStatus === 'error' ? 'OFFLINE' : '…'}
            </div>

            {/* Theme toggle — animated pill */}
            <ThemeToggle
              isDark={darkMode}
              onToggle={(next) => setDarkMode(next)}
            />

            {/* Notifications */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => {
                  setNotifOpen(o => !o)
                  if (!notifOpen && unreadCount > 0) {
                    markAllRead()
                    notificationsApi.readAll().catch(() => {})
                  }
                }}
                aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
                aria-expanded={notifOpen}
                style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: unreadCount > 0 ? '#7B61FF' : 'var(--color-text-muted)', transition: 'all 0.15s', position: 'relative',
                }}
              >
                <Bell size={13} />
                {unreadCount > 0 && (
                  <div style={{
                    position: 'absolute', top: 5, right: 5, width: 6, height: 6, borderRadius: '50%',
                    background: '#7B61FF', boxShadow: '0 0 6px rgba(123,97,255,0.8)',
                    border: '1.5px solid #070B14',
                  }} />
                )}
              </button>
              {notifOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0, width: 290,
                  background: 'var(--color-bg-card)', border: '1px solid rgba(123,97,255,0.2)',
                  borderRadius: 14, boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
                  overflow: 'hidden', zIndex: 100, animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both',
                }}>
                  <div style={{
                    padding: '11px 14px', borderBottom: '1px solid rgba(255,255,255,0.05)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                  }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>Notifications</span>
                    {notifications.length > 0 && (
                      <span
                        onClick={() => { clearNotifications(); notificationsApi.clear().catch(() => {}) }}
                        style={{ fontSize: 11, color: '#FF4D6A', cursor: 'pointer', fontWeight: 500 }}
                      >
                        Clear All
                      </span>
                    )}
                  </div>
                  {notifications.length === 0 ? (
                    <div style={{ padding: '24px 14px', textAlign: 'center', fontSize: 12, color: 'var(--color-text-muted)' }}>
                      No new notifications
                    </div>
                  ) : (
                    notifications.slice(0, 5).map((n) => {
                      const color = TYPE_COLORS[n.type] || '#7B61FF'
                      return (
                        <div key={n.id} role={(n as InboxItem).link ? 'button' : undefined}
                          onClick={() => { const link = (n as InboxItem).link; if (link) { setNotifOpen(false); navigate(link) } }}
                          style={{
                          cursor: (n as InboxItem).link ? 'pointer' : 'default',
                          padding: '10px 14px',
                          borderBottom: '1px solid rgba(255,255,255,0.04)',
                          display: 'flex', gap: 10,
                          background: n.read ? 'transparent' : 'rgba(123,97,255,0.02)',
                        }}>
                          <div style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0, marginTop: 5 }} />
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 1 }}>{n.title}</div>
                            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.3 }}>{n.message}</div>
                            <div style={{ fontSize: 10, color: 'var(--color-text-muted)', marginTop: 3 }}>{formatNotifTime(n.created_at)}</div>
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              )}
            </div>

            {/* User menu */}
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setUserMenuOpen(o => !o)}
                aria-label="Account menu"
                aria-expanded={userMenuOpen}
                style={{
                  width: 32, height: 32, borderRadius: 8, border: 'none',
                  background: 'linear-gradient(135deg, #7B61FF, #5EE6FF)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 13, fontWeight: 700, color: '#fff', cursor: 'pointer',
                  boxShadow: '0 0 12px rgba(123,97,255,0.3)', flexShrink: 0,
                }}
              >
                {(userName || userEmail || '?').charAt(0).toUpperCase()}
              </button>
              {userMenuOpen && (
                <div role="menu" style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0, width: 240, zIndex: 100,
                  background: 'var(--color-bg-card)', border: '1px solid rgba(123,97,255,0.2)', borderRadius: 12,
                  boxShadow: '0 20px 60px rgba(0,0,0,0.5)', overflow: 'hidden',
                }}>
                  <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{userName || 'Signed in'}</div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{userEmail}</div>
                    {role && <div style={{ fontSize: 11, color: '#9580FF', marginTop: 4 }}>{role}</div>}
                  </div>
                  <button role="menuitem" onClick={() => { setUserMenuOpen(false); navigate('/settings') }}
                    style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'transparent', border: 'none', color: 'var(--color-text-primary)', fontSize: 13, cursor: 'pointer' }}>
                    Settings
                  </button>
                  <button role="menuitem" onClick={() => { void logout() }}
                    style={{ width: '100%', textAlign: 'left', padding: '10px 14px', background: 'transparent', border: 'none', borderTop: '1px solid rgba(255,255,255,0.06)', color: '#FF8A9B', fontSize: 13, cursor: 'pointer' }}>
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ── PAGE CONTENT ── */}
        <main role="main" style={{ flex: 1, overflow: 'auto', position: 'relative', paddingBottom: isMobile ? 64 : 0 }}>
          {!emailVerified && userEmail && (
            <div role="status" style={{
              display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '8px 24px',
              background: 'rgba(245,166,35,0.08)', borderBottom: '1px solid rgba(245,166,35,0.2)', fontSize: 12.5, color: '#F5C26B',
            }}>
              <span>Please verify {userEmail}. Check your inbox for the link.</span>
              <button onClick={resendVerification} style={{ background: 'transparent', border: 'none', color: '#F5A623', fontWeight: 600, cursor: 'pointer', fontSize: 12.5, padding: 0 }}>
                Resend email
              </button>
            </div>
          )}
          {children}
        </main>
      </div>

      {/* ── MOBILE BOTTOM NAV ── */}
      {isMobile && (
        <nav
          aria-label="Mobile navigation"
          style={{
            position: 'fixed', bottom: 0, left: 0, right: 0, height: 60,
            background: darkMode ? 'rgba(11,16,28,0.97)' : 'rgba(255,255,255,0.97)',
            borderTop: `1px solid ${darkMode ? 'rgba(255,255,255,0.06)' : '#E2E8F0'}`,
            backdropFilter: 'blur(20px)', zIndex: 50,
            display: 'flex', alignItems: 'center', justifyContent: 'space-around',
            padding: '0 8px',
          }}
        >
          {mobileNavItems.map(({ to, label, icon: Icon, exact }) => {
            const active = exact ? location.pathname === to : location.pathname.startsWith(to)
            return (
              <NavLink
                key={to}
                to={to}
                end={exact}
                aria-label={label}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
                  padding: '6px 12px', borderRadius: 10,
                  background: active ? 'rgba(123,97,255,0.12)' : 'transparent',
                  textDecoration: 'none',
                  transition: 'all 0.15s',
                }}
              >
                <Icon size={18} color={active ? '#7B61FF' : darkMode ? 'var(--color-text-muted)' : '#94A3B8'} />
                <span style={{
                  fontSize: 9, fontWeight: active ? 700 : 500,
                  color: active ? '#7B61FF' : darkMode ? 'var(--color-text-muted)' : '#94A3B8',
                  letterSpacing: '0.03em',
                }}>{label}</span>
              </NavLink>
            )
          })}
        </nav>
      )}
    </div>
  )
}
