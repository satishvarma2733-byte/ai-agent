import type { LeadField } from '../../api/leadFields'

type Values = Record<string, string | number | boolean> | null | undefined

// Inputs for a workspace's own lead fields. Empty values are sent as "" so the server clears them.
export default function CustomFieldInputs({ fields, values, onChange }: {
  fields: LeadField[]
  values: Values
  onChange: (values: Record<string, string | number | boolean>) => void
}) {
  if (!fields.length) return null
  const current = values ?? {}
  const set = (key: string, value: string | boolean) => onChange({ ...current, [key]: value })
  const inputStyle = { height: 34, fontSize: 12.5 } as const

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      {fields.map(field => {
        const id = `custom-${field.key}`
        const value = current[field.key]
        return (
          <div key={field.id}>
            <label htmlFor={id} style={{ display: 'block', fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4, fontWeight: 600 }}>{field.label}</label>
            {field.field_type === 'select' ? (
              <select id={id} className="avn-input" value={String(value ?? '')} onChange={e => set(field.key, e.target.value)} style={{ ...inputStyle, padding: '0 8px' }}>
                <option value="">—</option>
                {(field.options ?? []).map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : field.field_type === 'boolean' ? (
              <select id={id} className="avn-input" value={value === true ? 'yes' : value === false ? 'no' : ''}
                onChange={e => set(field.key, e.target.value === '' ? '' : e.target.value === 'yes')} style={{ ...inputStyle, padding: '0 8px' }}>
                <option value="">—</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            ) : (
              <input id={id} className="avn-input" style={inputStyle}
                type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'}
                value={value === undefined || value === null ? '' : String(value)}
                onChange={e => set(field.key, e.target.value)} />
            )}
          </div>
        )
      })}
    </div>
  )
}
