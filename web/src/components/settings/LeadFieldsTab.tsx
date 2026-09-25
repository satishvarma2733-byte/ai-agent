import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import { LoadingState, ErrorState } from '../ui/States'
import { leadFieldsApi, type LeadField, type LeadFieldType } from '../../api/leadFields'

const TYPE_LABELS: Record<LeadFieldType, string> = {
  text: 'Text', number: 'Number', date: 'Date', select: 'Choice', boolean: 'Yes / No',
}

// The workspace's own lead fields: shown on every lead, in imports (by label) and exports,
// and settable from workflows as "custom.<key>".
export default function LeadFieldsTab({ canEdit }: { canEdit: boolean }) {
  const [fields, setFields] = useState<LeadField[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [type, setType] = useState<LeadFieldType>('text')
  const [options, setOptions] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    leadFieldsApi.list()
      .then(f => { if (!cancelled) setFields(f) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load fields') })
    return () => { cancelled = true }
  }, [])

  const add = async () => {
    setSaving(true)
    try {
      const created = await leadFieldsApi.create({
        label: label.trim(), field_type: type,
        options: type === 'select' ? options.split(',').map(o => o.trim()).filter(Boolean) : undefined,
      })
      setFields(prev => [...(prev ?? []), created])
      setLabel(''); setOptions(''); setType('text')
      toast.success(`Added "${created.label}"`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not add the field')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (f: LeadField) => {
    if (!confirm(`Delete "${f.label}"? Its value is removed from every lead.`)) return
    try {
      await leadFieldsApi.remove(f.id)
      setFields(prev => prev?.filter(x => x.id !== f.id) ?? null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not delete the field')
    }
  }

  const move = async (index: number, delta: number) => {
    if (!fields) return
    const next = [...fields]
    const [item] = next.splice(index, 1)
    next.splice(index + delta, 0, item)
    setFields(next)
    try {
      await Promise.all(next.map((f, position) => f.position === position ? null : leadFieldsApi.update(f.id, { position })))
      setFields(next.map((f, position) => ({ ...f, position })))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not reorder')
    }
  }

  if (error) return <ErrorState message={error} />
  if (!fields) return <LoadingState />
  return (
    <Card padding={0}>
      <div style={{ padding: '14px 20px', fontSize: 12.5, color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)', lineHeight: 1.6 }}>
        Fields your team fills in on every lead. CSV imports match them by column name, exports include them,
        and workflows can set them with the "Update CRM" step.
      </div>
      {fields.length === 0 ? (
        <div style={{ padding: '24px 20px', fontSize: 12.5, color: 'var(--color-text-muted)' }}>No custom fields yet.</div>
      ) : (
        <table className="avn-table">
          <thead><tr><th>Field</th><th>Type</th><th>Key</th><th /></tr></thead>
          <tbody>
            {fields.map((f, i) => (
              <tr key={f.id}>
                <td style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{f.label}</td>
                <td>{TYPE_LABELS[f.field_type as LeadFieldType] ?? f.field_type}{f.options?.length ? `: ${f.options.join(', ')}` : ''}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{f.key}</td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {canEdit && (
                    <>
                      <button aria-label={`Move ${f.label} up`} disabled={i === 0} onClick={() => move(i, -1)} style={iconButton}><ArrowUp size={13} /></button>
                      <button aria-label={`Move ${f.label} down`} disabled={i === fields.length - 1} onClick={() => move(i, 1)} style={iconButton}><ArrowDown size={13} /></button>
                      <button aria-label={`Delete ${f.label}`} onClick={() => remove(f)} style={{ ...iconButton, color: '#FF4D6A' }}><Trash2 size={13} /></button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit ? (
        <div style={{ display: 'flex', gap: 8, padding: '14px 20px', borderTop: '1px solid var(--color-border)', flexWrap: 'wrap' }}>
          <input className="avn-input" placeholder="Field name, e.g. Property type" value={label} onChange={e => setLabel(e.target.value)}
            aria-label="Field name" style={{ flex: '1 1 200px', height: 36 }} maxLength={100} />
          <select className="avn-input" value={type} onChange={e => setType(e.target.value as LeadFieldType)} aria-label="Field type" style={{ width: 130, height: 36, padding: '0 8px' }}>
            {Object.entries(TYPE_LABELS).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
          {type === 'select' && (
            <input className="avn-input" placeholder="Choices, comma separated" value={options} onChange={e => setOptions(e.target.value)}
              aria-label="Choices" style={{ flex: '1 1 200px', height: 36 }} />
          )}
          <Button variant="primary" onClick={add} loading={saving} disabled={!label.trim() || (type === 'select' && !options.trim())}>Add field</Button>
        </div>
      ) : (
        <div style={{ padding: '12px 20px', fontSize: 12, color: 'var(--color-text-muted)' }}>Only Admins and the Owner can change fields.</div>
      )}
    </Card>
  )
}

const iconButton = { background: 'transparent', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', padding: 4 } as const
