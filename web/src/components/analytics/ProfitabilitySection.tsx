import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe2, IndianRupee } from 'lucide-react'
import Card from '../ui/Card'
import { analyticsApi, type LanguageStat, type Profitability, type ProfitRow } from '../../api/analytics'

function money(value: number | null | undefined, currency: string) {
  if (value === null || value === undefined) return '—'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: value >= 100 ? 0 : 2 }).format(value)
  } catch {
    return `${value} ${currency}`
  }
}

const header = (icon: React.ReactNode, title: string, sub: string) => (
  <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 8 }}>
    {icon}<span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>{title}</span>
    <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{sub}</span>
  </div>
)

// Calls by the language the caller spoke, from the transcript's script.
export function LanguageTable({ languages }: { languages: LanguageStat[] }) {
  return (
    <Card padding={0}>
      {header(<Globe2 size={14} color="#5EE6FF" />, 'By language', "from what callers said in this period")}
      {!languages.length ? <div style={{ padding: 16, fontSize: 12.5, color: 'var(--color-text-muted)' }}>No calls in this period.</div> : (
        <div style={{ overflowX: 'auto' }}>
          <table className="avn-table">
            <thead><tr><th>Language</th><th style={{ textAlign: 'right' }}>Calls</th><th style={{ textAlign: 'right' }}>Bookings</th>
              <th style={{ textAlign: 'right' }}>Booking rate</th><th style={{ textAlign: 'right' }}>Minutes</th><th style={{ textAlign: 'right' }}>Avg duration</th></tr></thead>
            <tbody>
              {languages.map(l => (
                <tr key={l.language}>
                  <td style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{l.name}</td>
                  <td style={{ textAlign: 'right' }}>{l.calls}</td>
                  <td style={{ textAlign: 'right' }}>{l.bookings}</td>
                  <td style={{ textAlign: 'right' }}>{l.calls ? `${Math.round((l.bookings / l.calls) * 100)}%` : '—'}</td>
                  <td style={{ textAlign: 'right' }}>{l.minutes}</td>
                  <td style={{ textAlign: 'right' }}>{l.avg_duration}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ padding: '8px 20px 12px', fontSize: 11.5, color: 'var(--color-text-muted)' }}>
        Hindi or Telugu typed in English letters counts as English; "Mixed" means callers switched between an Indian language and English.
      </div>
    </Card>
  )
}

function Rows({ rows, currency, campaign }: { rows: (ProfitRow & { leads?: number; reached?: number; status?: string })[]; currency: string; campaign?: boolean }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="avn-table">
        <thead>
          <tr>
            <th>{campaign ? 'Campaign' : 'Agent'}</th>
            {campaign && <th style={{ textAlign: 'right' }}>Leads reached</th>}
            <th style={{ textAlign: 'right' }}>Calls</th><th style={{ textAlign: 'right' }}>Bookings</th>
            <th style={{ textAlign: 'right' }}>Conversion</th><th style={{ textAlign: 'right' }}>Cost</th>
            <th style={{ textAlign: 'right' }}>Cost / booking</th><th style={{ textAlign: 'right' }}>Est. revenue</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{r.name}{campaign && r.status ? <span style={{ fontWeight: 400, color: 'var(--color-text-muted)' }}> · {r.status}</span> : null}</td>
              {campaign && <td style={{ textAlign: 'right' }}>{r.reached} / {r.leads}</td>}
              <td style={{ textAlign: 'right' }}>{r.calls}</td>
              <td style={{ textAlign: 'right' }}>{r.bookings}</td>
              <td style={{ textAlign: 'right' }}>{r.conversion_rate === null || r.conversion_rate === undefined ? '—' : `${r.conversion_rate}%`}</td>
              <td style={{ textAlign: 'right' }}>{money(r.cost_usd, 'USD')}</td>
              <td style={{ textAlign: 'right' }}>{money(r.cost_per_booking_usd, 'USD')}</td>
              <td style={{ textAlign: 'right' }}>{money(r.revenue, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// What calls cost and bring in, per agent and per campaign.
export default function ProfitabilitySection({ days }: { days: number }) {
  const [data, setData] = useState<Profitability | null>(null)
  useEffect(() => {
    let cancelled = false
    analyticsApi.profitability(days).then(d => { if (!cancelled) setData(d) }).catch(() => { if (!cancelled) setData(null) })
    return () => { cancelled = true }
  }, [days])
  if (!data) return null
  const currency = data.currency ?? 'INR'
  return (
    <Card padding={0}>
      {header(<IndianRupee size={14} color="#22D3A5" />, 'Profitability', `last ${data.days} days`)}
      <div style={{ padding: '12px 20px', display: 'flex', gap: 24, flexWrap: 'wrap', fontSize: 12.5 }}>
        <span>Cost <strong style={{ color: 'var(--color-text-primary)' }}>{money(data.totals.cost_usd, 'USD')}</strong></span>
        <span>Bookings <strong style={{ color: 'var(--color-text-primary)' }}>{data.totals.bookings}</strong></span>
        <span>Cost per booking <strong style={{ color: 'var(--color-text-primary)' }}>{money(data.totals.cost_per_booking_usd, 'USD')}</strong></span>
        <span>Estimated revenue <strong style={{ color: 'var(--color-text-primary)' }}>{money(data.totals.revenue, currency)}</strong></span>
      </div>
      {data.booking_value === null || data.booking_value === undefined ? (
        <div style={{ padding: '0 20px 12px', fontSize: 12, color: 'var(--color-text-muted)' }}>
          Set your average booking value in <Link to="/settings" style={{ color: 'var(--color-link)' }}>Settings → Workspace</Link> to see revenue.
        </div>
      ) : null}
      {data.agents.length > 0 && <Rows rows={data.agents} currency={currency} />}
      {data.campaigns.length > 0 && <Rows rows={data.campaigns} currency={currency} campaign />}
      <div style={{ padding: '8px 20px 12px', fontSize: 11.5, color: 'var(--color-text-muted)' }}>
        Cost is what the voice pipeline reports per call (model and telephony). Revenue = bookings × your booking value.
      </div>
    </Card>
  )
}
