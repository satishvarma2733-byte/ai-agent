import { type ReactNode, type CSSProperties } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  style?: CSSProperties
  padding?: number | string
  hover?: boolean
  onClick?: () => void
}

export default function Card({
  children,
  className = '',
  style,
  padding = '20px',
  hover = false,
  onClick,
}: CardProps) {
  return (
    <div
      className={`glass-card ${className}`}
      onClick={onClick}
      style={{
        padding,
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
      onMouseEnter={hover ? (e) => {
        const el = e.currentTarget as HTMLDivElement
        el.style.borderColor = 'rgba(123,97,255,0.2)'
        el.style.boxShadow = '0 8px 40px rgba(0,0,0,0.5), 0 0 0 1px rgba(123,97,255,0.1)'
      } : undefined}
      onMouseLeave={hover ? (e) => {
        const el = e.currentTarget as HTMLDivElement
        el.style.borderColor = ''
        el.style.boxShadow = ''
      } : undefined}
    >
      {children}
    </div>
  )
}
