import { type ReactNode } from 'react'
import Button from './Button'

export function Spinner({ size = 20, color = '#7B61FF' }: { size?: number; color?: string }) {
  return (
    <svg
      style={{ width: size, height: size, flexShrink: 0 }}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle cx="12" cy="12" r="10" stroke={color} strokeWidth="2.5" strokeOpacity="0.15" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke={color}
        strokeWidth="2.5"
        strokeLinecap="round"
        style={{ animation: 'spin-slow 0.8s linear infinite' }}
      />
    </svg>
  )
}

export function WaveLoadingState({ message = 'Loading…' }: { message?: string }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '64px 24px',
      gap: 20,
    }}>
      {/* Waveform bars loading */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, height: 36 }}>
        {[0.6, 1, 0.4, 0.9, 0.5, 1, 0.7, 0.3, 0.8, 0.5].map((h, i) => (
          <div
            key={i}
            style={{
              width: 4,
              height: 36 * h,
              borderRadius: 4,
              background: 'linear-gradient(180deg, #7B61FF, #5EE6FF)',
              transformOrigin: 'center',
              animation: `waveform 0.${7 + i % 4}s ease-in-out ${i * 0.08}s infinite`,
            }}
          />
        ))}
      </div>
      <div style={{ fontSize: 13, color: 'var(--color-text-muted)', fontWeight: 500 }}>{message}</div>
    </div>
  )
}

export function LoadingState({ message = 'Loading…' }: { message?: string }) {
  return <WaveLoadingState message={message} />
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '64px 24px',
      gap: 12,
      textAlign: 'center',
    }}>
      {icon && (
        <div style={{
          width: 56,
          height: 56,
          borderRadius: 16,
          background: 'rgba(123,97,255,0.08)',
          border: '1px solid rgba(123,97,255,0.15)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--color-text-muted)',
          marginBottom: 4,
        }}>
          {icon}
        </div>
      )}
      <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--color-text-secondary)', letterSpacing: '-0.01em' }}>
        {title}
      </div>
      {description && (
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)', maxWidth: 380, lineHeight: 1.6 }}>
          {description}
        </div>
      )}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '56px 24px',
      gap: 12,
      textAlign: 'center',
    }}>
      <div style={{
        width: 56,
        height: 56,
        borderRadius: 16,
        background: 'rgba(255,77,106,0.08)',
        border: '1px solid rgba(255,77,106,0.2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 24,
        boxShadow: '0 0 24px rgba(255,77,106,0.15)',
        marginBottom: 4,
      }}>
        ⚠
      </div>
      <div style={{ fontSize: 14, color: '#FF6B84', fontWeight: 600 }}>Something went wrong</div>
      <div style={{ fontSize: 13, color: 'var(--color-text-muted)', maxWidth: 360 }}>{message}</div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} style={{ marginTop: 4 }}>
          Try again
        </Button>
      )}
    </div>
  )
}
