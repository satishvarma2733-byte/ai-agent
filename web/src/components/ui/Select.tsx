import { type SelectHTMLAttributes } from 'react'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  options: { value: string | number; label: string }[]
}

export default function Select({ label, error, hint, options, id, ...props }: SelectProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, width: '100%' }}>
      {label && (
        <label htmlFor={inputId} style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', letterSpacing: '0.03em', textTransform: 'uppercase' }}>
          {label}
        </label>
      )}
      <select
        id={inputId}
        {...props}
        className="avn-input"
        style={{
          height: 38,
          paddingRight: 32,
          cursor: 'pointer',
          appearance: 'none',
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%234B5675' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'right 10px center',
          borderColor: error ? '#FF4D6A' : undefined,
        }}
      >
        {options.map(o => (
          <option key={o.value} value={o.value} style={{ background: 'var(--color-bg-card)', color: 'var(--color-text-primary)' }}>
            {o.label}
          </option>
        ))}
      </select>
      {error && <span style={{ fontSize: 11.5, color: '#FF4D6A' }}>{error}</span>}
      {hint && !error && <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>{hint}</span>}
    </div>
  )
}
