import { type InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  fullWidth?: boolean
}

export default function Input({
  label,
  error,
  hint,
  fullWidth = true,
  id,
  style,
  ...props
}: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, width: fullWidth ? '100%' : undefined }}>
      {label && (
        <label
          htmlFor={inputId}
          style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', letterSpacing: '0.03em', textTransform: 'uppercase' }}
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        {...props}
        className="avn-input"
        style={{
          height: 38,
          borderColor: error ? '#FF4D6A' : undefined,
          boxShadow: error ? '0 0 0 2px rgba(255,77,106,0.15)' : undefined,
          ...style,
        }}
      />
      {error && <span style={{ fontSize: 11.5, color: '#FF4D6A' }}>{error}</span>}
      {hint && !error && <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>{hint}</span>}
    </div>
  )
}
