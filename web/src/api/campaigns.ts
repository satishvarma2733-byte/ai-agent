import { api } from './client'
import type { Campaign, CampaignLead } from '../types'

export const campaignsApi = {
  list: () => api.get<Campaign[]>('/api/crm/campaigns'),
  get: (id: string) => api.get<Campaign & { leads: CampaignLead[] }>(`/api/crm/campaigns/${id}`),
  create: (payload: { name: string; leads: { phone: string; name: string; custom_fields?: Record<string, unknown> }[]; agent_id?: string; concurrency_limit?: number; retry_limit?: number }) =>
    api.post<Campaign>('/api/crm/campaigns', payload),
  start: (id: string) => api.post<{ status: string }>(`/api/crm/campaigns/${id}/start`),
  pause: (id: string) => api.post<{ status: string }>(`/api/crm/campaigns/${id}/pause`),
  delete: (id: string) => api.delete<{ status: string }>(`/api/crm/campaigns/${id}`),
  export: (id: string) => api.get<Blob>(`/api/crm/campaigns/${id}/export`),
}
