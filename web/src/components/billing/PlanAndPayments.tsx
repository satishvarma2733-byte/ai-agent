import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, ExternalLink } from 'lucide-react'
import toast from 'react-hot-toast'
import Card from '../ui/Card'
import Button from '../ui/Button'
import { billingApi, type BillingOverview, type PaymentProvider } from '../../api/billing'

const PROVIDER_LABEL: Record<string, string> = { razorpay: 'Razorpay', stripe: 'Stripe' }

function money(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: amount % 1 ? 2 : 0 }).format(amount)
  } catch {
    return `${amount} ${currency}`
  }
}

function statusText(s: NonNullable<BillingOverview['subscription']>) {
  const end = s.current_period_end ? new Date(s.current_period_end).toLocaleDateString() : null
  if (s.status === 'ended') return 'Ended'
  if (s.status === 'past_due') return 'Payment failed: the provider is retrying'
  if (s.cancel_at_period_end) return end ? `Cancelled, ends ${end}` : 'Cancelled at the end of this period'
  return end ? `Active, renews ${end}` : 'Active'
}

// Paid plan: buy through Razorpay or Stripe, see the subscription and invoices. Only the owner can pay or cancel.
export default function PlanAndPayments() {
  const [data, setData] = useState<BillingOverview | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()

  const load = useCallback(() => billingApi.get().then(setData).catch(() => setData(null)), [])
  useEffect(() => { load() }, [load])

  // Back from the provider's payment page: the plan starts once its webhook arrives, usually within seconds.
  useEffect(() => {
    const result = params.get('checkout')
    if (!result) return
    if (result === 'success') {
      toast.success('Payment received. Your plan will show here as soon as the provider confirms it.')
      const timers = [3000, 8000, 15000].map(ms => setTimeout(load, ms))
      params.delete('checkout')
      setParams(params, { replace: true })
      return () => timers.forEach(clearTimeout)
    }
    toast('Checkout cancelled. Nothing was charged.')
    params.delete('checkout')
    setParams(params, { replace: true })
  }, [params, setParams, load])

  if (!data) return null

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key)
    try {
      await action()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setBusy(null)
    }
  }
  const pay = (planId: string, provider: PaymentProvider) => run(`${planId}-${provider}`, async () => {
    const { url } = await billingApi.checkout(planId, provider)
    window.location.assign(url)
  })
  const portal = () => run('portal', async () => { window.location.assign((await billingApi.portal()).url) })
  const cancel = () => run('cancel', async () => {
    if (!confirm('Cancel the plan? It stays on until the end of the period you have paid for.')) return
    setData(await billingApi.cancel())
    toast.success('Plan cancelled at the end of this period')
  })

  const sub = data.subscription
  const hasPlan = sub && (sub.status === 'active' || sub.status === 'past_due')

  const usage = data.usage
  const meters = [
    { label: 'Call minutes this month', used: usage.minutes_used, limit: usage.minutes_limit },
    { label: 'AI agents', used: usage.agents, limit: usage.agents_limit },
    { label: 'Team members (incl. pending invitations)', used: usage.members, limit: usage.members_limit },
  ].filter(m => m.limit !== null && m.limit !== undefined) as { label: string; used: number; limit: number }[]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {usage.outbound_blocked && (
        <Card style={{ borderLeft: '3px solid var(--color-danger)' }}>
          <div role="alert" style={{ fontSize: 13, color: 'var(--color-text-primary)', lineHeight: 1.5 }}>
            This month's call minutes are used up, so outbound calls and campaigns are paused until next month.
            Inbound calls are still answered.{data.can_manage ? ' Upgrade below to call now.' : ' Ask the workspace owner to upgrade.'}
          </div>
        </Card>
      )}
      {meters.length > 0 && (
        <Card>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 12 }}>{data.plan} plan limits</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
            {meters.map(m => {
              const pct = Math.min(100, Math.round((m.used / Math.max(m.limit, 1)) * 100))
              const color = pct >= 100 ? 'var(--color-danger)' : pct >= 80 ? 'var(--color-warning)' : '#22D3A5'
              return (
                <div key={m.label}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 4 }}>
                    <span style={{ color: 'var(--color-text-secondary)' }}>{m.label}</span>
                    <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{m.used.toLocaleString()} / {m.limit.toLocaleString()}</span>
                  </div>
                  <div role="progressbar" aria-label={m.label} aria-valuemin={0} aria-valuemax={m.limit} aria-valuenow={m.used}
                    style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}
      {sub && (
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)' }}>
                {sub.plan_name} · {PROVIDER_LABEL[sub.provider] ?? sub.provider}
              </div>
              <div style={{ fontSize: 12.5, color: sub.status === 'past_due' ? 'var(--color-danger)' : 'var(--color-text-muted)', marginTop: 2 }}>
                {statusText(sub)}
              </div>
            </div>
            {data.can_manage && hasPlan && (
              <div style={{ display: 'flex', gap: 8 }}>
                {sub.provider === 'stripe' && (
                  <Button variant="secondary" size="sm" icon={<ExternalLink size={12} />} loading={busy === 'portal'} onClick={portal}>Manage billing</Button>
                )}
                {!sub.cancel_at_period_end && (
                  <Button variant="ghost" size="sm" loading={busy === 'cancel'} onClick={cancel}>Cancel plan</Button>
                )}
              </div>
            )}
          </div>
        </Card>
      )}

      {!hasPlan && (
        <Card>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 4 }}>Plans</div>
          <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginBottom: 14 }}>
            {data.plans.length === 0 ? "Paid plans aren't set up on this server yet."
              : data.can_manage ? 'Pay in INR with Razorpay (UPI, cards, netbanking) or in other currencies with Stripe.'
              : 'Only the workspace owner can choose a plan.'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
            {data.plans.map(plan => (
              <div key={plan.id} style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 12, padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)' }}>{plan.name}</div>
                <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>{plan.minutes_included.toLocaleString()} call minutes a month</div>
                {plan.features.length > 0 && (
                  <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {plan.features.map(f => (
                      <li key={f} style={{ display: 'flex', gap: 6, fontSize: 12.5, color: 'var(--color-text-secondary)' }}>
                        <Check size={13} color="#22D3A5" style={{ flexShrink: 0, marginTop: 2 }} />{f}
                      </li>
                    ))}
                  </ul>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 'auto' }}>
                  {plan.prices.map(price => (
                    <Button key={price.provider} size="sm" variant={price.provider === 'razorpay' ? 'primary' : 'secondary'}
                      disabled={!data.can_manage || !price.available} loading={busy === `${plan.id}-${price.provider}`}
                      onClick={() => pay(plan.id, price.provider as PaymentProvider)}>
                      {money(price.amount, price.currency)}/month · {PROVIDER_LABEL[price.provider]}
                      {!price.available && ' (not set up)'}
                    </Button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 12 }}>Invoices</div>
        {data.invoices.length === 0 ? (
          <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>No invoices yet.</div>
        ) : (
          <table className="avn-table">
            <thead><tr><th>Date</th><th>Invoice</th><th style={{ textAlign: 'right' }}>Amount</th><th>Status</th><th /></tr></thead>
            <tbody>
              {data.invoices.map(inv => (
                <tr key={inv.id}>
                  <td>{new Date(inv.created_at).toLocaleDateString()}</td>
                  <td>{inv.number ?? '—'}</td>
                  <td style={{ textAlign: 'right' }}>{money(inv.amount, inv.currency)}</td>
                  <td style={{ textTransform: 'capitalize', color: inv.status === 'failed' ? 'var(--color-danger)' : undefined }}>{inv.status}</td>
                  <td>{inv.url && <a href={inv.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-link)' }}>View</a>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
