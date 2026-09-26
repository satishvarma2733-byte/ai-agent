import { useEffect, useState } from 'react'
import { IndianRupee } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import { api } from '../../api/client'
import type { Schema } from '../../api/types'

type Business = Schema<'BusinessSettingsIO'>
const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD']

// Average value of a booking, which Analytics uses to estimate revenue per agent and campaign.
export default function BusinessValueCard() {
  const [value, setValue] = useState<string>('')
  const [currency, setCurrency] = useState('INR')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get<Business>('/api/workspace/business').then(b => {
      setValue(b.booking_value === null || b.booking_value === undefined ? '' : String(b.booking_value))
      setCurrency(b.currency ?? 'INR')
      setLoaded(true)
    }).catch(() => setLoaded(true))
  }, [])
  if (!loaded) return null

  const save = async () => {
    setSaving(true)
    try {
      await api.put<Business>('/api/workspace/business', { booking_value: value === '' ? null : Number(value), currency })
      toast.success('Saved')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <IndianRupee size={16} color="#22D3A5" />
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>Booking value</div>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginBottom: 12 }}>
        What one booked appointment is worth to you on average. Analytics multiplies bookings by it to estimate revenue.
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="biz-value" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>Average booking value</label>
          <input id="biz-value" type="number" min={0} className="avn-input" value={value} onChange={e => setValue(e.target.value)} style={{ width: 160, height: 34 }} />
        </div>
        <div>
          <label htmlFor="biz-currency" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>Currency</label>
          <select id="biz-currency" className="avn-input" value={currency} onChange={e => setCurrency(e.target.value)} style={{ height: 34 }}>
            {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <Button variant="primary" onClick={save} loading={saving}>Save</Button>
      </div>
    </Card>
  )
}
