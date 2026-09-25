import { type ReactNode, type CSSProperties } from 'react'

interface GlassCardProps {
  children: ReactNode
  className?: string
  style?: CSSProperties
  padding?: number | string
  hover?: boolean
  glow?: boolean
  gradient?: boolean
  onClick?: () => void
}

export default function GlassCard({
  children,
  className = '',
  style,
  padding = '20px',
  hover = true,
  glow = false,
  gradient = false,
  onClick,
}: GlassCardProps) {
  return (
    <div
      className={`glass-card ${gradient ? 'gradient-border' : ''} ${className}`}
      onClick={onClick}
      style={{
        padding,
        cursor: onClick ? 'pointer' : 'default',
        boxShadow: glow
          ? '0 0 40px rgba(123,97,255,0.35), 0 4px 24px rgba(0,0,0,0.4)'
          : '0 4px 24px rgba(0,0,0,0.4)',
        transition: hover
          ? 'border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease'
          : 'none',
        ...style,
      }}
      onMouseEnter={hover && onClick ? (e) => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'
      } : undefined}
      onMouseLeave={hover && onClick ? (e) => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)'
      } : undefined}
    >
      {children}
    </div>
  )
}
