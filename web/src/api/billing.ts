import { api } from './client'
import type { Schema } from './types'

export type BillingOverview = Schema<'BillingOut'>
export type BillingPlan = Schema<'PlanOut'>
export type PaymentProvider = 'razorpay' | 'stripe'

export const billingApi = {
  get: () => api.get<BillingOverview>('/api/billing'),
  /** The provider's payment page; the plan starts when the provider confirms payment. */
  checkout: (plan_id: string, provider: PaymentProvider) => api.post<Schema<'RedirectOut'>>('/api/billing/checkout', { plan_id, provider }),
  portal: () => api.post<Schema<'RedirectOut'>>('/api/billing/portal'),
  cancel: () => api.post<BillingOverview>('/api/billing/cancel'),
}
