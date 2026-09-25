import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  width?: number | string
}

export default function Modal({ open, onClose, title, children, width = 560 }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(7,11,20,0.88)',
          backdropFilter: 'blur(6px)',
        }}
      />

      {/* Panel */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: width,
          background: 'var(--color-bg-card)',
          border: '1px solid rgba(123,97,255,0.2)',
          borderRadius: 18,
          boxShadow: '0 24px 80px rgba(0,0,0,0.8), 0 0 0 1px rgba(123,97,255,0.08)',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '18px 22px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            flexShrink: 0,
          }}
        >
          <div style={{
            fontSize: 15,
            fontWeight: 700,
            color: 'var(--color-text-primary)',
            letterSpacing: '-0.02em',
            fontFamily: 'Satoshi, Inter, sans-serif',
          }}>
            {title}
          </div>
          <button aria-label="Close"
            onClick={onClose}
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.07)',
              color: 'var(--color-text-muted)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.15s',
            }}
            onMouseOver={e => {
              const el = e.currentTarget
              el.style.background = 'rgba(255,77,106,0.1)'
              el.style.borderColor = 'rgba(255,77,106,0.2)'
              el.style.color = '#FF4D6A'
            }}
            onMouseOut={e => {
              const el = e.currentTarget
              el.style.background = 'rgba(255,255,255,0.04)'
              el.style.borderColor = 'rgba(255,255,255,0.07)'
              el.style.color = 'var(--color-text-muted)'
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, scrollbarWidth: 'thin', scrollbarColor: 'rgba(123,97,255,0.3) transparent' }}>
          {children}
        </div>
      </div>
    </div>
  )
}
