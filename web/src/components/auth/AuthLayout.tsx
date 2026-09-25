import type { ReactNode } from 'react'
import { Zap } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export default function AuthLayout({ title, subtitle, children, footer }: {
  title: string
  subtitle?: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh',
      background: '#070B14', position: 'relative', overflow: 'hidden', padding: 16,
      fontFamily: "'General Sans', 'Inter', sans-serif",
    }}>
      <div className="orb-bg orb-violet" style={{ filter: 'blur(100px)', opacity: 0.15, width: 400, height: 400 }} />
      <div className="orb-bg orb-cyan" style={{ filter: 'blur(100px)', opacity: 0.12, width: 350, height: 350, right: '10%' }} />
      <div className="glass-card" style={{
        width: '100%', maxWidth: 420, padding: '40px 32px', border: '1px solid rgba(123,97,255,0.2)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)', borderRadius: 20, background: 'rgba(14,20,32,0.85)',
        backdropFilter: 'blur(24px)', zIndex: 10,
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: 28, textAlign: 'center' }}>
          <div style={{
            width: 48, height: 48, borderRadius: 14, background: 'linear-gradient(135deg, #7B61FF 0%, #5EE6FF 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 24px rgba(123,97,255,0.5)', marginBottom: 16,
          }}>
            <Zap size={24} color="#fff" strokeWidth={2.5} />
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.02em', marginBottom: 6 }}>{title}</h1>
          {subtitle && <p style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{subtitle}</p>}
        </div>
        {children}
        {footer && <div style={{ marginTop: 24, textAlign: 'center', fontSize: 13, color: 'var(--color-text-muted)' }}>{footer}</div>}
      </div>
    </div>
  )
}

export function AuthField({ id, label, icon: Icon, ...input }: {
  id: string
  label: string
  icon: LucideIcon
} & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={id} style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>{label}</label>
      <div style={{ position: 'relative' }}>
        <Icon size={16} color="var(--color-text-muted)" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} aria-hidden />
        <input id={id} className="avn-input" style={{ paddingLeft: 38, height: 42, fontSize: 14, width: '100%' }} {...input} />
      </div>
    </div>
  )
}

export function AuthSubmit({ loading, label, loadingLabel }: { loading: boolean; label: string; loadingLabel: string }) {
  return (
    <button type="submit" disabled={loading} className="avn-btn avn-btn-primary"
      style={{ height: 42, fontSize: 14, fontWeight: 600, width: '100%', marginTop: 6 }}>
      {loading ? loadingLabel : label}
    </button>
  )
}
