import { type TextareaHTMLAttributes } from 'react'

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
}

export default function Textarea({ label, error, hint, id, style, ...props }: TextareaProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, width: '100%' }}>
      {label && (
        <label htmlFor={inputId} style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
          {label}
        </label>
      )}
      <textarea
        id={inputId}
        {...props}
        className="avn-input"
        style={{
          resize: 'vertical',
          minHeight: 80,
          height: 'auto',
          padding: '10px 14px',
          borderColor: error ? '#FF4D6A' : undefined,
          boxShadow: error ? '0 0 0 2px rgba(255,77,106,0.15)' : undefined,
          lineHeight: 1.6,
          fontFamily: 'inherit',
          ...style,
        }}
      />
      {error && <span style={{ fontSize: 11.5, color: '#FF4D6A' }}>{error}</span>}
      {hint && !error && <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>{hint}</span>}
    </div>
  )
}
