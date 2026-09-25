import { type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 300,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={onCancel}
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(7,11,20,0.88)',
          backdropFilter: 'blur(6px)',
        }}
      />
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 420,
          background: 'var(--color-bg-card)',
          border: `1px solid ${destructive ? 'rgba(255,77,106,0.25)' : 'rgba(123,97,255,0.2)'}`,
          borderRadius: 18,
          boxShadow: `0 24px 80px rgba(0,0,0,0.8), 0 0 0 1px ${destructive ? 'rgba(255,77,106,0.08)' : 'rgba(123,97,255,0.08)'}`,
          padding: 28,
          animation: 'scaleIn 0.2s cubic-bezier(0.22,1,0.36,1) both',
        }}
      >
        {/* Icon */}
        <div style={{
          width: 44,
          height: 44,
          borderRadius: 12,
          background: destructive ? 'rgba(255,77,106,0.1)' : 'rgba(123,97,255,0.1)',
          border: `1px solid ${destructive ? 'rgba(255,77,106,0.25)' : 'rgba(123,97,255,0.2)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
          boxShadow: `0 0 20px ${destructive ? 'rgba(255,77,106,0.15)' : 'rgba(123,97,255,0.15)'}`,
        }}>
          <AlertTriangle size={20} color={destructive ? '#FF4D6A' : '#7B61FF'} />
        </div>

        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.02em', marginBottom: 8, fontFamily: 'Satoshi, Inter, sans-serif' }}>
          {title}
        </div>
        <div style={{ fontSize: 13.5, color: 'var(--color-text-muted)', lineHeight: 1.65, marginBottom: 24 }}>
          {message}
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            disabled={loading}
            style={{
              padding: '9px 18px',
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 10,
              color: 'var(--color-text-secondary)',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            style={{
              padding: '9px 18px',
              background: destructive
                ? 'linear-gradient(135deg, #FF4D6A, #CC1F38)'
                : 'linear-gradient(135deg, #7B61FF, #5851CC)',
              border: 'none',
              borderRadius: 10,
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.6 : 1,
              transition: 'opacity 0.15s',
              boxShadow: destructive
                ? '0 0 20px rgba(255,77,106,0.3)'
                : '0 0 20px rgba(123,97,255,0.35)',
            }}
          >
            {loading ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
