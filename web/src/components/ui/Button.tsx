import { type ButtonHTMLAttributes, type ReactNode } from 'react'
import clsx from 'clsx'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'cyan' | 'outline'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
  children?: ReactNode
}

const variantClass: Record<Variant, string> = {
  primary:   'avn-btn-primary',
  secondary: 'avn-btn-secondary',
  ghost:     'avn-btn-ghost',
  danger:    'avn-btn-danger',
  cyan:      'avn-btn-secondary',
  outline:   'avn-btn-secondary',
}

const sizeClass: Record<Size, string> = {
  sm: 'avn-btn-sm',
  md: '',
  lg: 'avn-btn-lg',
}

export default function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  children,
  className,
  disabled,
  style,
  ...props
}: ButtonProps) {
  const cyanStyle = variant === 'cyan' ? {
    background: 'rgba(94,230,255,0.1)',
    border: '1px solid rgba(94,230,255,0.25)',
    color: '#5EE6FF',
  } : {}

  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={clsx('avn-btn', variantClass[variant], sizeClass[size], className)}
      style={{ ...cyanStyle, ...style }}
    >
      {loading ? (
        <svg
          style={{ width: 14, height: 14, flexShrink: 0, animation: 'spin-slow 1s linear infinite' }}
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.2" />
          <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
      ) : icon ? (
        <span style={{ display: 'flex', flexShrink: 0 }}>{icon}</span>
      ) : null}
      {children}
    </button>
  )
}
