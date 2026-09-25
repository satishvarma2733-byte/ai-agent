import { useEffect, useState } from 'react'
import { CreditCard, PhoneCall, Clock, DollarSign, Bot } from 'lucide-react'
import Card from '../components/ui/Card'
import GradientStatCard from '../components/ui/GradientStatCard'
import PlanAndPayments from '../components/billing/PlanAndPayments'
import { LoadingState, ErrorState } from '../components/ui/States'
import { analyticsApi, type Overview } from '../api/analytics'
import { workspaceApi, type Workspace } from '../api/workspace'

type Loaded = { overview: Overview; workspace: Workspace }

function load(): Promise<Loaded> {
  return Promise.all([analyticsApi.overview(30), workspaceApi.get()]).then(([overview, workspace]) => ({ overview, workspace }))
}

export default function Billing() {
  const [data, setData] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    load()
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load usage') })
    return () => { cancelled = true }
  }, [])

  const retry = () => { setError(null); setData(null); load().then(setData).catch(e => setError(e instanceof Error ? e.message : 'Failed to load usage')) }
  const monthName = new Date().toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

  return (
    <div className="page-wrapper">
      <div style={{ padding: '28px 32px 0', marginBottom: 24 }}>
        <div style={{
          background: 'linear-gradient(135deg, rgba(123,97,255,0.08), rgba(34,211,165,0.04))',
          border: '1px solid rgba(123,97,255,0.14)', borderRadius: 18, padding: '22px 28px',
        }}>
          <div style={{ fontFamily: 'Satoshi, Inter, sans-serif', fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--color-text-primary)', marginBottom: 6 }}>Usage &amp; Billing</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Your plan and what your workspace has used, from its own call records</div>
        </div>
      </div>

      <div style={{ padding: '0 32px 32px' }}>
        {error ? <ErrorState message={error} onRetry={retry} /> : !data ? <LoadingState /> : (
          <>
            <Card style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(123,97,255,0.12)', border: '1px solid rgba(123,97,255,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CreditCard size={18} color="#9580FF" />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 2 }}>{data.workspace.name}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)' }}>{data.workspace.plan} plan</div>
                </div>
                <span className="avn-chip avn-chip-violet" style={{ textTransform: 'capitalize' }}>{data.workspace.status}</span>
              </div>
            </Card>

            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 12 }}>{monthName}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px,1fr))', gap: 14, marginBottom: 24 }}>
              <GradientStatCard label="Calls" value={data.overview.month.calls} icon={<PhoneCall size={20} color="#fff" />} gradient="linear-gradient(135deg,#7B61FF,#5851CC)" />
              <GradientStatCard label="Call minutes" value={data.overview.month.minutes} icon={<Clock size={20} color="#fff" />} gradient="linear-gradient(135deg,#22D3A5,#15997A)" delay={60} />
              <GradientStatCard label="Est. provider cost" value={`$${data.overview.month.cost_usd.toFixed(2)}`} icon={<DollarSign size={20} color="#fff" />} gradient="linear-gradient(135deg,#F5A623,#D97706)" delay={120} />
              <GradientStatCard label="Agents" value={data.overview.agents.length} icon={<Bot size={20} color="#fff" />} gradient="linear-gradient(135deg,#5EE6FF,#0EA5E9)" delay={180} />
            </div>

            <Card style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 12 }}>All time</div>
              <table className="avn-table">
                <tbody>
                  <tr><td>Calls</td><td style={{ textAlign: 'right' }}>{data.overview.totals.calls.toLocaleString()}</td></tr>
                  <tr><td>Call minutes</td><td style={{ textAlign: 'right' }}>{data.overview.totals.minutes.toLocaleString()}</td></tr>
                  <tr><td>Estimated provider cost</td><td style={{ textAlign: 'right' }}>${data.overview.totals.cost_usd.toFixed(2)}</td></tr>
                </tbody>
              </table>
              <div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 10 }}>
                Estimated cost is what the voice pipeline reports per call (model and telephony usage); it is not an invoice.
              </div>
            </Card>

            <PlanAndPayments minutesUsed={data.overview.month.minutes} />
          </>
        )}
      </div>
    </div>
  )
}
