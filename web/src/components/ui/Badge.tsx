import { type ReactNode } from 'react'

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'violet' | 'cyan'

interface BadgeProps {
  variant?: BadgeVariant
  dot?: boolean
  children: ReactNode
  glow?: boolean
  style?: React.CSSProperties
  className?: string
}

const chipClass: Record<BadgeVariant, string> = {
  default: 'avn-chip-gray',
  success: 'avn-chip-green',
  warning: 'avn-chip-amber',
  danger:  'avn-chip-red',
  info:    'avn-chip-cyan',
  violet:  'avn-chip-violet',
  cyan:    'avn-chip-cyan',
}

const dotColor: Record<BadgeVariant, string> = {
  default: 'var(--color-text-muted)',
  success: '#22D3A5',
  warning: '#F5A623',
  danger:  '#FF4D6A',
  info:    '#5EE6FF',
  violet:  '#9580FF',
  cyan:    '#5EE6FF',
}

export default function Badge({ variant = 'default', dot = false, children, glow = false, style, className }: BadgeProps) {
  const combinedStyle = {
    ...(glow ? { boxShadow: `0 0 10px ${dotColor[variant]}50` } : {}),
    ...style
  }
  return (
    <span
      className={`avn-chip ${chipClass[variant]} ${className || ''}`}
      style={combinedStyle}
    >
      {dot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: dotColor[variant],
            display: 'inline-block',
            flexShrink: 0,
            boxShadow: glow ? `0 0 6px ${dotColor[variant]}` : undefined,
          }}
        />
      )}
      {children}
    </span>
  )
}
