import { type ReactNode, useEffect, useRef, useState } from 'react'

interface GradientStatCardProps {
  label: string
  value: string | number
  icon: ReactNode
  gradient: string
  sub?: string
  trend?: { value: number; label: string }
  delay?: number
}

export default function GradientStatCard({
  label,
  value,
  icon,
  gradient,
  sub,
  trend,
  delay = 0,
}: GradientStatCardProps) {
  const [displayed, setDisplayed] = useState(0)
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const numericValue = typeof value === 'number' ? value : parseFloat(String(value).replace(/[^0-9.]/g, ''))
  const isNumeric = !isNaN(numericValue)
  const prefix = typeof value === 'string' ? value.match(/^[^0-9]*/)?.[0] ?? '' : ''
  const suffix = typeof value === 'string' ? value.match(/[^0-9.]*$/)?.[0] ?? '' : ''

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(timer)
  }, [delay])

  useEffect(() => {
    if (!visible || !isNumeric) return
    let start = 0
    const end = numericValue
    const duration = 1200
    const step = (timestamp: number) => {
      if (!start) start = timestamp
      const progress = Math.min((timestamp - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplayed(Math.floor(eased * end))
      if (progress < 1) requestAnimationFrame(step)
      else setDisplayed(end)
    }
    requestAnimationFrame(step)
  }, [visible, numericValue, isNumeric])

  const displayValue = isNumeric
    ? `${prefix}${displayed % 1 === 0 ? displayed : displayed.toFixed(1)}${suffix}`
    : value

  return (
    <div
      ref={ref}
      className="glass-card"
      style={{
        padding: '22px 24px',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(12px)',
        transition: `opacity 0.4s ease ${delay}ms, transform 0.4s cubic-bezier(0.22,1,0.36,1) ${delay}ms`,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Gradient orb background */}
      <div
        style={{
          position: 'absolute',
          top: -40,
          right: -40,
          width: 120,
          height: 120,
          borderRadius: '50%',
          background: gradient,
          opacity: 0.08,
          filter: 'blur(30px)',
          pointerEvents: 'none',
        }}
      />

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="stat-label" style={{ marginBottom: 10 }}>{label}</div>
          <div className="stat-number">{displayValue}</div>
          {sub && (
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 6 }}>{sub}</div>
          )}
          {trend && (
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              marginTop: 8,
              padding: '2px 8px',
              borderRadius: 100,
              fontSize: 11,
              fontWeight: 600,
              background: trend.value >= 0 ? 'rgba(34,211,165,0.12)' : 'rgba(255,77,106,0.12)',
              color: trend.value >= 0 ? '#22D3A5' : '#FF4D6A',
            }}>
              {trend.value >= 0 ? '↑' : '↓'} {Math.abs(trend.value)}% {trend.label}
            </div>
          )}
        </div>

        <div
          style={{
            width: 46,
            height: 46,
            borderRadius: 12,
            background: gradient,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: `0 8px 24px rgba(0,0,0,0.3)`,
          }}
        >
          {icon}
        </div>
      </div>
    </div>
  )
}
