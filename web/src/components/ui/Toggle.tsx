import { useId } from 'react'

interface ToggleProps {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
  hint?: string
  disabled?: boolean
  id?: string
}

export default function Toggle({ checked, onChange, label, hint, disabled, id }: ToggleProps) {
  const autoId = useId()
  const toggleId = id ?? autoId

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
      <button
        id={toggleId}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={label ? `${toggleId}-label` : undefined}
        aria-describedby={hint ? `${toggleId}-hint` : undefined}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        style={{
          width: 38,
          height: 22,
          borderRadius: 11,
          background: checked
            ? 'linear-gradient(90deg, #7B61FF, #9580FF)'
            : 'rgba(255,255,255,0.06)',
          border: `1px solid ${checked ? 'rgba(123,97,255,0.4)' : 'rgba(255,255,255,0.1)'}`,
          cursor: disabled ? 'not-allowed' : 'pointer',
          position: 'relative',
          transition: 'background 0.2s, border-color 0.2s',
          flexShrink: 0,
          marginTop: 2,
          opacity: disabled ? 0.4 : 1,
          padding: 0,
          boxShadow: checked ? '0 0 12px rgba(123,97,255,0.4)' : 'none',
        }}
      >
        <span
          style={{
            position: 'absolute',
            top: 2,
            left: checked ? 18 : 2,
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: '#fff',
            transition: 'left 0.2s cubic-bezier(0.22,1,0.36,1)',
            boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
          }}
        />
      </button>
      {(label || hint) && (
        <div>
          {label && <div id={`${toggleId}-label`} style={{ fontSize: 13, color: 'var(--color-text-secondary)', fontWeight: 500 }}>{label}</div>}
          {hint && <div id={`${toggleId}-hint`} style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 2, lineHeight: 1.5 }}>{hint}</div>}
        </div>
      )}
    </div>
  )
}
