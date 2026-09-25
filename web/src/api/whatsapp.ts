import { api } from './client'
import type { Schema } from './types'

export type WhatsAppStatus = Schema<'WhatsAppStatusOut'>
export type WhatsAppMessage = Schema<'WhatsAppMessageOut'>
export type WhatsAppConnect = Schema<'WhatsAppConnectIn'>
export type WhatsAppSend = Schema<'WhatsAppSendIn'>

export const whatsappApi = {
  status: () => api.get<WhatsAppStatus>('/api/integrations/whatsapp'),
  connect: (body: WhatsAppConnect) => api.put<WhatsAppStatus>('/api/integrations/whatsapp', body),
  disconnect: () => api.delete<void>('/api/integrations/whatsapp'),
  send: (body: WhatsAppSend) => api.post<WhatsAppMessage>('/api/crm/whatsapp', body),
  messages: (leadId?: string) =>
    api.get<WhatsAppMessage[]>(`/api/whatsapp/messages${leadId ? `?lead_id=${encodeURIComponent(leadId)}` : ''}`),
}
