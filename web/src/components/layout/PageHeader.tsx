import { type ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  subtitle?: string
  actions?: ReactNode
  accent?: string
}

export default function PageHeader({ title, subtitle, actions, accent }: PageHeaderProps) {
  return (
    <div style={{ padding: '32px 32px 0', marginBottom: 28 }}>
      <div style={{
        background: accent
          ? `linear-gradient(135deg, ${accent}10 0%, rgba(94,230,255,0.03) 100%)`
          : 'linear-gradient(135deg, rgba(123,97,255,0.08) 0%, rgba(94,230,255,0.04) 100%)',
        border: `1px solid ${accent ? `${accent}20` : 'rgba(123,97,255,0.12)'}`,
        borderRadius: 18,
        padding: '22px 28px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        position: 'relative',
        overflow: 'hidden',
        flexWrap: 'wrap',
      }}>
        {/* Ambient glow */}
        <div style={{
          position: 'absolute', top: -50, right: -50,
          width: 180, height: 180,
          borderRadius: '50%',
          background: accent ?? 'rgba(123,97,255,0.12)',
          opacity: 0.06,
          filter: 'blur(60px)',
          pointerEvents: 'none',
        }} />

        <div>
          <div style={{
            fontFamily: 'Satoshi, Inter, sans-serif',
            fontSize: 26,
            fontWeight: 700,
            letterSpacing: '-0.03em',
            background: `linear-gradient(135deg, var(--color-text-primary) 40%, ${accent ?? '#9580FF'})`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            marginBottom: 4,
          }}>
            {title}
          </div>
          {subtitle && (
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{subtitle}</div>
          )}
        </div>

        {actions && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}
